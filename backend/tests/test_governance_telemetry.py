"""企业生产遥测接入适配与合成运维验证 API 路由测试（Phase 3.9.4 Task 19 / T22）。

与 ``test_governance_observability.py`` / ``test_governance_release.py`` 同一套纪律：
想成为某个人，必须**真的以那个人登录**拿到 token。焦点：

- 未认证 / 旧头伪造 / 停用账号 → 拒绝；
- 读端点权限矩阵（OBSERVABILITY_READ：admin/reviewer/auditor/viewer 可读，business_only 403）；
- 合成演练端点职责分离（INCIDENT_ACTION 仅 admin）；
- 合成演练落审计，actor_kind 恒 user，响应含 ``simulation_only=true`` / ``auto_*: false``（红线⑨/⑪）；
- 无 human_actions 时 Incident 状态恒为 open，绝不自动关闭（红线⑨）；
- 生产环境合成演练一律 403（红线④/⑪）；
- 响应永远不含 真实外发 / 自动回滚 / AUTO_RESOLVED / AUTO_CLOSED 语义（红线⑤/⑨/⑫/⑬/⑭）。
"""

from __future__ import annotations

import types

import pytest


@pytest.fixture()
def gov(governance_env):
    """遥测控制平面按主体所属组织合成只读 + 演练快照（无共享存储）。"""

    return governance_env


def _auth(env, token_key: str) -> dict:
    return env["bearer"](env[token_key])


# --------------------------------------------------------------------------- #
# 一、没有凭据就没有身份                                                        #
# --------------------------------------------------------------------------- #
def test_missing_credentials_is_401(gov):
    r = gov["client"].get("/governance/telemetry/providers")
    assert r.status_code == 401


def test_garbage_token_is_401(gov):
    r = gov["client"].get(
        "/governance/telemetry/providers",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401


def test_suspended_account_is_rejected(gov):
    r = gov["client"].get(
        "/governance/telemetry/providers", headers=_auth(gov, "suspended_token")
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 二、旧漏洞回归：请求头不再是身份                                              #
# --------------------------------------------------------------------------- #
def test_legacy_actor_headers_rejected(gov):
    r = gov["client"].get(
        "/governance/telemetry/providers",
        headers={"x-actor-id": "governor-1", "x-actor-kind": "user"},
    )
    assert r.status_code == 400
    assert "x-actor-id" in r.text


# --------------------------------------------------------------------------- #
# 三、读端点权限矩阵（OBSERVABILITY_READ）                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),
        ("reviewer_token", 200),
        ("auditor_token", 200),
        ("viewer_token", 200),
        ("business_only_token", 403),
    ],
)
def test_providers_permission_matrix(gov, token_key, expected):
    r = gov["client"].get(
        "/governance/telemetry/providers", headers=_auth(gov, token_key)
    )
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "path",
    [
        "/governance/telemetry/summary",
        "/governance/telemetry/synthetic/scenarios",
        "/governance/telemetry/synthetic/health",
        "/governance/telemetry/synthetic/metrics",
        "/governance/telemetry/synthetic/logs",
        "/governance/telemetry/synthetic/traces",
    ],
)
def test_read_endpoints_permission_matrix(gov, path):
    r = gov["client"].get(path, headers=_auth(gov, "viewer_token"))
    assert r.status_code == 200, r.text
    r2 = gov["client"].get(path, headers=_auth(gov, "business_only_token"))
    assert r2.status_code == 403, r2.text


def test_provider_health_404_unknown(gov):
    r = gov["client"].get(
        "/governance/telemetry/does-not-exist/health", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 404


def test_providers_lists_synthetic_only(gov):
    r = gov["client"].get(
        "/governance/telemetry/providers", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 200
    body = r.json()
    # 红线⑪：准备层仅有合成源，且显式声明 synthetic_only。
    assert body["note"].startswith("synthetic_only=true")
    assert "synthetic" in body["providers"]


def test_synthetic_metrics_normalized(gov):
    r = gov["client"].get(
        "/governance/telemetry/synthetic/metrics", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    # 归一化后至少有一组指标。
    assert len(body["normalized"]["metrics"]) >= 1
    # 合成信封标记 simulation_only=True（红线⑪）。
    assert body["normalized"]["metrics"][0]["simulation_only"] is True


# --------------------------------------------------------------------------- #
# 四、合成演练端点职责分离（INCIDENT_ACTION 仅 admin）                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),
        ("reviewer_token", 403),   # 有 observability:read 但无 incident:action
        ("auditor_token", 403),
        ("viewer_token", 403),
        ("business_only_token", 403),
    ],
)
def test_synthetic_run_permission_matrix(gov, token_key, expected):
    r = gov["client"].post(
        "/governance/telemetry/synthetic/run",
        headers=_auth(gov, token_key),
        json={"scenario": "backend_error_spike", "component": "api"},
    )
    assert r.status_code == expected, r.text


def test_synthetic_run_invalid_scenario_400(gov):
    r = gov["client"].post(
        "/governance/telemetry/synthetic/run",
        headers=_auth(gov, "admin_token"),
        json={"scenario": "not_a_real_scenario", "component": "api"},
    )
    assert r.status_code == 400


def test_synthetic_run_records_audit_no_auto(gov):
    r = gov["client"].post(
        "/governance/telemetry/synthetic/run",
        headers=_auth(gov, "admin_token"),
        json={"scenario": "backend_error_spike", "component": "api"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 红线⑪：整场演练仅为模拟。
    assert body["simulation_only"] is True
    # 红线⑨：无 human_actions 时 Incident 状态恒为 open，绝不自动关闭。
    assert body["incident"]["status"] == "open"
    assert body["auto_resolved"] is False
    assert body["auto_closed"] is False
    assert body["auto_rollback"] is False
    # 红线⑫：告警仅模拟投递，绝不真实外发。
    assert body["alert_delivery"]["delivery_status"] == "simulated_delivery"
    # 红线⑤/⑨：响应显式声明 auto_rollback=false（fail-closed 声明，而非真实回滚）。
    assert body["auto_rollback"] is False
    assert "AUTO_RESOLVED" not in r.text
    assert "auto_deploy" not in r.text


def test_synthetic_run_human_close_reaches_closed(gov):
    r = gov["client"].post(
        "/governance/telemetry/synthetic/run",
        headers=_auth(gov, "admin_token"),
        json={
            "scenario": "backend_error_spike",
            "component": "api",
            "human_actions": {"ack": True, "recover": True, "validate": True, "close": True},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 仅当真实 USER 显式提供 human_actions 时才 closed_by_human（红线⑨/⑩）。
    assert body["incident"]["status"] == "closed_by_human"
    assert body["incident"]["human_steps"]["close"]["kind"] == "user"


# --------------------------------------------------------------------------- #
# 五、生产环境禁止合成演练（红线④/⑪）                                          #
# --------------------------------------------------------------------------- #
def test_synthetic_run_forbidden_in_production(gov, monkeypatch):
    def _fake_settings():
        return types.SimpleNamespace(is_production=True)

    monkeypatch.setattr("app.api.governance_telemetry._settings", _fake_settings)
    r = gov["client"].post(
        "/governance/telemetry/synthetic/run",
        headers=_auth(gov, "admin_token"),
        json={"scenario": "backend_error_spike", "component": "api"},
    )
    assert r.status_code == 403
    assert "生产环境" in r.text


# --------------------------------------------------------------------------- #
# 六、Provider 巡检落审计（OBSERVABILITY_READ）                                #
# --------------------------------------------------------------------------- #
def test_check_provider_records_audit(gov):
    r = gov["client"].post(
        "/governance/telemetry/synthetic/check",
        headers=_auth(gov, "admin_token"),
        json={"detail": "routine"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_id"] == "synthetic"
    assert body["checked_by"]  # 真实 USER 责任人

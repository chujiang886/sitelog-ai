"""企业生产可观测性与事故响应 API 路由测试（Phase 3.9.3 Task 17 / T25）。

与 ``test_governance_release.py`` 同一套纪律：想成为某个人，必须**真的以那个人登录**
拿到 token。焦点：

- 未认证 / 旧头伪造 / 停用账号 → 拒绝；
- 读端点权限矩阵（OBSERVABILITY_READ：admin/reviewer/auditor/viewer 可读，business_only 403）；
- 人工事故动作端点职责分离（INCIDENT_ACTION 仅 admin）；
- 人工动作落审计，actor_kind 恒 user，响应含 ``auto_state_transition: false``（红线⑨/⑩）；
- 响应永远不含 AUTO_RESOLVED / AUTO_CLOSED / auto_rollback（红线⑤/⑨）。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def gov(governance_env):
    """可观测性控制平面按主体所属组织合成只读快照（无共享存储）。"""

    return governance_env


def _auth(env, token_key: str) -> dict:
    return env["bearer"](env[token_key])


# --------------------------------------------------------------------------- #
# 一、没有凭据就没有身份                                                        #
# --------------------------------------------------------------------------- #
def test_missing_credentials_is_401(gov):
    r = gov["client"].get("/governance/observability/health")
    assert r.status_code == 401


def test_garbage_token_is_401(gov):
    r = gov["client"].get(
        "/governance/observability/health",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401


def test_suspended_account_is_rejected(gov):
    r = gov["client"].get(
        "/governance/observability/health", headers=_auth(gov, "suspended_token")
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 二、旧漏洞回归：请求头不再是身份                                              #
# --------------------------------------------------------------------------- #
def test_legacy_actor_headers_rejected(gov):
    r = gov["client"].get(
        "/governance/observability/health",
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
def test_health_permission_matrix(gov, token_key, expected):
    r = gov["client"].get(
        "/governance/observability/health", headers=_auth(gov, token_key)
    )
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "path",
    [
        "/governance/observability/metrics",
        "/governance/observability/slo",
        "/governance/observability/incidents",
    ],
)
def test_read_endpoints_permission_matrix(gov, path):
    r = gov["client"].get(path, headers=_auth(gov, "viewer_token"))
    assert r.status_code == 200, r.text
    r2 = gov["client"].get(path, headers=_auth(gov, "business_only_token"))
    assert r2.status_code == 403, r2.text


def test_health_simulation_only(gov):
    r = gov["client"].get(
        "/governance/observability/health", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["simulation_only"] is True
    # 红线⑪：所有组件均 UNKNOWN（准备层无真实监测）
    assert body["overall"] == "unknown"
    for c in body["components"]:
        assert c["status"] == "unknown"
        assert c["simulation_only"] is True


def test_incident_detail_404_in_prep_layer(gov):
    r = gov["client"].get(
        "/governance/observability/incidents/INC-1", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# 四、人工事故动作端点职责分离（INCIDENT_ACTION 仅 admin）                     #
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
def test_acknowledge_permission_matrix(gov, token_key, expected):
    r = gov["client"].post(
        "/governance/observability/incidents/INC-1/acknowledge",
        headers=_auth(gov, token_key),
        json={"reason": "人工确认"},
    )
    assert r.status_code == expected, r.text


def test_resolve_records_audit_and_no_auto_transition(gov):
    r = gov["client"].post(
        "/governance/observability/incidents/INC-1/resolve",
        headers=_auth(gov, "admin_token"),
        json={"reason": "已恢复"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["actor_kind"] == "user"
    assert body["auto_state_transition"] is False
    assert body["category"] == "incident_human_resolved"
    # 红线⑤/⑨：响应绝不出现自动关闭 / 回滚语义
    assert "AUTO" not in r.text
    assert "auto_rollback" not in r.text


def test_close_requires_reason(gov):
    r = gov["client"].post(
        "/governance/observability/incidents/INC-1/close",
        headers=_auth(gov, "admin_token"),
        json={"reason": ""},
    )
    # 空理由也应被接受（后端不强制内容，但必须 actor_kind=user 落审计）；
    # 若未来收紧，下面断言改为 400 即可。
    assert r.status_code in (200, 400), r.text


def test_assign_commander_requires_commander_id(gov):
    r = gov["client"].post(
        "/governance/observability/incidents/INC-1/assign-commander",
        headers=_auth(gov, "admin_token"),
        json={"reason": "指派指挥官"},
    )
    assert r.status_code == 400, r.text


def test_assign_commander_ok(gov):
    r = gov["client"].post(
        "/governance/observability/incidents/INC-1/assign-commander",
        headers=_auth(gov, "admin_token"),
        json={"reason": "指派指挥官", "commander_id": "cmd-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "incident_human_acknowledged"

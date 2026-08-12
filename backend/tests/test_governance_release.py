"""企业生产发布闸门与证据包 API 路由测试（Phase 3.9.2 Task 9 / T12）。

与 ``test_governance_dashboard.py`` 同一套纪律：想成为某个人，必须**真的以那个人登录**
拿到 token（``governance_env`` 不提供伪造身份捷径）。本路由是纯只读查看 + 真实人工签署，
因此测试焦点在于：

- 未认证 / 旧头伪造 / 停用账号 → 拒绝；
- 读端点权限矩阵（RELEASE_READ：admin/reviewer/auditor/viewer 可读，business_only 403）；
- 签署端点职责分离（RELEASE_SIGNOFF 仅 admin）；
- 签署落审计，actor_kind 恒 user，责任来自凭据；
- 跨租户 org-id 指向他人组织 → 403；
- 响应永远不含 APPROVED / GO / release_approved=True（红线②/③/⑧/⑩）。
"""

from __future__ import annotations

import pytest

from app.identity.accountability import (
    GOVERNANCE_ACCOUNTABILITY_ACTION,
    parse_accountability,
)


@pytest.fixture()
def gov(governance_env):
    """发布控制平面按主体所属组织合成只读快照（无共享存储，故无需预置数据）。"""

    return governance_env


def _auth(env, token_key: str) -> dict:
    return env["bearer"](env[token_key])


# --------------------------------------------------------------------------- #
# 一、没有凭据就没有身份                                                        #
# --------------------------------------------------------------------------- #
def test_missing_credentials_is_401(gov):
    r = gov["client"].get("/governance/releases")
    assert r.status_code == 401


def test_garbage_token_is_401(gov):
    r = gov["client"].get(
        "/governance/releases", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert r.status_code == 401


def test_suspended_account_is_rejected(gov):
    r = gov["client"].get(
        "/governance/releases", headers=_auth(gov, "suspended_token")
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 二、旧漏洞回归：请求头不再是身份                                              #
# --------------------------------------------------------------------------- #
def test_legacy_actor_headers_rejected(gov):
    r = gov["client"].get(
        "/governance/releases",
        headers={"x-actor-id": "governor-1", "x-actor-kind": "user"},
    )
    assert r.status_code == 400
    assert "x-actor-id" in r.text


# --------------------------------------------------------------------------- #
# 三、读端点权限矩阵（RELEASE_READ）                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),
        ("reviewer_token", 200),
        ("auditor_token", 200),
        ("viewer_token", 200),
        ("business_only_token", 403),  # 业务管理员 ≠ 治理角色
    ],
)
def test_list_releases_permission_matrix(gov, token_key, expected):
    r = gov["client"].get("/governance/releases", headers=_auth(gov, token_key))
    assert r.status_code == expected, r.text


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
def test_view_release_permission_matrix(gov, token_key, expected):
    r = gov["client"].get(
        "/governance/releases/RC-3.9.2", headers=_auth(gov, token_key)
    )
    assert r.status_code == expected, r.text


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
def test_release_evidence_gate_manifest_read_matrix(gov, token_key, expected):
    base = "/governance/releases/RC-3.9.2"
    for sub in ("/evidence", "/gate", "/manifest"):
        r = gov["client"].get(base + sub, headers=_auth(gov, token_key))
        assert r.status_code == expected, f"{sub}: {r.text}"


# --------------------------------------------------------------------------- #
# 四、签署端点职责分离（RELEASE_SIGNOFF 仅 admin）                              #
# --------------------------------------------------------------------------- #
def _signoff_body(role="production-owner", decision="no_go", reason="x"):
    return {"role": role, "decision": decision, "reason": reason}


@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),  # 唯一持有 RELEASE_SIGNOFF
        ("reviewer_token", 403),
        ("auditor_token", 403),
        ("viewer_token", 403),
        ("business_only_token", 403),
    ],
)
def test_signoff_permission_matrix(gov, token_key, expected):
    r = gov["client"].post(
        "/governance/releases/RC-3.9.2/signoff",
        headers=_auth(gov, token_key),
        json=_signoff_body(),
    )
    assert r.status_code == expected, r.text


def test_signoff_invalid_role_400(gov):
    r = gov["client"].post(
        "/governance/releases/RC-3.9.2/signoff",
        headers=_auth(gov, "admin_token"),
        json=_signoff_body(role="ceo", decision="no_go"),
    )
    assert r.status_code == 400


def test_signoff_invalid_decision_400(gov):
    r = gov["client"].post(
        "/governance/releases/RC-3.9.2/signoff",
        headers=_auth(gov, "admin_token"),
        json=_signoff_body(decision="launch_it"),
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# 五、责任来自凭据（T4）；AI 无法到达本路由                                    #
# --------------------------------------------------------------------------- #
def test_signoff_is_attributed_to_token_holder(gov):
    """责任人是 token 持有者；响应 actor_kind 恒 'user'（红线⑥/⑧）。"""

    r = gov["client"].post(
        "/governance/releases/RC-3.9.2/signoff",
        headers=_auth(gov, "admin_token"),
        json=_signoff_body(role="production-owner", decision="no_go"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["actor_kind"] == "user"
    assert body["actor_id"] == gov["ids"]["gov_admin"]
    assert body["role"] == "production-owner"
    assert body["decision"] == "no_go"


# --------------------------------------------------------------------------- #
# 六、响应永不含放行语义（红线②/③/⑧/⑩）                                       #
# --------------------------------------------------------------------------- #
def test_release_snapshot_never_approved(gov):
    r = gov["client"].get(
        "/governance/releases/RC-3.9.2", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate"]["release_approved"] is False
    assert body["gate"]["status"] != "approved"
    assert body["gate"]["status"] in (
        "ready_for_human_review",
        "blocked",
        "pending_verification",
    )
    # 工程护栏态如实回传（红线①）
    assert body["engineering_enabled"] is False


def test_gate_status_value_never_approved(gov):
    r = gov["client"].get(
        "/governance/releases/RC-3.9.2/gate", headers=_auth(gov, "admin_token")
    )
    assert r.status_code == 200
    assert r.json()["status"] != "approved"


# --------------------------------------------------------------------------- #
# 七、组织隔离                                                                  #
# --------------------------------------------------------------------------- #
def test_other_tenant_cannot_target_our_org_on_read(gov):
    headers = {**_auth(gov, "admin_b_token"), "org-id": gov["ids"]["tenant_a"]}
    r = gov["client"].get("/governance/releases", headers=headers)
    assert r.status_code == 403


def test_other_tenant_cannot_target_our_org_on_signoff(gov):
    headers = {**_auth(gov, "admin_b_token"), "org-id": gov["ids"]["tenant_a"]}
    r = gov["client"].post(
        "/governance/releases/RC-3.9.2/signoff",
        headers=headers,
        json=_signoff_body(),
    )
    assert r.status_code == 403

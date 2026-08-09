"""治理驾驶舱 FastAPI 路由测试（Phase 3.8.26 建立，3.8.28 身份改造后重写）。

## 这份测试为什么被整体重写

改造前它长这样::

    USER_HEADERS = {"x-actor-id": "governor-1", "x-actor-kind": "user"}
    r = client.get("/governance/reviews", headers=USER_HEADERS)
    assert r.status_code == 200

也就是说：**测试自己就在演示那个漏洞** —— 两个自填的请求头换来 200。
它当时确实测住了"缺头会被拒"，但没能测住"随便一个头就能过"，因为在那套
设计里这两件事是同一件事。

重写后，测试里想成为某个人，必须**真的以那个人登录一次**拿到 token
（``governance_env`` 夹具不提供任何伪造身份的捷径）。于是"权限对不对"
这件事第一次变成可测的：同一个端点，四种治理角色会得到四种结果。

## 覆盖

- 未认证 / 旧头伪造 / 停用账号 → 拒绝；
- 四类治理角色 × 读写端点 → 权限矩阵；
- 只有业务角色的合法用户 → 默认拒绝（治理权限不随业务管理员身份附送）；
- 跨租户 → 看不到对方的治理事实；
- 责任人来自凭据，请求体/请求头都改不了它。
"""

from __future__ import annotations

import pytest

from app.identity.accountability import (
    GOVERNANCE_ACCOUNTABILITY_ACTION,
    parse_accountability,
)


@pytest.fixture()
def gov(governance_env):
    """在 A 租户的驾驶舱里放一条待研判的工作流。

    组织标识用**真实租户 id**（不再是写死的 ``demo-org``）：身份改造后
    驾驶舱按主体所属组织分实例，写死组织等于让所有租户共用一份治理事实。
    """

    org_a = governance_env["ids"]["tenant_a"]
    svc = governance_env["build_demo_service"](org_a)
    svc._orchestrator.register_candidate(
        workflow_id="gw-1",
        source_type="assistant_draft",
        source_id="ans-1",
        title="密封胶核查",
        source_facts=["f1"],
        references=["r1"],
    )
    svc._orchestrator.submit_for_review(workflow_id="gw-1", actor_id="ai")
    governance_env["svc"] = svc
    return governance_env


def _auth(env, token_key: str) -> dict:
    return env["bearer"](env[token_key])


# --------------------------------------------------------------------------- #
# 一、没有凭据就没有身份                                                        #
# --------------------------------------------------------------------------- #
def test_missing_credentials_is_401(gov):
    r = gov["client"].get("/governance/reviews")
    assert r.status_code == 401


def test_garbage_token_is_401(gov):
    r = gov["client"].get(
        "/governance/reviews", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert r.status_code == 401


def test_non_bearer_scheme_is_401(gov):
    """Basic 认证不是治理身份来源 —— 不认识的方案一律拒绝，不做兼容猜测。"""

    r = gov["client"].get(
        "/governance/reviews", headers={"Authorization": "Basic YWRtaW46YWRtaW4="}
    )
    assert r.status_code == 401


def test_suspended_account_is_rejected_even_with_valid_token(gov):
    """凭据还在手上，但人已经停用 —— 回库确认这一步就是为它准备的。

    这是"角色缓存在 token 里"的经典失效场景：签名有效、未过期、声明完整，
    唯独这个人已经不在岗。只信 token 的实现会放行。
    """

    r = gov["client"].get("/governance/reviews", headers=_auth(gov, "suspended_token"))
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 二、旧漏洞回归：请求头不再是身份                                              #
# --------------------------------------------------------------------------- #
def test_legacy_actor_headers_are_rejected_not_ignored(gov):
    """携带旧头一律 400，且**不是**因为顺带缺 token 才失败。

    静默忽略在功能上安全，在运维语义上危险：调用方会以为自己指定成功了
    责任人。治理系统里"我以为记的是张三、实际记的是李四"属于责任错置。
    """

    r = gov["client"].get(
        "/governance/reviews",
        headers={"x-actor-id": "governor-1", "x-actor-kind": "user"},
    )
    assert r.status_code == 400
    assert "x-actor-id" in r.text


def test_legacy_headers_rejected_even_with_valid_token(gov):
    """带着合法 token 也不许再带旧头 —— 否则等于保留了一个"看起来生效"的入口。"""

    headers = {**_auth(gov, "admin_token"), "x-actor-id": "someone-else"}
    r = gov["client"].get("/governance/reviews", headers=headers)
    assert r.status_code == 400


def test_ai_actor_header_can_no_longer_reach_the_permission_layer(gov):
    """改造前这里断言 403（AI 被人类门控挡住）。

    现在是 400，而且拦截点更靠前：请求根本没能声明自己是 AI —— **请求里
    不存在能声明主体类别的字段**。从"AI 被拒绝"变成"AI 无从声明"，是这一
    阶段最实质的变化，所以这条用例保留下来记录这个位移。
    """

    r = gov["client"].post(
        "/governance/review/confirm",
        headers={"x-actor-id": "ai-1", "x-actor-kind": "ai"},
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "x"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# 三、权限矩阵：同一个端点，四种角色四种结果                                    #
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
def test_list_reviews_permission_matrix(gov, token_key, expected):
    r = gov["client"].get("/governance/reviews", headers=_auth(gov, token_key))
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),
        ("auditor_token", 200),
        ("reviewer_token", 403),  # 判断者看不到全量审计（职责分离）
        ("viewer_token", 403),
    ],
)
def test_audit_read_is_narrower_than_workflow_read(gov, token_key, expected):
    """审计调阅权限刻意比工作流查看权限窄。

    能下判断的人不该同时掌握"对自己判断的审计视角"，否则职责分离只剩形式。
    """

    r = gov["client"].get("/governance/audit?limit=50", headers=_auth(gov, token_key))
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "token_key,expected",
    [
        ("admin_token", 200),
        ("reviewer_token", 200),
        ("auditor_token", 403),  # 看得见 ≠ 说了算
        ("viewer_token", 403),
        ("business_only_token", 403),
    ],
)
def test_confirm_review_permission_matrix(gov, token_key, expected):
    r = gov["client"].post(
        "/governance/review/confirm",
        headers=_auth(gov, token_key),
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "经核查属实"},
    )
    assert r.status_code == expected, r.text


def test_business_admin_has_zero_governance_permissions(gov):
    """默认拒绝的主证人：一个合法登录、业务上是管理员的人，治理权限为空。"""

    r = gov["client"].get("/governance/me", headers=_auth(gov, "business_only_token"))
    assert r.status_code == 200
    body = r.json()
    assert body["permissions"] == []
    assert body["has_governance_access"] is False


# --------------------------------------------------------------------------- #
# 四、功能仍然可用（改造没把功能改坏）                                          #
# --------------------------------------------------------------------------- #
def test_list_pending_reviews_returns_the_workflow(gov):
    r = gov["client"].get("/governance/reviews", headers=_auth(gov, "admin_token"))
    assert r.status_code == 200
    assert any(w["workflow_id"] == "gw-1" for w in r.json())


def test_summary(gov):
    r = gov["client"].get("/governance/summary", headers=_auth(gov, "admin_token"))
    assert r.status_code == 200
    assert r.json()["pending_review"] == 1


def test_confirm_review_advances_status(gov):
    r = gov["client"].post(
        "/governance/review/confirm",
        headers=_auth(gov, "reviewer_token"),
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "经核查属实"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["decision"] == "confirmed"

    r2 = gov["client"].get(
        "/governance/workflows/gw-1", headers=_auth(gov, "admin_token")
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "human_confirmed"


def test_audit_records_accumulate(gov):
    gov["client"].post(
        "/governance/review/confirm",
        headers=_auth(gov, "admin_token"),
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "ok"},
    )
    r = gov["client"].get("/governance/audit?limit=50", headers=_auth(gov, "admin_token"))
    assert r.status_code == 200
    assert len(r.json()) >= 2


# --------------------------------------------------------------------------- #
# 五、责任来自凭据（T4）                                                        #
# --------------------------------------------------------------------------- #
def test_confirmation_is_attributed_to_the_token_holder(gov):
    """责任人是 token 的持有者，不是请求里写的任何东西。"""

    gov["client"].post(
        "/governance/review/confirm",
        headers=_auth(gov, "reviewer_token"),
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "已复核"},
    )
    audit = gov["svc"]._audit
    records = audit.query(target="gw-1")
    acct = [r for r in records if r.action == GOVERNANCE_ACCOUNTABILITY_ACTION]
    assert acct, "研判确认未留下问责记录"
    parsed = parse_accountability(acct[-1].detail)
    assert parsed["user_id"] == gov["ids"]["gov_reviewer"]
    assert parsed["role"] == "governance-reviewer"
    assert parsed["action"] == "confirm_review"
    assert parsed["resource"] == "gw-1"
    assert parsed["actor_kind"] == "user"


def test_accountability_records_the_role_at_action_time(gov):
    """同一条工作流被两种角色操作，问责记录能分辨出各自的身份。"""

    gov["client"].get("/governance/summary", headers=_auth(gov, "viewer_token"))
    gov["client"].get("/governance/summary", headers=_auth(gov, "auditor_token"))
    records = gov["svc"]._audit.query(target=gov["ids"]["tenant_a"])
    roles = {
        parse_accountability(r.detail).get("role")
        for r in records
        if r.action == GOVERNANCE_ACCOUNTABILITY_ACTION
    }
    assert {"governance-viewer", "governance-auditor"} <= roles


# --------------------------------------------------------------------------- #
# 六、组织隔离                                                                  #
# --------------------------------------------------------------------------- #
def test_other_tenant_cannot_see_our_workflows(gov):
    """B 租户的治理管理员权限齐全，但看不到 A 租户的治理事实。"""

    r = gov["client"].get("/governance/reviews", headers=_auth(gov, "admin_b_token"))
    assert r.status_code == 200
    assert not any(w["workflow_id"] == "gw-1" for w in r.json())


def test_org_header_cannot_be_used_to_reach_another_tenant(gov):
    """``org-id`` 头只能复述自己的组织；指向别人的组织 → 403。"""

    headers = {**_auth(gov, "admin_b_token"), "org-id": gov["ids"]["tenant_a"]}
    r = gov["client"].get("/governance/reviews", headers=headers)
    assert r.status_code == 403


def test_org_header_echoing_own_org_is_allowed(gov):
    headers = {**_auth(gov, "admin_token"), "org-id": gov["ids"]["tenant_a"]}
    r = gov["client"].get("/governance/reviews", headers=headers)
    assert r.status_code == 200

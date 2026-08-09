"""Phase 3.8.28 T4：治理动作身份绑定（责任五元组）单测。

被测对象是 ``app.identity.accountability``。它要保证的事只有一句话：
**每一个治理动作都能回答"谁、以什么身份、在什么时候、对什么对象、做了什么"，
而这五项没有一项来自请求方**。

用例分五组：
① 五元组构造 —— 字段齐全、值全部取自主体，不受调用方污染；
② 序列化/反序列化 —— detail 含分号等号也不破坏解析（人写的理由不能被限制）；
③ 审计写入 —— 动作名固定、actor 与主体一致、kind 决定审计分类；
④ 红线拒绝 —— 动作/资源名命中禁语时拒绝留痕；
⑤ 装配缺失 —— audit 为 None 时不炸（可观测性缺口不升级为功能故障）。
"""

from __future__ import annotations

import pytest

from app.identity import (
    ACCOUNTABILITY_CONTEXT_FIELDS,
    ACCOUNTABILITY_FIELDS,
    GOVERNANCE_ACCOUNTABILITY_ACTION,
    GovernancePermission,
    accountability_context,
    format_accountability,
    parse_accountability,
    record_accountability,
)
from app.identity.errors import IdentityRedLineViolationError
from app.identity.principal import ActorKind, build_principal


class _RecordingAudit:
    """只记不判的审计替身。

    刻意**不**继承真实 ``AuditService``：这一组用例要验证的是"问责层调用了
    什么"，不是"审计服务写对了没有"。用替身能让断言直接落在调用参数上，
    真实审计服务的行为由 agents 侧自己的测试负责。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _make(self, name: str):
        def _writer(**kwargs):
            self.calls.append((name, kwargs))
            return kwargs

        return _writer

    def __getattr__(self, name: str):
        if name.startswith("record_agent_governance_workflow_"):
            return self._make(name)
        raise AttributeError(name)


def _principal(**over):
    base = dict(
        actor_id="u-1001",
        org_id="org-A",
        roles=("designer", "governance-reviewer"),
        permissions={GovernancePermission.REVIEW_CONFIRM},
        email="chen@a.local",
        display_name="陈工",
    )
    base.update(over)
    return build_principal(**base)


# --------------------------------------------------------------------------- #
# ① 五元组构造                                                                 #
# --------------------------------------------------------------------------- #
def test_context_contains_full_accountability_tuple():
    ctx = accountability_context(
        _principal(), action="confirm_review", resource="wf-1"
    )
    for key in ACCOUNTABILITY_FIELDS + ACCOUNTABILITY_CONTEXT_FIELDS:
        assert key in ctx, f"责任上下文缺字段：{key}"
        assert str(ctx[key]).strip(), f"责任字段为空：{key}"


def test_role_prefers_governance_role_over_business_role():
    """责任落在**治理身份**上，而不是这个人碰巧还有哪些业务角色。

    "陈工以 governance-reviewer 的身份确认了这条线索"是有意义的；
    "陈工（他还是个 designer）确认了这条线索"会让复盘时抓错重点。
    """

    ctx = accountability_context(
        _principal(), action="confirm_review", resource="wf-1"
    )
    assert ctx["role"] == "governance-reviewer"
    # 业务角色不丢，只是不占据 role 这一格（审计仍可还原完整上下文）。
    assert "designer" in ctx["roles"]


def test_role_falls_back_to_all_roles_when_no_governance_role():
    """没有治理角色时退回全部角色，而不是留空。

    这种主体本来就进不了治理端点（权限集为空 → 默认拒绝），但万一某条路径
    把它带到了问责层，责任记录里也得写清楚"这人当时只有业务角色"——
    留空会让事后看起来像是记录丢失。
    """

    ctx = accountability_context(
        _principal(roles=("admin",), permissions=set()),
        action="list_workflows",
        resource="org-A",
    )
    assert ctx["role"] == "admin"


def test_context_ignores_caller_supplied_identity():
    """调用方只能给 action / resource，给不了身份。

    这条用例的价值不在断言本身，而在于**签名**：``accountability_context``
    是 keyword-only 且只收这两个参数，任何试图传 user_id / role 的代码
    连导入都过不了。这里用运行时断言把这个约束钉死，防止将来有人"顺手"
    加一个 actor_id 覆盖参数。
    """

    with pytest.raises(TypeError):
        accountability_context(  # type: ignore[call-arg]
            _principal(), action="x", resource="y", user_id="伪造的人"
        )


def test_actor_kind_is_always_user():
    ctx = accountability_context(_principal(), action="a", resource="r")
    assert ctx["actor_kind"] == ActorKind.USER.value


# --------------------------------------------------------------------------- #
# ② 序列化 / 反序列化                                                          #
# --------------------------------------------------------------------------- #
def test_format_parse_roundtrip():
    ctx = accountability_context(
        _principal(), action="close_workflow", resource="wf-9"
    )
    text = format_accountability(ctx, detail="note=已闭环")
    back = parse_accountability(text)
    for key in ACCOUNTABILITY_FIELDS + ACCOUNTABILITY_CONTEXT_FIELDS:
        assert back[key] == str(ctx[key])
    assert back["detail"] == "note=已闭环"


def test_detail_may_contain_separators_without_breaking_parse():
    """人写的研判理由里出现 ``;`` 和 ``=`` 是常态，不能因此把责任信息解析歪。"""

    ctx = accountability_context(
        _principal(), action="confirm_review", resource="wf-2"
    )
    messy = "decision=confirmed;reason=甲方要求 A=B；且需复核; 见附件"
    back = parse_accountability(format_accountability(ctx, detail=messy))
    assert back["user_id"] == "u-1001"
    assert back["action"] == "confirm_review"
    assert back["detail"] == messy


def test_field_order_is_stable():
    """字段顺序是外部可依赖的约定（日志检索、grep、离线解析都吃这个顺序）。"""

    ctx = accountability_context(_principal(), action="a", resource="r")
    text = format_accountability(ctx)
    keys = [seg.split("=", 1)[0] for seg in text.split(";")]
    assert tuple(keys) == ACCOUNTABILITY_FIELDS + ACCOUNTABILITY_CONTEXT_FIELDS


# --------------------------------------------------------------------------- #
# ③ 审计写入                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kind,expected_method",
    [
        ("create", "record_agent_governance_workflow_create"),
        ("review", "record_agent_governance_workflow_review"),
        ("execution", "record_agent_governance_workflow_execution"),
        ("view", "record_agent_governance_workflow_view"),
    ],
)
def test_kind_routes_to_expected_audit_category(kind, expected_method):
    audit = _RecordingAudit()
    record_accountability(
        audit, _principal(), action="do", resource="wf-1", kind=kind
    )
    assert audit.calls, "问责记录未写入"
    method, kwargs = audit.calls[0]
    assert method == expected_method
    assert kwargs["action"] == GOVERNANCE_ACCOUNTABILITY_ACTION
    assert kwargs["actor_id"] == "u-1001"
    assert kwargs["target"] == "wf-1"


def test_recorded_detail_carries_the_five_tuple():
    audit = _RecordingAudit()
    record_accountability(
        audit,
        _principal(),
        action="submit_result",
        resource="wf-7",
        kind="execution",
        detail="result=已更换密封胶",
    )
    _, kwargs = audit.calls[0]
    parsed = parse_accountability(kwargs["detail"])
    assert parsed["user_id"] == "u-1001"
    assert parsed["role"] == "governance-reviewer"
    assert parsed["action"] == "submit_result"
    assert parsed["resource"] == "wf-7"
    assert parsed["org_id"] == "org-A"
    assert parsed["detail"] == "result=已更换密封胶"
    assert parsed["timestamp"]


def test_action_name_is_fixed_so_all_records_are_greppable():
    """所有问责记录共用一个动作名 —— 这正是"一次捞全某人治理动作"的前提。"""

    audit = _RecordingAudit()
    for act, kind in (
        ("report_workflow", "create"),
        ("confirm_review", "review"),
        ("close_workflow", "execution"),
    ):
        record_accountability(
            audit, _principal(), action=act, resource="wf", kind=kind
        )
    assert {kw["action"] for _, kw in audit.calls} == {
        GOVERNANCE_ACCOUNTABILITY_ACTION
    }


def test_unknown_kind_raises_rather_than_falling_back():
    audit = _RecordingAudit()
    with pytest.raises(ValueError):
        record_accountability(
            audit, _principal(), action="a", resource="r", kind="approve"
        )
    assert not audit.calls


# --------------------------------------------------------------------------- #
# ④ 红线拒绝                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "action",
    ["auto_approve", "auto-execute", "ai_approve", "bypass_human", "skip_human"],
)
def test_forbidden_action_name_is_refused(action):
    """留下一条 ``auto_approve`` 的问责记录，等于承认这个动作合法发生过。"""

    audit = _RecordingAudit()
    with pytest.raises(IdentityRedLineViolationError):
        record_accountability(
            audit, _principal(), action=action, resource="wf-1", kind="review"
        )
    assert not audit.calls, "红线动作不得留下任何痕迹"


def test_forbidden_resource_name_is_refused():
    audit = _RecordingAudit()
    with pytest.raises(IdentityRedLineViolationError):
        record_accountability(
            audit,
            _principal(),
            action="close_workflow",
            resource="engineering_approved-batch",
            kind="execution",
        )
    assert not audit.calls


def test_forbidden_check_is_case_insensitive():
    with pytest.raises(IdentityRedLineViolationError):
        accountability_context(
            _principal(), action="Auto_Approve", resource="wf"
        )


# --------------------------------------------------------------------------- #
# ⑤ 装配缺失                                                                   #
# --------------------------------------------------------------------------- #
def test_missing_audit_does_not_break_the_action_path():
    """没接审计不该让治理动作失败 —— 但责任上下文照样构造并返回。"""

    ctx = record_accountability(
        None, _principal(), action="confirm_review", resource="wf-1", kind="review"
    )
    assert ctx is not None
    assert ctx["user_id"] == "u-1001"


def test_missing_audit_still_enforces_red_line():
    """审计缺席不是红线的豁免理由。"""

    with pytest.raises(IdentityRedLineViolationError):
        record_accountability(
            None, _principal(), action="auto_confirm", resource="wf", kind="review"
        )

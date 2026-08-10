"""Enterprise Agent Policy & Runtime Governance Layer —— 测试（任务7，Phase 3.8.17）。

七类测试：policy / tool_access / guard / runtime_record / permission / audit / red_line。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 AI 自动批准 Agent 运行（approve_run / auto_approve_execution /
    allow_execution / bypass_policy / override_policy / force_run 等被拦截；
    Guard 只返回核查事实，绝不返回「已批准」语义）；
④ 禁止 AI 自动修改 Agent 策略（auto_update_policy / auto_apply_policy /
    auto_approve_policy / update_policy / modify_policy / auto_activate 等被拦截；
    状态推进必须 require_human_actor(USER)）；
⑤ 禁止 AI 自动放行工具访问（auto_grant_tool / allow_tool_access / whitelist_tool /
    unlock_tool / elevate_tool_access / enable_tool 等被拦截；工具策略默认拒绝）；
⑥ AI 不替代人工责任（audit 禁止 record_human_approval；人工确认节点强制
    require_human_actor(USER)；判定记录只陈述事实，不含处置/批准建议）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_runtime_policy import (
    AgentExecutionGuard,
    AgentRuntimeGovernanceService,
    AgentRuntimePolicy,
    AgentRuntimePolicyStatus,
    AgentToolAccessPolicy,
    RuntimeCheckOutcome,
    RuntimeDecisionRecord,
)
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, Permission, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.service import EnterpriseOperationLayer


# ---------------------------------------------------------------------------
# 共享构造器（不修改任何持久化配置，仅内存构造）
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _svc(org_id: str = "org-1") -> AgentRuntimeGovernanceService:
    return AgentRuntimeGovernanceService(
        org_id=org_id,
        audit=_audit(org_id),
        identity=_identity(org_id),
        visibility=None,
        permission_policy=_policy(org_id),
    )


def _admin(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )


def _expert(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="exp", name="E", role_kind=RoleKind.EXPERT
    )


def _designer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="des", name="D", role_kind=RoleKind.DESIGNER
    )


# ===========================================================================
# 类别 1：AgentRuntimePolicy（策略模型，ACTIVE 必须人工确认）
# ===========================================================================

def test_policy_construct_active_rejected() -> None:
    # 红线④/⑥：构造期禁止直接落 ACTIVE（AI 无法凭空创造生效策略）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRuntimePolicy(
            policy_id="p-active", agent_id="a1",
            status=AgentRuntimePolicyStatus.ACTIVE,
        )


def test_policy_construct_draft_and_deprecated_ok() -> None:
    # DRAFT 为唯一合法的新增态；DEPRECATED 允许作为历史事实导入
    draft = AgentRuntimePolicy(policy_id="p-draft", agent_id="a1")
    assert draft.status is AgentRuntimePolicyStatus.DRAFT
    dep = AgentRuntimePolicy(
        policy_id="p-dep", agent_id="a1",
        status=AgentRuntimePolicyStatus.DEPRECATED,
    )
    assert dep.status is AgentRuntimePolicyStatus.DEPRECATED


def test_policy_is_effective_readonly() -> None:
    draft = AgentRuntimePolicy(policy_id="p1", agent_id="a1")
    # 模型层不提供任何激活方法；is_effective 仅反映当前状态（只读事实）
    assert draft.is_effective is False
    assert not hasattr(draft, "activate")
    assert not hasattr(draft, "auto_activate")


def test_policy_covers_rule_scope_default_deny() -> None:
    p = AgentRuntimePolicy(
        policy_id="p2", agent_id="a1",
        rules=["max_steps<=5", "timeout<=30"],
        scope=["project:P1", "env:test"],
    )
    # 显式声明 → 覆盖
    assert p.covers_rule("max_steps<=5") is True
    assert p.covers_scope("project:P1") is True
    # 默认拒绝：未声明的规则/作用域一律 False
    assert p.covers_rule("unknown_rule") is False
    assert p.covers_scope("project:P9") is False
    # 空字符串默认拒绝
    assert p.covers_rule("") is False
    assert p.covers_scope("") is False


# ===========================================================================
# 类别 2：AgentToolAccessPolicy（工具访问策略，默认拒绝）
# ===========================================================================

def test_tool_access_empty_name_denied() -> None:
    p = AgentToolAccessPolicy(
        policy_id="t1", agent_id="a1",
        allowed_tools=["web_search", "calculator"],
    )
    # 空工具名 → 拒绝（未声明的东西不放行）
    assert p.is_tool_allowed("") is False
    assert p.is_tool_allowed("   ") is False


def test_tool_access_denied_priority_and_whitelist() -> None:
    p = AgentToolAccessPolicy(
        policy_id="t2", agent_id="a1",
        allowed_tools=["web_search", "calculator"],
        denied_tools=["calculator"],
    )
    # denied 优先于 allowed：即便在白名单，被显式拒绝即拒绝
    assert p.is_tool_allowed("calculator") is False
    assert p.is_tool_allowed("web_search") is True
    # 不在白名单 → 拒绝
    assert p.is_tool_allowed("file_write") is False


def test_tool_access_empty_allowlist_denies_all() -> None:
    # 空白名单 ≠ 全放行（红线⑤）
    p = AgentToolAccessPolicy(policy_id="t3", agent_id="a1", allowed_tools=[])
    assert p.is_tool_allowed("anything") is False
    # 模型不提供任何放行入口
    for meth in ("grant", "allow", "whitelist", "unlock", "enable_tool"):
        assert not hasattr(p, meth), f"AgentToolAccessPolicy 不应含 {meth}"


def test_tool_access_check_tool_returns_outcome() -> None:
    p = AgentToolAccessPolicy(
        policy_id="t4", agent_id="a1", allowed_tools=["web_search"],
    )
    assert p.check_tool("web_search") is RuntimeCheckOutcome.PASS
    assert p.check_tool("unknown") is RuntimeCheckOutcome.FAIL


# ===========================================================================
# 类别 3：AgentExecutionGuard（只检查，不批准）
# ===========================================================================

def test_guard_check_policy_default_deny() -> None:
    g = AgentExecutionGuard(org_id="org-1", permission_policy=_policy())
    # 无 ACTIVE 策略 → FAIL（草稿/弃用不算数）
    draft = AgentRuntimePolicy(policy_id="gp1", agent_id="a1",
                               rules=["r1"], status=AgentRuntimePolicyStatus.DRAFT)
    assert g.check_policy(agent_id="a1", policies=[draft],
                          requested_rules=["r1"]) is RuntimeCheckOutcome.FAIL
    # 无 agent_id → FAIL
    assert g.check_policy(agent_id="", policies=[draft]) is RuntimeCheckOutcome.FAIL


def test_guard_check_policy_active_pass() -> None:
    g = AgentExecutionGuard(org_id="org-1", permission_policy=_policy())
    # 人工确认生效后的策略对象（服务层 confirm_policy_active 即置 ACTIVE；
    # 测试中以 DRAFT 构造后翻转 status 忠实模拟「已人工确认」态）
    active = AgentRuntimePolicy(
        policy_id="gp2", agent_id="a1", rules=["r1", "r2"],
        scope=["project:P1"],
    )
    active.status = AgentRuntimePolicyStatus.ACTIVE
    # 未声明请求规则时，仅要求存在生效策略即 PASS
    assert g.check_policy(agent_id="a1", policies=[active]) is RuntimeCheckOutcome.PASS
    # 请求规则全部被覆盖 → PASS
    assert g.check_policy(agent_id="a1", policies=[active],
                          requested_rules=["r1", "r2"]) is RuntimeCheckOutcome.PASS
    # 存在未声明规则 → FAIL
    assert g.check_policy(agent_id="a1", policies=[active],
                          requested_rules=["r1", "rX"]) is RuntimeCheckOutcome.FAIL


def test_guard_check_permission_default_deny() -> None:
    g = AgentExecutionGuard(org_id="org-1", permission_policy=_policy())
    # 无 user → FAIL
    assert g.check_permission(user=None) is RuntimeCheckOutcome.FAIL
    # EXPERT（仅 knowledge）访问 tool 资源 → 默认拒绝
    assert g.check_permission(
        user=_expert(), resource_category="tool"
    ) is RuntimeCheckOutcome.FAIL
    # ADMIN 访问 tool 资源 → 通过（角色作用域 + 身份双重校验）
    assert g.check_permission(
        user=_admin(), resource_category="tool"
    ) is RuntimeCheckOutcome.PASS


def test_guard_check_scope_default_deny() -> None:
    g = AgentExecutionGuard(org_id="org-1", permission_policy=_policy())
    active = AgentRuntimePolicy(policy_id="gs1", agent_id="a1", scope=["project:P1"])
    active.status = AgentRuntimePolicyStatus.ACTIVE
    # 无请求作用域 / 无 agent_id → FAIL
    assert g.check_scope(agent_id="a1", policies=[active],
                         requested_scope="") is RuntimeCheckOutcome.FAIL
    # 未声明作用域 → FAIL
    assert g.check_scope(agent_id="a1", policies=[active],
                         requested_scope="project:P9") is RuntimeCheckOutcome.FAIL
    # 已声明作用域 → PASS
    assert g.check_scope(agent_id="a1", policies=[active],
                         requested_scope="project:P1") is RuntimeCheckOutcome.PASS


def test_guard_check_tool_access_default_deny() -> None:
    g = AgentExecutionGuard(org_id="org-1", permission_policy=_policy())
    # 无策略 → FAIL
    assert g.check_tool_access(
        agent_id="a1", tool_name="web_search", tool_policies=[]
    ) is RuntimeCheckOutcome.FAIL
    tp = AgentToolAccessPolicy(
        policy_id="gt1", agent_id="a1", allowed_tools=["web_search"],
    )
    # 允许的工具 → PASS
    assert g.check_tool_access(
        agent_id="a1", tool_name="web_search", tool_policies=[tp]
    ) is RuntimeCheckOutcome.PASS
    # 未列入 → FAIL
    assert g.check_tool_access(
        agent_id="a1", tool_name="file_write", tool_policies=[tp]
    ) is RuntimeCheckOutcome.FAIL


# ===========================================================================
# 类别 4：RuntimeDecisionRecord（只记录事实，不构成批准）
# ===========================================================================

def test_runtime_record_requires_source() -> None:
    # 红线⑥：无 source 禁止落库
    with pytest.raises(EnterpriseRedLineViolationError):
        RuntimeDecisionRecord(record_id="r1", agent_id="a1")
    with pytest.raises(EnterpriseRedLineViolationError):
        RuntimeDecisionRecord(record_id="r2", agent_id="a1", source="   ")


def test_runtime_record_defaults_fail_closed() -> None:
    r = RuntimeDecisionRecord(record_id="r3", agent_id="a1", source="policy-x")
    # 缺省一律 FAIL（fail-closed）
    assert r.policy_result is RuntimeCheckOutcome.FAIL
    assert r.permission_result is RuntimeCheckOutcome.FAIL
    assert r.scope_result is RuntimeCheckOutcome.FAIL
    assert r.tool_result is RuntimeCheckOutcome.FAIL
    # 模型不提供任何 approve/allow/grant 方法
    for bad in ("approve", "allow", "grant", "engineering_approved"):
        assert not hasattr(r, bad), f"RuntimeDecisionRecord 不应含 {bad}"


def test_runtime_record_all_checks_passed_is_fact_only() -> None:
    r = RuntimeDecisionRecord(
        record_id="r4", agent_id="a1", source="policy-x",
        policy_result=RuntimeCheckOutcome.PASS,
        permission_result=RuntimeCheckOutcome.PASS,
        scope_result=RuntimeCheckOutcome.PASS,
        tool_result=RuntimeCheckOutcome.PASS,
    )
    # 仅为事实汇总，不等于批准（红线③）
    assert r.all_checks_passed is True
    # 不携带任何 approval 语义
    assert not hasattr(r, "approved")
    assert not hasattr(r, "decision")
    assert "policy=pass" in r.summary()
    assert "source=policy-x" in r.summary()


# ===========================================================================
# 类别 5：权限隔离（默认拒绝，AgentPermissionPolicy 接入）
# ===========================================================================

def test_ensure_access_denied_for_expert_data() -> None:
    svc = _svc("org-1")
    # EXPERT 仅 knowledge 作用域，访问 data 类别 → 默认拒绝（红线⑥）
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc._ensure_access(user=_expert(), resource_category="data")


def test_ensure_access_allowed_for_admin_data() -> None:
    svc = _svc("org-1")
    # ADMIN 含 all 作用域，访问 data 类别 → 通过
    assert svc._ensure_access(user=_admin(), resource_category="data") is None


def test_permission_policy_default_deny_tool_for_expert() -> None:
    policy = AgentPermissionPolicy(org_id="org-1", identity=_identity())
    # EXPERT 仅 knowledge → tool 默认拒绝
    assert policy.check_agent_access(
        user=_expert(), resource_category="tool",
        required_permission=Permission.READ_RESOURCE,
    ) is False
    # DESIGNER 含 tool → 通过
    assert policy.check_agent_access(
        user=_designer(), resource_category="tool",
        required_permission=Permission.READ_RESOURCE,
    ) is True


def test_list_runtime_policies_requires_access() -> None:
    svc = _svc("org-1")
    svc.register_runtime_policy(
        policy=AgentRuntimePolicy(policy_id="lp1", agent_id="a1"),
    )
    # EXPERT 无 data 权限 → 列举被默认拒绝
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc.list_runtime_policies(user=_expert(), resource_category="data")
    # ADMIN → 通过
    out = svc.list_runtime_policies(user=_admin(), resource_category="data")
    assert len(out) == 1 and out[0].policy_id == "lp1"


# ===========================================================================
# 类别 6：审计（AGENT_POLICY / AGENT_RUNTIME_CHECK / AGENT_TOOL_ACCESS，任务5）
# ===========================================================================

def test_audit_categories_present() -> None:
    """本层只对**自己新增的 3 类**负责；总数权威断言唯一保留在
    ``test_enterprise_knowledge_governance_audit.py``（Phase 3.8.31 Task 9）。
    """
    for cat, val in (
        ("AGENT_POLICY", "agent_policy"),
        ("AGENT_RUNTIME_CHECK", "agent_runtime_check"),
        ("AGENT_TOOL_ACCESS", "agent_tool_access"),
    ):
        assert hasattr(AuditActionCategory, cat)
        assert getattr(AuditActionCategory, cat).value == val


def test_audit_register_and_confirm_policy_recorded_as_user() -> None:
    audit = _audit("org-1")
    svc = AgentRuntimeGovernanceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.register_runtime_policy(
        policy=AgentRuntimePolicy(policy_id="ap1", agent_id="a1"),
        actor_id="ai",
    )
    # AI 登记为 DRAFT
    assert len(audit.query(category=AuditActionCategory.AGENT_POLICY)) == 1
    # 仅人工（USER）可确认生效
    svc.confirm_policy_active(
        policy_id="ap1", actor_kind=AuditActorKind.USER,
        actor_id="real-manager", activated_at="2026-08-06",
    )
    recs = audit.query(category=AuditActionCategory.AGENT_POLICY)
    assert len(recs) == 2
    active_rec = [r for r in recs if r.action == "confirm_agent_runtime_policy_active"]
    assert active_rec and active_rec[0].actor_kind is AuditActorKind.USER


def test_audit_runtime_check_and_tool_access_recorded() -> None:
    audit = _audit("org-1")
    svc = AgentRuntimeGovernanceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.register_runtime_policy(
        policy=AgentRuntimePolicy(policy_id="ac1", agent_id="a1"),
    )
    svc.register_tool_access_policy(
        policy=AgentToolAccessPolicy(
            policy_id="at1", agent_id="a1", allowed_tools=["web_search"],
        ),
    )
    svc.run_execution_check(
        record_id="rd1", agent_id="a1", user=_admin(),
        requested_rules=["r-na"], requested_scope="project:P9",
        tool_name="web_search",
    )
    assert len(audit.query(category=AuditActionCategory.AGENT_RUNTIME_CHECK)) == 1
    svc.check_tool_access(agent_id="a1", tool_name="web_search")
    assert len(audit.query(category=AuditActionCategory.AGENT_TOOL_ACCESS)) >= 1
    # 红线④/⑥：审计禁止 record_human_approval（AI 不伪造人工批准）；访问即拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


# ===========================================================================
# 类别 7：红线（fail-closed，6 条）
# ===========================================================================

def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


def test_runtime_governance_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    assert safety_invariants_ok() is False
    # 红线①：启用态下禁止构造治理服务 / Guard
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRuntimeGovernanceService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentExecutionGuard(org_id="org-1")


def test_confirm_policy_active_rejects_ai_actor() -> None:
    svc = _svc("org-1")
    svc.register_runtime_policy(
        policy=AgentRuntimePolicy(policy_id="cp1", agent_id="a1"),
    )
    # 红线④/⑥：AI/系统/空 actor_kind 不得确认策略生效
    for bad in (AuditActorKind.AI, AuditActorKind.SYSTEM, None, ""):
        with pytest.raises(EnterpriseRedLineViolationError):
            svc.confirm_policy_active(
                policy_id="cp1", actor_kind=bad, actor_id="x",
            )
    # USER 可确认（验证人工路径可用）
    svc.confirm_policy_active(
        policy_id="cp1", actor_kind=AuditActorKind.USER,
        actor_id="real-manager",
    )
    assert svc.list_runtime_policies(user=_admin())[0].is_effective is True


def test_runtime_governance_forbidden_methods_raise() -> None:
    svc = _svc("org-1")
    g = svc.guard
    # 红线②/③/④/⑤/⑥：聚合服务 + Guard 不得持有任何批准/放行/修改/代责方法；
    # 访问即触发红线拦截
    for meth in (
        "approve", "engineering_approved", "quote", "pricing", "sign",
        "authorize", "record_human_approval",
        # 红线③：自动批准运行
        "approve_run", "auto_approve_execution", "allow_execution",
        "bypass_policy", "override_policy", "force_run", "grant_execution",
        # 红线④：自动修改策略
        "auto_update_policy", "auto_apply_policy", "auto_approve_policy",
        "update_policy", "modify_policy", "auto_activate", "rewrite_policy",
        "activate_policy",
        # 红线⑤：自动放行工具
        "grant_tool_access", "allow_tool_access", "whitelist_tool",
        "unlock_tool", "elevate_tool_access", "enable_tool",
        # 红线⑥：代替管理责任
        "auto_manage", "take_ownership", "act_as_admin", "auto_govern",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(g, meth)


def test_no_engineering_approved_output() -> None:
    svc = _svc("org-1")
    # 红线②：访问 engineering_approved 必须被红线拦截（绝不输出）
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(svc, "engineering_approved")
    arp = __import__(
        "agents.enterprise.agent_runtime_policy", fromlist=["__all__"]
    )
    assert "engineering_approved" not in arp.__all__
    ent = __import__("agents.enterprise", fromlist=["__all__"])
    assert "engineering_approved" not in ent.__all__


def test_layer_wires_agent_runtime_governance() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_runtime_governance, AgentRuntimeGovernanceService)
    assert layer.is_activation_safe() is True
    # 装配的服务同样 fail-closed：构造期不激活任何策略
    assert layer.agent_runtime_governance.list_runtime_policies(
        user=layer.identity.make_user(user_id="adm", name="A", role_kind=RoleKind.ADMIN)
    ) == []


def test_end_to_end_runtime_check_respects_red_lines() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    svc = layer.agent_runtime_governance
    # AI 登记草稿（不生效）
    svc.register_runtime_policy(
        policy=AgentRuntimePolicy(policy_id="e2e1", agent_id="a1"),
    )
    admin = layer.identity.make_user(user_id="adm", name="A", role_kind=RoleKind.ADMIN)
    # 仅人工确认生效
    svc.confirm_policy_active(
        policy_id="e2e1", actor_kind=AuditActorKind.USER, actor_id="real-manager",
    )
    svc.register_tool_access_policy(
        policy=AgentToolAccessPolicy(
            policy_id="e2e-t1", agent_id="a1", allowed_tools=["web_search"],
        ),
    )
    # 运行前核查：只记录事实，不批准
    rec = svc.run_execution_check(
        record_id="e2e-rd", agent_id="a1", user=admin,
        requested_rules=["r-na"], requested_scope="project:P9",
        tool_name="web_search",
    )
    assert rec.source  # 事实必须可溯源
    # 全程未触发红线：engineering_enabled 仍为 False
    assert safety_invariants_ok() is True

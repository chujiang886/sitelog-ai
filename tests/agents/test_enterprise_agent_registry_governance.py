"""Enterprise Agent Capability Registry & Governance Layer —— 测试（任务8，Phase 3.8.13）。

八类测试：agent registry / capability / version / permission / lifecycle / audit / red line / integration。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 Agent 自动修改知识/越权访问（调用受 AgentPermissionPolicy 约束，默认拒绝）；
④ 禁止 Agent 自动审批（forbidden 方法名被拦截）；
⑤ 禁止绕过 UnifiedActivationGate（safety_invariants_ok 护栏）；
⑥ AI 不替代专家责任（activate / deprecate 须 require_human_actor(AuditActorKind.USER)）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_capability import AgentCapability
from agents.enterprise.agent_lifecycle_service import AgentLifecycleService
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_registry import AgentRegistry, AgentStatus
from agents.enterprise.agent_version import (
    AgentVersionManager,
    AgentVersionStatus,
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
# 共享构造器
# ---------------------------------------------------------------------------

def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _lifecycle(org_id: str = "org-1") -> AgentLifecycleService:
    return AgentLifecycleService(
        org_id=org_id, audit=_audit(org_id), identity=_identity(org_id)
    )


def _cap(cap_id: str, agent_id: str, **kw) -> AgentCapability:
    return AgentCapability(capability_id=cap_id, agent_id=agent_id, **kw)


def _register_draft(svc: AgentLifecycleService, agent_id: str = "a1") -> AgentRegistry:
    caps = [
        _cap(
            "c1",
            agent_id,
            input_types=["text"],
            output_types=["plan"],
            permissions=["read_resource"],
            limitations=["不得写入知识库", "不得生成工程参数"],
        )
    ]
    return svc.register(
        agent_id=agent_id,
        name="AgentOne",
        agent_type="planner",
        capabilities=caps,
        owner="owner-1",
        created_at="2026-08-05T00:00:00Z",
    )


# ===========================================================================
# 类别 1：AgentRegistry 模型
# ===========================================================================

def test_agent_registry_default_status_draft() -> None:
    reg = AgentRegistry(agent_id="a1", name="A", type="planner", version="0.1.0")
    assert reg.status is AgentStatus.DRAFT
    assert reg.capabilities == []
    assert reg.is_active is False
    assert reg.is_deprecated is False


def test_agent_registry_status_enum_coercion() -> None:
    reg = AgentRegistry(agent_id="a1", name="A", type="planner", version="0.1.0", status="active")
    assert reg.status is AgentStatus.ACTIVE
    assert reg.is_active is True


# ===========================================================================
# 类别 2：AgentCapability 边界声明
# ===========================================================================

def test_agent_capability_fields_and_boundary() -> None:
    cap = _cap(
        "c1", "a1",
        input_types=["text", "image"],
        output_types=["plan"],
        permissions=["read_resource"],
        limitations=["不得写入知识库"],
    )
    assert cap.input_types == ["text", "image"]
    assert cap.output_types == ["plan"]
    assert cap.permissions == ["read_resource"]
    assert cap.forbids("写入知识库") is True
    assert cap.forbids("不存在的约束") is False
    assert cap.denies_write is True


# ===========================================================================
# 类别 3：AgentVersion 版本管理（可追踪 + 人工门禁）
# ===========================================================================

def test_agent_version_create_is_draft_then_activate_requires_user() -> None:
    svc = AgentVersionManager(org_id="org-1", audit=_audit())
    svc.create_version(version_id="a1@v1", agent_id="a1", change_log="init")
    svc.submit_review(version_id="a1@v1")
    # 红线⑥：AI 不得激活
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.activate_version(version_id="a1@v1", actor_id="ai", actor_kind=AuditActorKind.AI)
    v = svc.activate_version(
        version_id="a1@v1", actor_id="u", actor_kind=AuditActorKind.USER
    )
    assert v.status is AgentVersionStatus.ACTIVE
    assert svc.active_version(agent_id="a1") is v


def test_agent_version_only_reviewing_can_activate() -> None:
    svc = AgentVersionManager(org_id="org-1", audit=_audit())
    svc.create_version(version_id="a1@v1", agent_id="a1", change_log="init")
    with pytest.raises(ValueError):
        svc.activate_version(
            version_id="a1@v1", actor_id="u", actor_kind=AuditActorKind.USER
        )


def test_agent_version_deprecate_requires_user_and_traceability() -> None:
    svc = AgentVersionManager(org_id="org-1", audit=_audit())
    svc.create_version(version_id="a1@v1", agent_id="a1", change_log="init")
    svc.submit_review(version_id="a1@v1")
    svc.activate_version(version_id="a1@v1", actor_id="u", actor_kind=AuditActorKind.USER)
    # AI 不得弃用
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.deprecate_version(
            version_id="a1@v1", actor_id="ai", actor_kind=AuditActorKind.AI
        )
    v = svc.deprecate_version(
        version_id="a1@v1", actor_id="u", actor_kind=AuditActorKind.USER
    )
    assert v.status is AgentVersionStatus.DEPRECATED
    # 版本可追踪：仍可按 id 取回
    assert svc.get(version_id="a1@v1").status is AgentVersionStatus.DEPRECATED


def test_agent_version_audit_records() -> None:
    audit = _audit()
    svc = AgentVersionManager(org_id="org-1", audit=audit)
    svc.create_version(version_id="a1@v1", agent_id="a1", change_log="init")
    svc.submit_review(version_id="a1@v1")
    svc.activate_version(version_id="a1@v1", actor_id="u", actor_kind=AuditActorKind.USER)
    recs = audit.query(category=AuditActionCategory.AGENT_VERSION)
    actions = [r.action for r in recs]
    assert "create_agent_version" in actions
    assert "submit_agent_version_review" in actions
    assert "activate_agent_version" in actions
    user_recs = [r for r in recs if r.action == "activate_agent_version"]
    assert user_recs and user_recs[0].actor_kind == AuditActorKind.USER


# ===========================================================================
# 类别 4：AgentPermissionPolicy（默认拒绝）
# ===========================================================================

def test_permission_policy_default_deny_unknown_category() -> None:
    policy = AgentPermissionPolicy(org_id="org-1")
    # 空类别 → 默认拒绝
    assert policy.is_agent_resource_permitted(RoleKind.ADMIN, "") is False
    # 未授权类别 → 默认拒绝
    assert policy.is_agent_resource_permitted(RoleKind.EXPERT, "data") is False
    assert policy.is_agent_resource_permitted(RoleKind.REVIEWER, "tool") is False


def test_permission_policy_role_scope() -> None:
    policy = AgentPermissionPolicy(org_id="org-1")
    # ADMIN 含 all，全可访问
    assert policy.is_agent_resource_permitted(RoleKind.ADMIN, "tool") is True
    assert policy.is_agent_resource_permitted(RoleKind.ADMIN, "data") is True
    # ENGINEER 可访问 knowledge/tool/data
    assert policy.is_agent_resource_permitted(RoleKind.ENGINEER, "data") is True
    # EXPERT 仅 knowledge
    assert policy.is_agent_resource_permitted(RoleKind.EXPERT, "knowledge") is True
    assert policy.is_agent_resource_permitted(RoleKind.EXPERT, "tool") is False


def test_permission_policy_check_via_identity_default_deny() -> None:
    identity = _identity()
    policy = AgentPermissionPolicy(org_id="org-1", identity=identity)
    expert = identity.make_user(user_id="e1", name="E", role_kind=RoleKind.EXPERT)
    admin = identity.make_user(user_id="a1", name="A", role_kind=RoleKind.ADMIN)
    # EXPERT 访问 data → 角色作用域拒绝（默认拒绝）
    assert policy.check_agent_access(user=expert, resource_category="data") is False
    # EXPERT 访问 knowledge → 角色允许 + 身份有权限
    assert policy.check_agent_access(user=expert, resource_category="knowledge") is True
    # ADMIN 访问 data → 允许
    assert policy.check_agent_access(user=admin, resource_category="data") is True


# ===========================================================================
# 类别 5：AgentLifecycleService 生命周期治理
# ===========================================================================

def test_lifecycle_register_creates_draft_and_capabilities() -> None:
    svc = _lifecycle()
    reg = _register_draft(svc, "a1")
    assert reg.status is AgentStatus.DRAFT
    assert reg.agent_id == "a1"
    # 能力登记
    assert svc.list_capabilities(agent_id="a1")[0].capability_id == "c1"
    # 首条版本自动登记
    assert svc.version_manager.latest_version(agent_id="a1") is not None
    assert svc.version_manager.latest_version(agent_id="a1").status is AgentVersionStatus.DRAFT


def test_lifecycle_activate_requires_user() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")
    svc.submit_review(agent_id="a1")
    # 红线⑥：AI 不得激活
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.activate(agent_id="a1", actor_id="ai", actor_kind=AuditActorKind.AI)
    reg = svc.activate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    assert reg.status is AgentStatus.ACTIVE


def test_lifecycle_deprecate_requires_user_and_state_machine() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")
    # 仍 DRAFT，不得弃用
    with pytest.raises(ValueError):
        svc.deprecate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    svc.submit_review(agent_id="a1")
    svc.activate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    # AI 不得弃用
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.deprecate(agent_id="a1", actor_id="ai", actor_kind=AuditActorKind.AI)
    reg = svc.deprecate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    assert reg.status is AgentStatus.DEPRECATED


def test_lifecycle_full_flow_syncs_version() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")
    svc.submit_review(agent_id="a1")
    svc.activate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    # 激活后对应版本也应为 ACTIVE（人工门禁同步）
    v = svc.version_manager.active_version(agent_id="a1")
    assert v is not None and v.status is AgentVersionStatus.ACTIVE
    # 审计：注册/复核/激活 均为 AGENT_REGISTER
    recs = svc._audit.query(category=AuditActionCategory.AGENT_REGISTER)
    actions = [r.action for r in recs]
    assert "register_agent" in actions
    assert "submit_agent_review" in actions
    assert "activate_agent" in actions
    act = [r for r in recs if r.action == "activate_agent"]
    assert act and act[0].actor_kind == AuditActorKind.USER


def test_lifecycle_org_isolation() -> None:
    svc = _lifecycle("org-1")
    _register_draft(svc, "a1")
    # 其它组织服务访问被拒
    other = _lifecycle("org-2")
    with pytest.raises(Exception):
        other.get(agent_id="a1")


# ===========================================================================
# 类别 6：审计（AGENT_REGISTER / AGENT_EXECUTION / AGENT_VERSION）
# ===========================================================================

def test_audit_categories_present_and_recordable() -> None:
    audit = _audit()
    assert audit.record_agent_register_action(record_id="r1", actor_id="ai") is not None
    assert audit.record_agent_execution_action(record_id="r2", actor_id="ai") is not None
    assert audit.record_agent_version_action(record_id="r3", actor_id="ai") is not None
    regs = audit.query(category=AuditActionCategory.AGENT_REGISTER)
    execs = audit.query(category=AuditActionCategory.AGENT_EXECUTION)
    vers = audit.query(category=AuditActionCategory.AGENT_VERSION)
    assert len(regs) == 1 and regs[0].category is AuditActionCategory.AGENT_REGISTER
    assert len(execs) == 1 and execs[0].category is AuditActionCategory.AGENT_EXECUTION
    assert len(vers) == 1 and vers[0].category is AuditActionCategory.AGENT_VERSION


def test_audit_execution_records_invocation() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")
    svc.submit_review(agent_id="a1")
    svc.activate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    identity = _identity()
    admin = identity.make_user(user_id="a1", name="A", role_kind=RoleKind.ADMIN)
    svc.record_invocation(
        agent_id="a1", capability_id="c1", user=admin,
        resource_category="knowledge", actor_id="ai",
    )
    recs = svc._audit.query(category=AuditActionCategory.AGENT_EXECUTION)
    assert any(r.action == "invoke_agent" for r in recs)


# ===========================================================================
# 类别 7：红线（fail-closed，6 条）
# ===========================================================================

def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


@pytest.mark.parametrize(
    "svc_factory",
    [
        lambda: AgentLifecycleService(org_id="org-1", audit=AuditService(org_id="org-1")),
        lambda: AgentVersionManager(org_id="org-1", audit=AuditService(org_id="org-1")),
        lambda: EnterpriseOperationLayer(org_id="org-1"),
    ],
)
def test_service_construction_fail_closed(svc_factory, monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_factory()


def test_forbidden_methods_raise(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: False)
    svc = _lifecycle()
    for meth in ("approve", "engineering_approved", "quote", "pricing", "sign", "authorize", "record_human_approval", "auto_activate", "publish", "apply"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)()
    # AuditService 也不得伪造 human approval
    with pytest.raises(EnterpriseRedLineViolationError):
        _audit().record_human_approval()


def test_invocation_requires_active_agent() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")  # 仍 DRAFT
    identity = _identity()
    admin = identity.make_user(user_id="a1", name="A", role_kind=RoleKind.ADMIN)
    with pytest.raises(ValueError):
        svc.record_invocation(
            agent_id="a1", capability_id="c1", user=admin, resource_category="knowledge"
        )


def test_invocation_denied_by_permission_policy() -> None:
    svc = _lifecycle()
    _register_draft(svc, "a1")
    svc.submit_review(agent_id="a1")
    svc.activate(agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER)
    identity = _identity()
    # EXPERT 无权访问 data 类别
    expert = identity.make_user(user_id="e1", name="E", role_kind=RoleKind.EXPERT)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_invocation(
            agent_id="a1", capability_id="c1", user=expert, resource_category="data"
        )
    # 拒绝调用被如实审计
    denied = svc._audit.query(category=AuditActionCategory.AGENT_EXECUTION)
    assert any(r.action == "invoke_agent_denied" for r in denied)


# ===========================================================================
# 类别 8：集成（EnterpriseOperationLayer 装配 + 端到端）
# ===========================================================================

def test_layer_wires_agent_governance() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_registry, AgentLifecycleService)
    assert isinstance(layer.agent_permission_policy, AgentPermissionPolicy)
    assert layer.is_activation_safe() is True


def test_layer_end_to_end_flow() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    caps = [
        _cap("c1", "a1", input_types=["text"], output_types=["plan"],
             permissions=["read_resource"], limitations=["不得写入知识库"])
    ]
    reg = layer.agent_registry.register(
        agent_id="a1", name="AgentOne", agent_type="planner",
        capabilities=caps, owner="owner-1",
    )
    assert reg.status is AgentStatus.DRAFT
    layer.agent_registry.submit_review(agent_id="a1")
    layer.agent_registry.activate(
        agent_id="a1", actor_id="u", actor_kind=AuditActorKind.USER
    )
    assert layer.agent_registry.get(agent_id="a1").status is AgentStatus.ACTIVE
    # 通过聚合层权限策略校验一次调用
    admin = layer.identity.make_user(user_id="a1", name="A", role_kind=RoleKind.ADMIN)
    layer.agent_registry.record_invocation(
        agent_id="a1", capability_id="c1", user=admin, resource_category="knowledge"
    )
    execs = layer.audit.query(category=AuditActionCategory.AGENT_EXECUTION)
    assert any(r.action == "invoke_agent" for r in execs)

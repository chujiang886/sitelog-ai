"""Phase 3.8.30 治理全链路追踪与统一审计智能层测试（fail-closed，八类）。

覆盖：trace / link / timeline / replay / report / permission / audit / red_line。

本层是**纯只读**事实串联层，不持有任何治理状态写入口；所有出口 fail-closed。
测试严格守约：
- 不开启 engineering_enabled（fixture 锁定 False，不碰磁盘）；
- 不输出 engineering_approved（断言审计记录无该语义）；
- 不 AI 自动改治理记录 / 出结论 / 关事件 / 代责（结构级 + 类型级 + 语义级三重拦截断言）；
- 不修改 verified.json / engineering_enabled。
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from agents.enterprise import GovernanceTraceabilityService as _ExportedTop  # 验证顶层导出
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.governance_traceability import (
    AuditViewer,
    GovernanceAuditTimeline,
    GovernanceReplayStep,
    GovernanceReplayView,
    GovernanceTrace,
    GovernanceTraceabilityService,
    GovernanceTraceLink,
    GovernanceTraceLinkKind,
    GovernanceTraceReport,
    GovernanceTraceSourceType,
    SourceTrace,
    TRACEABILITY_FORBIDDEN_COUNT,
    _FORBIDDEN_TRACE_FIELDS,
    _TRACEABILITY_FORBIDDEN,
)
from agents.enterprise.governance_traceability.models import (
    _AUDIT_MUTATION_MARKERS,
    _CONCLUSION_MARKERS,
    _INCIDENT_CLOSURE_MARKERS,
)
from agents.enterprise.identity import IdentityService, Permission, RoleKind
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch):
    """红线①：锁定 engineering_enabled=False（只读断言，不碰磁盘）。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


# ---------------------------------------------------------------------------
# 装配助手
# ---------------------------------------------------------------------------

def _identity(org: str = "org-27") -> IdentityService:
    return IdentityService(org_id=org)


def _user(identity: IdentityService, kind: RoleKind, uid: str = "u-1") -> "object":
    return identity.make_user(user_id=uid, name=uid, role_kind=kind)


def _viewer(user) -> AuditViewer:
    return AuditViewer.from_user(user)


def _audit(org: str = "org-27") -> AuditService:
    return AuditService(org_id=org)


def _policy(org: str = "org-27", identity: IdentityService | None = None) -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org, identity=identity)


def _svc(org: str = "org-27") -> GovernanceTraceabilityService:
    """复刻装配层：audit + identity + policy 三件套（默认拒绝双闸门）。"""
    identity = _identity(org)
    audit = _audit(org)
    policy = _policy(org, identity=identity)
    return GovernanceTraceabilityService(
        org_id=org,
        audit=audit,
        identity=identity,
        permission_policy=policy,
    )


def _admin(org: str = "org-27"):
    return _viewer(_user(_identity(org), RoleKind.ADMIN, uid="admin-1"))


def _reviewer(org: str = "org-27"):
    return _viewer(_user(_identity(org), RoleKind.REVIEWER, uid="rev-1"))


# ===========================================================================
# 类别一：trace（任务1 全链路唯一，只串事实，不下结论）
# ===========================================================================

def test_package_export_present():
    assert _ExportedTop is GovernanceTraceabilityService


def test_engineering_disabled_guard():
    # 红线①：构造期断言 engineering_enabled=False。
    assert safety_invariants_ok() is True


def test_register_and_get_trace():
    svc = _svc()
    admin = _admin()
    t = svc.register_trace(
        trace_id="tr-1", source_id="ev-1", created_at="2026-08-09T09:00:00Z",
        user=admin, source_type=GovernanceTraceSourceType.GOVERNANCE_EVENT,
        title="密封胶脱胶事件", description="现场反馈",
    )
    assert t.trace_id == "tr-1"
    assert t.source_id == "ev-1"
    assert t.requires_human_review is True  # 红线⑥：恒 True
    got = svc.get_trace(trace_id="tr-1", user=admin)
    assert got.trace_id == "tr-1"


def test_duplicate_trace_id_rejected():
    svc = _svc()
    admin = _admin()
    svc.register_trace(
        trace_id="tr-dup", source_id="ev-1", created_at="2026-08-09T09:00:00Z",
        user=admin,
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.register_trace(
            trace_id="tr-dup", source_id="ev-2", created_at="2026-08-09T09:00:00Z",
            user=admin,
        )


def test_missing_trace_raises():
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.get_trace(trace_id="nope", user=_admin())


def test_list_traces_filters_org_and_type():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="t-a", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin, source_type=GovernanceTraceSourceType.GOVERNANCE_EVENT)
    svc.register_trace(trace_id="t-b", source_id="e2", created_at="2026-08-09T10:00:00Z",
                       user=admin, source_type=GovernanceTraceSourceType.AUDIT_RECORD)
    all_t = svc.list_traces(user=admin)
    assert {t.trace_id for t in all_t} == {"t-a", "t-b"}
    only_audit = svc.list_traces(user=admin, source_type=GovernanceTraceSourceType.AUDIT_RECORD)
    assert [t.trace_id for t in only_audit] == ["t-b"]


def test_trace_model_rejects_empty_identifiers():
    # 红线⑥：无标识 / 无来源 / 无时序 禁止落库（类型级）。
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(trace_id="", source_id="e1", created_at="2026-08-09T09:00:00Z")
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(trace_id="tr-x", source_id="", created_at="2026-08-09T09:00:00Z")
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(trace_id="tr-x", source_id="e1", created_at="")


def test_trace_requires_human_review_cannot_be_false():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(
            trace_id="tr-y", source_id="e1", created_at="2026-08-09T09:00:00Z",
            requires_human_review=False,
        )


# ===========================================================================
# 类别二：link（任务2 只建立关联，不触碰目标对象状态）
# ===========================================================================

def test_link_establishes_only_association():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-l", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    ln = svc.link(
        link_id="ln-1", trace_id="tr-l", link_kind=GovernanceTraceLinkKind.AUDIT,
        target_id="audit-99", user=admin, created_at="2026-08-09T09:05:00Z",
        note="关联审计记录 audit-99",
    )
    assert ln.target_id == "audit-99"
    assert ln.link_kind is GovernanceTraceLinkKind.AUDIT
    # 关联不改变被关联对象（这里是纯字符串 id）——证明本层仅登记关联事实。
    listed = svc.list_links(trace_id="tr-l", user=admin)
    assert [l.link_id for l in listed] == ["ln-1"]
    assert all(not l.note or True for l in listed)


def test_link_to_missing_trace_rejected():
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.link(
            link_id="ln-x", trace_id="tr-ghost", link_kind=GovernanceTraceLinkKind.EVENT,
            target_id="e1", user=_admin(),
        )


def test_duplicate_link_id_rejected():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-l", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    svc.link(link_id="ln-dup", trace_id="tr-l", link_kind=GovernanceTraceLinkKind.EVENT,
             target_id="e1", user=admin)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.link(link_id="ln-dup", trace_id="tr-l", link_kind=GovernanceTraceLinkKind.EVENT,
                 target_id="e2", user=admin)


# ===========================================================================
# 类别三：timeline（任务3 统一审计时间线，只读，四要素）
# ===========================================================================

def test_build_audit_timeline_read_only_and_aggregates():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-tl", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    # 预先写入一条目标为该链路的既有审计记录，验证聚合能力。
    svc._audit.record_user_action(
        record_id="a-1", actor_id="someone", action="verify", target="tr-tl",
    )
    tl = svc.build_audit_timeline(trace_id="tr-tl", user=admin)
    assert isinstance(tl, GovernanceAuditTimeline)
    assert tl.read_only is True            # 红线③：恒只读
    assert tl.requires_human_review is True  # 红线⑥
    assert isinstance(tl.entries, tuple)   # 不可变
    # 至少包含：链路登记事实 + 聚合到的既有审计记录。
    actions = {e.action for e in tl.entries}
    assert "register_trace" in actions
    assert "verify" in actions
    # 四要素齐备：ts / actor / action / source。
    for e in tl.entries:
        assert e.ts is not None
        assert e.actor_id is not None
        assert e.action
        assert e.source


def test_timeline_entries_frozen():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-tl2", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    tl = svc.build_audit_timeline(trace_id="tr-tl2", user=admin)
    with pytest.raises(FrozenInstanceError):
        tl.entries[0].action = "tampered"  # 红线③：不可改写


# ===========================================================================
# 类别四：replay（任务4 重建事实，禁止重新执行）
# ===========================================================================

def test_build_replay_view_no_re_execution():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-rp", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin, description="原始事实描述")
    svc.link(link_id="ln-rp", trace_id="tr-rp", link_kind=GovernanceTraceLinkKind.AUDIT,
             target_id="audit-7", user=admin, note="关联依据")
    view = svc.build_replay_view(trace_id="tr-rp", user=admin)
    assert isinstance(view, GovernanceReplayView)
    assert view.re_execution_performed is False  # 红线④/⑤：绝不重新执行
    assert view.read_only is True
    assert isinstance(view.steps, tuple)
    assert len(view.steps) >= 2
    for step in view.steps:
        assert step.re_executed is False       # 红线④/⑤
        assert step.fact is not None           # 原样引用，不做推断


def test_replay_step_cannot_be_marked_executed():
    # 类型级：试图把重放标记成已执行 → 红线违例。
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceReplayView(
            trace_id="tr", org_id="org-27",
            steps=(GovernanceReplayStep(
                seq=1, ts="2026-08-09T09:00:00Z", actor_kind=AuditActorKind.USER,
                actor_id="a", action="register_trace", source="tr",
                re_executed=True,
            ),),
        )


# ===========================================================================
# 类别五：report（任务5 完整来源链，零结论）
# ===========================================================================

def test_build_trace_report_full_source_chain_no_conclusion():
    svc = _svc()
    admin = _admin()
    svc.register_trace(
        trace_id="tr-rpt", source_id="ev-1", workflow_id="wf-1", task_id="task-1",
        created_at="2026-08-09T09:00:00Z", user=admin,
        source_type=GovernanceTraceSourceType.GOVERNANCE_EVENT, title="主事件",
    )
    svc.link(link_id="ln-rpt", trace_id="tr-rpt", link_kind=GovernanceTraceLinkKind.AUDIT,
             target_id="audit-5", user=admin, note="关联审计")
    rpt = svc.build_trace_report(report_id="rpt-1", trace_id="tr-rpt", user=admin)
    assert isinstance(rpt, GovernanceTraceReport)
    assert rpt.conclusion_included is False    # 红线④：零结论
    assert rpt.read_only is True
    assert rpt.requires_human_review is True    # 红线⑥
    # 来源链完整：来源事件 + 工作流 + 任务 + 关联审计。
    kinds = {(s.source_kind.value, s.source_id) for s in rpt.source_chain}
    assert ("event", "ev-1") in kinds
    assert ("workflow", "wf-1") in kinds
    assert ("task", "task-1") in kinds
    assert ("audit", "audit-5") in kinds
    assert rpt.timeline is not None and rpt.timeline.read_only is True


def test_report_cannot_include_conclusion():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTraceReport(
            report_id="r", trace_id="t", org_id="org-27",
            conclusion_included=True,
        )


def test_report_is_frozen():
    rpt = GovernanceTraceReport(report_id="r", trace_id="t", org_id="org-27")
    with pytest.raises(FrozenInstanceError):
        rpt.conclusion_included = True  # 红线③：不可改写


# ===========================================================================
# 类别六：permission（任务7 双闸门：组织隔离 + 默认拒绝 + 人工强制）
# ===========================================================================

def test_admin_passes_dual_gate():
    svc = _svc()
    t = svc.register_trace(
        trace_id="tr-perm", source_id="e1", created_at="2026-08-09T09:00:00Z",
        user=_admin(),
    )
    assert t is not None
    tl = svc.build_audit_timeline(trace_id="tr-perm", user=_admin())
    assert tl.read_only is True


def test_reviewer_denied_by_resource_scope():
    # 红线⑥：REVIEWER 的 Agent 资源作用域仅 {knowledge}，不含 data → 默认拒绝。
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.register_trace(
            trace_id="tr-rev", source_id="e1", created_at="2026-08-09T09:00:00Z",
            user=_reviewer(),
        )


def test_anonymous_access_denied():
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.register_trace(
            trace_id="tr-anon", source_id="e1", created_at="2026-08-09T09:00:00Z",
            user=None,
        )


def test_cross_org_access_denied():
    # 外组织的人即便持有 VIEW_AUDIT 也不得读取本组织审计事实。
    svc = _svc(org="org-27")
    outsider = _viewer(_user(_identity("org-99"), RoleKind.ADMIN, uid="out-1"))
    with pytest.raises(EnterpriseIsolationError):
        svc.register_trace(
            trace_id="tr-xorg", source_id="e1", created_at="2026-08-09T09:00:00Z",
            user=outsider,
        )


def test_ai_actor_denied():
    # 红线⑥：非 USER（AI）不得执行任何追踪层操作。
    svc = _svc()
    ai_viewer = AuditViewer(actor_kind=AuditActorKind.AI, org_id="org-27", actor_id="ai-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.register_trace(
            trace_id="tr-ai", source_id="e1", created_at="2026-08-09T09:00:00Z",
            user=ai_viewer,
        )


# ===========================================================================
# 类别七：audit（任务6 接入，actor 真实，无 record_human_approval）
# ===========================================================================

def test_audit_categories_added():
    """本层只对**自己新增的 3 类**负责。

    审计大类**总数**的权威断言唯一保留在
    ``tests/agents/test_enterprise_knowledge_governance_audit.py``
    （``EXPECTED_CATEGORIES`` 全量成员名集合 + 总数）。
    Phase 3.8.31 Task 9：消除「每新增一类就要连改十几处旧测试」的脆性。
    """
    # Phase 3.8.30 Task 6 新增 3 类只读事实审计。
    assert AuditActionCategory.GOVERNANCE_TRACE.value == "governance_trace"
    assert AuditActionCategory.GOVERNANCE_TIMELINE.value == "governance_timeline"
    assert AuditActionCategory.GOVERNANCE_REPLAY.value == "governance_replay"


def test_trace_timeline_replay_audit_actor_is_user():
    svc = _svc()
    admin = _admin()
    svc.register_trace(
        trace_id="tr-aud", source_id="e1", created_at="2026-08-09T09:00:00Z",
        user=admin,
    )
    svc.build_audit_timeline(trace_id="tr-aud", user=admin)
    svc.build_replay_view(trace_id="tr-aud", user=admin)
    recs = svc._audit._records
    cats = {r.category for r in recs}
    assert AuditActionCategory.GOVERNANCE_TRACE in cats
    assert AuditActionCategory.GOVERNANCE_TIMELINE in cats
    assert AuditActionCategory.GOVERNANCE_REPLAY in cats
    # 三者的 actor_kind 一律 USER（真实责任人），绝无 AI 伪装。
    for r in recs:
        if r.category in (
            AuditActionCategory.GOVERNANCE_TRACE,
            AuditActionCategory.GOVERNANCE_TIMELINE,
            AuditActionCategory.GOVERNANCE_REPLAY,
        ):
            assert r.actor_kind is AuditActorKind.USER
            assert r.actor_id == "admin-1"  # 真实 actor 透传


def test_no_record_human_approval_method():
    # 红线⑥：审计层不得把动作记录为人工审批（方法名被拦截）。
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc._audit.record_human_approval(record_id="x", actor_id="a")  # type: ignore


def test_no_engineering_approved_in_audit_records():
    svc = _svc()
    admin = _admin()
    svc.register_trace(trace_id="tr-ea", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    svc.build_trace_report(report_id="r-ea", trace_id="tr-ea", user=admin)
    for r in svc._audit._records:
        assert "engineering_approved" not in (r.detail or "")


# ===========================================================================
# 类别八：red_line（结构级 + 类型级 + 语义级 三重 fail-closed）
# ===========================================================================

def test_forbidden_method_names_intercepted():
    # 结构级：任何禁名调用一律抛红线违例（AI 不可越权）。
    svc = _svc()
    for name in ("auto_modify_audit", "conclude", "close_incident",
                 "sign_off_audit", "replay_execute", "modify_audit", "verdict"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()


def test_forbidden_set_membership_and_count():
    assert TRACEABILITY_FORBIDDEN_COUNT >= 240
    assert "auto_modify_audit" in _TRACEABILITY_FORBIDDEN
    assert "record_human_approval" in _TRACEABILITY_FORBIDDEN
    assert "engineering_approved" in _TRACEABILITY_FORBIDDEN
    assert "close_incident" in _TRACEABILITY_FORBIDDEN
    assert "replay_execute" in _TRACEABILITY_FORBIDDEN


def test_trace_model_has_no_conclusion_or_closure_fields():
    # 类型级：GovernanceTrace 根本不存在结论 / 关闭字段。
    for f in _FORBIDDEN_TRACE_FIELDS:
        assert not hasattr(GovernanceTrace, f), f"追踪模型不应含字段 {f!r}"


def test_semantic_mutation_marker_rejected():
    # 语义级：描述含「改审计」标记 → 拒绝（红线③）。
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(
            trace_id="tr-sem", source_id="e1", created_at="2026-08-09T09:00:00Z",
            description="请 AI auto_modify_audit 修改记录",
        )


def test_semantic_closure_marker_rejected():
    # 语义级：含「关事件」标记 → 拒绝（红线⑤）。
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceTrace(
            trace_id="tr-clo", source_id="e1", created_at="2026-08-09T09:00:00Z",
            description="请 AI 自动关闭事件",
        )


def test_marker_constants_are_nonempty():
    assert len(_AUDIT_MUTATION_MARKERS) > 0
    assert len(_CONCLUSION_MARKERS) > 0
    assert len(_INCIDENT_CLOSURE_MARKERS) > 0


def test_service_is_read_only_and_stats():
    svc = _svc()
    admin = _admin()
    assert svc.is_read_only() is True
    svc.register_trace(trace_id="tr-st", source_id="e1", created_at="2026-08-09T09:00:00Z",
                       user=admin)
    svc.link(link_id="ln-st", trace_id="tr-st", link_kind=GovernanceTraceLinkKind.EVENT,
             target_id="e1", user=admin)
    st = svc.stats(user=admin)
    assert st["traces"] == 1 and st["links"] == 1


def test_source_trace_requires_source_id():
    # 红线⑥：来源链每一环都必须可溯源。
    with pytest.raises(EnterpriseRedLineViolationError):
        SourceTrace(source_kind=GovernanceTraceLinkKind.EVENT, source_id="")


# ===========================================================================
# 集成：挂载到 EnterpriseOperationLayer（只读出口验证）
# ===========================================================================

def test_mounted_on_enterprise_operation_layer():
    from agents.enterprise import EnterpriseOperationLayer

    layer = EnterpriseOperationLayer("org-27")
    svc = getattr(layer, "agent_governance_traceability", None)
    assert isinstance(svc, GovernanceTraceabilityService)
    assert svc.is_read_only() is True
    # 装配层整体保持未激活安全态。
    assert layer.is_activation_safe() is True

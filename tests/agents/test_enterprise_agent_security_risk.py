"""Enterprise Agent Security & Risk Governance Layer —— 测试（任务8，Phase 3.8.18）。

八类测试：security_event / risk_candidate / detector / report / review /
permission / audit / red_line。

最高红线（fail-closed，6 条，与主理人 Phase 3.8.18 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 AI 自动封禁 Agent（auto_disable_agent / block_agent / kill_agent 等被拦截；
   检测器只产出候选，绝不改变 Agent 可用状态）；
④ 禁止 AI 自动修改权限（auto_change_permission / auto_grant_permission /
   auto_revoke_permission 等被拦截；本层只读权限）；
⑤ 禁止 AI 自动处置安全风险（auto_resolve_risk / auto_fix_risk 等被拦截；
   requires_human_review 恒为 True；处置强制 require_human_actor(USER)）；
⑥ AI 不替代安全责任（audit 禁止 record_human_approval；事件/候选/报告只陈述事实；
   报告无来源链即拒绝生成）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_security_risk import (
    AgentRiskCandidate,
    AgentRiskReview,
    AgentRiskReviewStatus,
    AgentSecurityDetector,
    AgentSecurityEvent,
    AgentSecurityEventType,
    AgentSecurityReport,
    AgentSecurityRiskService,
    AgentSecuritySeverity,
    SourceTrace,
)
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.organization import EnterpriseIsolationError
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


def _svc(org_id: str = "org-1") -> AgentSecurityRiskService:
    return AgentSecurityRiskService(
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


def _reviewer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


def _event(
    event_id: str,
    agent_id: str = "a1",
    event_type: AgentSecurityEventType = AgentSecurityEventType.ACCESS,
    severity: AgentSecuritySeverity = AgentSecuritySeverity.INFO,
) -> AgentSecurityEvent:
    return AgentSecurityEvent(
        event_id=event_id,
        agent_id=agent_id,
        event_type=event_type,
        severity=severity,
        source=f"runtime_log:{event_id}",
        timestamp="2026-08-06T10:00:00",
    )


def _risk(risk_id: str = "r1", agent_id: str = "a1") -> AgentRiskCandidate:
    return AgentRiskCandidate(
        risk_id=risk_id,
        agent_id=agent_id,
        pattern="manual_pattern",
        evidence=["event:e1"],
        source="manual",
        detected_at="2026-08-06T10:00:00",
    )


# ===========================================================================
# 类别 1：AgentSecurityEvent（安全事件模型，只记录事实）
# ===========================================================================

def test_security_event_records_fact_only() -> None:
    e = _event("e1", severity=AgentSecuritySeverity.HIGH)
    assert e.event_type is AgentSecurityEventType.ACCESS
    assert e.severity is AgentSecuritySeverity.HIGH
    assert "agent=a1" in e.summary()
    # 只记录事实：模型层没有任何处置/封禁/权限修改方法（红线③/④/⑤）
    for forbidden in (
        "disable", "block", "kill", "resolve", "fix",
        "grant_permission", "revoke_permission",
    ):
        assert not hasattr(e, forbidden)


def test_security_event_without_source_rejected() -> None:
    # 红线⑥：禁止落库无源安全事实
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentSecurityEvent(event_id="e-bad", agent_id="a1", source="")


def test_security_event_enum_coercion() -> None:
    e = AgentSecurityEvent(
        event_id="e2", agent_id="a1",
        event_type="permission", severity="critical", source="log",
    )
    assert e.event_type is AgentSecurityEventType.PERMISSION
    assert e.severity is AgentSecuritySeverity.CRITICAL


# ===========================================================================
# 类别 2：AgentRiskCandidate（风险候选，强制人工复核）
# ===========================================================================

def test_risk_candidate_requires_human_review_forced_true() -> None:
    r = _risk()
    assert r.requires_human_review is True


def test_risk_candidate_reject_human_review_false() -> None:
    # 红线⑤：AI 不得自行免除人工复核
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRiskCandidate(
            risk_id="r-bad", agent_id="a1", pattern="p",
            evidence=["event:e1"], requires_human_review=False,
        )


def test_risk_candidate_requires_pattern_and_evidence() -> None:
    # 红线⑥：无模式描述 / 无证据的风险指控一律拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRiskCandidate(risk_id="r-a", agent_id="a1", pattern="", evidence=["e"])
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRiskCandidate(risk_id="r-b", agent_id="a1", pattern="p", evidence=[])


def test_risk_candidate_has_no_resolve_methods() -> None:
    r = _risk()
    # 红线⑤：模型层结构上无处置能力
    for forbidden in ("resolve", "fix", "dismiss", "close", "mitigate"):
        assert not hasattr(r, forbidden)


# ===========================================================================
# 类别 3：AgentSecurityDetector（只发现，不处理）
# ===========================================================================

def test_detector_access_anomaly_finds_candidate_only() -> None:
    d = AgentSecurityDetector(org_id="org-1")
    events = [_event(f"e{i}") for i in range(3)]
    found = d.detect_access_anomaly(
        agent_id="a1", events=events, threshold=3, detected_at="t"
    )
    assert len(found) == 1
    assert found[0].pattern == "access_frequency_over_threshold"
    # 只发现不处理：候选恒待人工复核，且检测器不返回任何处置结论
    assert found[0].requires_human_review is True


def test_detector_access_severe_event() -> None:
    d = AgentSecurityDetector(org_id="org-1")
    events = [_event("e1", severity=AgentSecuritySeverity.CRITICAL)]
    found = d.detect_access_anomaly(
        agent_id="a1", events=events, threshold=99, detected_at="t"
    )
    assert [c.pattern for c in found] == ["high_severity_access_event"]


def test_detector_permission_anomaly() -> None:
    d = AgentSecurityDetector(org_id="org-1")
    events = [
        _event("p1", event_type=AgentSecurityEventType.PERMISSION),
        _event("p2", event_type=AgentSecurityEventType.PERMISSION),
    ]
    found = d.detect_permission_anomaly(
        agent_id="a1", events=events, threshold=2, detected_at="t"
    )
    assert len(found) == 1
    assert found[0].pattern == "repeated_permission_anomaly"
    # 红线④：检测器绝不修改权限
    for forbidden in (
        "auto_change_permission", "auto_grant_permission", "auto_revoke_permission",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(d, forbidden)


def test_detector_execution_anomaly_and_critical() -> None:
    d = AgentSecurityDetector(org_id="org-1")
    events = [
        _event("x1", event_type=AgentSecurityEventType.EXECUTION),
        _event(
            "x2",
            event_type=AgentSecurityEventType.EXECUTION,
            severity=AgentSecuritySeverity.CRITICAL,
        ),
    ]
    found = d.detect_execution_anomaly(
        agent_id="a1", events=events, threshold=2, detected_at="t"
    )
    patterns = sorted(c.pattern for c in found)
    assert patterns == ["critical_execution_event", "repeated_execution_anomaly"]


def test_detector_no_input_no_fabrication() -> None:
    d = AgentSecurityDetector(org_id="org-1")
    # 不臆造风险：无 agent_id / 无事件 → 空
    assert d.detect_access_anomaly(agent_id="", events=[]) == []
    assert d.detect_permission_anomaly(agent_id="a1", events=[]) == []
    assert d.detect_execution_anomaly(agent_id="a1", events=[]) == []


# ===========================================================================
# 类别 4：AgentSecurityReport（事实 + 候选 + 来源链）
# ===========================================================================

def test_source_trace_traceable() -> None:
    t = SourceTrace(trace_id="t1", entries=["event:e1", "  ", ""])
    assert t.entries == ["event:e1"]
    assert t.is_traceable is True
    t.add_entry("   ")     # 空值不入链，不编造来源
    assert t.entries == ["event:e1"]
    assert t.render() == "event:e1"


def test_report_without_source_trace_rejected() -> None:
    # 红线⑥：无来源链的安全报告一律拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentSecurityReport(report_id="rep-bad", source_trace=None)
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentSecurityReport(
            report_id="rep-bad2", source_trace=SourceTrace(trace_id="t", entries=[])
        )


def test_service_generate_report_with_trace() -> None:
    s = _svc()
    s.record_security_event(event=_event("e1", severity=AgentSecuritySeverity.HIGH))
    s.record_security_event(event=_event("e2"))
    s.register_risk_candidate(risk=_risk("r1"))
    rep = s.generate_security_report(report_id="rep-1", agent_id="a1", generated_at="t")
    assert rep.source_trace is not None and rep.source_trace.is_traceable
    assert len(rep.events) == 2 and len(rep.risks) == 1
    assert rep.pending_human_review_count == 1
    assert rep.severity_breakdown() == {"high": 1, "info": 1}
    assert "pending_human_review=1" in rep.summary()


def test_service_generate_report_no_fact_rejected() -> None:
    s = _svc()
    # 无任何事实来源 → 拒绝生成（不编造报告）
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_security_report(report_id="rep-empty", agent_id="a-none")


# ===========================================================================
# 类别 5：AgentRiskReview（风险处置必须真实 USER）
# ===========================================================================

def test_review_construct_reviewed_rejected() -> None:
    # 红线⑤/⑥：构造期禁止直接落 reviewed
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRiskReview(
            review_id="rv-bad", risk_id="r1",
            status=AgentRiskReviewStatus.REVIEWED,
        )


def test_register_risk_creates_pending_review() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("r1"))
    reviews = s.list_risk_reviews(user=_admin())
    assert len(reviews) == 1
    assert reviews[0].status is AgentRiskReviewStatus.PENDING
    assert reviews[0].is_reviewed is False


def test_human_review_requires_real_user() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("r1"))
    # 红线⑤/⑥：AI / system / None 一律拒绝
    for kind in (AuditActorKind.AI, AuditActorKind.SYSTEM, None):
        with pytest.raises(EnterpriseRedLineViolationError):
            s.human_review_risk(
                risk_id="r1", actor_kind=kind, actor_id="ai", decision="ignore"
            )


def test_human_review_by_user_ok_and_terminal() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("r1"))
    rv = s.human_review_risk(
        risk_id="r1", actor_kind=AuditActorKind.USER, actor_id="expert-1",
        decision="确认为误报，已线下核实", reviewed_at="2026-08-06T12:00:00",
    )
    assert rv.status is AgentRiskReviewStatus.REVIEWED
    assert rv.reviewer_id == "expert-1"
    # 终态：不可重复处置
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_risk(
            risk_id="r1", actor_kind=AuditActorKind.USER, actor_id="expert-2",
            decision="再处置一次",
        )


def test_human_review_requires_actor_and_decision() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("r1"))
    # 红线⑥：人工责任可追溯 —— actor_id 与 decision 都不得为空
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_risk(
            risk_id="r1", actor_kind=AuditActorKind.USER, actor_id="", decision="d"
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_risk(
            risk_id="r1", actor_kind=AuditActorKind.USER, actor_id="u", decision="  "
        )


def test_human_review_unknown_risk_rejected() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_risk(
            risk_id="not-exist", actor_kind=AuditActorKind.USER,
            actor_id="u", decision="d",
        )


# ===========================================================================
# 类别 6：权限接入与安全数据隔离（默认拒绝）
# ===========================================================================

def test_list_security_data_permission_default_deny() -> None:
    s = _svc()
    s.record_security_event(event=_event("e1"))
    # REVIEWER 角色不在 data 资源作用域内 → 默认拒绝
    with pytest.raises(EnterpriseIsolationError):
        s.list_security_events(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_risk_candidates(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_risk_reviews(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_security_reports(user=_reviewer())


def test_list_security_data_admin_ok_and_org_scoped() -> None:
    s = _svc("org-1")
    s.record_security_event(event=_event("e1"))
    s.record_security_event(
        event=_event("e2", event_type=AgentSecurityEventType.EXECUTION)
    )
    assert len(s.list_security_events(user=_admin())) == 2
    assert len(
        s.list_security_events(
            user=_admin(), event_type=AgentSecurityEventType.EXECUTION
        )
    ) == 1
    # 组织隔离：另一组织的服务读不到本组织事实
    other = _svc("org-2")
    assert other.list_security_events(user=_admin("org-2")) == []


def test_service_reads_permission_but_never_writes() -> None:
    s = _svc()
    # 红线④：服务层结构上不具备任何写权限能力
    for forbidden in (
        "auto_change_permission", "change_permission",
        "auto_grant_permission", "grant_permission",
        "auto_revoke_permission", "revoke_permission",
        "escalate_permission", "elevate_permission",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(s, forbidden)


# ===========================================================================
# 类别 7：审计（3 类别，actor 真实）
# ===========================================================================

def test_audit_has_three_new_categories() -> None:
    """本层只对**自己新增的 3 类**负责；总数权威断言唯一保留在
    ``test_enterprise_knowledge_governance_audit.py``（Phase 3.8.31 Task 9）。
    """
    names = set(AuditActionCategory.__members__)
    assert {"AGENT_SECURITY_EVENT", "AGENT_RISK", "AGENT_RISK_REVIEW"} <= names


def test_audit_security_event_actor_is_ai() -> None:
    audit = _audit()
    s = AgentSecurityRiskService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    s.record_security_event(event=_event("e1"))
    recs = audit.query(category=AuditActionCategory.AGENT_SECURITY_EVENT)
    assert len(recs) == 1
    assert recs[0].actor_kind is AuditActorKind.AI


def test_audit_risk_and_review_actor_truthful() -> None:
    audit = _audit()
    s = AgentSecurityRiskService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    s.register_risk_candidate(risk=_risk("r1"))
    risk_recs = audit.query(category=AuditActionCategory.AGENT_RISK)
    assert len(risk_recs) == 1 and risk_recs[0].actor_kind is AuditActorKind.AI
    s.human_review_risk(
        risk_id="r1", actor_kind=AuditActorKind.USER, actor_id="expert-1",
        decision="已线下核实",
    )
    review_recs = audit.query(category=AuditActionCategory.AGENT_RISK_REVIEW)
    assert len(review_recs) == 1
    # 红线⑥：人工处置如实记为 USER，绝不伪造 human approval
    assert review_recs[0].actor_kind is AuditActorKind.USER
    assert review_recs[0].actor_id == "expert-1"


def test_audit_forbids_record_human_approval() -> None:
    audit = _audit()
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


def test_run_detection_writes_audit_and_registers() -> None:
    audit = _audit()
    s = AgentSecurityRiskService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    for i in range(3):
        s.record_security_event(event=_event(f"e{i}"))
    found = s.run_detection(agent_id="a1", detected_at="t")
    assert len(found) == 1
    assert all(c.requires_human_review for c in found)
    assert len(audit.query(category=AuditActionCategory.AGENT_RISK)) == 1
    # 检测产出的候选一并生成 pending 复核单（等待真实人工）
    reviews = s.list_risk_reviews(user=_admin(), status=AgentRiskReviewStatus.PENDING)
    assert len(reviews) == 1


# ===========================================================================
# 类别 8：红线（6 条 fail-closed）
# ===========================================================================

def test_red_line_1_engineering_enabled_stays_false() -> None:
    assert safety_invariants_ok() is True


def test_red_line_1_enabled_state_blocks_construction(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentSecurityRiskService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentSecurityDetector(org_id="org-1")


def test_red_line_1_enabled_state_blocks_writes(monkeypatch) -> None:
    s = _svc()
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.record_security_event(event=_event("e-x"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.run_detection(agent_id="a1")
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_security_report(report_id="rep-x")


def test_red_line_2_no_engineering_approved() -> None:
    s = _svc()
    d = AgentSecurityDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in ("approve", "engineering_approved", "sign", "authorize"):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_3_no_auto_disable_agent() -> None:
    s = _svc()
    d = AgentSecurityDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_disable_agent", "disable_agent", "block_agent", "auto_block_agent",
            "kill_agent", "auto_kill_agent", "ban_agent", "suspend_agent",
            "terminate_agent", "shutdown_agent", "quarantine_agent",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_4_no_auto_permission_change() -> None:
    s = _svc()
    d = AgentSecurityDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_change_permission", "auto_grant_permission",
            "auto_revoke_permission", "modify_permission", "update_permission",
            "reset_permission",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_5_no_auto_risk_resolution() -> None:
    s = _svc()
    d = AgentSecurityDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_resolve_risk", "resolve_risk", "auto_fix_risk", "fix_risk",
            "auto_mitigate_risk", "auto_close_risk", "auto_dismiss_risk",
            "auto_remediate", "handle_incident",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_6_no_ai_security_responsibility() -> None:
    s = _svc()
    for forbidden in (
        "record_human_approval", "auto_secure", "take_security_ownership",
        "act_as_security_officer", "assume_security_responsibility",
        "auto_govern_security", "quote", "pricing",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(s, forbidden)


def test_red_line_service_layer_rejects_non_human_review_candidate() -> None:
    s = _svc()

    class _Fake:
        risk_id = "r-fake"
        agent_id = "a1"
        requires_human_review = False
        org_id = ""
        detected_at = ""

        def summary(self) -> str:  # pragma: no cover - 不应被调用
            return ""

    with pytest.raises(EnterpriseRedLineViolationError):
        s.register_risk_candidate(risk=_Fake())  # type: ignore[arg-type]


def test_enterprise_layer_wires_security_service() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_security_risk, AgentSecurityRiskService)
    # 共享同一审计实例（安全事实与其他企业动作同源可查）
    assert layer.agent_security_risk._audit is layer.audit
    assert layer.agent_security_risk._identity is layer.identity
    assert (
        layer.agent_security_risk._permission_policy is layer.agent_permission_policy
    )
    assert layer.is_activation_safe() is True

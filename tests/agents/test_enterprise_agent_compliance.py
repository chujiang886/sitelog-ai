"""Enterprise Agent Compliance & Audit Intelligence Layer —— 测试（任务9，Phase 3.8.19）。

九类测试：rule / check / detector / risk_candidate / report / review /
audit / permission / red_line。

最高红线（fail-closed，6 条，与主理人 Phase 3.8.19 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动判定违法/违规（auto_violate / auto_penalty / auto_judge_compliance
   等被拦截；ComplianceCheckResult 刻意无任何判罚态）；
④ 禁止 AI 自动处罚 Agent（auto_suspend_agent / auto_ban_agent 等被拦截；
   requires_human_review 恒为 True；整改强制 require_human_actor(USER)）；
⑤ 禁止 AI 自动修改权限或策略（auto_change_permission / auto_modify_policy /
   activate_rule 等被拦截；规则生效/废止强制真实 USER）；
⑥ AI 不代替合规责任人（audit 禁止 record_human_approval；规则须有 source；
   检查须有 evidence；报告无来源链即拒绝生成；decision 必须人工填写）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_compliance import (
    AgentComplianceDetector,
    AgentComplianceReport,
    AgentComplianceService,
    ComplianceCheck,
    ComplianceCheckResult,
    ComplianceReview,
    ComplianceReviewStatus,
    ComplianceRiskCandidate,
    ComplianceRule,
    ComplianceRuleScope,
    ComplianceRuleStatus,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_runtime_policy import (
    RuntimeCheckOutcome,
    RuntimeDecisionRecord,
)
from agents.enterprise.agent_security_risk import SourceTrace
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


def _svc(org_id: str = "org-1") -> AgentComplianceService:
    return AgentComplianceService(
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


def _rule(
    rule_id: str = "cr1",
    scope: ComplianceRuleScope = ComplianceRuleScope.AUDIT,
    keywords: list[str] | None = None,
) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        name="留痕完备性规则",
        description="Agent 行为须留痕可溯源",
        scope=scope,
        source="企业制度:BOIP-COMP-001",
        keywords=list(keywords or []),
        created_at="2026-08-06T10:00:00",
    )


def _check(
    check_id: str = "cc1",
    agent_id: str = "a1",
    rule_id: str = "cr1",
    result: ComplianceCheckResult = ComplianceCheckResult.PASS,
) -> ComplianceCheck:
    return ComplianceCheck(
        check_id=check_id,
        agent_id=agent_id,
        rule_id=rule_id,
        result=result,
        evidence=[f"audit:{check_id}"],
        timestamp="2026-08-06T10:00:00",
    )


def _risk(risk_id: str = "cx1", agent_id: str = "a1") -> ComplianceRiskCandidate:
    return ComplianceRiskCandidate(
        risk_id=risk_id,
        agent_id=agent_id,
        pattern="manual_pattern",
        evidence=["audit:e1"],
        rule_id="cr1",
        detected_at="2026-08-06T10:00:00",
        source="manual",
    )


def _registered(org_id: str = "org-1", audit: AuditService | None = None):
    """服务 + 已由真实人工确认生效的规则（便于检测类测试复用）。"""
    a = audit or _audit(org_id)
    s = AgentComplianceService(
        org_id=org_id, audit=a, identity=_identity(org_id),
        permission_policy=_policy(org_id),
    )
    s.register_compliance_rule(rule=_rule(keywords=["export_data"]))
    s.confirm_rule_active(
        rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="officer-1",
        confirmed_at="2026-08-06T10:05:00",
    )
    return s, a


class _FakeAuditRecord:
    """最小审计事实替身（只带检测器读取的字段）。"""

    def __init__(self, record_id: str, action: str, target: str, category: str = "agent_runtime"):
        self.record_id = record_id
        self.action = action
        self.target = target
        self.actor_id = "ai"
        self.category = category


def _runtime_record(record_id: str, agent_id: str = "a1", passed: bool = False):
    outcome = RuntimeCheckOutcome.PASS if passed else RuntimeCheckOutcome.FAIL
    return RuntimeDecisionRecord(
        record_id=record_id,
        agent_id=agent_id,
        policy_result=outcome,
        permission_result=outcome,
        scope_result=outcome,
        tool_result=outcome,
        timestamp="2026-08-06T10:00:00",
        source=f"runtime_log:{record_id}",
    )


# ===========================================================================
# 类别 1：ComplianceRule（规则来源可追溯，生效须人工）
# ===========================================================================

def test_rule_requires_traceable_source() -> None:
    # 红线⑥：无 source 即拒绝落库，AI 不得凭空编造合规规则
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRule(rule_id="cr-x", name="无源规则", source="")


def test_rule_requires_name() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRule(rule_id="cr-x", name="", source="制度:X")


def test_rule_defaults_to_draft_and_not_effective() -> None:
    r = _rule()
    assert r.status is ComplianceRuleStatus.DRAFT
    assert r.is_effective is False


def test_rule_construct_active_is_forbidden() -> None:
    # 红线⑤：AI 不得在构造期直接落 active
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRule(
            rule_id="cr-x", name="N", source="制度:X",
            status=ComplianceRuleStatus.ACTIVE,
        )


def test_rule_keyword_match_is_explicit_only() -> None:
    r = _rule(keywords=["export_data", " "])
    # 空白关键词被清洗，不新增、不推断
    assert r.keywords == ["export_data"]
    assert r.matches_keyword("agent export_data batch") is True
    assert r.matches_keyword("agent read") is False
    assert r.matches_keyword("") is False


def test_rule_summary_has_no_verdict_semantics() -> None:
    text = _rule().summary()
    assert "rule=cr1" in text and "status=draft" in text
    for bad in ("violation", "illegal", "penalty", "approved"):
        assert bad not in text


def test_register_rule_rejects_active_input() -> None:
    s = _svc()
    r = _rule()
    r.status = ComplianceRuleStatus.ACTIVE  # 绕过构造期后仍被服务层拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        s.register_compliance_rule(rule=r)


def test_confirm_rule_active_requires_real_user() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    # 红线⑤/⑥：AI / system / None 一律拒绝
    for kind in (AuditActorKind.AI, AuditActorKind.SYSTEM, None):
        with pytest.raises(EnterpriseRedLineViolationError):
            s.confirm_rule_active(
                rule_id="cr1", actor_kind=kind, actor_id="ai"
            )
    rule = s.confirm_rule_active(
        rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="officer-1",
        confirmed_at="t1",
    )
    assert rule.status is ComplianceRuleStatus.ACTIVE
    assert rule.confirmed_by == "officer-1" and rule.confirmed_at == "t1"


def test_confirm_rule_active_requires_actor_id_and_existing_rule() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_active(
            rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="  "
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_active(
            rule_id="nope", actor_kind=AuditActorKind.USER, actor_id="officer-1"
        )


def test_confirm_rule_deprecated_requires_real_user_and_is_terminal() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_deprecated(
            rule_id="cr1", actor_kind=AuditActorKind.AI, actor_id="ai"
        )
    r = s.confirm_rule_deprecated(
        rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="officer-1"
    )
    assert r.status is ComplianceRuleStatus.DEPRECATED
    # 已废止不可再生效
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_active(
            rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="officer-1"
        )


# ===========================================================================
# 类别 2：ComplianceCheck（只记录检查事实，无判罚态）
# ===========================================================================

def test_check_result_enum_has_no_verdict_value() -> None:
    # 红线③：枚举刻意不含 violation / illegal / fail 等判罚态
    values = {m.value for m in ComplianceCheckResult}
    assert values == {"pass", "attention", "not_applicable"}
    for bad in ("violation", "illegal", "fail", "penalty", "guilty"):
        assert bad not in values


def test_check_requires_evidence() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceCheck(check_id="cc-x", agent_id="a1", rule_id="cr1", evidence=[])


def test_check_requires_rule_binding() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceCheck(
            check_id="cc-x", agent_id="a1", rule_id="", evidence=["audit:1"]
        )


def test_check_attention_is_not_a_violation_conclusion() -> None:
    c = _check(result=ComplianceCheckResult.ATTENTION)
    assert c.needs_attention is True
    text = c.summary()
    assert "result=attention" in text
    for bad in ("violation", "illegal", "penalty", "approved"):
        assert bad not in text


def test_record_check_rejects_unregistered_rule() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.record_compliance_check(check=_check(rule_id="ghost-rule"))


def test_record_check_persists_fact_with_org_scope() -> None:
    s = _svc("org-1")
    s.register_compliance_rule(rule=_rule())
    out = s.record_compliance_check(check=_check())
    assert out.org_id == "org-1"
    assert len(s.list_compliance_checks(user=_admin())) == 1


# ===========================================================================
# 类别 3：AgentComplianceDetector（只发现候选，不判罚）
# ===========================================================================

def test_detector_returns_empty_on_missing_facts() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    r = _rule()
    assert d.check_audit_pattern(agent_id="", rule=r, audit_records=[]) == []
    assert d.check_permission_pattern(agent_id="a1", rule=r, audit_records=[]) == []
    assert d.check_runtime_pattern(agent_id="a1", rule=r, decision_records=[]) == []


def test_detector_audit_frequency_candidate() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    records = [_FakeAuditRecord(f"r{i}", "read", "a1") for i in range(3)]
    found = d.check_audit_pattern(
        agent_id="a1", rule=_rule(), audit_records=records, threshold=3
    )
    assert len(found) == 1
    assert found[0].pattern == "audit_activity_over_threshold"
    assert found[0].requires_human_review is True


def test_detector_audit_keyword_candidate() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    records = [_FakeAuditRecord("r1", "export_data", "a1")]
    found = d.check_audit_pattern(
        agent_id="a1", rule=_rule(keywords=["export_data"]),
        audit_records=records, threshold=99,
    )
    assert len(found) == 1
    assert found[0].pattern == "audit_action_keyword_hit"


def test_detector_permission_pattern_reads_only() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    records = [
        _FakeAuditRecord(f"p{i}", "check", "a1", category="agent_permission")
        for i in range(2)
    ]
    found = d.check_permission_pattern(
        agent_id="a1", rule=_rule(scope=ComplianceRuleScope.PERMISSION),
        audit_records=records, threshold=2,
    )
    assert len(found) == 1
    assert found[0].pattern == "repeated_permission_audit_pattern"
    # 红线⑤：检测器结构上不具备任何写权限能力
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(d, "auto_change_permission")


def test_detector_runtime_pattern_consumes_existing_facts_only() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    facts = [_runtime_record("d1"), _runtime_record("d2")]
    found = d.check_runtime_pattern(
        agent_id="a1", rule=_rule(scope=ComplianceRuleScope.RUNTIME),
        decision_records=facts, threshold=2,
    )
    assert len(found) == 1
    assert found[0].pattern == "runtime_check_not_passed_pattern"
    # 全通过的记录不产生候选（不臆造合规风险）
    ok = [_runtime_record("d3", passed=True), _runtime_record("d4", passed=True)]
    assert d.check_runtime_pattern(
        agent_id="a1", rule=_rule(), decision_records=ok, threshold=2
    ) == []


def test_detector_below_threshold_no_candidate() -> None:
    d = AgentComplianceDetector(org_id="org-1")
    assert d.check_runtime_pattern(
        agent_id="a1", rule=_rule(), decision_records=[_runtime_record("d1")],
        threshold=2,
    ) == []


def test_run_detection_requires_active_rule() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    # 红线⑤：未经人工确认生效的规则不产生任何效力
    with pytest.raises(EnterpriseRedLineViolationError):
        s.run_compliance_detection(agent_id="a1", rule_id="cr1")
    with pytest.raises(EnterpriseRedLineViolationError):
        s.run_compliance_detection(agent_id="a1", rule_id="ghost")


def test_run_detection_registers_candidates_and_pending_review() -> None:
    s, audit = _registered()
    records = [_FakeAuditRecord(f"r{i}", "export_data", "a1") for i in range(3)]
    found = s.run_compliance_detection(
        agent_id="a1", rule_id="cr1", audit_records=records, detected_at="t",
    )
    assert len(found) == 2  # 频度候选 + 关键词候选
    assert all(c.requires_human_review for c in found)
    reviews = s.list_compliance_reviews(
        user=_admin(), status=ComplianceReviewStatus.PENDING
    )
    assert len(reviews) == 2
    assert len(audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_RISK)) == 2


# ===========================================================================
# 类别 4：ComplianceRiskCandidate（强制人工复核）
# ===========================================================================

def test_risk_candidate_requires_human_review_always_true() -> None:
    # 红线④：AI 不得自行免除人工复核
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRiskCandidate(
            risk_id="cx-x", agent_id="a1", pattern="p",
            evidence=["e"], requires_human_review=False,
        )
    assert _risk().requires_human_review is True


def test_risk_candidate_requires_pattern_and_evidence() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRiskCandidate(
            risk_id="cx-x", agent_id="a1", pattern="", evidence=["e"]
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceRiskCandidate(
            risk_id="cx-x", agent_id="a1", pattern="p", evidence=[]
        )


def test_risk_candidate_summary_is_not_a_verdict() -> None:
    text = _risk().summary()
    assert "requires_human_review=True" in text
    for bad in ("violation", "illegal", "penalty", "banned", "approved"):
        assert bad not in text


def test_register_risk_creates_pending_review() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("cx1"))
    reviews = s.list_compliance_reviews(user=_admin())
    assert len(reviews) == 1
    assert reviews[0].status is ComplianceReviewStatus.PENDING
    assert reviews[0].is_reviewed is False


def test_register_risk_rejects_review_waiver() -> None:
    s = _svc()
    r = _risk("cx1")
    r.requires_human_review = False  # 绕过构造期后仍被服务层拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        s.register_risk_candidate(risk=r)


# ===========================================================================
# 类别 5：AgentComplianceReport（只汇总事实 + 强可溯源）
# ===========================================================================

def test_report_requires_source_trace() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentComplianceReport(report_id="rep-x", source_trace=None)
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentComplianceReport(
            report_id="rep-x", source_trace=SourceTrace(trace_id="t-x")
        )


def test_generate_report_rejects_empty_facts() -> None:
    s = _svc()
    # 红线⑥：无任何事实来源 → 拒绝生成
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_compliance_report(report_id="rep-1")


def test_generate_report_aggregates_facts_only() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    s.record_compliance_check(check=_check("cc1"))
    s.record_compliance_check(
        check=_check("cc2", result=ComplianceCheckResult.ATTENTION)
    )
    s.register_risk_candidate(risk=_risk("cx1"))
    rep = s.generate_compliance_report(report_id="rep-1", generated_at="t")
    assert len(rep.checks) == 2 and len(rep.risks) == 1
    assert rep.attention_count == 1
    assert rep.pending_human_review_count == 1
    assert rep.result_breakdown() == {"pass": 1, "attention": 1}
    assert rep.source_trace is not None and rep.source_trace.is_traceable


def test_report_summary_contains_no_penalty_or_approval() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    s.record_compliance_check(check=_check("cc1"))
    text = s.generate_compliance_report(report_id="rep-1").summary()
    assert "report=rep-1" in text and "pending_human_review=" in text
    for bad in (
        "violation", "illegal", "penalty", "suspend", "ban",
        "approved", "engineering_approved",
    ):
        assert bad not in text


def test_report_filtered_by_agent() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    s.record_compliance_check(check=_check("cc1", agent_id="a1"))
    s.record_compliance_check(check=_check("cc2", agent_id="a2"))
    rep = s.generate_compliance_report(report_id="rep-a1", agent_id="a1")
    assert [c.check_id for c in rep.checks] == ["cc1"]


# ===========================================================================
# 类别 6：ComplianceReview（人工整改，必须真实 USER）
# ===========================================================================

def test_review_construct_reviewed_is_forbidden() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ComplianceReview(
            review_id="cv-x", risk_id="cx1",
            status=ComplianceReviewStatus.REVIEWED,
        )


def test_human_review_requires_real_user() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("cx1"))
    # 红线④/⑥：AI / system / None 一律拒绝
    for kind in (AuditActorKind.AI, AuditActorKind.SYSTEM, None):
        with pytest.raises(EnterpriseRedLineViolationError):
            s.human_review_compliance_risk(
                risk_id="cx1", actor_kind=kind, actor_id="ai", decision="d"
            )


def test_human_review_requires_actor_id_and_decision() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("cx1"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_compliance_risk(
            risk_id="cx1", actor_kind=AuditActorKind.USER,
            actor_id=" ", decision="d",
        )
    # 红线⑥：AI 不得代填整改结论
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_compliance_risk(
            risk_id="cx1", actor_kind=AuditActorKind.USER,
            actor_id="officer-1", decision="   ",
        )


def test_human_review_success_and_terminal() -> None:
    s = _svc()
    s.register_risk_candidate(risk=_risk("cx1"))
    review = s.human_review_compliance_risk(
        risk_id="cx1", actor_kind=AuditActorKind.USER, actor_id="officer-1",
        decision="已线下核实，无需整改", reviewed_at="t2",
    )
    assert review.is_reviewed is True
    assert review.reviewer_id == "officer-1"
    assert review.decision == "已线下核实，无需整改"
    # 终态不可重复处置
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_compliance_risk(
            risk_id="cx1", actor_kind=AuditActorKind.USER,
            actor_id="officer-2", decision="重复",
        )


def test_human_review_rejects_unknown_risk() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_compliance_risk(
            risk_id="ghost", actor_kind=AuditActorKind.USER,
            actor_id="officer-1", decision="d",
        )


# ===========================================================================
# 类别 7：审计（3 新类别，累计 50，actor 真实）
# ===========================================================================

def test_audit_has_three_new_categories() -> None:
    """本层只对**自己新增的 3 类**负责；总数权威断言唯一保留在
    ``test_enterprise_knowledge_governance_audit.py``（Phase 3.8.31 Task 9）。
    """
    names = set(AuditActionCategory.__members__)
    assert {
        "AGENT_COMPLIANCE_RULE",
        "AGENT_COMPLIANCE_CHECK",
        "AGENT_COMPLIANCE_RISK",
    } <= names


def test_audit_rule_register_actor_is_ai_confirm_is_user() -> None:
    audit = _audit()
    s = AgentComplianceService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    s.register_compliance_rule(rule=_rule())
    recs = audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_RULE)
    assert len(recs) == 1 and recs[0].actor_kind is AuditActorKind.AI
    s.confirm_rule_active(
        rule_id="cr1", actor_kind=AuditActorKind.USER, actor_id="officer-1"
    )
    recs = audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_RULE)
    assert len(recs) == 2
    assert recs[1].actor_kind is AuditActorKind.USER
    assert recs[1].actor_id == "officer-1"


def test_audit_check_category_records_ai_actor() -> None:
    audit = _audit()
    s = AgentComplianceService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    s.register_compliance_rule(rule=_rule())
    s.record_compliance_check(check=_check())
    recs = audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_CHECK)
    assert len(recs) == 1 and recs[0].actor_kind is AuditActorKind.AI


def test_audit_risk_and_review_actor_truthful() -> None:
    audit = _audit()
    s = AgentComplianceService(
        org_id="org-1", audit=audit, identity=_identity(),
        permission_policy=_policy(),
    )
    s.register_risk_candidate(risk=_risk("cx1"))
    recs = audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_RISK)
    assert len(recs) == 1 and recs[0].actor_kind is AuditActorKind.AI
    s.human_review_compliance_risk(
        risk_id="cx1", actor_kind=AuditActorKind.USER, actor_id="officer-1",
        decision="已线下核实",
    )
    recs = audit.query(category=AuditActionCategory.AGENT_COMPLIANCE_RISK)
    # 红线⑥：人工处置如实记为 USER，绝不伪造 human approval
    assert recs[-1].actor_kind is AuditActorKind.USER
    assert recs[-1].actor_id == "officer-1"


def test_audit_forbids_record_human_approval() -> None:
    audit = _audit()
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


# ===========================================================================
# 类别 8：权限接入与合规数据隔离（默认拒绝）
# ===========================================================================

def test_list_compliance_data_permission_default_deny() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    # REVIEWER 角色不在 data 资源作用域内 → 默认拒绝
    with pytest.raises(EnterpriseIsolationError):
        s.list_compliance_rules(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_compliance_checks(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_risk_candidates(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_compliance_reviews(user=_reviewer())
    with pytest.raises(EnterpriseIsolationError):
        s.list_compliance_reports(user=_reviewer())


def test_list_compliance_data_admin_ok_and_org_scoped() -> None:
    s = _svc("org-1")
    s.register_compliance_rule(rule=_rule("cr1"))
    s.register_compliance_rule(
        rule=_rule("cr2", scope=ComplianceRuleScope.RUNTIME)
    )
    assert len(s.list_compliance_rules(user=_admin())) == 2
    assert len(
        s.list_compliance_rules(user=_admin(), scope=ComplianceRuleScope.RUNTIME)
    ) == 1
    assert len(
        s.list_compliance_rules(user=_admin(), status=ComplianceRuleStatus.DRAFT)
    ) == 2
    # 组织隔离：另一组织的服务读不到本组织事实
    other = _svc("org-2")
    assert other.list_compliance_rules(user=_admin("org-2")) == []


def test_list_checks_filter_by_agent_and_result() -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    s.record_compliance_check(check=_check("cc1", agent_id="a1"))
    s.record_compliance_check(
        check=_check("cc2", agent_id="a2", result=ComplianceCheckResult.ATTENTION)
    )
    assert len(s.list_compliance_checks(user=_admin(), agent_id="a1")) == 1
    assert len(
        s.list_compliance_checks(
            user=_admin(), result=ComplianceCheckResult.ATTENTION
        )
    ) == 1


def test_service_reads_permission_but_never_writes() -> None:
    s = _svc()
    # 红线⑤：服务层结构上不具备任何写权限/改策略能力
    for forbidden in (
        "auto_change_permission", "change_permission",
        "auto_grant_permission", "grant_permission",
        "auto_revoke_permission", "revoke_permission",
        "auto_modify_policy", "modify_policy",
        "auto_activate_rule", "activate_rule",
        "auto_update_rule", "update_rule",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(s, forbidden)


def test_enterprise_layer_wires_compliance_service() -> None:
    layer = EnterpriseOperationLayer("org-1")
    assert isinstance(layer.agent_compliance, AgentComplianceService)
    # 共享审计与运行时事实源（只读消费 Phase 3.8.17）
    assert layer.agent_compliance._audit is layer.audit
    assert layer.agent_compliance._runtime_policy is layer.agent_runtime_governance


# ===========================================================================
# 类别 9：红线（6 条 fail-closed）
# ===========================================================================

def test_red_line_1_engineering_enabled_stays_false() -> None:
    assert safety_invariants_ok() is True


def test_red_line_1_enabled_state_blocks_construction(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentComplianceService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentComplianceDetector(org_id="org-1")


def test_red_line_1_enabled_state_blocks_writes(monkeypatch) -> None:
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.register_compliance_rule(rule=_rule("cr-x"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.record_compliance_check(check=_check("cc-x"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.register_risk_candidate(risk=_risk("cx-x"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.run_compliance_detection(agent_id="a1", rule_id="cr1")
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_compliance_report(report_id="rep-x")


def test_red_line_2_no_engineering_approved() -> None:
    s = _svc()
    d = AgentComplianceDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "approve", "engineering_approved", "quote", "pricing",
            "sign", "authorize", "record_human_approval",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_3_no_auto_violation_judgement() -> None:
    s = _svc()
    d = AgentComplianceDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_violate", "violate", "auto_penalty", "penalty",
            "auto_judge_compliance", "judge_compliance", "auto_judge",
            "judge_violation", "auto_determine_violation", "determine_violation",
            "declare_violation", "auto_declare_illegal", "declare_illegal",
            "judge_illegal", "auto_fine", "fine_agent", "auto_sanction",
            "sanction_agent", "auto_convict", "convict",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_4_no_auto_agent_penalty() -> None:
    s = _svc()
    d = AgentComplianceDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_suspend_agent", "suspend_agent", "auto_ban_agent", "ban_agent",
            "auto_punish_agent", "punish_agent", "auto_disable_agent",
            "disable_agent", "auto_block_agent", "block_agent",
            "auto_terminate_agent", "terminate_agent", "auto_quarantine_agent",
            "quarantine_agent", "auto_revoke_agent", "revoke_agent",
            "auto_kill_agent", "kill_agent",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_5_no_auto_permission_or_policy_change() -> None:
    s = _svc()
    d = AgentComplianceDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_change_permission", "auto_grant_permission",
            "auto_revoke_permission", "auto_modify_permission",
            "modify_permission", "auto_escalate_permission",
            "escalate_permission", "auto_modify_policy", "auto_update_policy",
            "update_policy", "auto_apply_policy", "apply_policy",
            "auto_activate_rule", "activate_rule", "auto_change_rule",
            "change_rule",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_6_no_ai_as_compliance_officer() -> None:
    s = _svc()
    d = AgentComplianceDetector(org_id="org-1")
    for target in (s, d):
        for forbidden in (
            "auto_certify_compliance", "certify_compliance", "auto_attest",
            "attest_compliance", "auto_clear_compliance", "clear_compliance",
            "act_as_compliance_officer", "take_compliance_ownership",
            "assume_compliance_responsibility", "auto_govern_compliance",
            "auto_sign_compliance",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_6_human_nodes_are_mandatory() -> None:
    """三个人工节点（规则生效 / 规则废止 / 风险整改）均强制真实 USER。"""
    s = _svc()
    s.register_compliance_rule(rule=_rule())
    s.register_risk_candidate(risk=_risk("cx1"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_active(
            rule_id="cr1", actor_kind=AuditActorKind.AI, actor_id="ai"
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.confirm_rule_deprecated(
            rule_id="cr1", actor_kind=AuditActorKind.AI, actor_id="ai"
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_review_compliance_risk(
            risk_id="cx1", actor_kind=AuditActorKind.AI,
            actor_id="ai", decision="d",
        )

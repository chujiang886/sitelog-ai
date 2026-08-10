"""Enterprise Agent Evaluation & Quality Governance Layer —— 测试（任务8，Phase 3.8.15）。

八类测试：quality_metric / evaluation / version_comparison / feedback / report /
permission / audit / red_line。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 AI 自动评级 Agent（auto_rate_agent / auto_grade_agent / auto_score_agent 等被
   拦截；AgentQualityMetric 只记事实，无 verdict/score/rating 字段）；
④ 禁止 AI 自动禁用/弃用 Agent（disable_agent / auto_deprecate_agent 等被拦截）；
⑤ 禁止 AI 自动修改 Agent（modify_agent / auto_update_agent 等被拦截）；
⑥ AI 不替代人工责任（AgentEvaluation 评价者须为真实 USER；AgentFeedback 强制人工审核；
   版本比较不自动决定升级；审计报告不承载 human approval）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_quality_governance import (
    AgentEvaluation,
    AgentFeedback,
    AgentQualityGovernanceService,
    AgentQualityMetric,
    AgentQualityMetricType,
    AgentQualityReport,
    AgentVersionComparison,
)
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.data_insight import SourceTrace
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
    """确保测试全程 engineering_enabled=false（红线①/⑤），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _svc(org_id: str = "org-1") -> AgentQualityGovernanceService:
    return AgentQualityGovernanceService(
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


# ===========================================================================
# 类别 1：AgentQualityMetric（事实型，只记录，禁评分）
# ===========================================================================

def test_quality_metric_negative_value_clamped_to_zero() -> None:
    neg = AgentQualityMetric(
        metric_id="qm1", agent_id="a1",
        metric_type=AgentQualityMetricType.TASK_COUNT, value=-3.0,
    )
    # 仅范围约束，不评价：负值裁剪为 0
    assert neg.value == 0.0


def test_quality_metric_type_enum_coercion() -> None:
    m = AgentQualityMetric(
        metric_id="qm2", agent_id="a1",
        metric_type="feedback_negative", value=2.0,
    )
    # 字符串归一为枚举
    assert m.metric_type is AgentQualityMetricType.FEEDBACK_NEGATIVE


def test_quality_metric_has_no_evaluation_fields() -> None:
    m = AgentQualityMetric(
        metric_id="qm3", agent_id="a1",
        metric_type=AgentQualityMetricType.SUCCESS_COUNT, value=5.0,
    )
    # 红线③/⑥：结构上禁评，不得携带任何 verdict/score/rating/grade 语义
    for bad in ("verdict", "score", "rating", "grade", "quality", "level"):
        assert not hasattr(m, bad), f"AgentQualityMetric 不应含评价字段 {bad}"


def test_quality_metric_recorded_and_listable() -> None:
    svc = _svc("org-1")
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm4", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=10.0,
            period="2026-08", source="execution_log",
        )
    )
    out = svc.list_quality_metrics(user=_admin())
    assert len(out) == 1 and out[0].metric_id == "qm4"
    # 登记即归属当前组织
    assert out[0].org_id == "org-1"


# ===========================================================================
# 类别 2：AgentEvaluation（人工评价，禁 AI 作最终评价者）
# ===========================================================================

def test_evaluation_ai_as_evaluator_rejected() -> None:
    # 红线⑥：AI/系统不得作为评价者（数据层拦截）
    for bad in ("ai", "system", ""):
        with pytest.raises(EnterpriseRedLineViolationError):
            AgentEvaluation(
                evaluation_id="ev1", agent_id="a1", evaluator=bad,
            )


def test_evaluation_user_submit_requires_human_actor() -> None:
    svc = _svc("org-1")
    ev = AgentEvaluation(
        evaluation_id="ev2", agent_id="a1", evaluator="user-1",
        criteria="准确性", comment="回答基本可用",
    )
    # actor_kind 默认 USER → 通过 require_human_actor
    svc.submit_evaluation(evaluation=ev)
    assert svc.list_evaluations(user=_admin())[0].evaluation_id == "ev2"


def test_evaluation_submit_rejects_ai_actor() -> None:
    svc = _svc("org-1")
    ev = AgentEvaluation(
        evaluation_id="ev3", agent_id="a1", evaluator="user-1",
    )
    # 红线⑥：actor_kind=AI 不应通过 human-gating
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.submit_evaluation(evaluation=ev, actor_kind=AuditActorKind.AI)


# ===========================================================================
# 类别 3：AgentVersionComparison（仅比较，禁自动决定升级）
# ===========================================================================

def test_version_comparison_requires_traceable_source() -> None:
    # 无 source_trace → 红线违例（禁 AI 创造无源比较）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentVersionComparison(comparison_id="vc1", agent_id="a1")
    # source_trace 不可追溯 → 同样违例
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentVersionComparison(
            comparison_id="vc2", agent_id="a1",
            source_trace=SourceTrace(raw_refs=[]),
        )


def test_compare_versions_only_computes_facts() -> None:
    svc = _svc("org-1")
    comp = svc.compare_versions(
        comparison_id="vc3", agent_id="a1",
        version_facts={
            "v1": {"call_count": 100, "success_rate": 0.8, "duration": 1.2},
            "v2": {"call_count": 150, "success_rate": 0.9, "duration": 1.0},
        },
        created_at="2026-08-01",
    )
    assert comp.source_trace is not None and comp.source_trace.is_traceable
    assert comp.versions == ["v1", "v2"]
    # 仅算出 delta 事实：call_count +50，success_rate +0.1，duration -0.2
    assert any("call_count_delta=50" in c for c in comp.changes)
    assert any("success_rate_delta=0.1" in c for c in comp.changes)
    assert any("duration_delta=-0.2" in c for c in comp.changes)


def test_compare_versions_requires_facts() -> None:
    svc = _svc("org-1")
    # 禁 AI 创造空的无源比较
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.compare_versions(comparison_id="vc4", agent_id="a1", version_facts={})


def test_version_comparison_service_has_no_upgrade_methods() -> None:
    svc = _svc("org-1")
    # 红线③/⑥：比较服务不得提供任何自动升级/降级入口；访问即触发红线拦截
    for meth in (
        "auto_upgrade", "recommend_upgrade", "decide_upgrade", "promote_version",
        "auto_promote", "make_management_decision", "recommend", "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)


# ===========================================================================
# 类别 4：AgentFeedback（用户反馈，须人工审核）
# ===========================================================================

def test_feedback_requires_human_review_always_true() -> None:
    fb = AgentFeedback(
        feedback_id="fb1", agent_id="a1", user_id="user-1", content="建议增加导出",
    )
    assert fb.requires_human_review is True
    # 即便传入 False，__post_init__ 也强制为 True（红线③/⑥：AI 不代责审核）
    fb2 = AgentFeedback(
        feedback_id="fb2", agent_id="a1", user_id="user-2", content="x",
        requires_human_review=False,
    )
    assert fb2.requires_human_review is True


def test_feedback_submit_and_human_review() -> None:
    svc = _svc("org-1")
    svc.submit_feedback(
        feedback=AgentFeedback(
            feedback_id="fb3", agent_id="a1", user_id="user-1", content="很好用",
        )
    )
    fb = svc.review_feedback(
        feedback_id="fb3", reviewer="user-reviewer", review_status="approved",
    )
    assert fb.reviewed is True
    assert fb.reviewed_by == "user-reviewer"
    assert fb.review_status == "approved"


def test_feedback_review_rejects_ai_reviewer() -> None:
    svc = _svc("org-1")
    svc.submit_feedback(
        feedback=AgentFeedback(
            feedback_id="fb4", agent_id="a1", user_id="user-1", content="有问题",
        )
    )
    # 红线⑥：reviewer 为 ai/system/空 → 不得代责审核
    for bad in ("ai", "system", ""):
        with pytest.raises(EnterpriseRedLineViolationError):
            svc.review_feedback(feedback_id="fb4", reviewer=bad)
    # actor_kind=AI 也不应通过 human-gating
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.review_feedback(
            feedback_id="fb4", reviewer="user-reviewer",
            actor_kind=AuditActorKind.AI,
        )


# ===========================================================================
# 类别 5：AgentQualityReport（事实汇编，来源可追溯）
# ===========================================================================

def test_quality_report_requires_traceable_source() -> None:
    # 无 source_trace → 红线违例（禁 AI 创造无源报告）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentQualityReport(report_id="qr1", org_id="org-1")
    # source_trace 不可追溯 → 同样违例
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentQualityReport(
            report_id="qr2", org_id="org-1",
            source_trace=SourceTrace(raw_refs=[]),
        )


def test_generate_quality_report_assembles_facts_only() -> None:
    svc = _svc("org-1")
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm5", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=12.0,
            period="2026-08", source="execution_log",
        )
    )
    svc.submit_evaluation(
        evaluation=AgentEvaluation(
            evaluation_id="ev4", agent_id="a1", evaluator="user-1",
            criteria="稳定性", comment="稳定",
        )
    )
    svc.submit_feedback(
        feedback=AgentFeedback(
            feedback_id="fb5", agent_id="a1", user_id="user-2", content="满意",
        )
    )
    svc.compare_versions(
        comparison_id="vc5", agent_id="a1",
        version_facts={"v1": {"call_count": 10, "success_rate": 0.8, "duration": 1.0}},
    )
    report = svc.generate_quality_report(
        report_id="qr3", user=_admin(), period="2026-08",
    )
    assert report.source_trace is not None and report.source_trace.is_traceable
    assert "qm5" in report.quality_metrics
    assert "ev4" in report.evaluations
    assert "fb5" in report.feedbacks
    assert "vc5" in report.version_comparisons
    # 仅汇编事实，无处置/升级/优化语义字段
    for bad in ("approved", "upgrade", "dispose", "decision", "optimize"):
        assert not hasattr(report, bad), f"AgentQualityReport 不应含 {bad}"


def test_generate_quality_report_requires_facts() -> None:
    svc = _svc("org-1")
    # 禁 AI 创造空的无源报告
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.generate_quality_report(report_id="qr4", user=_admin(), period="2026-08")


# ===========================================================================
# 类别 6：权限隔离（默认拒绝，AgentPermissionPolicy 接入）
# ===========================================================================

def test_quality_data_list_denied_by_default_for_expert() -> None:
    svc = _svc("org-1")
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm6", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=1.0,
        )
    )
    # EXPERT 访问 data 类别 → 默认拒绝（红线③/⑥：评价数据受控访问）
    with pytest.raises(Exception):
        svc.list_quality_metrics(user=_expert(), resource_category="data")


def test_quality_data_list_allowed_for_admin() -> None:
    svc = _svc("org-1")
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm7", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=1.0,
        )
    )
    out = svc.list_quality_metrics(user=_admin(), resource_category="data")
    assert len(out) == 1 and out[0].metric_id == "qm7"


def test_permission_policy_default_deny_data_for_expert() -> None:
    policy = AgentPermissionPolicy(org_id="org-1", identity=_identity())
    expert = _expert()
    # EXPERT 仅 knowledge，访问 data 默认拒绝
    assert policy.check_agent_access(
        user=expert, resource_category="data",
        required_permission=Permission.READ_RESOURCE,
    ) is False
    # ADMIN 访问 data 允许
    assert policy.check_agent_access(
        user=_admin(), resource_category="data",
        required_permission=Permission.READ_RESOURCE,
    ) is True


# ===========================================================================
# 类别 7：审计（AGENT_QUALITY / AGENT_EVALUATION / AGENT_FEEDBACK，任务6）
# ===========================================================================

def test_audit_categories_present() -> None:
    """本层只对**自己新增的 3 类**负责；总数权威断言唯一保留在
    ``test_enterprise_knowledge_governance_audit.py``（Phase 3.8.31 Task 9）。
    """
    for cat in ("AGENT_QUALITY", "AGENT_EVALUATION", "AGENT_FEEDBACK"):
        assert hasattr(AuditActionCategory, cat)
        assert getattr(AuditActionCategory, cat).value in (
            "agent_quality", "agent_evaluation", "agent_feedback"
        )
    # 3.8.17 新增类别同步存在
    for cat, val in (
        ("AGENT_POLICY", "agent_policy"),
        ("AGENT_RUNTIME_CHECK", "agent_runtime_check"),
        ("AGENT_TOOL_ACCESS", "agent_tool_access"),
    ):
        assert hasattr(AuditActionCategory, cat)
        assert getattr(AuditActionCategory, cat).value == val


def test_audit_quality_evaluation_feedback_recorded() -> None:
    audit = _audit("org-1")
    svc = AgentQualityGovernanceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm8", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=1.0,
        )
    )
    svc.submit_evaluation(
        evaluation=AgentEvaluation(
            evaluation_id="ev5", agent_id="a1", evaluator="user-1",
        )
    )
    svc.submit_feedback(
        feedback=AgentFeedback(
            feedback_id="fb6", agent_id="a1", user_id="user-2", content="ok",
        )
    )
    svc.compare_versions(
        comparison_id="vc6", agent_id="a1",
        version_facts={"v1": {"call_count": 5, "success_rate": 0.9, "duration": 1.0}},
    )
    svc.generate_quality_report(report_id="qr5", user=_admin(), period="2026-08")

    assert len(audit.query(category=AuditActionCategory.AGENT_QUALITY)) == 3
    assert len(audit.query(category=AuditActionCategory.AGENT_EVALUATION)) == 1
    assert len(audit.query(category=AuditActionCategory.AGENT_FEEDBACK)) == 1


def test_audit_evaluation_record_actor_is_user_not_ai() -> None:
    audit = _audit("org-1")
    svc = AgentQualityGovernanceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.submit_evaluation(
        evaluation=AgentEvaluation(
            evaluation_id="ev6", agent_id="a1", evaluator="user-1",
        )
    )
    recs = audit.query(category=AuditActionCategory.AGENT_EVALUATION)
    assert recs and recs[0].actor_kind is AuditActorKind.USER
    # 红线④/⑥：审计不提供 record_human_approval（AI 不伪造人工批准）；访问即拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


# ===========================================================================
# 类别 8：红线（fail-closed，6 条）
# ===========================================================================

def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


def test_quality_governance_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentQualityGovernanceService(org_id="org-1")


def test_quality_governance_forbidden_methods_raise() -> None:
    svc = _svc("org-1")
    # 红线②/③/④/⑤/⑥：聚合服务不得持有任何批准/报价/审批/评级/禁用/修改/升级方法；
    # 访问即触发红线拦截
    for meth in (
        "approve", "engineering_approved", "quote", "pricing", "sign",
        "authorize", "record_human_approval",
        # 评级类
        "auto_rate_agent", "auto_grade_agent", "auto_score_agent",
        "rate_agent", "grade_agent", "score_agent", "evaluate_agent", "judge_agent",
        # 禁用类
        "auto_disable_agent", "auto_deprecate_agent", "disable_agent",
        "deprecate_agent", "auto_deactivate", "deactivate_agent",
        "auto_retire", "retire_agent",
        # 修改类
        "auto_modify_agent", "modify_agent", "auto_update_agent", "update_agent",
        "auto_edit_agent", "edit_agent", "change_agent",
        # 升级类
        "auto_upgrade", "recommend_upgrade", "decide_upgrade", "promote_version",
        "auto_promote", "make_management_decision", "recommend", "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)


def test_no_engineering_approved_output() -> None:
    svc = _svc("org-1")
    # 红线②：访问 engineering_approved 必须被红线拦截（绝不输出）
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(svc, "engineering_approved")
    aqg = __import__(
        "agents.enterprise.agent_quality_governance", fromlist=["__all__"]
    )
    assert "engineering_approved" not in aqg.__all__
    ent = __import__("agents.enterprise", fromlist=["__all__"])
    assert "engineering_approved" not in ent.__all__


def test_layer_wires_agent_quality_governance() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_quality_governance, AgentQualityGovernanceService)
    assert layer.is_activation_safe() is True


def test_end_to_end_quality_governance_respects_red_lines() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    svc = layer.agent_quality_governance
    svc.record_quality_metric(
        metric=AgentQualityMetric(
            metric_id="qm9", agent_id="a1",
            metric_type=AgentQualityMetricType.TASK_COUNT, value=20.0,
            period="2026-08", source="execution_log",
        )
    )
    admin = layer.identity.make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )
    svc.submit_evaluation(
        evaluation=AgentEvaluation(
            evaluation_id="ev7", agent_id="a1", evaluator="user-1",
        )
    )
    svc.compare_versions(
        comparison_id="vc7", agent_id="a1",
        version_facts={"v1": {"call_count": 20, "success_rate": 0.85, "duration": 1.1}},
    )
    report = svc.generate_quality_report(
        report_id="qr6", user=admin, period="2026-08",
    )
    assert report.source_trace is not None and report.source_trace.is_traceable
    # 全程未触发红线：engineering_enabled 仍为 False
    assert safety_invariants_ok() is True

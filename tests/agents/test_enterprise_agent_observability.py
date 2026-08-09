"""Enterprise Agent Observability & Performance Intelligence Layer —— 测试（任务8，Phase 3.8.14）。

八类测试：execution / metric / trace / health / report / permission / audit / red line。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 Agent 自动评价/禁用/优化（AgentMetric 禁评、AgentHealthCandidate 禁处置、
   AgentPerformanceReport 禁优化，各服务 _FORBIDDEN 覆盖）；
④ 禁止 AI 自动审批（forbidden 方法名被拦截）；
⑤ 禁止绕过 UnifiedActivationGate（safety_invariants_ok 护栏）；
⑥ AI 不替代专家责任（健康候选 requires_human_review 恒 True；审计报告 anomalies 仅候选）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_observability import (
    AgentExecutionLog,
    AgentExecutionStatus,
    AgentHealthCandidate,
    AgentHealthDetector,
    AgentMetric,
    AgentMetricType,
    AgentObservabilityService,
    AgentPerformanceReport,
    AgentPerformanceReportService,
    AgentTrace,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
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


def _svc(org_id: str = "org-1") -> AgentObservabilityService:
    return AgentObservabilityService(
        org_id=org_id,
        audit=_audit(org_id),
        identity=_identity(org_id),
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
# 类别 1：AgentExecutionLog（事实型，只记录）
# ===========================================================================

def test_execution_log_default_status_success() -> None:
    log = AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t1")
    assert log.status is AgentExecutionStatus.SUCCESS
    assert log.is_successful is True
    assert log.duration == 0.0


def test_execution_log_status_coercion_and_failure() -> None:
    log = AgentExecutionLog(
        execution_id="e2", agent_id="a1", task_id="t1", status="failure", duration=2.5
    )
    # 字符串归一为枚举
    assert log.status is AgentExecutionStatus.FAILURE
    assert log.is_successful is False
    assert log.duration == 2.5


def test_execution_log_org_injected_on_record() -> None:
    svc = _svc("org-1")
    log = AgentExecutionLog(execution_id="e3", agent_id="a1", task_id="t1")
    svc.record_execution(execution=log)
    # 登记即归属当前组织（监控数据统一作用域）
    assert log.org_id == "org-1"
    assert svc.list_executions(user=_admin())[0].execution_id == "e3"


# ===========================================================================
# 类别 2：AgentMetric（事实型，禁止自动评价 Agent 好坏）
# ===========================================================================

def test_metric_success_rate_clamped_and_non_negative() -> None:
    over = AgentMetric(
        metric_id="m1", agent_id="a1",
        metric_type=AgentMetricType.SUCCESS_RATE, value=1.5
    )
    neg = AgentMetric(
        metric_id="m2", agent_id="a1",
        metric_type=AgentMetricType.CALL_COUNT, value=-3.0
    )
    # 成功率裁剪至 [0,1]；调用次数非负（仅范围约束，不评价）
    assert over.value == 1.0
    assert neg.value == 0.0


def test_metric_has_no_evaluation_fields() -> None:
    m = AgentMetric(
        metric_id="m3", agent_id="a1",
        metric_type=AgentMetricType.DURATION, value=1.0
    )
    # 红线③/⑥：结构上禁评，不得携带任何 verdict/score/rating 语义
    for bad in ("verdict", "score", "rating", "grade", "quality"):
        assert not hasattr(m, bad), f"AgentMetric 不应含评价字段 {bad}"


def test_derive_metrics_computes_facts_only() -> None:
    svc = _svc("org-1")
    statuses = [
        AgentExecutionStatus.SUCCESS,
        AgentExecutionStatus.SUCCESS,
        AgentExecutionStatus.SUCCESS,
        AgentExecutionStatus.FAILURE,
    ]
    durations = [1.0, 2.0, 3.0, 4.0]
    for i, (st, du) in enumerate(zip(statuses, durations)):
        svc.record_execution(
            execution=AgentExecutionLog(
                execution_id=f"e{i}", agent_id="a1", task_id="t",
                status=st, duration=du,
            )
        )
    metrics = svc.derive_metrics(agent_id="a1", period="2026-08")
    by_type = {m.metric_type: m.value for m in metrics}
    assert by_type[AgentMetricType.CALL_COUNT] == 4.0
    assert by_type[AgentMetricType.SUCCESS_RATE] == pytest.approx(0.75)
    assert by_type[AgentMetricType.DURATION] == pytest.approx(2.5)


def test_derive_metrics_requires_logs() -> None:
    svc = _svc("org-1")
    # 禁 AI 创造无源指标
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.derive_metrics(agent_id="a-ghost", period="2026-08")


# ===========================================================================
# 类别 3：AgentTrace（可追踪）
# ===========================================================================

def test_trace_root_and_leaf_flags() -> None:
    root = AgentTrace(trace_id="tr1", agent_id="a1")
    assert root.is_root is True
    assert root.is_leaf is True
    nested = AgentTrace(
        trace_id="tr2", agent_id="a1", parent_agent="a0", child_agent="a2",
        action="delegate",
    )
    assert nested.is_root is False
    assert nested.is_leaf is False


def test_trace_recorded_and_listable_with_org() -> None:
    svc = _svc("org-1")
    svc.record_trace(
        trace=AgentTrace(trace_id="tr3", agent_id="a1", child_agent="a2")
    )
    out = svc.list_traces(user=_admin())
    assert len(out) == 1 and out[0].trace_id == "tr3"
    # 登记即归属当前组织
    assert out[0].org_id == "org-1"


# ===========================================================================
# 类别 4：AgentHealthCandidate / AgentHealthDetector（仅发现，禁处置）
# ===========================================================================

def test_health_candidate_requires_human_review_always_true() -> None:
    c = AgentHealthCandidate(health_id="h1", agent_id="a1", pattern="x", evidence="y")
    assert c.requires_human_review is True
    # 即便传入 False，__post_init__ 也强制为 True（红线③/⑥：AI 不代责）
    c2 = AgentHealthCandidate(
        health_id="h2", agent_id="a1", requires_human_review=False
    )
    assert c2.requires_human_review is True


def test_health_detect_from_executions_creates_candidate() -> None:
    detector = AgentHealthDetector(org_id="org-1", audit=_audit())
    logs = [
        AgentExecutionLog(execution_id=f"e{i}", agent_id="a1", task_id="t",
                          org_id="org-1",
                          status=AgentExecutionStatus.SUCCESS if i < 2 else AgentExecutionStatus.FAILURE)
        for i in range(5)
    ]
    cand = detector.detect_from_execution_logs(
        health_id="h1", agent_id="a1", logs=logs
    )
    assert isinstance(cand, AgentHealthCandidate)
    assert cand.requires_human_review is True
    assert "failure_rate" in cand.pattern
    assert "failed=3" in cand.evidence


def test_health_detect_requires_logs() -> None:
    detector = AgentHealthDetector(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        detector.detect_from_execution_logs(
            health_id="h1", agent_id="a1", logs=[]
        )


def test_health_detect_no_cross_org() -> None:
    detector = AgentHealthDetector(org_id="org-1")
    logs = [
        AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t",
                          org_id="org-2", status=AgentExecutionStatus.FAILURE)
    ]
    with pytest.raises(Exception):
        detector.detect_from_execution_logs(
            health_id="h1", agent_id="a1", logs=logs
        )


def test_health_detector_forbidden_disposition_methods() -> None:
    detector = AgentHealthDetector(org_id="org-1")
    # 红线③/⑥：检测器不得提供任何自动处置/禁用入口；访问即触发红线拦截
    for meth in (
        "disable_agent", "auto_disable", "deactivate_agent", "kill_agent",
        "suspend_agent", "restart_agent", "auto_fix", "auto_heal", "mitigate",
        "resolve", "fix", "close", "evaluate_agent", "rate_agent",
        "score_agent", "judge_agent",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(detector, meth)


# ===========================================================================
# 类别 5：AgentPerformanceReport（事实汇编，禁用自动优化）
# ===========================================================================

def test_performance_report_requires_traceable_source() -> None:
    # 无 source_trace → 红线违例（禁 AI 创造无源报告）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentPerformanceReport(report_id="r1", org_id="org-1")
    # source_trace 不可追溯 → 同样违例
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentPerformanceReport(
            report_id="r2", org_id="org-1",
            source_trace=SourceTrace(raw_refs=[]),
        )


def test_report_generate_assembles_facts_only() -> None:
    svc = _svc("org-1")
    for i in range(3):
        svc.record_execution(
            execution=AgentExecutionLog(
                execution_id=f"e{i}", agent_id="a1", task_id="t",
                status=AgentExecutionStatus.SUCCESS, duration=float(i + 1),
            )
        )
    svc.record_metric(
        metric=AgentMetric(
            metric_id="m1", agent_id="a1",
            metric_type=AgentMetricType.CALL_COUNT, value=3.0,
            source="derived_from_execution_log",
        )
    )
    report = svc.generate_report(report_id="rep1", user=_admin(), period="2026-08")
    assert report.source_trace is not None and report.source_trace.is_traceable
    assert "m1" in report.facts
    assert len(report.anomaly_candidates) == 0  # 仅汇编，无处置


def test_report_service_forbidden_optimize_methods() -> None:
    svc = _svc("org-1")
    rs = svc.report_service
    # 红线③/⑥：报告服务不得提供任何自动优化/调参入口；访问即触发红线拦截
    for meth in (
        "auto_optimize", "optimize_agent", "tune_agent", "auto_tune",
        "retrain_agent", "reconfigure_agent", "auto_fix", "auto_heal",
        "make_management_decision", "recommend", "decide", "evaluate_agent",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(rs, meth)


# ===========================================================================
# 类别 6：权限隔离（默认拒绝，AgentPermissionPolicy 接入）
# ===========================================================================

def test_observability_list_denied_by_default_for_expert() -> None:
    svc = _svc("org-1")
    svc.record_execution(
        execution=AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t")
    )
    # EXPERT 访问 data 类别 → 默认拒绝（红线③/⑥：监控数据受控访问）
    with pytest.raises(Exception):
        svc.list_executions(user=_expert(), resource_category="data")


def test_observability_list_allowed_for_admin() -> None:
    svc = _svc("org-1")
    svc.record_execution(
        execution=AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t")
    )
    out = svc.list_executions(user=_admin(), resource_category="data")
    assert len(out) == 1 and out[0].execution_id == "e1"


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
# 类别 7：审计（AGENT_METRIC / AGENT_TRACE / AGENT_HEALTH，任务6）
# ===========================================================================

def test_audit_agent_metric_trace_health_recorded() -> None:
    audit = _audit("org-1")
    svc = AgentObservabilityService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.record_execution(
        execution=AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t")
    )
    svc.record_metric(
        metric=AgentMetric(
            metric_id="m1", agent_id="a1",
            metric_type=AgentMetricType.CALL_COUNT, value=1.0,
        )
    )
    svc.record_trace(trace=AgentTrace(trace_id="tr1", agent_id="a1"))
    svc.detect_health(health_id="h1", agent_id="a1", user=_admin())
    assert len(audit.query(category=AuditActionCategory.AGENT_EXECUTION)) == 1
    assert len(audit.query(category=AuditActionCategory.AGENT_METRIC)) == 1
    assert len(audit.query(category=AuditActionCategory.AGENT_TRACE)) == 1
    assert len(audit.query(category=AuditActionCategory.AGENT_HEALTH)) == 1


def test_audit_categories_present_in_enum() -> None:
    # 任务6：三个新审计类别就位（累计 35 个由审计增强测试保障，此处校验存在性）
    for cat in ("AGENT_METRIC", "AGENT_TRACE", "AGENT_HEALTH"):
        assert hasattr(AuditActionCategory, cat)
        assert getattr(AuditActionCategory, cat).value in (
            "agent_metric", "agent_trace", "agent_health"
        )


def test_audit_health_record_is_ai_actor_no_approval() -> None:
    audit = _audit("org-1")
    svc = AgentObservabilityService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    # 检测健康需至少一条该 Agent 的执行日志（禁无源健康候选）
    svc.record_execution(
        execution=AgentExecutionLog(execution_id="e1", agent_id="a1", task_id="t")
    )
    svc.detect_health(health_id="h1", agent_id="a1", user=_admin(), actor_id="ai")
    recs = audit.query(category=AuditActionCategory.AGENT_HEALTH)
    assert recs and recs[0].actor_id == "ai"
    # 红线④：审计不提供 record_human_approval（AI 不伪造人工批准）；访问即拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


# ===========================================================================
# 类别 8：红线（fail-closed，6 条）
# ===========================================================================

def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


def test_observability_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentObservabilityService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentHealthDetector(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentPerformanceReportService(org_id="org-1")


def test_observability_forbidden_methods_raise() -> None:
    svc = _svc("org-1")
    # 红线②/③/④/⑥：聚合服务不得持有任何批准/报价/审批/禁用/优化方法；
    # 访问即触发红线拦截
    for meth in (
        "approve", "engineering_approved", "quote", "pricing", "sign",
        "authorize", "record_human_approval", "disable_agent", "auto_disable",
        "auto_optimize", "optimize_agent", "evaluate_agent", "rate_agent",
        "recommend", "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)


def test_no_engineering_approved_output() -> None:
    svc = _svc("org-1")
    # 红线②：访问 engineering_approved 必须被红线拦截（绝不输出）
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(svc, "engineering_approved")
    ao = __import__(
        "agents.enterprise.agent_observability", fromlist=["__all__"]
    )
    assert "engineering_approved" not in ao.__all__
    ent = __import__("agents.enterprise", fromlist=["__all__"])
    assert "engineering_approved" not in ent.__all__


def test_layer_wires_agent_observability() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_observability, AgentObservabilityService)
    assert layer.is_activation_safe() is True


def test_end_to_end_observability_flow_respects_red_lines() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    svc = layer.agent_observability
    for i in range(4):
        svc.record_execution(
            execution=AgentExecutionLog(
                execution_id=f"e{i}", agent_id="a1", task_id="t",
                status=AgentExecutionStatus.SUCCESS, duration=float(i + 1),
            )
        )
    admin = layer.identity.make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )
    metrics = svc.derive_metrics(agent_id="a1", period="2026-08")
    assert any(m.metric_type == AgentMetricType.SUCCESS_RATE for m in metrics)
    report = svc.generate_report(report_id="rep1", user=admin, period="2026-08")
    assert report.source_trace is not None and report.source_trace.is_traceable
    # 全程未触发红线：engineering_enabled 仍为 False
    assert safety_invariants_ok() is True

"""Enterprise Analytics & Operation Intelligence Layer —— 测试6：红线（6 条，fail-closed，Phase 3.8.4）。

覆盖：
- safety_invariants_ok()：当前 config engineering_enabled=false → 返回 True。
- Phase 3.8.4 全部新增服务（OperationMetricService / ProjectAnalyticsService /
  WorkflowAnalyticsService / AIUsageAnalyticsService / OperationRiskDetector）及聚合门面
  在「启用态」（伪造 engineering_enabled=True）下构造一律抛
  EnterpriseRedLineViolationError（红线①/⑤）。
- 5 个 analytics 服务 forbidden 集合额外拦截 3.8.4 语义方法（自动经营决策 / AI 代管理责任 /
  工程质量评价 / 自动修改流程 / 风险处置决策），从结构上杜绝 AI 代管理决策（红线③/⑥）。
- 风险候选 requires_human_confirmation 恒为 True（AI 不代管理确认）。
- AI 使用记录恒记 actor=AI，绝不伪造为人工（红线⑥）。
- 聚合门面暴露 5 个新子服务；layer.is_activation_safe() 返回 True。
- 不修改 verified.json / config.yaml / engineering_enabled 文件（仅 monkeypatch）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.operation_metric import OperationMetricService
from agents.enterprise.operation_risk import OperationRiskDetector, RiskCandidate
from agents.enterprise.ai_usage_analytics import AIUsageAnalyticsService
from agents.enterprise.project_analytics import ProjectAnalyticsService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.workflow_analytics import WorkflowAnalyticsService


def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


@pytest.mark.parametrize(
    "svc_factory",
    [
        lambda: OperationMetricService(org_id="org-1"),
        lambda: ProjectAnalyticsService(org_id="org-1"),
        lambda: WorkflowAnalyticsService(org_id="org-1"),
        lambda: AIUsageAnalyticsService(org_id="org-1"),
        lambda: OperationRiskDetector(org_id="org-1"),
        lambda: EnterpriseOperationLayer(org_id="org-1"),
    ],
)
def test_phase_3_8_4_service_construction_fail_closed(svc_factory, monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_factory()


def test_analytics_services_forbid_decision_methods() -> None:
    """3.8.4 红线③/⑥：analytics 层从结构上杜绝 AI 代管理决策。"""
    om = OperationMetricService(org_id="org-1")
    pa = ProjectAnalyticsService(org_id="org-1")
    wa = WorkflowAnalyticsService(org_id="org-1")
    aa = AIUsageAnalyticsService(org_id="org-1")
    rk = OperationRiskDetector(org_id="org-1")
    for svc, meth in [
        (om, "auto_business_decision"),
        (pa, "evaluate_quality"),       # 禁止工程质量评价
        (pa, "make_management_decision"),
        (wa, "modify_workflow"),        # 禁止自动修改流程
        (wa, "auto_fix"),
        (aa, "auto_business_decision"),
        (rk, "decide"),                 # 禁止风险处置决策
        (rk, "resolve"),
        (rk, "mitigate"),
    ]:
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, meth)


def test_risk_candidate_requires_human_confirmation_always_true() -> None:
    c = RiskCandidate(risk_id="R-X", org_id="org-1", risk_type="sla_overdue", requires_human_confirmation=False)
    assert c.requires_human_confirmation is True


def test_ai_usage_never_recorded_as_human() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = AIUsageAnalyticsService(org_id="org-1", audit=audit)
    svc.record_ai_usage(event_id="E-1", task_type="design_consult", success=True, recorded_at="t0")
    ai_recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "record_ai_usage" for r in ai_recs)
    user_recs = audit.query(actor_kind=AuditActorKind.USER)
    assert not any(r.action == "record_ai_usage" for r in user_recs)


def test_aggregate_layer_exposes_new_subservices() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    for attr in (
        "operation_metrics",
        "project_analytics",
        "workflow_analytics",
        "ai_usage_analytics",
        "operation_risk",
    ):
        assert hasattr(layer, attr), f"聚合层缺少 {attr}"


def test_enterprise_layer_is_activation_safe() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert layer.is_activation_safe() is True

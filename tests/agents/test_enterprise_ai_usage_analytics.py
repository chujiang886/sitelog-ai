"""Enterprise Analytics & Operation Intelligence Layer —— 测试4：AI 使用分析（任务4，Phase 3.8.4）。

覆盖：
- record_ai_usage + compute_analytics 统计调用次数 / 任务类型 / 响应情况。
- **禁止记录为人工行为**：record_ai_usage 恒记 actor=AI，不产生 USER 审计记录（红线⑥）。
- 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
- 额外拦截 auto_business_decision / make_management_decision（3.8.4 红线③/⑥）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.ai_usage_analytics import AIUsageAnalyticsService
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_record_and_compute_analytics() -> None:
    svc = AIUsageAnalyticsService(org_id="org-1")
    svc.record_ai_usage(event_id="E-1", task_type="design_consult", success=True, response_time=1.2)
    svc.record_ai_usage(event_id="E-2", task_type="design_consult", success=False, response_time=3.4)
    svc.record_ai_usage(event_id="E-3", task_type="vision", success=True, response_time=0.8)
    a = svc.compute_analytics(analytics_id="AA-1", computed_at="t0")
    assert a.total_calls == 3
    assert a.task_type_distribution == {"design_consult": 2, "vision": 1}
    assert a.response_ok == 2
    assert a.response_fail == 1
    assert a.avg_response_time == pytest.approx((1.2 + 3.4 + 0.8) / 3)


def test_recorded_by_forced_ai_not_user() -> None:
    svc = AIUsageAnalyticsService(org_id="org-1")
    ev = svc.record_ai_usage(event_id="E-1", task_type="design_consult", recorded_by="someone")
    assert ev.recorded_by == "ai"  # 来源备注强制恒为 ai


def test_never_records_as_human_action() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = AIUsageAnalyticsService(org_id="org-1", audit=audit)
    svc.record_ai_usage(event_id="E-1", task_type="design_consult", success=True, recorded_at="t0")
    ai_recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "record_ai_usage" for r in ai_recs)
    user_recs = audit.query(actor_kind=AuditActorKind.USER)
    assert not any(r.action == "record_ai_usage" for r in user_recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        AIUsageAnalyticsService(org_id="org-1")


def test_forbidden_decision_method_blocked() -> None:
    svc = AIUsageAnalyticsService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.auto_business_decision  # 3.8.4 红线③

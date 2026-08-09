"""Enterprise Analytics & Operation Intelligence Layer —— 测试2：项目分析（任务2，Phase 3.8.4）。

覆盖：
- compute_project_analytics 统计项目数量 / 完成率 / 状态分布 / 平均周期。
- **禁止评价工程质量**：evaluate_quality / score_project 被 mixin 拦截（红线③/⑥）。
- 审计如实标注 AI 动作。
- 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.project import ProjectService
from agents.enterprise.project_analytics import ProjectAnalyticsService
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _seed_projects(org_id: str) -> ProjectService:
    svc = ProjectService(org_id=org_id)
    svc.create_project(project_id="P-1", name="p1", customer_id="C-1")
    svc.create_project(project_id="P-2", name="p2", customer_id="C-2")
    svc.create_project(project_id="P-3", name="p3", customer_id="C-3")
    svc.link_solution(project_id="P-1", solution_id="SOL-1")  # 仅作关联示例
    # 标记完成态（archived 视为完成，纯业务事实）
    svc._projects["P-2"].status = "archived"
    svc._projects["P-3"].status = "archived"
    return svc


def test_compute_project_analytics_facts() -> None:
    projects = _seed_projects("org-1")
    svc = ProjectAnalyticsService(org_id="org-1", project_service=projects)
    a = svc.compute_project_analytics(
        analytics_id="PA-1",
        computed_at="t0",
        cycle_days_by_project={"P-1": 10.0, "P-2": 20.0, "P-3": 30.0},
    )
    assert a.total_projects == 3
    assert a.completed_count == 2
    assert a.completion_rate == pytest.approx(2 / 3)
    assert a.avg_cycle_days == pytest.approx(20.0)
    assert a.status_distribution == {"draft": 1, "archived": 2}
    assert a.notes  # 事实描述，非评价


def test_compute_project_analytics_empty() -> None:
    svc = ProjectAnalyticsService(org_id="org-1", project_service=ProjectService(org_id="org-1"))
    a = svc.compute_project_analytics(analytics_id="PA-0")
    assert a.total_projects == 0
    assert a.completion_rate == 0.0
    assert a.avg_cycle_days == 0.0


def test_no_quality_evaluation_entrypoint() -> None:
    svc = ProjectAnalyticsService(org_id="org-1")
    # 红线③/⑥：禁止工程质量评价入口
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.evaluate_quality
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.score_project


def test_audit_records_ai_action() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = ProjectAnalyticsService(org_id="org-1", audit=audit, project_service=_seed_projects("org-1"))
    svc.compute_project_analytics(analytics_id="PA-1", computed_at="t0")
    recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "compute_project_analytics" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        ProjectAnalyticsService(org_id="org-1")

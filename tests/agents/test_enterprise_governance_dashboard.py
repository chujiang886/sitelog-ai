"""Phase 3.8.26 治理驾驶舱层测试（fail-closed）。

覆盖：列表 / 待审核 / 执行状态 / 审计 / 风险 / 人工确认（强制 USER）/ 权限默认拒绝 /
跨组织隔离 / 禁名结构拦截 / AI 越权被拦 / 接入 EnterpriseOperationLayer。

不引入任何大型测试框架，沿用仓库既有 pytest 纪律。
"""

from __future__ import annotations

import pytest

from agents.enterprise import GovernanceDashboardService as _Exported  # 验证包导出
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.governance_dashboard import (
    DashboardUser,
    GovernanceDashboardService,
    _DASHBOARD_FORBIDDEN,
)
from agents.enterprise.governance_workflow.models import GovernanceWorkflowStatus
from agents.enterprise.governance_workflow.orchestrator import (
    GovernanceWorkflowOrchestrator,
)
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError


@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch):
    """红线①：锁定 engineering_enabled=False（只读断言，不碰磁盘）。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _orch(org: str = "org-26") -> GovernanceWorkflowOrchestrator:
    audit = AuditService(org_id=org)
    return GovernanceWorkflowOrchestrator(org_id=org, audit=audit)


def _svc(org: str = "org-26", permission_policy=None):
    orch = _orch(org)
    audit = orch._audit
    return GovernanceDashboardService(
        org_id=org, orchestrator=orch, audit=audit, permission_policy=permission_policy
    )


def _user(actor_id: str = "governor-1", kind=AuditActorKind.USER) -> DashboardUser:
    return DashboardUser(actor_id=actor_id, actor_kind=kind)


def _seed_pending(svc: GovernanceDashboardService, wid: str = "gw-1") -> None:
    svc._orchestrator.register_candidate(
        workflow_id=wid, source_type="assistant_draft", source_id="ans-1",
        title="密封胶核查", source_facts=["f1"], references=["r1"],
    )
    svc._orchestrator.submit_for_review(workflow_id=wid, actor_id="ai")


# ---------------------------------------------------------------------------
# 基本列表 / 待审核 / 执行状态 / 审计 / 风险
# ---------------------------------------------------------------------------

def test_package_export_present():
    assert _Exported is GovernanceDashboardService


def test_list_pending_reviews_after_submit():
    svc = _svc()
    _seed_pending(svc)
    pending = svc.list_pending_reviews(org_id="org-26", user=_user())
    assert [w.workflow_id for w in pending] == ["gw-1"]
    # 状态确为 under_review
    assert pending[0].status is GovernanceWorkflowStatus.UNDER_REVIEW


def test_list_workflows_filters_by_status():
    svc = _svc()
    _seed_pending(svc)
    created = svc.list_workflows(
        org_id="org-26", user=_user(), status=GovernanceWorkflowStatus.UNDER_REVIEW
    )
    assert len(created) == 1
    none = svc.list_workflows(
        org_id="org-26", user=_user(), status=GovernanceWorkflowStatus.COMPLETED
    )
    assert none == []


def test_execution_status_view():
    svc = _svc()
    _seed_pending(svc)
    svc.confirm_review(
        org_id="org-26", user=_user(), workflow_id="gw-1",
        decision="confirmed", reason="经核查属实",
    )
    view = svc.get_execution_status(org_id="org-26", user=_user(), workflow_id="gw-1")
    assert view.status == GovernanceWorkflowStatus.HUMAN_CONFIRMED.value
    assert view.confirmed_by == "governor-1"
    assert view.archived is False


def test_audit_records_filtered_to_governance_categories():
    svc = _svc()
    _seed_pending(svc)
    svc.confirm_review(
        org_id="org-26", user=_user(), workflow_id="gw-1",
        decision="confirmed", reason="ok",
    )
    recs = svc.list_audit_records(org_id="org-26", user=_user())
    cats = {r.category for r in recs}
    assert cats <= {
        AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE,
        AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW,
        AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION,
    }
    assert len(recs) >= 2


def test_risk_alerts_surface_pending_review():
    svc = _svc()
    _seed_pending(svc)
    alerts = svc.list_risk_alerts(org_id="org-26", user=_user())
    assert any(a.workflow_id == "gw-1" and a.severity == "action" for a in alerts)


def test_summary_counts():
    svc = _svc()
    _seed_pending(svc)
    s = svc.summary(org_id="org-26", user=_user())
    assert s.total == 1
    assert s.pending_review == 1


# ---------------------------------------------------------------------------
# 人工确认（唯一写入口，强制 USER）
# ---------------------------------------------------------------------------

def test_confirm_review_moves_to_human_confirmed():
    svc = _svc()
    _seed_pending(svc)
    rev = svc.confirm_review(
        org_id="org-26", user=_user(), workflow_id="gw-1",
        decision="confirmed", reason="同意处置",
    )
    assert rev.decision.value == "confirmed"
    wf = svc._orchestrator.get_workflow("gw-1")
    assert wf.status is GovernanceWorkflowStatus.HUMAN_CONFIRMED
    assert wf.confirmed_by == "governor-1"


def test_confirm_review_derive_task_calls_accountability_layer():
    class _FakeAccountability:
        def __init__(self):
            self.calls = []

        def create_task(self, **kw):
            self.calls.append(kw)

    fake = _FakeAccountability()
    svc = _svc()
    svc._orchestrator._governance_workflow = fake
    _seed_pending(svc)
    svc.confirm_review(
        org_id="org-26", user=_user(), workflow_id="gw-1",
        decision="confirmed", reason="ok", derive_task=True, task_id="gt-1",
    )
    assert fake.calls and fake.calls[0]["task_id"] == "gt-1"
    assert fake.calls[0]["actor_id"] == "governor-1"


# ---------------------------------------------------------------------------
# 红线：AI 越权 / 默认拒绝 / 组织隔离 / 结构拦截
# ---------------------------------------------------------------------------

def test_confirm_review_rejects_ai():
    svc = _svc()
    _seed_pending(svc)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.confirm_review(
            org_id="org-26",
            user=DashboardUser(actor_id="ai-1", actor_kind=AuditActorKind.AI),
            workflow_id="gw-1", decision="confirmed", reason="ai-try",
        )


def test_confirm_review_requires_user_object():
    svc = _svc()
    _seed_pending(svc)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.confirm_review(
            org_id="org-26", user=None,  # type: ignore
            workflow_id="gw-1", decision="confirmed", reason="x",
        )


def test_read_requires_user():
    svc = _svc()
    _seed_pending(svc)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.list_workflows(
            org_id="org-26",
            user=DashboardUser(actor_id="ai-1", actor_kind=AuditActorKind.AI),
        )


def test_permission_default_deny():
    class _DenyPolicy:
        def check_agent_access(self, *, user, resource_category):
            return False

    svc = _svc(permission_policy=_DenyPolicy())
    _seed_pending(svc)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.list_workflows(org_id="org-26", user=_user())


def test_permission_grant_allows():
    class _AllowPolicy:
        def check_agent_access(self, *, user, resource_category):
            return True

    svc = _svc(permission_policy=_AllowPolicy())
    _seed_pending(svc)
    out = svc.list_workflows(org_id="org-26", user=_user())
    assert [w.workflow_id for w in out] == ["gw-1"]


def test_org_isolation_rejected():
    svc = _svc(org="org-26")
    with pytest.raises(EnterpriseIsolationError):
        svc.list_workflows(org_id="other-org", user=_user())


def test_structural_forbidden_blocks_auto_methods():
    # _RedLineForbiddenMixin 通过 __getattr__ 拦截「未定义但命中禁名」的调用，
    # 因此服务本身不得定义 auto_execute 等方法；外部尝试调用即被拦截。
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.auto_execute()  # 未定义 → 命中 _DASHBOARD_FORBIDDEN
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.generate_policy()


def test_forbidden_set_contains_key_fragments():
    for frag in ("auto_confirm", "auto_execute", "auto_close", "generate_policy",
                 "modify_knowledge", "confirm_on_behalf"):
        assert frag in _DASHBOARD_FORBIDDEN


def test_require_human_actor_rejects_ai_directly():
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor(AuditActorKind.AI)


# ---------------------------------------------------------------------------
# 接入 EnterpriseOperationLayer
# ---------------------------------------------------------------------------

def test_wired_into_operation_layer():
    from agents.enterprise import EnterpriseOperationLayer

    layer = EnterpriseOperationLayer(org_id="org-26")
    assert hasattr(layer, "agent_governance_dashboard")
    assert isinstance(layer.agent_governance_dashboard, GovernanceDashboardService)

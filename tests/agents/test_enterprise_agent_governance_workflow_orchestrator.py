"""Enterprise Agent Governance Workflow Orchestration Layer —— 测试（Phase 3.8.25）。

覆盖：工作流创建 / 状态转换（合法+非法+终态） / 权限隔离（跨组织拒绝） /
人工确认（AI 调用被 require_human_actor 拦截） / 审计记录 / 禁止自动执行。

最高红线（fail-closed，6 条）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（结构级禁名拦截）；
③ 禁止 AI 自动治理 / 自动审批 / 自动关闭问题（前进转移全 require_human_actor）；
④ 禁止 AI 自动执行治理动作（执行记录 actor_kind 必须为 user）；
⑤ 禁止 AI 自动生成治理策略 / 改知识（六组语义扫描）；
⑥ 禁止 AI 代替治理责任人（actor_kind=USER + 审计留痕）。

启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import types
import pytest

from agents.enterprise.agent_governance_workflow import GovernanceTaskSourceType
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.governance_workflow.models import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
)
from agents.enterprise.governance_workflow.orchestrator import (
    GovernanceWorkflowOrchestrator,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise import GovernanceAnswerDraft


@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


# ---------------------------------------------------------------------------
# 共享构造器（仅内存构造，不落盘）
# ---------------------------------------------------------------------------

class _FakeGovernanceWorkflow:
    """3.8.21 问责层替身：仅记录 create_task 调用，便于验证派生任务。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create_task(self, *, task_id, source_type, source_id, title="", detail="",
                    created_at="", actor_id="ai", actor_kind=None):
        self.calls.append({
            "task_id": task_id, "source_type": source_type, "source_id": source_id,
            "actor_id": actor_id, "actor_kind": actor_kind,
        })
        return object()


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _orchestrator(org_id: str = "org-1", governance_workflow=None):
    return GovernanceWorkflowOrchestrator(
        org_id=org_id,
        audit=_audit(org_id),
        identity=_identity(org_id),
        permission_policy=_policy(org_id),
        governance_workflow=governance_workflow,
    )


# ---------------------------------------------------------------------------
# 任务1：工作流创建
# ---------------------------------------------------------------------------

def test_register_candidate_creates_created_state() -> None:
    orch = _orchestrator()
    wf = orch.register_candidate(
        workflow_id="gw-1", source_type="human_reported", source_id="risk-1",
        title="门窗密封胶老化",
    )
    assert wf.status is GovernanceWorkflowStatus.CREATED
    assert wf.requires_human_confirmation is True
    assert wf.created_by == "ai"  # AI 创建时如实记为 ai，不伪装人工


def test_create_from_answer_draft_requires_human_review() -> None:
    orch = _orchestrator()
    draft = GovernanceAnswerDraft(
        answer_id="ans-1", query_id="q-1", requires_human_review=True,
        summary="现场记录显示密封胶老化", facts=["f1"], references=["r1"],
    )
    wf = orch.create_from_answer_draft(draft=draft)
    assert wf.source_type is GovernanceWorkflowSourceType.ASSISTANT_DRAFT
    assert wf.source_id == "ans-1"
    assert wf.draft_id == "ans-1"


def test_create_from_answer_draft_rejects_unverified() -> None:
    orch = _orchestrator()
    # 真实 GovernanceAnswerDraft 在构造期即强制 requires_human_review=True（红线④/⑥），
    # 故用 duck-typed 草稿对象验证编排器自身的防御性闸门（getattr 取值）。
    bad = types.SimpleNamespace(
        answer_id="ans-2", query_id="q-2", requires_human_review=False,
        summary="", facts=[], references=[],
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.create_from_answer_draft(draft=bad)


# ---------------------------------------------------------------------------
# 任务2：状态转换（合法 / 非法 / 终态）
# ---------------------------------------------------------------------------

def _to_under_review(orch, wid="gw-1"):
    orch.register_candidate(workflow_id=wid, source_type="human_reported", source_id="r")
    orch.submit_for_review(workflow_id=wid)


def test_legal_transition_chain_reaches_completed() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="研判通过",
    )
    orch.start_execution(workflow_id="gw-1", actor_id="u-b", actor_kind=AuditActorKind.USER)
    orch.submit_execution_result(
        workflow_id="gw-1", action="replace", actor="u-b",
        actor_kind=AuditActorKind.USER, result="已更换",
    )
    orch.human_complete(workflow_id="gw-1", actor_id="u-a", actor_kind=AuditActorKind.USER)
    orch.archive(workflow_id="gw-1", actor_id="u-a", actor_kind=AuditActorKind.USER)
    wf = orch.get_workflow("gw-1")
    assert wf.status is GovernanceWorkflowStatus.COMPLETED
    assert wf.archived is True
    assert wf.completed_by == "u-a"


def test_illegal_transition_rejected() -> None:
    orch = _orchestrator()
    # CREATED 直接跳 HUMAN_CONFIRMED 非法
    orch.register_candidate(workflow_id="gw-x", source_type="human_reported", source_id="r")
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.human_confirm(
            workflow_id="gw-x", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
            decision="confirmed", reason="x",
        )


def test_terminal_state_cannot_transition() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x",
    )
    orch.start_execution(workflow_id="gw-1", actor_id="u-b", actor_kind=AuditActorKind.USER)
    orch.submit_execution_result(
        workflow_id="gw-1", action="a", actor="u-b", actor_kind=AuditActorKind.USER,
    )
    orch.human_complete(workflow_id="gw-1", actor_id="u-a", actor_kind=AuditActorKind.USER)
    # COMPLETED 之后任何前进转移都必须被拒
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.start_execution(workflow_id="gw-1", actor_id="u-b", actor_kind=AuditActorKind.USER)


def test_rejected_review_does_not_advance() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="rejected", reason="证据不足",
    )
    assert orch.get_workflow("gw-1").status is GovernanceWorkflowStatus.UNDER_REVIEW


# ---------------------------------------------------------------------------
# 任务3：权限隔离（跨组织拒绝）
# ---------------------------------------------------------------------------

def test_cross_org_access_rejected() -> None:
    orch = _orchestrator(org_id="org-1")
    orch.register_candidate(workflow_id="gw-1", source_type="human_reported", source_id="r")
    orch.submit_for_review(workflow_id="gw-1")
    with pytest.raises(EnterpriseIsolationError):
        orch.human_confirm(
            workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
            decision="confirmed", reason="x", org_id="org-2",
        )


def test_list_workflows_filters_by_org() -> None:
    orch = _orchestrator(org_id="org-1")
    orch.register_candidate(workflow_id="gw-1", source_type="human_reported", source_id="r",
                            title="t", description="d")
    # 直接构造一个他组织的工作流对象，验证 list 过滤
    other = GovernanceWorkflow(
        workflow_id="gw-2", source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
        source_id="r2", org_id="org-9", title="t2", description="d2",
    )
    orch._workflows["gw-2"] = other
    listed = orch.list_workflows(org_id="org-1")
    ids = {w.workflow_id for w in listed}
    assert "gw-1" in ids
    assert "gw-2" not in ids


# ---------------------------------------------------------------------------
# 任务4：人工确认（AI 调用被红线拦截）
# ---------------------------------------------------------------------------

def test_ai_cannot_confirm() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.human_confirm(
            workflow_id="gw-1", reviewer_id="ai-bot", reviewer_kind=AuditActorKind.AI,
            decision="confirmed", reason="ai says ok",
        )


def test_ai_cannot_execute() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.start_execution(workflow_id="gw-1", actor_id="ai", actor_kind=AuditActorKind.AI)


def test_ai_cannot_submit_execution_result() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x",
    )
    orch.start_execution(workflow_id="gw-1", actor_id="u-b", actor_kind=AuditActorKind.USER)
    with pytest.raises(EnterpriseRedLineViolationError):
        orch.submit_execution_result(
            workflow_id="gw-1", action="a", actor="ai", actor_kind=AuditActorKind.AI,
        )


def test_execution_record_requires_human_actor_kind() -> None:
    # GovernanceExecutionRecord 构造期强制 actor_kind=='user'
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceExecutionRecord(
            record_id="rec-1", workflow_id="gw-1", action="a", actor="ai",
            actor_kind="ai", source="s",
        )


# 任务4-②：确认通过可派生 3.8.21 治理任务（仍由真实人工 actor 登记）
def test_human_confirm_can_derive_governance_task() -> None:
    fake = _FakeGovernanceWorkflow()
    orch = _orchestrator(governance_workflow=fake)
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x", derive_task=True, task_id="gt-1",
    )
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["task_id"] == "gt-1"
    assert call["source_type"] is GovernanceTaskSourceType.GOVERNANCE_INSIGHT
    assert call["actor_id"] == "u-a"
    assert call["actor_kind"] is AuditActorKind.USER


# ---------------------------------------------------------------------------
# 任务5：审计记录
# ---------------------------------------------------------------------------

def test_audit_records_created_and_reviewed_and_executed() -> None:
    orch = _orchestrator()
    orch.register_candidate(workflow_id="gw-1", source_type="human_reported", source_id="r")
    orch.submit_for_review(workflow_id="gw-1")
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x",
    )
    orch.start_execution(workflow_id="gw-1", actor_id="u-b", actor_kind=AuditActorKind.USER)
    orch.submit_execution_result(
        workflow_id="gw-1", action="a", actor="u-b", actor_kind=AuditActorKind.USER,
        result="done",
    )
    cats = {r.category for r in orch._audit._records}
    assert AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION in cats


def test_audit_records_actor_kind_for_human_actions() -> None:
    orch = _orchestrator()
    _to_under_review(orch)
    orch.human_confirm(
        workflow_id="gw-1", reviewer_id="u-a", reviewer_kind=AuditActorKind.USER,
        decision="confirmed", reason="x",
    )
    # submit_for_review 是 AI 推送（合法、actor_kind=AI）；human_confirm 才是人工研判
    # 决定（actor_kind=USER）。审计记录 id 以 "gwr-" 前缀标识人工确认动作。
    human_review_recs = [
        r for r in orch._audit._records
        if r.category is AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW
        and r.record_id.startswith("gwr-")
    ]
    assert human_review_recs
    assert human_review_recs[0].actor_kind is AuditActorKind.USER


# ---------------------------------------------------------------------------
# 任务6：禁止自动执行（结构级禁名 + 状态机无 AUTO 态）
# ---------------------------------------------------------------------------

def test_forbidden_auto_methods_are_blocked() -> None:
    orch = _orchestrator()
    for name in ("auto_approve", "auto_execute", "auto_close_workflow",
                 "auto_signoff_workflow", "generate_policy", "decide_workflow"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(orch, name)


def test_workflow_status_has_no_auto_states() -> None:
    values = {s.value for s in GovernanceWorkflowStatus}
    for forbidden in ("auto_approved", "auto_executed", "auto_closed"):
        assert forbidden not in values


def test_workflow_review_decision_has_no_auto_approved() -> None:
    values = {d.value for d in WorkflowReviewDecision}
    assert "auto_approved" not in values
    assert "ai_confirmed" not in values


def test_safety_invariants_ok_held() -> None:
    # 红线① 不变量在测试全程保持
    assert safety_invariants_ok() is True

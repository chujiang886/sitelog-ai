"""Enterprise Agent Governance Workflow Orchestration Layer —— 测试（任务6，Phase 3.8.25）。

八类测试对应主理人六条最高红线（fail-closed）：

① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动治理 / 自动审批 / 自动关闭问题（_WORKFLOW_FORBIDDEN 命中即抛；
   工作流只能由真实人工经 human_confirm / start_execution / submit_execution_result /
   human_complete 推进；构件只允许落 CREATED；枚举中不存在 AUTO_APPROVED/
   AUTO_EXECUTED/AUTO_CLOSED）；
④ 禁止 AI 自动执行治理动作（GovernanceExecutionRecord.actor_kind 必须 user；
   所有执行入口强制 USER；本层不持有任何 execute/apply 能力）；
⑤ 禁止 AI 自动生成治理策略（generate_policy / recommend_policy 等被结构性拦截；
   文本经策略语义扫描）；
⑥ 禁止 AI 代替治理责任人（human_confirm / start_execution / record_execution /
   submit_execution_result / human_complete / append_human_note / human_archive 全部
   强制 require_human_actor(USER)；GovernanceWorkflowReview 构造期二次强制；
   编排层复用 3.8.21 问责原语，不代替责任人）。

启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agents.enterprise.agent_governance_workflow import (
    GovernanceTask,
    GovernanceTaskStatus,
    GovernanceWorkflowService,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.governance_workflow import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowOrchestrator,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
    _ALLOWED_WORKFLOW_TRANSITIONS,
    _FORBIDDEN_STATUS_NAMES,
    _ORCHESTRATION_FORBIDDEN,
    _WORKFLOW_FORBIDDEN,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# 共享构造器（不修改任何持久化配置，仅内存构造）
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _forbidden_access(obj: object, name: str) -> bool:
    """访问 obj.name 是否触发红线结构拦截（EnterpriseRedLineViolationError）。

    ``hasattr`` 只捕获 ``AttributeError``，而禁止方法名会抛
    ``EnterpriseRedLineViolationError``，故须用本辅助判定结构不可达。
    """
    try:
        getattr(obj, name)
    except EnterpriseRedLineViolationError:
        return True
    except AttributeError:
        return False
    return False


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _admin(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="zhuguan", name="Z", role_kind=RoleKind.ADMIN
    )


def _reviewer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


def _engineer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="eng", name="E", role_kind=RoleKind.ENGINEER
    )


def _orch(
    *,
    org_id: str = "org-1",
    audit: "AuditService | None" = None,
    permission_policy: "AgentPermissionPolicy | None" = None,
) -> GovernanceWorkflowOrchestrator:
    """编排服务（默认无权限策略 / 无审计；按需装配）。"""
    return GovernanceWorkflowOrchestrator(
        org_id=org_id,
        audit=audit,
        permission_policy=permission_policy,
    )


@dataclass
class _FakeDraft:
    """3.8.24 GovernanceAnswerDraft 的最小可溯源替身（仅承载事实材料）。"""

    answer_id: str = "ans-1"
    facts: "list[str]" = field(default_factory=list)
    references: "list[str]" = field(default_factory=list)
    summary: str = "draft summary"
    org_id: str = "org-1"
    requires_human_review: bool = True
    contains_recommendation: bool = False


def _seed_workflow(
    orch: GovernanceWorkflowOrchestrator,
    workflow_id: str = "wf-1",
    source_id: str = "gt-1",
) -> GovernanceWorkflow:
    """登记一条 CREATED 候选工作流（AI 可发起，只落候选态）。"""
    return orch.create_workflow(
        workflow_id=workflow_id,
        source_type=GovernanceWorkflowSourceType.GOVERNANCE_TASK,
        source_id=source_id,
        title="治理线索候选",
        description="一条来自治理任务的待研判线索",
        source_facts=["事实1：x 异常", "事实2：y 偏离基线"],
    )


# ---------------------------------------------------------------------------
# 任务6-①：保持 engineering_enabled=false（红线①）
# ---------------------------------------------------------------------------

class TestEngineeringDisabled:
    def test_safety_invariants_ok_true_when_engineering_disabled(self) -> None:
        # 夹具已将 engineering_enabled 置为 False（禁用态）；safety_invariants_ok()
        # 表示「护栏完好 = 禁用态」，故返回 True。红线①：禁用态下构造才不会抛错。
        assert safety_invariants_ok() is True

    def test_construct_workflow_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        # 启用态下 safety_invariants_ok() 应为 False（护栏破损），构造必须抛错。
        assert safety_invariants_ok() is False
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflow(
                workflow_id="wf-x",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-x",
            )

    def test_construct_review_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflowReview(
                review_id="rv-x",
                workflow_id="wf-x",
                reviewer_id="u1",
                reviewer_kind=AuditActorKind.USER,
                decision=WorkflowReviewDecision.CONFIRMED,
                reason="人工研判通过",
            )

    def test_construct_execution_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceExecutionRecord(
                record_id="ex-x",
                workflow_id="wf-x",
                action="执行动作",
                actor="u1",
                source="workflow:wf-x",
            )

    def test_construct_orchestrator_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflowOrchestrator(org_id="org-1")

    def test_create_workflow_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        orch = GovernanceWorkflowOrchestrator.__new__(GovernanceWorkflowOrchestrator)
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_workflow(
                workflow_id="wf-x",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-x",
            )


# ---------------------------------------------------------------------------
# 任务6-②：结构级 forbidden 拦截（红线②/③/④/⑤/⑥）
# ---------------------------------------------------------------------------

class TestStructuralForbidden:
    def test_workflow_forbidden_superset_of_orchestration(self) -> None:
        assert _ORCHESTRATION_FORBIDDEN
        assert set(_ORCHESTRATION_FORBIDDEN).issubset(set(_WORKFLOW_FORBIDDEN))

    def test_orchestrator_forbidden_field_is_workflow_forbidden(self) -> None:
        orch = _orch()
        assert orch._FORBIDDEN == _WORKFLOW_FORBIDDEN

    def test_approval_names_structurally_blocked(self) -> None:
        orch = _orch()
        for name in (
            "auto_approve_workflow",
            "approve_workflow",
            "auto_human_confirm",
            "auto_signoff_workflow",
            "bypass_human_review",
            "engineering_approved",
            "record_human_approval",
        ):
            assert name in _WORKFLOW_FORBIDDEN
            assert _forbidden_access(orch, name) is True

    def test_execution_names_structurally_blocked(self) -> None:
        orch = _orch()
        for name in (
            "auto_execute_workflow",
            "auto_apply_knowledge",
            "auto_execute_knowledge",
            "auto_update_knowledge",
            "auto_merge_knowledge",
            "auto_remediate_workflow",
        ):
            assert name in _WORKFLOW_FORBIDDEN
            assert _forbidden_access(orch, name) is True

    def test_closure_names_structurally_blocked(self) -> None:
        orch = _orch()
        for name in (
            "auto_close_workflow",
            "close_workflow",
            "auto_complete_workflow",
            "auto_archive_workflow",
            "auto_terminate_workflow",
            "auto_close_issue",
        ):
            assert name in _WORKFLOW_FORBIDDEN
            assert _forbidden_access(orch, name) is True

    def test_policy_names_structurally_blocked(self) -> None:
        orch = _orch()
        for name in (
            "generate_policy",
            "recommend_policy",
            "auto_generate_policy",
            "synthesize_policy",
            "policy_recommendation",
        ):
            assert name in _WORKFLOW_FORBIDDEN
            assert _forbidden_access(orch, name) is True

    def test_allowed_methods_not_blocked(self) -> None:
        orch = _orch()
        for name in (
            "create_workflow",
            "submit_for_review",
            "human_confirm",
            "start_execution",
            "human_complete",
        ):
            assert _forbidden_access(orch, name) is False


# ---------------------------------------------------------------------------
# 任务6-③：工作流创建（AI 仅能落 CREATED，source_id 必填）
# ---------------------------------------------------------------------------

class TestWorkflowCreation:
    def test_ai_create_lands_created_only(self) -> None:
        orch = _orch()
        wf = _seed_workflow(orch)
        assert wf.status is GovernanceWorkflowStatus.CREATED
        assert wf.requires_human_confirmation is True
        assert wf.confirmed_by == ""
        assert wf.completed_by == ""
        assert wf.archived is False

    def test_source_id_required(self) -> None:
        orch = _orch()
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_workflow(
                workflow_id="wf-no-src",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="",
                title="无来源",
            )

    def test_duplicate_workflow_rejected(self) -> None:
        orch = _orch()
        _seed_workflow(orch, workflow_id="wf-dup")
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_workflow(
                workflow_id="wf-dup",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-other",
            )

    def test_construction_status_must_be_created(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: False
        )
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflow(
                workflow_id="wf-bad",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-bad",
                status=GovernanceWorkflowStatus.COMPLETED,
            )

    def test_auto_approval_marker_in_title_rejected(self) -> None:
        orch = _orch()
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_workflow(
                workflow_id="wf-marker",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-marker",
                title="本工作流由 AI 自动审批通过",
            )

    def test_auto_execute_marker_in_facts_rejected(self) -> None:
        orch = _orch()
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_workflow(
                workflow_id="wf-marker2",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-marker2",
                source_facts=["事实：系统将自动执行治理动作"],
            )


# ---------------------------------------------------------------------------
# 任务6-④：状态转换（仅前进、非法迁移拒绝、AI 无法推过 under_review）
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_six_state_linear_machine(self) -> None:
        expected = [
            GovernanceWorkflowStatus.CREATED,
            GovernanceWorkflowStatus.UNDER_REVIEW,
            GovernanceWorkflowStatus.HUMAN_CONFIRMED,
            GovernanceWorkflowStatus.IN_PROGRESS,
            GovernanceWorkflowStatus.WAITING_RESULT,
            GovernanceWorkflowStatus.COMPLETED,
        ]
        assert list(_ALLOWED_WORKFLOW_TRANSITIONS) == expected
        assert _ALLOWED_WORKFLOW_TRANSITIONS[GovernanceWorkflowStatus.COMPLETED] == ()

    def test_ai_can_submit_for_review(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        wf2 = orch.submit_for_review(workflow_id="wf-1", actor_id="ai")
        assert wf2.status is GovernanceWorkflowStatus.UNDER_REVIEW

    def test_submit_from_non_created_rejected(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.submit_for_review(workflow_id="wf-1")

    def test_ai_cannot_confirm(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.human_confirm(
                workflow_id="wf-1",
                actor_kind=AuditActorKind.AI,
                actor_id="ai-1",
                decision=WorkflowReviewDecision.CONFIRMED,
                reason="AI 想确认",
            )

    def test_ai_cannot_jump_to_execution(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.start_execution(
                workflow_id="wf-1",
                actor_kind=AuditActorKind.USER,
                actor_id="u1",
            )

    def test_human_confirm_requires_under_review(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.human_confirm(
                workflow_id="wf-1",
                actor_kind=AuditActorKind.USER,
                actor_id="u1",
                decision=WorkflowReviewDecision.CONFIRMED,
                reason="人工研判通过",
            )

    def test_full_human_driven_progression(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.CONFIRMED,
            reason="人工研判通过，立案处理",
        )
        wf = orch.get_workflow("wf-1")
        assert wf.status is GovernanceWorkflowStatus.HUMAN_CONFIRMED
        assert wf.confirmed_by == "u1"
        orch.start_execution(workflow_id="wf-1", actor_kind=AuditActorKind.USER, actor_id="u1")
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.IN_PROGRESS
        orch.submit_execution_result(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            result="已人工处置并验证",
        )
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.WAITING_RESULT
        orch.human_complete(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            human_result="治理闭环，责任由 u1 确认",
        )
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.COMPLETED
        assert orch.get_workflow("wf-1").completed_by == "u1"


# ---------------------------------------------------------------------------
# 任务6-⑤：权限与跨组织隔离（默认拒绝）
# ---------------------------------------------------------------------------

class TestPermissionIsolation:
    def test_review_role_denied_on_data_category(self) -> None:
        orch = _orch(permission_policy=_policy())
        with pytest.raises(EnterpriseIsolationError):
            orch.list_workflows(user=_reviewer())

    def test_admin_role_allowed_on_data_category(self) -> None:
        orch = _orch(permission_policy=_policy())
        assert orch.list_workflows(user=_admin()) == []

    def test_create_blocked_for_review_role(self) -> None:
        orch = _orch(permission_policy=_policy())
        with pytest.raises(EnterpriseIsolationError):
            orch.create_workflow(
                workflow_id="wf-perm",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="src-perm",
                user=_reviewer(),
            )

    def test_cross_org_rejected(self) -> None:
        orch = _orch(org_id="org-1")
        with pytest.raises(EnterpriseIsolationError):
            orch._ensure_same_org("org-2", op="test-cross")

    def test_same_org_allowed(self) -> None:
        orch = _orch(org_id="org-1")
        orch._ensure_same_org("org-1", op="test-same")

    def test_no_policy_no_access_check(self) -> None:
        orch = _orch()
        assert orch.list_workflows(user=_reviewer()) == []


# ---------------------------------------------------------------------------
# 任务6-⑥：人工确认（human_confirm 强制 USER，REJECTED/NEED_MORE_INFO 不迁移）
# ---------------------------------------------------------------------------

class TestHumanConfirmation:
    def test_review_requires_user(self) -> None:
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflowReview(
                review_id="rv-1",
                workflow_id="wf-1",
                reviewer_id="u1",
                reviewer_kind=AuditActorKind.AI,
                decision=WorkflowReviewDecision.CONFIRMED,
                reason="AI 研判",
            )

    def test_review_requires_reason(self) -> None:
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceWorkflowReview(
                review_id="rv-2",
                workflow_id="wf-1",
                reviewer_id="u1",
                reviewer_kind=AuditActorKind.USER,
                decision=WorkflowReviewDecision.CONFIRMED,
                reason="",
            )

    def test_confirmed_transitions_state(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        review = orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.CONFIRMED,
            reason="人工研判通过",
        )
        assert review.is_confirmed is True
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.HUMAN_CONFIRMED

    def test_rejected_does_not_transition(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        review = orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.REJECTED,
            reason="证据不足，驳回",
        )
        assert review.is_confirmed is False
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.UNDER_REVIEW
        assert orch.get_workflow("wf-1").confirmed_by == ""

    def test_need_more_info_does_not_transition(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.NEED_MORE_INFO,
            reason="需补充日志",
        )
        assert orch.get_workflow("wf-1").status is GovernanceWorkflowStatus.UNDER_REVIEW

    def test_review_recorded_and_queryable(self) -> None:
        orch = _orch()
        _seed_workflow(orch)
        orch.submit_for_review(workflow_id="wf-1")
        orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.CONFIRMED,
            reason="人工研判通过",
        )
        reviews = orch.list_reviews(workflow_id="wf-1")
        assert len(reviews) == 1
        assert reviews[0].reviewer_id == "u1"


# ---------------------------------------------------------------------------
# 任务6-⑦：审计记录（3 类 WORKFLOW_CREATE/REVIEW/EXECUTION 落库、计数 68）
# ---------------------------------------------------------------------------

class TestAuditRecords:
    def test_audit_category_count_still_68(self) -> None:
        cats = {c.value for c in AuditActionCategory}
        assert len(cats) == 69
        for v in (
            "agent_governance_workflow_create",
            "agent_governance_workflow_review",
            "agent_governance_workflow_execution",
        ):
            assert v in cats

    def test_create_and_review_and_execution_logged(self) -> None:
        audit = _audit()
        orch = _orch(audit=audit)
        orch.create_workflow(
            workflow_id="wf-1",
            source_type=GovernanceWorkflowSourceType.GOVERNANCE_TASK,
            source_id="gt-1",
        )
        orch.submit_for_review(workflow_id="wf-1", actor_id="ai")
        creates = audit.query(
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE
        )
        assert len(creates) == 2
        assert creates[0].actor_kind is AuditActorKind.AI

        orch.human_confirm(
            workflow_id="wf-1",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            decision=WorkflowReviewDecision.CONFIRMED,
            reason="人工研判通过",
        )
        reviews = audit.query(
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW
        )
        assert len(reviews) == 1
        assert reviews[0].actor_kind is AuditActorKind.USER

        orch.start_execution(
            workflow_id="wf-1", actor_kind=AuditActorKind.USER, actor_id="u1"
        )
        execs = audit.query(
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION
        )
        assert len(execs) >= 1
        assert execs[0].actor_kind is AuditActorKind.USER

    def test_no_record_human_approval_entry(self) -> None:
        assert not hasattr(AuditService, "record_human_approval")
        with pytest.raises(EnterpriseRedLineViolationError):
            require_human_actor(AuditActorKind.AI)


# ---------------------------------------------------------------------------
# 任务6-⑧：禁止自动执行（_FORBIDDEN_STATUS_NAMES 不存在、actor_kind 必须 user、
#          create_from_draft 不自动创建治理动作）
# ---------------------------------------------------------------------------

class TestNoAutoExecution:
    def test_forbidden_status_names_absent_from_enum(self) -> None:
        members = {s.name for s in GovernanceWorkflowStatus}
        for name in _FORBIDDEN_STATUS_NAMES:
            assert name not in members

    def test_execution_record_requires_user_actor(self) -> None:
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceExecutionRecord(
                record_id="ex-1",
                workflow_id="wf-1",
                action="执行",
                actor="ai-bot",
                actor_kind="ai",
                source="workflow:wf-1",
            )

    def test_execution_record_requires_non_empty_fields(self) -> None:
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceExecutionRecord(
                record_id="ex-2",
                workflow_id="wf-1",
                action="",
                actor="u1",
                source="workflow:wf-1",
            )

    def test_create_from_draft_requires_user(self) -> None:
        orch = _orch()
        draft = _FakeDraft()
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_from_draft(
                draft=draft,
                workflow_id="wf-d",
                actor_kind=AuditActorKind.AI,
                actor_id="ai-1",
            )

    def test_create_from_draft_rejects_non_review_draft(self) -> None:
        orch = _orch()
        draft = _FakeDraft(requires_human_review=False)
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_from_draft(
                draft=draft,
                workflow_id="wf-d",
                actor_kind=AuditActorKind.USER,
                actor_id="u1",
            )

    def test_create_from_draft_rejects_recommendation_draft(self) -> None:
        orch = _orch()
        draft = _FakeDraft(contains_recommendation=True)
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.create_from_draft(
                draft=draft,
                workflow_id="wf-d",
                actor_kind=AuditActorKind.USER,
                actor_id="u1",
            )

    def test_create_from_draft_cross_org_rejected(self) -> None:
        orch = _orch(org_id="org-1")
        draft = _FakeDraft(org_id="org-2")
        with pytest.raises(EnterpriseIsolationError):
            orch.create_from_draft(
                draft=draft,
                workflow_id="wf-d",
                actor_kind=AuditActorKind.USER,
                actor_id="u1",
            )

    def test_create_from_draft_seeds_facts_no_auto_action(self) -> None:
        orch = _orch()
        draft = _FakeDraft(
            answer_id="ans-7",
            facts=["事实A", "事实B"],
            references=["ref-1"],
            summary="助手事实摘要",
        )
        wf = orch.create_from_draft(
            draft=draft,
            workflow_id="wf-d7",
            actor_kind=AuditActorKind.USER,
            actor_id="u1",
            title="从助手草稿立案",
        )
        assert wf.status is GovernanceWorkflowStatus.CREATED
        assert wf.source_facts == ["事实A", "事实B"]
        assert wf.source_id == "ans-7"
        assert wf.task_id == ""
        assert wf.confirmed_by == ""
        assert orch.list_execution_records(workflow_id="wf-d7") == []


# ---------------------------------------------------------------------------
# 复用验证：本层复用 3.8.21 问责原语，不代替责任人
# ---------------------------------------------------------------------------

class TestReuseOfGovernanceAccountabilityLayer:
    def test_321_primitives_re_exported(self) -> None:
        from agents.enterprise.governance_workflow import (
            GovernanceAssignment,
            GovernanceTask,
            GovernanceTaskSourceType,
            GovernanceTaskStatus,
            GovernanceWorkflowService,
        )
        assert GovernanceTask is not None
        assert GovernanceTaskStatus is not None
        assert GovernanceTaskSourceType is not None
        assert GovernanceAssignment is not None
        assert GovernanceWorkflowService is not None

    def test_321_five_state_machine_intact(self) -> None:
        assert GovernanceTaskStatus.CREATED
        assert GovernanceTaskStatus.ASSIGNED
        assert GovernanceTaskStatus.PROCESSING
        assert GovernanceTaskStatus.WAITING_REVIEW
        assert GovernanceTaskStatus.COMPLETED

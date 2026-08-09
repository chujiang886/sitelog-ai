"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 经验沉淀工作流（任务4，Phase 3.8.7）。

状态机（知识反馈闭环）：
    feedback_received → analysis → candidate_created → human_review → accepted / rejected

组合 ``FeedbackService`` / ``KnowledgeUpdateCandidateService`` / ``InsightValidationService``
编排闭环。其中 ``human_review`` 节点**严格**由真实 USER 执行（``require_human_actor``，
红线⑥）；其余节点可由 AI 提议/登记，但**绝不**自动落地知识（候选恒 requires_human_review，
红线③）。

红线（fail-closed，复用 3.8.0~3.8.6 基座 + 3.8.7 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``human_review`` 必须 ``require_human_actor(USER)``（红线⑥：AI 不得代替人工做复核判定）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动改知识入口（``auto_update_knowledge`` / ``auto_merge_knowledge`` /
  ``auto_approve_knowledge``）与自动经营决策入口（红线④/⑤）。
- 子服务（候选）只提候选，绝不自动写入知识库（red line ③）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import AuditService, require_human_actor
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.feedback import FeedbackRecord, FeedbackService
from agents.enterprise.knowledge_candidate import (
    KnowledgeChangeType,
    KnowledgeUpdateCandidate,
    KnowledgeUpdateCandidateService,
)
from agents.enterprise.insight_validation import (
    InsightValidationService,
    ValidationResult,
)


class ImprovementStage(str, Enum):
    """经验沉淀工作流阶段（任务4）。

    human_review 之后的终态为 accepted / rejected，且只能由真实 USER 推进（红线⑥）。
    """

    FEEDBACK_RECEIVED = "feedback_received"
    ANALYSIS = "analysis"
    CANDIDATE_CREATED = "candidate_created"
    HUMAN_REVIEW = "human_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class ImprovementCase:
    """经验沉淀案例（任务4，单条反馈的闭环追踪）。"""

    feedback_id: str
    candidate_id: str = ""
    stage: ImprovementStage = field(default=ImprovementStage.FEEDBACK_RECEIVED)
    current_reviewer: str = ""
    review_comment: str = ""
    decided_at: str = ""


class KnowledgeImprovementWorkflow(_RedLineForbiddenMixin):
    """经验沉淀工作流（任务4）。

    编排 feedback_received → analysis → candidate_created → human_review → accepted /
    rejected。组合 feedback / candidate / validation 三个子服务（共享同一 audit 实例）。
    human_review 节点严格 require_human_actor(USER)（红线⑥）。
    本工作流**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_update_knowledge 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③：禁止 AI 自动改知识
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        # 红线④/⑤：禁止自动经营决策 / 审批 / 管理建议
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "AnalyticsVisibilityPolicy | None" = None,
        feedback_service: "FeedbackService | None" = None,
        candidate_service: "KnowledgeUpdateCandidateService | None" = None,
        validation_service: "InsightValidationService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeImprovementWorkflow（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self.feedback = feedback_service or FeedbackService(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )
        self.candidates = candidate_service or KnowledgeUpdateCandidateService(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )
        self.validations = validation_service or InsightValidationService(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )
        self._cases: dict[str, ImprovementCase] = {}

    def receive_feedback(
        self,
        *,
        feedback_id: str,
        user_id: str,
        source_type: str,
        content: str,
        related_insight: str = "",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> FeedbackRecord:
        """闭环起点：接收一条用户反馈（stage: feedback_received）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下接收反馈（红线①/⑤）"
            )
        rec = self.feedback.create_feedback(
            feedback_id=feedback_id,
            user_id=user_id,
            source_type=source_type,
            content=content,
            related_insight=related_insight,
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        self._cases[feedback_id] = ImprovementCase(
            feedback_id=feedback_id, stage=ImprovementStage.FEEDBACK_RECEIVED
        )
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"wf-receive-{feedback_id}",
                actor_id=actor_id,
                action="feedback_received",
                target=feedback_id,
                detail=f"source_type={source_type}",
                ts=created_at,
            )
        return rec

    def begin_analysis(self, *, feedback_id: str, ts: str = "") -> ImprovementCase:
        """进入分析阶段（stage: analysis）。分析是对反馈的事实梳理，不产生任何知识落地。"""
        case = self._require_case(feedback_id)
        if case.stage != ImprovementStage.FEEDBACK_RECEIVED:
            raise EnterpriseRedLineViolationError(
                f"反馈 {feedback_id!r} 当前阶段 {case.stage.value!r} 不能进入分析"
                f"（仅 feedback_received 可进入 analysis）"
            )
        case.stage = ImprovementStage.ANALYSIS
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"wf-analysis-{feedback_id}",
                actor_id="ai",
                action="analysis_started",
                target=feedback_id,
                ts=ts,
            )
        return case

    def propose_from_analysis(
        self,
        *,
        feedback_id: str,
        candidate_id: str,
        source: str,
        change_type: KnowledgeChangeType,
        content: str,
        evidence: str,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeUpdateCandidate:
        """分析产出知识更新候选（stage: candidate_created）。

        仅提议候选，**绝不**自动写入知识库（red line ③）；候选 requires_human_review 恒 True。
        """
        case = self._require_case(feedback_id)
        if case.stage != ImprovementStage.ANALYSIS:
            raise EnterpriseRedLineViolationError(
                f"反馈 {feedback_id!r} 当前阶段 {case.stage.value!r} 不能提议候选"
                f"（须先 begin_analysis 进入 analysis）"
            )
        cand = self.candidates.propose_candidate(
            candidate_id=candidate_id,
            source=source,
            change_type=change_type,
            content=content,
            evidence=evidence,
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        case.candidate_id = candidate_id
        case.stage = ImprovementStage.CANDIDATE_CREATED
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"wf-candidate-{feedback_id}",
                actor_id=actor_id,
                action="candidate_created",
                target=feedback_id,
                detail=f"candidate_id={candidate_id}",
                ts=created_at,
            )
        return cand

    def human_review(
        self,
        *,
        feedback_id: str,
        decision: ImprovementStage,
        actor_id: str,
        actor_kind: Any,
        comment: str = "",
        ts: str = "",
    ) -> ImprovementCase:
        """人工复核节点（红线⑥：必须由真实 USER 发起；AI 不得代替人工判定）。

        ``decision`` 须为 ``ImprovementStage.ACCEPTED`` 或 ``ImprovementStage.REJECTED``。
        """
        require_human_actor(actor_kind)
        case = self._require_case(feedback_id)
        if case.stage != ImprovementStage.CANDIDATE_CREATED:
            raise EnterpriseRedLineViolationError(
                f"反馈 {feedback_id!r} 当前阶段 {case.stage.value!r} 不能进入人工复核"
                f"（须先 propose_from_analysis 进入 candidate_created）"
            )
        if decision not in (ImprovementStage.ACCEPTED, ImprovementStage.REJECTED):
            raise EnterpriseRedLineViolationError(
                f"human_review 决策须为 accepted / rejected，收到 {decision!r}（红线⑥）"
            )
        case.stage = ImprovementStage.HUMAN_REVIEW
        if decision == ImprovementStage.ACCEPTED:
            self.feedback.accept(
                feedback_id=feedback_id,
                actor_id=actor_id,
                actor_kind=actor_kind,
                ts=ts,
                comment=comment,
            )
            case.stage = ImprovementStage.ACCEPTED
        else:
            self.feedback.reject(
                feedback_id=feedback_id,
                actor_id=actor_id,
                actor_kind=actor_kind,
                ts=ts,
                comment=comment,
            )
            case.stage = ImprovementStage.REJECTED
        case.current_reviewer = actor_id
        case.review_comment = comment
        case.decided_at = ts
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"wf-review-{feedback_id}",
                actor_id=actor_id,
                action=f"human_review_{decision.value}",
                target=feedback_id,
                detail=comment,
                ts=ts,
            )
        return case

    def add_validation(
        self,
        *,
        validation_id: str,
        feedback_id: str,
        validator: str,
        result: ValidationResult,
        comment: str = "",
        timestamp: str = "",
        actor_id: str = "",
        actor_kind: Any = None,
    ) -> "ImprovementCase":
        """为候选关联的洞察补充人工验证（红线⑥：必须由真实 USER 发起）。

        验证是对候选 evidence 中关联洞察的事实确认，不替代 human_review 的接受/拒绝判定。
        """
        require_human_actor(actor_kind)
        case = self._require_case(feedback_id)
        self.validations.create_validation(
            validation_id=validation_id,
            insight_id=case.candidate_id,
            validator=validator,
            result=result,
            comment=comment,
            timestamp=timestamp,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        return case

    def get_case(self, *, feedback_id: str) -> ImprovementCase:
        """读取案例（按组织作用域）。"""
        return self._require_case(feedback_id)

    def list_cases(
        self, *, stage: "ImprovementStage | None" = None
    ) -> list[ImprovementCase]:
        """列出当前组织下案例（可按 stage 过滤）。"""
        out = [c for c in self._cases.values() if c is not None]
        # 仅返回本组织反馈（feedback 已按 org 隔离；此处按 case 所属反馈的 org 校验）
        filtered = []
        for c in out:
            try:
                self.feedback.get(feedback_id=c.feedback_id)
                filtered.append(c)
            except Exception:
                # 跨域 / 不存在的 case 不暴露
                continue
        if stage is not None:
            filtered = [c for c in filtered if c.stage == stage]
        return filtered

    def _require_case(self, feedback_id: str) -> ImprovementCase:
        from agents.enterprise.organization import EnterpriseIsolationError

        # 先确认反馈在本组织内存在（跨域访问抛隔离错误）
        self.feedback.get(feedback_id=feedback_id)
        case = self._cases.get(feedback_id)
        if case is None:
            raise EnterpriseIsolationError(f"经验沉淀案例 {feedback_id!r} 不存在")
        return case


__all__ = [
    "ImprovementStage",
    "ImprovementCase",
    "KnowledgeImprovementWorkflow",
]

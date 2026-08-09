"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 用户反馈（任务1，Phase 3.8.7）。

新增：
- ``FeedbackStatus``：反馈状态（submitted / reviewing / accepted / rejected）。
- ``FeedbackRecord``：用户反馈记录（feedback_id / org_id / user_id / source_type /
  content / related_insight / created_at / status）。
- ``FeedbackService``：创建/读取/列出反馈；提交后须人工审核（start_review / accept /
  reject 必须由真实 USER 发起，红线⑥）。

红线（fail-closed，复用 3.8.0~3.8.6 基座 + 3.8.7 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``start_review`` / ``accept`` / ``reject`` 必须 ``require_human_actor(USER)``（红线⑥：
  AI 不得代替人工做审核判定）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动改知识入口（``auto_update_knowledge`` / ``auto_merge_knowledge`` /
  ``auto_approve_knowledge``，红线③）与自动经营决策入口（红线④/⑤）。
- 可选联动 ``AuditService.record_feedback_action`` 如实标注发起方 actor（红线⑥）。
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


class FeedbackStatus(str, Enum):
    """反馈人工审核状态（任务1）。

    流程：submitted → reviewing → accepted / rejected。accepted / rejected 只能由真实
    USER（专家/主理人）执行（红线⑥）。
    """

    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class FeedbackRecord:
    """用户反馈记录（任务1）。

    仅承载反馈事实（谁、什么渠道、什么内容、关联哪条洞察），不承载任何决策/批准语义；
    ``status`` 必须经过人工审核流转，AI 不得直接置 accepted / rejected。
    """

    feedback_id: str
    org_id: str
    user_id: str
    source_type: str               # 反馈来源类型（如 app / email / meeting / dashboard ...）
    content: str                   # 反馈内容（中性描述，事实型）
    related_insight: str = ""      # 关联的数据洞察 id（DataInsight.insight_id，可空）
    created_at: str = ""
    status: FeedbackStatus = field(default=FeedbackStatus.SUBMITTED)


class FeedbackService(_RedLineForbiddenMixin):
    """用户反馈服务（任务1）。

    仅登记/读取事实型用户反馈；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。人工审核节点（start_review /
    accept / reject）强制 ``require_human_actor(USER)``（红线⑥）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
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
        # 红线③：禁止 AI 自动改知识（反馈本身不写知识库，仅提候选，由候选服务结构保证）
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
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "FeedbackService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._feedbacks: dict[str, FeedbackRecord] = {}

    def create_feedback(
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
        """登记一条用户反馈（默认 AI 代提交，status=submitted，待人工审核）。

        登记后如实记录 ``record_feedback_action``（actor 默认 AI，红线⑥：绝不伪造为人工）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记反馈（红线①/⑤）"
            )
        rec = FeedbackRecord(
            feedback_id=feedback_id,
            org_id=self._org_id,
            user_id=user_id,
            source_type=source_type,
            content=content,
            related_insight=related_insight,
            created_at=created_at,
            status=FeedbackStatus.SUBMITTED,
        )
        self._feedbacks[feedback_id] = rec
        if self._audit is not None:
            self._audit.record_feedback_action(
                record_id=f"feedback-{feedback_id}",
                actor_id=actor_id,
                action="submit_feedback",
                target=feedback_id,
                detail=(
                    f"user_id={user_id};source_type={source_type};"
                    f"related_insight={related_insight}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return rec

    def get(self, *, feedback_id: str) -> FeedbackRecord:
        """按组织作用域读取反馈（跨域访问抛隔离错误）。"""
        return self._get_scoped(feedback_id)

    def list_feedbacks(
        self,
        *,
        source_type: str = "",
        status: "FeedbackStatus | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[FeedbackRecord]:
        """列出当前组织下反馈（可按 source_type / status 过滤）。

        ``role`` 参数保留以对齐聚合层约定；反馈属运营事实数据，按组织作用域返回，
        不做角色级隐藏（敏感权限由 visibility 在聚合层统一约束）。
        """
        out = [f for f in self._feedbacks.values() if f.org_id == self._org_id]
        if source_type:
            out = [f for f in out if f.source_type == source_type]
        if status is not None:
            out = [f for f in out if f.status == status]
        return out

    def start_review(
        self,
        *,
        feedback_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
        comment: str = "",
    ) -> FeedbackRecord:
        """进入人工审核（红线⑥：必须由真实 USER 发起）。"""
        require_human_actor(actor_kind)
        rec = self._get_scoped(feedback_id)
        rec.status = FeedbackStatus.REVIEWING
        if self._audit is not None:
            self._audit.record_feedback_action(
                record_id=f"feedback-review-{feedback_id}",
                actor_id=actor_id,
                action="start_review",
                target=feedback_id,
                detail=comment,
                ts=ts,
                actor_kind=actor_kind,
            )
        return rec

    def accept(
        self,
        *,
        feedback_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
        comment: str = "",
    ) -> FeedbackRecord:
        """接受反馈（红线⑥：必须由真实 USER 发起；AI 不得代替人工接受判定）。"""
        require_human_actor(actor_kind)
        rec = self._get_scoped(feedback_id)
        rec.status = FeedbackStatus.ACCEPTED
        if self._audit is not None:
            self._audit.record_feedback_action(
                record_id=f"feedback-accept-{feedback_id}",
                actor_id=actor_id,
                action="accept_feedback",
                target=feedback_id,
                detail=comment,
                ts=ts,
                actor_kind=actor_kind,
            )
        return rec

    def reject(
        self,
        *,
        feedback_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
        comment: str = "",
    ) -> FeedbackRecord:
        """拒绝反馈（红线⑥：必须由真实 USER 发起；AI 不得代替人工拒绝判定）。"""
        require_human_actor(actor_kind)
        rec = self._get_scoped(feedback_id)
        rec.status = FeedbackStatus.REJECTED
        if self._audit is not None:
            self._audit.record_feedback_action(
                record_id=f"feedback-reject-{feedback_id}",
                actor_id=actor_id,
                action="reject_feedback",
                target=feedback_id,
                detail=comment,
                ts=ts,
                actor_kind=actor_kind,
            )
        return rec

    def _get_scoped(self, feedback_id: str) -> FeedbackRecord:
        from agents.enterprise.organization import EnterpriseIsolationError

        rec = self._feedbacks.get(feedback_id)
        if rec is None:
            raise EnterpriseIsolationError(f"反馈 {feedback_id!r} 不存在")
        if rec.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"反馈 {feedback_id!r} 归属组织 {rec.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return rec


__all__ = ["FeedbackStatus", "FeedbackRecord", "FeedbackService"]

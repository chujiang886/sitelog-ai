"""Phase 3.8.26 企业智能体治理驾驶舱服务层（人工操作界面后端核心）。

定位：在 3.8.25 ``GovernanceWorkflowOrchestrator``（治理状态单一真相源）之上，提供
**只读查询 + 单一人工确认入口** 的驾驶舱 API。本服务**不持有任何治理状态**，所有写操作
均委派给编排器（human_confirm），自身只做：权限闸门（默认拒绝）+ 组织隔离 + 人工强制
+ 审计留痕 + 视图整形。

API 形态（对应 Task2 的 HTTP 端点）：
- 只读（GET 等价）：list_workflows / list_pending_reviews / get_workflow_detail /
  get_execution_status / list_audit_records / list_risk_alerts / summary
- 写（POST 等价，强制 USER）：confirm_review

红线（fail-closed，与 3.8.25 同源，结构级 + 语义级 + 类型级三重）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _DASHBOARD_FORBIDDEN`` 结构拦截自动确认/执行/关闭/策略/代替责任人。
③ **不自动治理**：confirm_review 强制 ``require_human_actor(USER)``；AI 调任何写入口
   均被拦截；读接口同样仅对真实 USER 开放（驾驶舱为责任人专属）。
④ **不自动执行**：本服务无任何 execute / apply 能力，执行动作由编排器在人工确认后推进。
⑤ **不自动生成策略 / 不改知识**：本服务对 ``AgentPermissionPolicy`` /
   ``KnowledgeVisibilityPolicy`` 纯只读；不提供任何文本生成/改写入口。
⑥ **不代替责任人**：所有人工节点经编排器 ``require_human_actor(USER)``；审计留痕
   actor / time / action / object（Task5）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditRecord,
    require_human_actor,
)
from agents.enterprise.governance_dashboard.forbidden import _DASHBOARD_FORBIDDEN
from agents.enterprise.governance_dashboard.models import (
    DashboardSummary,
    DashboardUser,
    ExecutionStatusView,
    RiskAlert,
)
from agents.enterprise.governance_workflow.models import (
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
)
from agents.enterprise.identity import IdentityService
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)

# 治理驾驶舱关心 3 类审计（创建 / 研判 / 执行）。
_GOVERNANCE_WORKFLOW_AUDIT_CATEGORIES = (
    AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE,
    AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW,
    AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION,
)


class GovernanceDashboardService(_RedLineForbiddenMixin):
    """治理驾驶舱服务（Task1/2/3/4/5 主体）。

    与 3.8.25 编排器、3.8.24 知识助手、3.8.21 问责层一致：继承
    ``_RedLineForbiddenMixin``，通过 ``_FORBIDDEN`` 拦截禁名方法；只读委托编排器，
    写操作委派编排器。
    """

    # 结构级红线拦截：驾驶舱禁名（3.8.25 编排层 166 项 ∪ 本层增量）。
    _FORBIDDEN = _DASHBOARD_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        orchestrator: Any,  # GovernanceWorkflowOrchestrator（治理状态单一真相源）
        audit: Any = None,  # AuditService
        identity: "Optional[IdentityService]" = None,
        visibility: "Optional[KnowledgeVisibilityPolicy]" = None,
        permission_policy: "Optional[AgentPermissionPolicy]" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceDashboardService（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._orchestrator = orchestrator
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy

    # ------------------------------------------------------------------
    # 隔离与访问控制（红线⑤/⑥：默认拒绝 + 组织隔离 + 人工专属）
    # ------------------------------------------------------------------

    def _ensure_org_scope(self, target_org: str, op: str) -> None:
        """跨组织访问拦截（补 3.8.21/3.8.25 之缺）。"""
        tgt = str(target_org or "").strip()
        if self._org_id and tgt and tgt != self._org_id:
            raise EnterpriseIsolationError(
                f"{op} 拒绝跨组织访问：服务 org={self._org_id!r} 但请求 org={tgt!r}"
                f"（红线⑤/⑥：禁止跨组织读取/处置治理工作流）"
            )

    def _ensure_access(
        self, *, user: Any, resource_category: str = "governance_dashboard"
    ) -> None:
        """默认拒绝的权限闸门（复用 AgentPermissionPolicy）。

        - 无操作者（user is None）→ 拒绝（默认拒绝）。
        - 有权限策略且判定拒绝（或抛异常）→ 拒绝。
        """
        if user is None:
            raise EnterpriseRedLineViolationError(
                "缺少操作者：治理驾驶舱默认拒绝匿名访问（红线⑤）"
            )
        if self._permission_policy is not None:
            allowed = False
            try:
                allowed = bool(
                    self._permission_policy.check_agent_access(
                        user=user, resource_category=resource_category
                    )
                )
            except Exception:
                allowed = False
            if not allowed:
                raise EnterpriseRedLineViolationError(
                    f"权限策略拒绝访问 resource_category={resource_category!r}（默认拒绝，红线⑤）"
                )

    def _require_user(self, user: DashboardUser) -> DashboardUser:
        """驾驶舱仅对真实 USER 开放（读 + 写均强制，红线③/⑥）。"""
        if user is None or not isinstance(user, DashboardUser):
            raise EnterpriseRedLineViolationError(
                "治理驾驶舱仅对真实责任人（USER）开放（红线③/⑥）"
            )
        require_human_actor(user.actor_kind)
        return user

    def _audit_query(self, *, user: DashboardUser, action: str, target: str, detail: str = "") -> None:
        """记录一次驾驶舱查询（Task5：所有 UI 动作可审计）。"""
        if self._audit is not None:
            self._audit.record_dashboard_query(
                record_id=f"dash-{action}-{target}-{id(self)}",
                actor_id=user.actor_id,
                action=action,
                target=target,
                detail=detail,
                ts="",
            )

    # ------------------------------------------------------------------
    # 只读查询（GET 等价）：workflow 列表 / 待审核 / 执行状态 / 审计 / 风险
    # ------------------------------------------------------------------

    def list_workflows(
        self,
        *,
        org_id: str,
        user: DashboardUser,
        status: "Optional[GovernanceWorkflowStatus | str]" = None,
    ) -> List[Any]:
        """列出治理工作流（只读；组织隔离 + 默认拒绝 + 人工专属 + 审计）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "list_workflows")
        self._ensure_access(user=user)
        self._audit_query(user=user, action="list_workflows", target=org_id)
        return self._orchestrator.list_workflows(
            org_id=org_id, status=status, user=user
        )

    def list_pending_reviews(
        self, *, org_id: str, user: DashboardUser
    ) -> List[Any]:
        """待人工研判列表（status == UNDER_REVIEW，只读）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "list_pending_reviews")
        self._ensure_access(user=user)
        self._audit_query(user=user, action="list_pending_reviews", target=org_id)
        return self._orchestrator.list_workflows(
            org_id=org_id, status=GovernanceWorkflowStatus.UNDER_REVIEW, user=user
        )

    def get_workflow_detail(
        self, *, org_id: str, user: DashboardUser, workflow_id: str
    ) -> Any:
        """查看单条工作流详情（只读）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "get_workflow_detail")
        self._ensure_access(user=user)
        wf = self._orchestrator.get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or org_id, "get_workflow_detail")
        self._audit_query(user=user, action="get_workflow_detail", target=workflow_id)
        return wf

    def get_execution_status(
        self, *, org_id: str, user: DashboardUser, workflow_id: str
    ) -> ExecutionStatusView:
        """查看执行状态（状态 + 研判记录 + 执行跟踪记录，只读）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "get_execution_status")
        self._ensure_access(user=user)
        wf = self._orchestrator.get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or org_id, "get_execution_status")
        reviews = self._orchestrator.get_reviews(workflow_id)
        records = self._orchestrator.get_execution_records(workflow_id)
        self._audit_query(user=user, action="get_execution_status", target=workflow_id)
        return ExecutionStatusView(
            workflow_id=wf.workflow_id,
            status=wf.status.value if hasattr(wf.status, "value") else str(wf.status),
            confirmed_by=getattr(wf, "confirmed_by", "") or "",
            confirmed_at=getattr(wf, "confirmed_at", "") or "",
            completed_by=getattr(wf, "completed_by", "") or "",
            completed_at=getattr(wf, "completed_at", "") or "",
            archived=bool(getattr(wf, "archived", False)),
            reviews=list(reviews),
            execution_records=list(records),
        )

    def list_audit_records(
        self,
        *,
        org_id: str,
        user: DashboardUser,
        limit: int = 100,
        target: str = "",
    ) -> List[AuditRecord]:
        """列出治理相关审计记录（创建/研判/执行三类，只读；按 ts 倒序）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "list_audit_records")
        self._ensure_access(user=user)
        self._audit_query(user=user, action="list_audit_records", target=org_id)
        if self._audit is None:
            return []
        merged: List[AuditRecord] = []
        for cat in _GOVERNANCE_WORKFLOW_AUDIT_CATEGORIES:
            merged.extend(
                self._audit.query(category=cat, target=target)
            )
        merged.sort(key=lambda r: (r.ts or ""), reverse=True)
        if limit and limit > 0:
            merged = merged[:limit]
        return merged

    def list_risk_alerts(
        self, *, org_id: str, user: DashboardUser
    ) -> List[RiskAlert]:
        """只读风险提示（由工作流状态派生，不构成 AI 治理决定）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "list_risk_alerts")
        self._ensure_access(user=user)
        self._audit_query(user=user, action="list_risk_alerts", target=org_id)
        workflows = self._orchestrator.list_workflows(org_id=org_id, user=user)
        alerts: List[RiskAlert] = []
        for wf in workflows:
            status_val = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
            if status_val == GovernanceWorkflowStatus.UNDER_REVIEW.value:
                alerts.append(
                    RiskAlert(
                        workflow_id=wf.workflow_id,
                        severity="action",
                        title="待人工研判",
                        message=f"工作流 {wf.workflow_id} 处于待研判态，需真实责任人确认。",
                        status=status_val,
                    )
                )
            elif status_val == GovernanceWorkflowStatus.WAITING_RESULT.value:
                alerts.append(
                    RiskAlert(
                        workflow_id=wf.workflow_id,
                        severity="warning",
                        title="执行结果待确认",
                        message=f"工作流 {wf.workflow_id} 已提交执行结果，待真实责任人完成确认。",
                        status=status_val,
                    )
                )
            elif status_val == GovernanceWorkflowStatus.IN_PROGRESS.value:
                alerts.append(
                    RiskAlert(
                        workflow_id=wf.workflow_id,
                        severity="info",
                        title="执行中",
                        message=f"工作流 {wf.workflow_id} 真实责任人执行中。",
                        status=status_val,
                    )
                )
            elif status_val == GovernanceWorkflowStatus.HUMAN_CONFIRMED.value:
                alerts.append(
                    RiskAlert(
                        workflow_id=wf.workflow_id,
                        severity="info",
                        title="已确认待执行",
                        message=f"工作流 {wf.workflow_id} 已获人工确认，待执行。",
                        status=status_val,
                    )
                )
            elif status_val == GovernanceWorkflowStatus.CREATED.value:
                alerts.append(
                    RiskAlert(
                        workflow_id=wf.workflow_id,
                        severity="info",
                        title="候选未进入研判",
                        message=f"工作流 {wf.workflow_id} 仍为候选态，尚未推送人工研判。",
                        status=status_val,
                    )
                )
        return alerts

    def summary(self, *, org_id: str, user: DashboardUser) -> DashboardSummary:
        """驾驶舱总览（计数聚合，只读）。"""
        self._require_user(user)
        self._ensure_org_scope(org_id, "summary")
        self._ensure_access(user=user)
        workflows = self._orchestrator.list_workflows(org_id=org_id, user=user)
        s = DashboardSummary()
        s.total = len(workflows)
        for wf in workflows:
            status_val = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
            if status_val == GovernanceWorkflowStatus.UNDER_REVIEW.value:
                s.pending_review += 1
            elif status_val == GovernanceWorkflowStatus.IN_PROGRESS.value:
                s.in_progress += 1
            elif status_val == GovernanceWorkflowStatus.WAITING_RESULT.value:
                s.waiting_result += 1
            elif status_val == GovernanceWorkflowStatus.COMPLETED.value:
                s.completed += 1
        s.risk_count = len(self.list_risk_alerts(org_id=org_id, user=user))
        return s

    # ------------------------------------------------------------------
    # 写操作（POST 等价）：唯一人工确认入口（强制 USER）
    # ------------------------------------------------------------------

    def confirm_review(
        self,
        *,
        org_id: str,
        user: DashboardUser,
        workflow_id: str,
        decision: "WorkflowReviewDecision | str",
        reason: str,
        derive_task: bool = False,
        task_id: Optional[str] = None,
        reviewed_at: str = "",
    ) -> Any:
        """人工研判确认（POST /governance/review/confirm 后端，红线③/⑥）。

        强制 ``require_human_actor(USER)``；委派给编排器 ``human_confirm``（其再次强制
        USER 并写审计）。驾驶舱绝不代替责任人点击；AI 调此入口必被拦截。
        """
        # 红线⑥核心：确认人必须是真实 USER（先于任何委派）。
        self._require_user(user)
        self._ensure_org_scope(org_id, "confirm_review")
        self._ensure_access(user=user)

        decision_enum = WorkflowReviewDecision(decision)
        # 委派给编排器；reviewer_kind 显式固定为 USER（双保险）。
        return self._orchestrator.human_confirm(
            workflow_id=workflow_id,
            reviewer_id=user.actor_id,
            reviewer_kind=AuditActorKind.USER,
            decision=decision_enum,
            reason=reason,
            reviewed_at=reviewed_at,
            org_id=org_id,
            derive_task=derive_task,
            task_id=task_id,
        )


__all__ = ["GovernanceDashboardService"]

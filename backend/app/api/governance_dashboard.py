"""Backend FastAPI 路由：企业智能体治理驾驶舱（Phase 3.8.26）。

暴露 Task2 规定的 HTTP 端点：
- GET  /governance/workflows      治理工作流列表
- GET  /governance/reviews        待人工研判列表
- GET  /governance/audit          治理相关审计记录
- GET  /governance/workflows/{id} 单条执行状态
- GET  /governance/summary        驾驶舱总览
- POST /governance/review/confirm 人工研判确认（唯一写入口，强制 USER）

红线：
- 所有端点要求真实 USER（``x-actor-kind: user`` + ``x-actor-id``），否则 403；
- POST /review/confirm 委派给 ``GovernanceDashboardService.confirm_review``，其再委派给
  编排器 ``human_confirm``（双保险 require_human_actor），AI 无法越权；
- 本路由**不持有**任何治理状态，状态由 agents 包内编排器单一真相源持有。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让后端 app 命名空间能解析 agents 企业包（BOIP 根目录）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.governance_dashboard import (  # noqa: E402
    DashboardUser,
    GovernanceDashboardService,
)
from agents.enterprise.governance_workflow.orchestrator import (  # noqa: E402
    GovernanceWorkflowOrchestrator,
)

router = APIRouter(prefix="/governance", tags=["governance-dashboard"])

# 共享服务（生产由 EnterpriseOperationLayer 注入）；未注入时回退内存演示实例。
_SHARED_SERVICE: Optional[GovernanceDashboardService] = None
_DEMO_SERVICE: Optional[GovernanceDashboardService] = None
_DEMO_ORG = "demo-org"


def set_dashboard_service(svc: GovernanceDashboardService) -> None:
    """由应用启动钩子注入共享驾驶舱服务（来自 EnterpriseOperationLayer）。"""
    global _SHARED_SERVICE
    _SHARED_SERVICE = svc


def _build_demo_service() -> GovernanceDashboardService:
    global _DEMO_SERVICE
    if _DEMO_SERVICE is None:
        audit = AuditService(org_id=_DEMO_ORG)
        orchestrator = GovernanceWorkflowOrchestrator(org_id=_DEMO_ORG, audit=audit)
        _DEMO_SERVICE = GovernanceDashboardService(
            org_id=_DEMO_ORG, orchestrator=orchestrator, audit=audit
        )
    return _DEMO_SERVICE


def get_dashboard_service() -> GovernanceDashboardService:
    return _SHARED_SERVICE or _build_demo_service()


def require_user(
    x_actor_id: str = Header(..., description="真实责任人 id"),
    x_actor_kind: str = Header(default="user", description="必须为 user"),
) -> DashboardUser:
    """驾驶舱仅对真实 USER 开放（红线③/⑥）。"""
    if not x_actor_id or x_actor_kind != "user":
        raise HTTPException(
            status_code=403,
            detail="治理驾驶舱仅对真实责任人（USER）开放；AI 无法越权。",
        )
    return DashboardUser(actor_id=x_actor_id, actor_kind=x_actor_kind)


class ConfirmReviewRequest(BaseModel):
    workflow_id: str
    decision: str  # confirmed | rejected | need_more_info
    reason: str
    derive_task: bool = False
    task_id: Optional[str] = None


@router.get("/workflows")
def get_workflows(
    org_id: str = Header(default=_DEMO_ORG),
    status: Optional[str] = None,
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.list_workflows(org_id=org_id, user=user, status=status)


@router.get("/reviews")
def get_reviews(
    org_id: str = Header(default=_DEMO_ORG),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.list_pending_reviews(org_id=org_id, user=user)


@router.get("/audit")
def get_audit(
    org_id: str = Header(default=_DEMO_ORG),
    limit: int = 100,
    target: str = "",
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.list_audit_records(org_id=org_id, user=user, limit=limit, target=target)


@router.get("/workflows/{workflow_id}")
def get_workflow_execution(
    workflow_id: str,
    org_id: str = Header(default=_DEMO_ORG),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.get_execution_status(org_id=org_id, user=user, workflow_id=workflow_id)


@router.get("/summary")
def get_summary(
    org_id: str = Header(default=_DEMO_ORG),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.summary(org_id=org_id, user=user)


@router.post("/review/confirm", status_code=200)
def confirm_review(
    body: ConfirmReviewRequest,
    org_id: str = Header(default=_DEMO_ORG),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
    user: DashboardUser = Depends(require_user),
):
    return svc.confirm_review(
        org_id=org_id,
        user=user,
        workflow_id=body.workflow_id,
        decision=body.decision,
        reason=body.reason,
        derive_task=body.derive_task,
        task_id=body.task_id,
    )

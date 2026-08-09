"""Backend FastAPI 路由：企业智能体治理驾驶舱（Phase 3.8.26，3.8.28 身份改造）。

暴露的端点：
- GET  /governance/workflows      治理工作流列表        governance:workflow:read
- GET  /governance/reviews        待人工研判列表        governance:review:read
- GET  /governance/audit          治理相关审计记录      governance:audit:read
- GET  /governance/workflows/{id} 单条执行状态          governance:execution:read
- GET  /governance/summary        驾驶舱总览            governance:summary:read
- POST /governance/review/confirm 人工研判确认（唯一写入口）governance:review:confirm

## Phase 3.8.28 改了什么

改之前，本路由用 ``require_user`` 读取**旧式身份请求头**两个
请求头来确定"谁在操作"。这两个头由客户端任意填写，没有任何凭据支撑，因此：

    curl -X POST /governance/review/confirm \
         -H 'identity-header: 随便写' -H 'identity-header: user' ...

就能让治理工作流进入 ``human_confirmed``，且审计里的责任人写着"随便写"。
六个阶段建立的 Human-in-the-loop 红线，在传输层是敞开的。

改之后：

- 身份**只能**来自 ``Authorization: Bearer <token>``，由后端验签、回库确认
  用户仍然 active、并重读其角色（``app.identity``）；
- ``actor_kind`` 不再是入参，而是后端推导的结论 —— 请求里根本没有能声明
  "我是人"的字段；
- 组织边界来自主体，客户端指定的 ``org_id`` 只被允许"复述"而不能"指定"；
- 携带旧身份头一律 400，不静默忽略（避免调用方误以为指定成功）。

红线不变：
- POST /review/confirm 仍然委派给编排器 ``human_confirm``（require_human_actor
  双保险），AI 无法越权；
- 本路由**不持有**任何治理状态，状态由 agents 包内编排器单一真相源持有。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends, Header
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

from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    get_current_principal,
    record_accountability,
    require_governance_permission,
    require_same_org,
)

router = APIRouter(prefix="/governance", tags=["governance-dashboard"])

# 共享服务（生产由 EnterpriseOperationLayer 注入）；未注入时按组织回退内存演示实例。
_SHARED_SERVICE: Optional[GovernanceDashboardService] = None
_DEMO_SERVICES: Dict[str, GovernanceDashboardService] = {}
_DEMO_ORG = "demo-org"


def set_dashboard_service(svc: GovernanceDashboardService) -> None:
    """由应用启动钩子注入共享驾驶舱服务（来自 EnterpriseOperationLayer）。"""
    global _SHARED_SERVICE
    _SHARED_SERVICE = svc


def reset_dashboard_service() -> None:
    """清空共享服务与演示实例（Phase 3.8.27 新增的**装配复位**入口）。

    为什么需要它：演示服务是进程级缓存，一旦某个调用方（典型是测试夹具）
    向它登记过治理工作流，这些治理事实会**跨调用泄漏**到后续所有使用者身上；
    而编排器的 ``create_workflow`` 依红线⑥ **拒绝重复 workflow_id**
    （禁止覆盖既有治理事实），于是第二次登记同一条线索必然失败。

    正确的处理是复位**装配**，而不是放宽红线 —— 治理层宁可让调用方显式重建
    上下文，也不允许「同一个 id 被悄悄覆盖」。因此本函数只丢弃服务实例引用，
    **不删除、不改写任何治理事实**（红线⑥）：被丢弃的实例连同其内存态一起被
    垃圾回收，不存在「抹除已落库留痕」的语义。

    生产路径不调用本函数（服务由 ``EnterpriseOperationLayer`` 注入且长期存活）。
    """
    global _SHARED_SERVICE
    _SHARED_SERVICE = None
    _DEMO_SERVICES.clear()


def _build_demo_service(org_id: str = _DEMO_ORG) -> GovernanceDashboardService:
    """按组织构造（并缓存）内存演示服务。

    3.8.28 之前它是单例且组织写死 ``demo-org``；身份改造后组织来自主体
    （真实租户 id），因此必须按组织分实例，否则 A 租户的人会看到 B 租户的
    治理事实 —— 那正是我们这一阶段要消灭的问题。
    """

    key = str(org_id).strip() or _DEMO_ORG
    svc = _DEMO_SERVICES.get(key)
    if svc is None:
        audit = AuditService(org_id=key)
        orchestrator = GovernanceWorkflowOrchestrator(org_id=key, audit=audit)
        svc = GovernanceDashboardService(
            org_id=key, orchestrator=orchestrator, audit=audit
        )
        _DEMO_SERVICES[key] = svc
    return svc


def get_dashboard_service(
    principal: GovernancePrincipal = Depends(get_current_principal),
) -> GovernanceDashboardService:
    """取本主体所属组织的驾驶舱服务。

    注意依赖顺序：**先认证，再取服务**。反过来（先建服务再认证）会让未认证
    请求也能触发服务构造，把组织标识变成一个无需凭据即可探测的侧信道。
    """

    return _SHARED_SERVICE or _build_demo_service(principal.org_id)


def dashboard_user(principal: GovernancePrincipal) -> DashboardUser:
    """主体 → 驾驶舱操作者。

    ``actor_kind`` 恒为 ``"user"``：``GovernancePrincipal`` 在构造期就拒绝了
    一切非自然人主体（``IdentityNotHumanError``），能走到这里的必然是真人。
    这不是"我们填了个 user"，而是"非 user 根本构造不出主体"。
    """

    return DashboardUser(
        actor_id=principal.actor_id,
        actor_kind="user",
        display_name=principal.display_name or principal.email or "",
    )


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定。"""

    return require_same_org(principal, requested or "")


def _audit_of(svc: GovernanceDashboardService):
    """取驾驶舱服务持有的审计器（问责记录的写入口）。

    这里读的是私有属性，理由是本模块**就是**驾驶舱服务的装配处
    （``_build_demo_service`` 里的 ``AuditService`` 由这里创建并交给它）。
    为了让路由拿回自己刚交出去的东西而在 agents 包上新开一个公开属性，
    收益不足以抵消改动一个已冻结基线的风险。取不到就返回 ``None`` ——
    ``record_accountability`` 对 ``None`` 是安全的。
    """

    return getattr(svc, "audit", None) or getattr(svc, "_audit", None)


def _record(
    svc: GovernanceDashboardService,
    principal: GovernancePrincipal,
    *,
    action: str,
    resource: str,
    kind: str,
    detail: str = "",
) -> None:
    """写一条问责记录（责任五元组）。

    驾驶舱的读路径为什么也要单独落一条：它内部写的是
    ``record_dashboard_query``，那条记录里有 actor 但**没有角色** ——
    而"这个人当时是以 reviewer 还是 viewer 的身份看到这批治理事实的"
    正是事后审查要问的。ops 路由能把五元组嵌进现成的 VIEW 审计，
    驾驶舱没有这个位置可嵌，只能另起一条。
    """

    record_accountability(
        _audit_of(svc),
        principal,
        action=action,
        resource=resource,
        kind=kind,
        detail=detail,
        record_id=f"acct-{uuid.uuid4().hex[:12]}",
    )


class ConfirmReviewRequest(BaseModel):
    workflow_id: str
    decision: str  # confirmed | rejected | need_more_info
    reason: str
    derive_task: bool = False
    task_id: Optional[str] = None


OrgHeader = Annotated[Optional[str], Header(alias="org-id")]


@router.get("/workflows")
def get_workflows(
    org_id: OrgHeader = None,
    status: Optional[str] = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.WORKFLOW_READ)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    scope = _org(principal, org_id)
    result = svc.list_workflows(
        org_id=scope, user=dashboard_user(principal), status=status
    )
    _record(
        svc,
        principal,
        action="list_workflows",
        resource=scope,
        kind="view",
        detail=f"status={status or 'all'}",
    )
    return result


@router.get("/reviews")
def get_reviews(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.REVIEW_READ)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    scope = _org(principal, org_id)
    result = svc.list_pending_reviews(
        org_id=scope, user=dashboard_user(principal)
    )
    _record(
        svc, principal, action="list_pending_reviews", resource=scope, kind="view"
    )
    return result


@router.get("/audit")
def get_audit(
    org_id: OrgHeader = None,
    limit: int = 100,
    target: str = "",
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.AUDIT_READ)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    scope = _org(principal, org_id)
    result = svc.list_audit_records(
        org_id=scope,
        user=dashboard_user(principal),
        limit=limit,
        target=target,
    )
    # 读审计本身也要留痕：谁调阅了留痕，是审查中优先级最高的一条线索。
    _record(
        svc,
        principal,
        action="list_audit_records",
        resource=target or scope,
        kind="view",
        detail=f"limit={limit}",
    )
    return result


@router.get("/summary")
def get_summary(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.SUMMARY_READ)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    scope = _org(principal, org_id)
    result = svc.summary(org_id=scope, user=dashboard_user(principal))
    _record(svc, principal, action="summary", resource=scope, kind="view")
    return result


@router.get("/workflows/{workflow_id}")
def get_workflow_execution(
    workflow_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.EXECUTION_READ)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    result = svc.get_execution_status(
        org_id=_org(principal, org_id),
        user=dashboard_user(principal),
        workflow_id=workflow_id,
    )
    _record(
        svc,
        principal,
        action="get_execution_status",
        resource=workflow_id,
        kind="view",
    )
    return result


@router.post("/review/confirm", status_code=200)
def confirm_review(
    body: ConfirmReviewRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.REVIEW_CONFIRM)
    ),
    svc: GovernanceDashboardService = Depends(get_dashboard_service),
):
    """人工研判确认。责任人来自凭据，请求体无法指定"是谁确认的"。"""

    result = svc.confirm_review(
        org_id=_org(principal, org_id),
        user=dashboard_user(principal),
        workflow_id=body.workflow_id,
        decision=body.decision,
        reason=body.reason,
        derive_task=body.derive_task,
        task_id=body.task_id,
    )
    # 问责在业务动作**成功之后**才写：编排器拒绝的动作没有发生，不该留下
    # 一条"某人做过"的责任记录。
    _record(
        svc,
        principal,
        action="confirm_review",
        resource=body.workflow_id,
        kind="review",
        detail=f"decision={body.decision};reason={body.reason}",
    )
    return result


__all__ = [
    "ConfirmReviewRequest",
    "dashboard_user",
    "get_dashboard_service",
    "reset_dashboard_service",
    "router",
    "set_dashboard_service",
]

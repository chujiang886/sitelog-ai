"""Backend FastAPI 路由：企业生产可观测性、SRE 与事故响应 API（Phase 3.9.3 Task 17）。

暴露生产可观测性与事故响应控制平面的**只读查看**与**真实人工事故动作**两类端点：

- GET  /governance/observability/health
- GET  /governance/observability/metrics
- GET  /governance/observability/slo
- GET  /governance/incidents
- GET  /governance/incidents/{incident_id}
- GET  /governance/incidents/{incident_id}/timeline
- GET  /governance/incidents/{incident_id}/evidence
- GET  /governance/incidents/{incident_id}/postmortem
- POST /governance/incidents/{incident_id}/acknowledge   （真实 USER + INCIDENT_ACTION + 审计）
- POST /governance/incidents/{incident_id}/assign-commander
- POST /governance/incidents/{incident_id}/resolve
- POST /governance/incidents/{incident_id}/close

红线（fail-closed，全程）：
- 所有端点强制真实 USER，凭据只能来自 ``Authorization: Bearer <token>``（Phase 3.8.28）。
- 读端点要求 ``OBSERVABILITY_READ``；人工事故动作端点要求 ``INCIDENT_ACTION``
  （默认只授予 governance-admin，职责分离：其他角色只读）。
- 人工动作落 AuditService（append-only，actor_kind 恒 'user'）为系统真相源；本路由
  **不自动** ACK / RESOLVE / CLOSE 任何 Incident，不执行回滚 / 部署（红线⑤/⑨/⑩）。
- AI 主体无法到达本路由（Bearer 即真实 USER）；任何 ``actor_kind != user`` 的直接调用
  一律 403。
- 本路由**不持有**生产修复状态，不发送真实告警，不写密钥，不翻 engineering_enabled。
- 所有合成视图均标记 ``simulation_only=True`` / ``pending_verification``，绝不把模拟
  监控数据描述成真实 production observation（红线⑪）。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_release.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.production_observability import (  # noqa: E402
    ObservableComponent,
    ServiceHealthStatus,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError  # noqa: E402

from app.core.csrf import csrf_protect  # noqa: E402
from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    require_governance_permission,
    require_same_org,
)

router = APIRouter(
    prefix="/governance/observability",
    tags=["governance-observability"],
    dependencies=[Depends(csrf_protect)],
)


OrgHeader = Annotated[Optional[str], Header(alias="org-id")]


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定（跨组织访问 403）。"""

    return require_same_org(principal, requested or "")


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require_user_principal(principal: GovernancePrincipal) -> None:
    """AI / SYSTEM 主体一律拒绝（红线⑨/⑩）。"""

    if getattr(principal, "actor_kind", None) != "user":
        raise HTTPException(status_code=403, detail="仅真实 USER 责任人可操作事故响应")


def _synthesize_health(org_id: str) -> dict:
    """合成 11 组件健康快照（全部 UNKNOWN + simulation_only，红线⑪）。

    UNKNOWN 不得自动当 HEALTHY（红线⑨/⑪）。
    """

    snapshots = []
    for comp in ObservableComponent:
        snapshots.append(
            {
                "component": comp.value,
                "status": ServiceHealthStatus.UNKNOWN.value,
                "checked_at": _ts(),
                "source": "synthetic-readiness-probe",
                "evidence": "preparedness-layer-simulation",
                "latency_ms": None,
                "error": "",
                "trace_reference": "",
                "simulation_only": True,
            }
        )
    return {
        "overall": ServiceHealthStatus.UNKNOWN.value,
        "simulation_only": True,
        "note": "准备层只读合成视图；真实监测数据待生产接入后由真实监控源提供",
        "components": snapshots,
        "expected_components": [c.value for c in ObservableComponent],
    }


def _synthesize_slos(org_id: str) -> dict:
    """合成 SLO 列表（阈值均 pending_verification，红线⑪）。"""

    items = [
        {
            "slo_id": "avail-www",
            "name": "API 可用性",
            "component": "backend",
            "kind": "availability",
            "target": 0.999,
            "window": "30d",
            "threshold_verified": False,
            "status": "pending_verification",
        },
        {
            "slo_id": "lat-p95",
            "name": "P95 时延",
            "component": "backend",
            "kind": "latency",
            "target": 300.0,
            "window": "30d",
            "threshold_verified": False,
            "status": "pending_verification",
        },
        {
            "slo_id": "err-rate",
            "name": "错误率",
            "component": "backend",
            "kind": "error_rate",
            "target": 0.001,
            "window": "30d",
            "threshold_verified": False,
            "status": "pending_verification",
        },
    ]
    return {
        "simulation_only": True,
        "threshold_verified": False,
        "total": len(items),
        "met": 0,
        "breached": 0,
        "pending_verification": len(items),
        "items": items,
    }


def _synthesize_metrics(org_id: str) -> dict:
    """合成指标视图（空 + simulation_only，避免描述成真实生产指标，红线⑪）。"""

    return {
        "simulation_only": True,
        "note": "准备层无真实生产指标；指标快照待生产接入后由真实监控源提供",
        "snapshots": [],
    }


# --------------------------------------------------------------------------- #
# 只读端点                                                                     #
# --------------------------------------------------------------------------- #
@router.get("/health")
def view_health(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看组件健康总览（只读；全 UNKNOWN + simulation_only）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _synthesize_health(org_id)


@router.get("/metrics")
def view_metrics(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看指标视图（只读；simulation_only）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _synthesize_metrics(org_id)


@router.get("/slo")
def view_slo(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看 SLO 总览（只读；阈值 pending_verification）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _synthesize_slos(org_id)


@router.get("/incidents")
def list_incidents(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """列出事故（准备层无真实事故；返回空列表，不含任何 AUTO_* 状态）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return {
        "organization_id": org_id,
        "simulation_only": True,
        "active_incidents": [],
        "note": "准备层只读视图；真实事故由生产监控在接入后产生",
    }


@router.get("/incidents/{incident_id}")
def view_incident(
    incident_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看单条事故（准备层无真实事故 → 404）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    raise HTTPException(status_code=404, detail=f"准备层无真实事故：{incident_id}")


@router.get("/incidents/{incident_id}/timeline")
def view_timeline(
    incident_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看事故时间线（准备层无真实事故 → 404）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    raise HTTPException(status_code=404, detail=f"准备层无真实事故：{incident_id}")


@router.get("/incidents/{incident_id}/evidence")
def view_evidence(
    incident_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看事故证据（准备层无真实事故 → 404）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    raise HTTPException(status_code=404, detail=f"准备层无真实事故：{incident_id}")


@router.get("/incidents/{incident_id}/postmortem")
def view_postmortem(
    incident_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查看事故复盘（准备层无真实事故 → 404）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    raise HTTPException(status_code=404, detail=f"准备层无真实事故：{incident_id}")


# --------------------------------------------------------------------------- #
# 写入端点：真实人工事故动作（强 RBAC + 审计，绝不自动转移状态）            #
# --------------------------------------------------------------------------- #
class IncidentActionRequest(BaseModel):
    reason: str = ""
    commander_id: Optional[str] = None  # 仅 assign-commander 使用


def _record_human_action(
    *,
    principal: GovernancePrincipal,
    org_id: str,
    incident_id: str,
    record_method: str,
    detail: str,
) -> dict:
    """落一条真实人工事故动作审计（append-only，actor_kind 恒 user）。

    返回审计记录本身——本端点**不**自动把 Incident 转为 RESOLVED / CLOSED（红线⑨/⑩）。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    audit = AuditService(org_id=org_id)
    method = getattr(audit, record_method)
    try:
        rec = method(
            record_id=f"{incident_id}-{record_method}",
            actor_id=principal.actor_id,
            target=incident_id,
            detail=detail,
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {
        "incident_id": incident_id,
        "actor_id": principal.actor_id,
        "actor_kind": "user",
        "action": record_method,
        "category": rec.category.value,
        "detail": detail,
        "recorded_at": rec.ts,
        "auto_state_transition": False,  # fail-closed 显式声明
    }


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: str,
    body: IncidentActionRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.INCIDENT_ACTION)
    ),
):
    """真实人工 ACK 事故（红线⑨/⑩）。"""

    return _record_human_action(
        principal=principal,
        org_id=org_id,
        incident_id=incident_id,
        record_method="record_incident_human_acknowledged",
        detail=f"ack_by={principal.actor_id};reason={body.reason[:200]}",
    )


@router.post("/incidents/{incident_id}/assign-commander")
def assign_commander(
    incident_id: str,
    body: IncidentActionRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.INCIDENT_ACTION)
    ),
):
    """真实人工指派事故指挥官（红线⑩；AI 不得 self-assign）。"""

    if not body.commander_id:
        raise HTTPException(status_code=400, detail="assign-commander 必须提供 commander_id")
    return _record_human_action(
        principal=principal,
        org_id=org_id,
        incident_id=incident_id,
        record_method="record_incident_human_acknowledged",
        detail=f"assign_commander_by={principal.actor_id};commander={body.commander_id}",
    )


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: str,
    body: IncidentActionRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.INCIDENT_ACTION)
    ),
):
    """真实人工 RESOLVE 事故（红线⑨/⑩；绝不自动 RESOLVE）。"""

    return _record_human_action(
        principal=principal,
        org_id=org_id,
        incident_id=incident_id,
        record_method="record_incident_human_resolved",
        detail=f"resolved_by={principal.actor_id};reason={body.reason[:200]}",
    )


@router.post("/incidents/{incident_id}/close")
def close_incident(
    incident_id: str,
    body: IncidentActionRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.INCIDENT_ACTION)
    ),
):
    """真实人工 CLOSE 事故（红线⑨/⑩；绝不自动 CLOSE）。"""

    return _record_human_action(
        principal=principal,
        org_id=org_id,
        incident_id=incident_id,
        record_method="record_incident_human_closed",
        detail=f"closed_by={principal.actor_id};reason={body.reason[:200]}",
    )

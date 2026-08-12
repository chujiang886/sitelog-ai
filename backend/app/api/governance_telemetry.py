"""Backend FastAPI 路由：企业生产遥测接入适配与合成运维验证 API（Phase 3.9.4 Task 19）。

暴露生产遥测控制平面的**只读查看**与**真实人工合成演练**两类端点：

- GET  /governance/telemetry/providers
- GET  /governance/telemetry/summary
- GET  /governance/telemetry/{provider_id}/health
- GET  /governance/telemetry/{provider_id}/metrics
- GET  /governance/telemetry/{provider_id}/traces
- GET  /governance/telemetry/{provider_id}/logs
- GET  /governance/telemetry/synthetic/scenarios
- POST /governance/telemetry/{provider_id}/check      （真实 USER + OBSERVABILITY_READ + 审计）
- POST /governance/telemetry/synthetic/run            （真实 USER + INCIDENT_ACTION，生产环境 403）

红线（fail-closed，全程）：
- 所有端点强制真实 USER；凭据只能来自 ``Authorization: Bearer <token>``（Phase 3.8.28）。
- 读端点要求 ``OBSERVABILITY_READ``；合成演练端点要求 ``INCIDENT_ACTION``
  （默认只授予 governance-admin，职责分离）。
- 合成演练在**生产环境**一律 403（红线④/⑪）：合成演练只应在非生产、受控演练环境中由
  真实责任人触发，绝不自动部署 / 回滚 / 外发告警 / ACK-RESOLVE-CLOSE Incident。
- 端点不持有生产状态、不写密钥、不部署、不回滚、不自动关闭 Incident、
  不真实外发告警（红线⑨/⑫/⑬/⑭）。
- 本路由仅暴露 ``ProductionTelemetryService`` 的只读查询与人工演练入口；服务层不导出任何
  自动回滚 / 真实外发 / Runbook 执行能力（见 ``agents/enterprise/telemetry/__init__.py``）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_release.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.red_line import EnterpriseRedLineViolationError  # noqa: E402
from agents.enterprise.telemetry.models import SyntheticFaultScenario  # noqa: E402
from agents.enterprise.telemetry.service import ProductionTelemetryService  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.csrf import csrf_protect  # noqa: E402
from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    require_governance_permission,
    require_same_org,
)

router = APIRouter(
    prefix="/governance/telemetry",
    tags=["governance-telemetry"],
    dependencies=[Depends(csrf_protect)],
)


OrgHeader = Annotated[Optional[str], Header(alias="org-id")]


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定（跨组织访问 403）。"""

    return require_same_org(principal, requested or "")


def _require_user_principal(principal: GovernancePrincipal) -> None:
    """AI / SYSTEM 主体一律拒绝（红线⑥/⑧/⑩）。"""

    if getattr(principal, "actor_kind", None) != "user":
        raise HTTPException(status_code=403, detail="仅真实 USER 责任人可操作遥测端点")


def _svc(org_id: str) -> ProductionTelemetryService:
    """按主体所属组织合成遥测服务实例（无共享存储，fail-closed 构造）。"""

    audit = AuditService(org_id=org_id)
    # 构造即断言 safety_invariants_ok()（engineering_enabled 必须 False）。
    return ProductionTelemetryService(org_id=org_id, audit=audit, identity=None)


def _settings():
    return get_settings()


# --------------------------------------------------------------------------- #
# 请求体                                                                       #
# --------------------------------------------------------------------------- #
class CheckRequest(BaseModel):
    """Provider 巡检请求体（仅记录审计，不改任何生产状态）。"""

    detail: str = ""


class SyntheticRunRequest(BaseModel):
    """合成事故演练请求体（真实 USER + INCIDENT_ACTION 才可调用）。

    - ``scenario``：``SyntheticFaultScenario`` 的取值，仅 fixture 阈值；
    - ``human_actions``：只有真实 USER 经本端点显式提供（ack/recover/validate/close）
      才会被记入报告，服务层绝不自动发生（红线⑨/⑩）。
    """

    scenario: str
    component: str = "api"
    organization_id: Optional[str] = None
    human_actions: Dict[str, bool] = {}


# --------------------------------------------------------------------------- #
# 只读端点（OBSERVABILITY_READ）                                               #
# --------------------------------------------------------------------------- #
@router.get("/providers")
def list_providers(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """列出已注册遥测 Provider 及其健康汇总（只读快照）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    svc = _svc(org_id)
    return {
        "organization_id": org_id,
        "providers": svc.list_providers(),
        "health_summary": svc.provider_health_summary(),
        "engineering_enabled": load_engineering_enabled(),
        "note": "synthetic_only=true; 未配置真实生产源（fail-closed，绝不降级伪装）",
    }


@router.get("/summary")
def summary(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """遥测层只读汇总（Provider 数 / 健康 / 禁名计数 / 仅合成源标记）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _svc(org_id).summarize()


@router.get("/{provider_id}/health")
def provider_health(
    provider_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查询单个 Provider 健康（只读）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    svc = _svc(org_id)
    provider = svc.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"未知 provider: {provider_id!r}")
    return {"provider_id": provider_id, "health": provider.provider_health().to_dict()}


@router.get("/{provider_id}/metrics")
def provider_metrics(
    provider_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查询指标遥测（未配置真实源 → 空，绝不降级；红线⑪）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _svc(org_id).query_and_normalize(
        provider_id=provider_id,
        organization_id=org_id,
        component="api",
        types=["metrics"],
    )


@router.get("/{provider_id}/traces")
def provider_traces(
    provider_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查询链路追踪遥测（未配置真实源 → 空；红线⑪）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _svc(org_id).query_and_normalize(
        provider_id=provider_id,
        organization_id=org_id,
        component="api",
        types=["traces"],
    )


@router.get("/{provider_id}/logs")
def provider_logs(
    provider_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """查询日志遥测（未配置真实源 → 空；红线⑪）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _svc(org_id).query_and_normalize(
        provider_id=provider_id,
        organization_id=org_id,
        component="api",
        types=["logs"],
    )


@router.get("/synthetic/scenarios")
def synthetic_scenarios(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """列出合成故障场景目录（只读；数值仅为 test fixture，禁作真实生产阈值）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return {
        "organization_id": org_id,
        "scenarios": [s.value for s in SyntheticFaultScenario],
        "note": "合成场景目录；所有数值仅为 test fixture 阈值，禁止写成真实生产阈值",
    }


# --------------------------------------------------------------------------- #
# 写入端点：真实人工 Provider 巡检 / 合成事故演练                              #
# --------------------------------------------------------------------------- #
@router.post("/{provider_id}/check")
def check_provider(
    provider_id: str,
    body: CheckRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.OBSERVABILITY_READ)
    ),
):
    """真实 USER 巡检 Provider（落审计，不改任何生产状态）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    return _svc(org_id).check_provider(
        actor_id=principal.actor_id,
        provider_id=provider_id,
        detail=body.detail,
    )


@router.post("/synthetic/run")
def run_synthetic_drill(
    body: SyntheticRunRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.INCIDENT_ACTION)
    ),
):
    """真实 USER 触发一次合成事故演练（红线④/⑨/⑪/⑫/⑬/⑭）。

    - 仅 governance-admin（持有 INCIDENT_ACTION）可调用；
    - 生产环境一律 403（合成演练只应在受控演练环境由真人触发）；
    - 注入仅限 Synthetic Provider；告警路由仅模拟投递，绝不真实外发；
    - 无 human_actions 时 Incident 状态恒为 open，绝不自动 ACK/RESOLVE/CLOSE；
    - actor_kind 必须 'user'（AI 主体 403）。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    # 红线④/⑪：生产环境禁止合成演练（须真实责任人 + 受控非生产环境）。
    if _settings().is_production:
        raise HTTPException(status_code=403, detail="生产环境禁止运行合成演练（红线④/⑪）")
    try:
        scenario = SyntheticFaultScenario(body.scenario)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"非法合成场景：{body.scenario!r}（须为 {[s.value for s in SyntheticFaultScenario]}）",
        )
    svc = _svc(org_id)
    org_for_query = body.organization_id or org_id
    try:
        return svc.run_synthetic_incident_drill(
            scenario=scenario,
            actor_id=principal.actor_id,
            organization_id=org_for_query,
            component=body.component,
            human_actions=body.human_actions or None,
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))

"""Backend FastAPI 路由：生产激活干跑与人工决策演练（Phase 3.9.8 T13）。

本路由**只**提供生产激活流程的隔离模拟（dry-run）能力，绝不等价于、不触发、不替代
真实生产激活：

- GET  /governance/activation/simulation/                 能力说明（simulation_only=true）
- GET  /governance/activation/simulation/scenarios        14 个合成决策场景
- GET  /governance/activation/simulation/negative-paths   12 条负路径
- POST /governance/activation/simulation/run              运行一次完整干跑，返回报告
- GET  /governance/activation/simulation/report/{id}     读取历史干跑报告
- GET  /governance/activation/simulation/report/latest   最近一次干跑报告

红线（fail-closed，全程）：
- 本路由**不提供** /activate /deploy-production /go 端点；真实激活仍由主理人在人类终端、
  四角色签署后显式执行（红线①）。
- 所有响应均携带 simulation_only=true；production_activated 恒 false、real_signoff_count
  恒 0、engineering_enabled 恒 false。
- 所有写操作（run）只驱动隔离沙盒（agents/enterprise/production_release/simulation.py），
  绝不写入真实 HumanSignoffRegistry / FinalDecisionLedger / Evidence Registry / 生产审计命名空间
  （红线③/④/⑧/⑩）。
- 即便传入审计服务，也只登记 3.9.8 simulation-only 类别（actor_kind 恒 AI，detail 强制
  红线标记），绝不登记真实 human signoff / real decision（红线③）。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_activation.py 一致）。
from pathlib import Path

_BOIP_ROOT = Path(__file__).resolve().parents[3]
import sys

if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.production_release.simulation import (  # noqa: E402
    ProductionActivationNegativePathMatrix,
    build_decision_scenario_matrix,
    build_simulation_context,
    run_production_activation_dry_run,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError  # noqa: E402

from app.core.csrf import csrf_protect  # noqa: E402
from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    require_governance_permission,
)

router = APIRouter(
    prefix="/governance/activation/simulation",
    tags=["governance-activation-simulation"],
    dependencies=[Depends(csrf_protect)],
)

# 进程内最近干跑报告缓存（按 simulation_id）。系统真相源是返回的 report；重启即清空。
_REPORTS: Dict[str, Dict[str, Any]] = {}
_LATEST_ID: Optional[str] = None

DEFAULT_CANDIDATE_ID = "RC-3.9.8-SIM"


class SimulationRunRequest(BaseModel):
    """运行一次干跑的请求体（全部字段仅用于隔离沙盒，不影响真实生产）。"""

    simulation_id: Optional[str] = None
    candidate_id: str = DEFAULT_CANDIDATE_ID
    scenario: str = "production_activation_full_dry_run"


@router.get("/")
def capability() -> Dict[str, Any]:
    """能力说明：明确声明本路由只模拟、不激活。"""

    return {
        "simulation_only": True,
        "not_production": True,
        "phase": "3.9.8",
        "description": (
            "生产激活干跑与人工决策演练层。仅驱动隔离沙盒，不触发真实激活、"
            "不翻转 engineering_enabled、不写真实控制平面。"
        ),
        "endpoints": {
            "GET /": "本说明",
            "GET /scenarios": "14 个合成决策场景（含 READY/BLOCKED/NO_GO/NEED_MORE）",
            "GET /negative-paths": "12 条负路径（越权/污染输入一律 reject）",
            "POST /run": "运行一次完整干跑，返回总报告",
            "GET /report/{id}": "读取历史干跑报告（进程内，重启清空）",
            "GET /report/latest": "最近一次干跑报告",
        },
        "forbidden_endpoints": [
            "POST /governance/activation/activate",
            "POST /governance/activation/deploy-production",
            "POST /governance/activation/go",
        ],
        "red_lines": {
            "production_activated": False,
            "real_signoff_count": 0,
            "engineering_enabled": False,
        },
    }


@router.get("/scenarios")
def scenarios(
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
) -> Dict[str, Any]:
    """列出 14 个合成决策场景（只读，恒模拟）。"""

    matrix = build_decision_scenario_matrix()
    return {
        "simulation_only": True,
        "count": len(matrix),
        "scenarios": [s.to_dict() for s in matrix],
    }


@router.get("/negative-paths")
def negative_paths(
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
) -> Dict[str, Any]:
    """列出 12 条负路径评估结果（只读，恒模拟）。证明越权/污染输入一律 reject。"""

    ctx = build_simulation_context(
        simulation_id="sim-negative-paths",
        candidate_id=DEFAULT_CANDIDATE_ID,
        scenario="negative-paths",
    )
    matrix = ProductionActivationNegativePathMatrix()
    results = matrix.evaluate(context=ctx)
    return {
        "simulation_only": True,
        "count": len(results),
        "negative_paths": [r.to_dict() for r in results],
    }


@router.post("/run")
def run_dry_run(
    req: SimulationRunRequest,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
) -> Dict[str, Any]:
    """运行一次完整生产激活干跑，返回总报告（只驱动隔离沙盒）。

    审计服务仅在进程内 ephemeral AuditService 上登记 3.9.8 simulation-only 类别，
    绝不触碰生产审计命名空间（红线⑧/⑩）。
    """

    global _LATEST_ID
    sim_id = req.simulation_id or f"sim-{uuid.uuid4().hex[:12]}"
    audit = AuditService(org_id="simulation")
    try:
        report = run_production_activation_dry_run(
            simulation_id=sim_id,
            candidate_id=req.candidate_id,
            scenario=req.scenario,
            audit=audit,
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=409, detail=f"红线冲突，干跑被拒绝：{e}")

    payload = report.to_dict()
    payload["simulation_only"] = True
    _REPORTS[sim_id] = payload
    _LATEST_ID = sim_id
    return {"simulation_id": sim_id, "simulation_only": True, "report": payload}


@router.get("/report/latest")
def get_latest_report(
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
) -> Dict[str, Any]:
    """读取最近一次干跑报告（进程内缓存；重启清空）。

    注意：本端点必须注册在 ``/report/{simulation_id}`` **之前**，否则 Starlette 会把
    ``/report/latest`` 误匹配到动态路由（把 "latest" 当成 simulation_id）。
    """

    if _LATEST_ID is None or _LATEST_ID not in _REPORTS:
        raise HTTPException(status_code=404, detail="尚无干跑报告（进程内缓存，重启清空）")
    payload = _REPORTS[_LATEST_ID]
    return {"simulation_id": _LATEST_ID, "simulation_only": True, "report": payload}


@router.get("/report/{simulation_id}")
def get_report(
    simulation_id: str,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
) -> Dict[str, Any]:
    """读取一次历史干跑报告（进程内缓存；重启清空）。"""

    payload = _REPORTS.get(simulation_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该 simulation_id 的干跑报告（进程内缓存，重启清空）",
        )
    return {"simulation_id": simulation_id, "simulation_only": True, "report": payload}

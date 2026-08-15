"""Backend FastAPI 路由：外部预生产执行与资格验证 API（Phase 3.9.11 Tasks 32-33）。

只读为主 API（fail-closed，红线）：

- GET  /api/external-staging-execution/status        执行状态摘要
- GET  /api/external-staging-execution/plan          执行计划（10 步，全 plan-only/contract/pending）
- GET  /api/external-staging-execution/gate          执行闸门（BLOCKED / PENDING_* / READY_*）
- GET  /api/external-staging-execution/evidence      证据链（13 条，scope=external_staging，无 Secret）
- GET  /api/external-staging-execution/package       机器可读执行包（含 SHA-256）
- GET  /api/external-staging-execution/resources     8 资源适配器探针（诚实 PENDING）
- POST /api/external-staging-execution/human-record  人工登记（仅登记，绝不执行/部署）

红线：
- **禁止**任何 Production 端点 / 真实部署 / 回滚 / 写 Secret / 权限授予；
- 所有响应 ``contains_real_secret=false``、``production_activation_prohibited=true``、
  ``engineering_enabled=false``；
- 当前真实外部资源未提供 → 全部 pending，不伪造验证 / 不宣称真实执行；
- 任一写入端点（如需）须真实 USER + 特权角色 + RBAC + CSRF + 同组织 +
  External Staging 环境证明 + 审计，且绝不触及 Production；本层 human-record 仅登记，
  不做副作用、不改业务数据、不翻转 enabled。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

# 让 backend/app 命名空间可解析 agents 企业包。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.external_staging_execution import (  # noqa: E402
    ExternalStagingExecutionGate,
    build_default_execution_plan,
    build_execution_package,
    load_external_staging_identity,
)
from agents.external_staging_execution.security import (  # noqa: E402
    ExternalStagingExecutionSecurityValidator,
)
from agents.external_staging_qualification.models import (  # noqa: E402
    ExternalStagingResourceRegistry,
)
from agents.external_staging_execution.pipeline import ExecutionPipeline  # noqa: E402

router = APIRouter(
    prefix="/api/external-staging-execution",
    tags=["external-staging-execution"],
)

PHASE_BASE = "2f4a9838bcfc7105bc561f74fb2658906801e011"


def _source_commit() -> str:
    """尽力获取当前 git HEAD（失败回落占位，不阻断只读响应）。"""

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_BOIP_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _build_package() -> dict[str, Any]:
    """重算确定性执行包（与 generator 同口径，运行时自包含，不依赖落盘文件）。"""

    src = _source_commit()
    ident = load_external_staging_identity()
    registry = ExternalStagingResourceRegistry.build_default()
    plan = build_default_execution_plan()
    pipe = ExecutionPipeline()
    chain = pipe.run_evidence_chain()
    pending_resources = tuple(r.resource_id for r in registry.resources)
    gate = ExternalStagingExecutionGate().evaluate(
        plan=plan,
        evidence_chain=chain,
        environment_identity=ident.to_dict(),
        registry=registry,
        additional_pending_resources=pending_resources,
        human_verification_required=True,
    )
    return build_execution_package(
        source_commit=src,
        environment_identity=ident,
        plan=plan,
        evidence_chain=chain,
        gate=gate,
        pending_resources=pending_resources,
        human_pending=("external_resource_provisioning", "four_role_signoff"),
        baseline_commit=PHASE_BASE,
        evidence_source_commit=src,
        package_generated_from_commit=src,
    )


@router.get("/status")
def get_status():
    """执行状态摘要（fail-closed，非生产）。"""
    pkg = _build_package()
    return {
        "phase": pkg["phase"],
        "terminal_state": pkg["terminal_state"],
        "gate_status": pkg["gate"]["status"],
        "environment": pkg["environment_identity"]["environment"],
        "production": False,
        "external_pending": len(pkg["pending_resources"]),
        "engineering_enabled": load_engineering_enabled(),
        "production_activation_prohibited": True,
        "contains_real_secret": pkg["contains_real_secret"],
        "note": "8 外部预生产资源全部 pending（真实资源未提供，fail-closed 不伪造）。",
    }


@router.get("/plan")
def get_plan():
    """执行计划（10 步，全 plan-only / contract-test / pending，无真实执行）。"""
    pkg = _build_package()
    plan = pkg["execution_plan"]
    return {
        "phase": pkg["phase"],
        "any_real_execution": plan["summary"]["any_real_execution"],
        "step_count": plan["summary"]["step_count"],
        "steps": [
            {
                "kind": s["kind"],
                "status": s["status"],
                "is_real_execution": s["is_real_execution"],
            }
            for s in plan["steps"]
        ],
        "production_activation_prohibited": True,
    }


@router.get("/gate")
def get_gate():
    """执行闸门（BLOCKED / PENDING_* / READY_*，禁 GO/APPROVED/PRODUCTION_READY）。"""
    pkg = _build_package()
    return {"gate_status": pkg["gate"]["status"], "gate_checks": pkg["gate"]["checks"]}


@router.get("/evidence")
def get_evidence():
    """证据链（13 条，scope=external_staging，无 Secret）。"""
    pkg = _build_package()
    chain = pkg["evidence_chain"]
    return {
        "count": chain["summary"]["count"],
        "none_contains_secret": chain["summary"]["none_contains_secret"],
        "all_scope_external_staging": chain["summary"]["all_scope_external_staging"],
        "chain_hash": chain["chain_hash"],
    }


@router.get("/package")
def get_package():
    """机器可读执行包（含 SHA-256，确定性）。"""
    return _build_package()


@router.get("/resources")
def get_resources():
    """8 资源适配器探针（诚实 PENDING，无真实配置）。"""
    registry = ExternalStagingResourceRegistry.build_default()
    from agents.external_staging_execution.adapters import probe_all

    probes = probe_all()
    return {
        "environment": "external_staging",
        "production": False,
        "total": len(registry.resources),
        "resources": [
            {
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "configured": False,
                "verified": False,
                "qualification_status": "pending_external_staging_resource",
                "probe_status": probes.get(r.resource_id, {}).get("status", "pending"),
            }
            for r in registry.resources
        ],
        "engineering_enabled": load_engineering_enabled(),
    }


@router.post("/human-record")
async def post_human_record(request: Request):
    """人工登记（仅登记，绝不执行 / 部署 / 写 Secret / 翻转 enabled）。

    fail-closed：仅接受 scope=external_staging + action=human_record；其余动作一律
    默认拒绝（含 execute/deploy/activate/rollback_execute/production_write/secret_write）。
    本端点不持久化、不修改业务数据、不产生副作用。
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    scope = payload.get("scope", "external_staging")
    action = payload.get("action", "human_record")
    actor = payload.get("actor", "unknown")

    verdict = ExternalStagingExecutionSecurityValidator().validate_request(
        scope=scope,
        actor=actor,
        action=action,
        is_production_action=False,
    )
    if not verdict.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden_action",
                "reason": verdict.reason,
                "performs_execution": False,
                "production_activation_prohibited": True,
            },
        )

    # 仅登记（acknowledgment），不持久化、不执行、不部署。
    return {
        "recorded": True,
        "performs_execution": False,
        "production_activation_prohibited": True,
        "engineering_enabled": load_engineering_enabled(),
        "note": "仅登记人工动作；真实外部资源供给与 GO 须主理人在人类终端、四角色真实签署后显式执行。",
        "accepted_scope": scope,
        "accepted_action": action,
    }

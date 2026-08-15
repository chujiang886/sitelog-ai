"""Backend FastAPI 路由：外部预生产供给执行（Phase 3.9.13，T40-contract, T49-T53）。

**仅读、禁变更**（fail-closed，红线）：
- GET /api/v1/external-staging-provisioning-execution/status
- GET /api/v1/external-staging-provisioning-execution/resources
- GET /api/v1/external-staging-provisioning-execution/iac-readiness
- GET /api/v1/external-staging-provisioning-execution/apply-gate
- GET /api/v1/external-staging-provisioning-execution/evidence

红线：
- 禁止任何 POST/PUT/DELETE 或真实 apply / 部署 / 写 Secret / 权限授予；
- 所有响应 ``engineering_enabled=false``、``real_execution_allowed=false``、
  ``contains_real_secret=false``、``fabrication_free=true``；
- 8 资源全 pending（真实资源未提供，禁伪造）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.external_staging_provisioning.execution import (  # noqa: E402
    ProvisioningExecutionOrchestrator,
)
from agents.external_staging_provisioning.resource_state_machine import (  # noqa: E402
    build_default_bom,
    ProvisioningStateRegistry,
)
from agents.external_staging_provisioning.iac_readiness import IaCReadinessAuditor  # noqa: E402
from agents.external_staging_provisioning.api_contract_execution import (  # noqa: E402
    EXECUTION_API_CONTRACT,
)

router = APIRouter(
    prefix="/api/v1/external-staging-provisioning-execution",
    tags=["external-staging-provisioning-execution"],
)


def _source_commit() -> str:
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


def _orchestrate() -> dict[str, Any]:
    return ProvisioningExecutionOrchestrator().run(
        generated_from_commit=_source_commit()
    )


@router.get("/status")
def get_status():
    res = _orchestrate()
    return {
        "phase": "3.9.13",
        "terminal_state": res["terminal_state"],
        "engineering_enabled": res["engineering_enabled"],
        "real_execution_allowed": False,
        "total_resources": res["total_resources"],
        "provisioned": res["provisioned"],
        "registered": res["registered"],
        "connected": res["connected"],
        "isolated": res["isolated"],
        "qualified": res["qualified"],
        "any_real_progress": res["any_real_progress"],
        "apply_gate_status": res["apply_gate_status"],
        "dual_key_authorized": res["dual_key_authorized"],
        "fabrication_free": res["fabrication_free"],
        "contains_real_secret": False,
        "note": "8 外部预生产资源全 pending（真实资源未提供，fail-closed 不伪造）。",
    }


@router.get("/resources")
def get_resources():
    reg = ProvisioningStateRegistry(build_default_bom())
    return {
        "engineering_enabled": load_engineering_enabled(),
        "real_execution_allowed": False,
        "total": reg.summary()["total"],
        "all_pending": reg.all_pending(),
        "resources": reg.summary()["machines"],
        "contains_real_secret": False,
    }


@router.get("/iac-readiness")
def get_iac_readiness():
    report = IaCReadinessAuditor().audit_all()
    report["engineering_enabled"] = load_engineering_enabled()
    report["real_execution_allowed"] = False
    report["contains_real_secret"] = False
    return report


@router.get("/apply-gate")
def get_apply_gate():
    res = _orchestrate()
    return {
        "engineering_enabled": res["engineering_enabled"],
        "apply_gate_status": res["apply_gate_status"],
        "apply_gate_is_go": res["apply_gate_is_go"],
        "dual_key_authorized": res["dual_key_authorized"],
        "real_execution_allowed": False,
        "contains_real_secret": False,
    }


@router.get("/evidence")
def get_evidence():
    res = _orchestrate()
    return {
        "engineering_enabled": res["engineering_enabled"],
        "fabrication_free": res["fabrication_free"],
        "machine_package_hash": res["machine_package_hash"],
        "evidence": res["evidence"],
        "contract": EXECUTION_API_CONTRACT,
        "real_execution_allowed": False,
        "contains_real_secret": False,
    }

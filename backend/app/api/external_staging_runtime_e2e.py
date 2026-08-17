"""Backend FastAPI 路由：外部预生产运行时部署与端到端资格认定（Phase 3.9.14）。

**仅读、禁变更**（fail-closed，红线）：
- GET /api/v1/external-staging-runtime-e2e/status
- GET /api/v1/external-staging-runtime-e2e/isolation
- GET /api/v1/external-staging-runtime-e2e/qualification
- GET /api/v1/external-staging-runtime-e2e/health
- GET /api/v1/external-staging-runtime-e2e/e2e
- GET /api/v1/external-staging-runtime-e2e/change-control
- GET /api/v1/external-staging-runtime-e2e/evidence

红线：
- 禁止任何 POST/PUT/DELETE 或真实 apply / 部署 / 写 Secret / 权限授予；
- 所有响应 ``engineering_enabled=False``、``real_execution_allowed=False``、
  ``contains_real_secret=False``、``fabrication_free=True``、``terminal_state``；
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
from agents.external_staging_runtime.change_control import TERMINAL_STATE  # noqa: E402
from agents.external_staging_runtime.machine_package import build_machine_package  # noqa: E402
from agents.external_staging_runtime.api_contract import (  # noqa: E402
    EXTERNAL_RUNTIME_API_CONTRACT,
)
from agents.external_staging_runtime.readonly_api import dispatch  # noqa: E402

router = APIRouter(
    prefix="/api/v1/external-staging-runtime-e2e",
    tags=["external-staging-runtime-e2e"],
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


def _envelope(endpoint: str) -> dict[str, Any]:
    """统一 fail-closed 信封：复用 readonly_api.dispatch + 强制红线字段。"""

    body = dispatch(endpoint)
    body["phase"] = "3.9.14"
    body["terminal_state"] = TERMINAL_STATE
    body["engineering_enabled"] = bool(load_engineering_enabled())
    body["real_execution_allowed"] = False
    body["real_apply_allowed"] = False
    body["is_production"] = False
    body["contains_real_secret"] = False
    body["fabrication_free"] = True
    body["source_commit"] = _source_commit()
    return body


@router.get("/status")
def get_status():
    return _envelope("status")


@router.get("/isolation")
def get_isolation():
    return _envelope("isolation")


@router.get("/qualification")
def get_qualification():
    return _envelope("qualification")


@router.get("/health")
def get_health():
    return _envelope("health")


@router.get("/e2e")
def get_e2e():
    return _envelope("e2e")


@router.get("/change-control")
def get_change_control():
    return _envelope("change-control")


@router.get("/evidence")
def get_evidence():
    return _envelope("evidence")

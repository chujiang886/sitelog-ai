"""Phase 3.9.14 —— 只读 Dashboard 聚合视图（dashboard，fail-closed）。

``build_readonly_dashboard()`` 把 7 层只读结论聚合成单一可读视图，供 SSOT / 看板 / CI 比对。
视图本身只读，不执行任何动作；所有结论均来自 plan-only harness 结论，并经
``validate_package`` 强制 fail-closed 不变量。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_runtime.change_control import TERMINAL_STATE
from agents.external_staging_runtime.machine_package import (
    build_machine_package,
    validate_package,
)
from agents.external_staging_runtime.readonly_api import (
    get_change_control,
    get_e2e,
    get_evidence,
    get_health,
    get_isolation,
    get_qualification,
    get_status,
)


def build_readonly_dashboard() -> dict[str, Any]:
    pkg = build_machine_package()
    validation = validate_package(pkg)
    layers = {
        "status": get_status(),
        "isolation": get_isolation(),
        "qualification": get_qualification(),
        "health": get_health(),
        "e2e": get_e2e(),
        "change_control": get_change_control(),
        "evidence": get_evidence(),
    }
    return {
        "phase": "3.9.14",
        "terminal_state": TERMINAL_STATE,
        "dashboard": "readonly",
        "package_hash": pkg["package_hash"],
        "package_valid": validation["valid"],
        "engineering_enabled": False,
        "is_production": False,
        "real_apply_allowed": False,
        "real_execution_allowed": False,
        "layers": layers,
        "note": "read-only structural dashboard; no real resource provisioned/executed by AI",
    }


__all__ = ["build_readonly_dashboard"]

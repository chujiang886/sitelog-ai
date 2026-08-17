"""Phase 3.9.14 —— 只读 API 查询层（readonly_api，fail-closed）。

每个端点对应一个只读查询函数，直接复用 7 层 harness 的 ``to_dict()`` 结论，
**绝不**发起任何真实动作（不 apply / 不连接 / 不部署）。所有响应均含统一 fail-closed 标记：
``engineering_enabled=False`` / ``real_apply_allowed=False`` / ``is_production=False`` /
``contains_real_secret=False`` / ``fabrication_free=True``。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_runtime.change_control import (
    TERMINAL_STATE,
    evaluate_change_control,
)
from agents.external_staging_runtime.e2e_harness import EndToEndQualificationHarness
from agents.external_staging_runtime.evidence import build_phase3914_evidence
from agents.external_staging_runtime.isolation import ExternalStagingIsolationAuditor
from agents.external_staging_runtime.machine_package import build_machine_package
from agents.external_staging_runtime.qualification import RuntimeQualificationHarness
from agents.external_staging_runtime.runtime_health import RuntimeHealthHarness
from agents.external_staging_runtime.runtime_manifest import EXTERNAL_RESOURCE_KINDS


def _fb() -> dict[str, bool]:
    """统一 fail-closed 标记（不变量由 machine_package.validate_package 强制）。"""

    return {
        "engineering_enabled": False,
        "real_apply_allowed": False,
        "real_execution_allowed": False,
        "is_production": False,
        "contains_real_secret": False,
        "fabrication_free": True,
    }


def get_status() -> dict[str, Any]:
    pkg = build_machine_package()
    return {
        "endpoint": "status",
        "terminal_state": TERMINAL_STATE,
        "phase": "3.9.14",
        "layer_count": pkg["package"]["layer_count"],
        "total_resources": len(EXTERNAL_RESOURCE_KINDS),
        "resources_pending": len(EXTERNAL_RESOURCE_KINDS),
        "package_hash": pkg["package_hash"],
        "deterministic": pkg["deterministic"],
        **_fb(),
    }


def get_isolation() -> dict[str, Any]:
    report = ExternalStagingIsolationAuditor().audit_all()
    return {"endpoint": "isolation", **report.to_dict(), **_fb()}


def get_qualification() -> dict[str, Any]:
    report = RuntimeQualificationHarness().qualify_all()
    return {"endpoint": "qualification", **report.to_dict(), **_fb()}


def get_health() -> dict[str, Any]:
    report = RuntimeHealthHarness().assess()
    return {"endpoint": "health", **report.to_dict(), **_fb()}


def get_e2e() -> dict[str, Any]:
    plan = EndToEndQualificationHarness().build_plan()
    return {"endpoint": "e2e", **plan.to_dict(), **_fb()}


def get_change_control() -> dict[str, Any]:
    verdict = evaluate_change_control()
    return {"endpoint": "change-control", **verdict.to_dict(), **_fb()}


def get_evidence() -> dict[str, Any]:
    model = build_phase3914_evidence()
    return {"endpoint": "evidence", **model.to_dict(), **_fb()}


def dispatch(endpoint: str) -> dict[str, Any]:
    """只读端点分发（fail-closed：未知端点即抛错，不静默降级）。"""

    table = {
        "status": get_status,
        "isolation": get_isolation,
        "qualification": get_qualification,
        "health": get_health,
        "e2e": get_e2e,
        "change-control": get_change_control,
        "evidence": get_evidence,
    }
    if endpoint not in table:
        raise KeyError(f"unknown read-only endpoint: {endpoint}")
    return table[endpoint]()


__all__ = [
    "get_status",
    "get_isolation",
    "get_qualification",
    "get_health",
    "get_e2e",
    "get_change_control",
    "get_evidence",
    "dispatch",
]

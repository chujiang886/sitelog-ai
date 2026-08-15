"""Phase 3.9.13 —— 确定性执行包（machine_package，T41-T45 支撑）。

生成**确定性**的供给执行包：同一 BOM + 固定常量 → 同一 SHA-256。
包内含 8 资源 BOM（全 PENDING）、``engineering_enabled=False``、``real_resources_provisioned=0``。
此包用于 SSOT / 审计 / CI 比对，证明 AI 未伪造任何真实资源。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    build_default_bom,
)
from agents.config_loader import load_engineering_enabled


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_machine_package() -> dict[str, Any]:
    """构建确定性供给执行包。"""

    bom = [e.to_dict() for e in build_default_bom()]
    package = {
        "schema": "boip.ext_staging.provisioning_execution.1",
        "generated_by": "phase3.9.13.ai_autonomous_execution",
        "engineering_enabled": bool(load_engineering_enabled()),
        "real_resources_provisioned": 0,
        "total_resources": len(bom),
        "resources": bom,
        "note": "plan-only; no real external staging resource provisioned by AI",
    }
    package_hash = hashlib.sha256(
        _canonical_json(package).encode("utf-8")
    ).hexdigest()
    return {
        "package": package,
        "package_hash": package_hash,
        "deterministic": True,
    }


__all__ = ["build_machine_package"]

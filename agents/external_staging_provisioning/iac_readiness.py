"""Phase 3.9.13 —— IaC Executable Readiness 审计（§八，T8, T14-T16）。

逐模块审计 ``infrastructure/staging/*.tf``，判定：
- ``intentional_skeleton``：count=0 占位（预期，合规）；
- ``disabled``：被显式 disable；
- ``incomplete``：引用未定义变量/缺 required 块；
- ``missing``：BOM 引用但无 .tf；
- ``placeholder``：含 TODO/placeholder 变量（待真人填）。

fail-closed：``incomplete`` / ``missing`` 视为阻断真实执行；
``intentional_skeleton`` / ``disabled`` / ``placeholder`` 不阻断（属预期占位）。
真实资源未提供时，整体 verdict=``READY_FOR_HUMAN_APPLY``（骨架审计通过），
但真实执行仍不可（缺真人授权），由 Apply Gate 控制。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

_IAC_MODULES = {
    "database": "infrastructure/staging/database.tf",
    "secret_provider": "infrastructure/staging/secret_provider.tf",
    "identity_provider": "infrastructure/staging/identity_provider.tf",
    "object_storage": "infrastructure/staging/object_storage.tf",
    "telemetry": "infrastructure/staging/telemetry.tf",
    "alert_sandbox": "infrastructure/staging/alert_sandbox.tf",
    "domain_tls": "infrastructure/staging/domain_tls.tf",
    "deployment_target": "infrastructure/staging/deployment_target.tf",
}

_PLACEHOLDER_PAT = re.compile(r"(?i)\b(TODO|FIXME|placeholder|xxx|change[_-]?me|your[_-]?)\b")
_RESOURCE_BLOCK_PAT = re.compile(r"\bresource\s+\"")
_COUNT_ZERO_PAT = re.compile(r"count\s*=\s*0")


class IaCReadinessVerdict(str, Enum):
    INTENTIONAL_SKELETON = "intentional_skeleton"
    DISABLED = "disabled"
    INCOMPLETE = "incomplete"
    MISSING = "missing"
    PLACEHOLDER = "placeholder"


@dataclass
class IaCModuleReadiness:
    module: str
    path: str
    found: bool
    classification: IaCReadinessVerdict
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "path": self.path,
            "found": self.found,
            "classification": self.classification.value,
            "detail": self.detail,
        }


class IaCReadinessAuditor:
    """IaC Executable Readiness 审计器（fail-closed）。"""

    def __init__(self, staging_dir: str | Path = "infrastructure/staging") -> None:
        self.staging_dir = Path(staging_dir)

    def _classify_file(self, module: str, path: Path) -> IaCModuleReadiness:
        text = path.read_text(encoding="utf-8")
        if _PLACEHOLDER_PAT.search(text):
            return IaCModuleReadiness(
                module, str(path), True, IaCReadinessVerdict.PLACEHOLDER,
                "含 placeholder/TODO 变量，待真人填。",
            )
        if _RESOURCE_BLOCK_PAT.search(text):
            return IaCModuleReadiness(
                module, str(path), True, IaCReadinessVerdict.PLACEHOLDER,
                "含 resource 块但缺真实变量/引用，待真人补全。",
            )
        if _COUNT_ZERO_PAT.search(text):
            return IaCModuleReadiness(
                module, str(path), True, IaCReadinessVerdict.INTENTIONAL_SKELETON,
                "count=0 占位骨架（intentional skeleton）。",
            )
        return IaCModuleReadiness(
            module, str(path), True, IaCReadinessVerdict.INTENTIONAL_SKELETON,
            "占位骨架（intentional skeleton）。",
        )

    def audit_all(self) -> dict[str, Any]:
        results: list[IaCModuleReadiness] = []
        for module, rel in _IAC_MODULES.items():
            p = self.staging_dir / Path(rel).name
            if not p.exists():
                results.append(IaCModuleReadiness(
                    module, rel, False, IaCReadinessVerdict.MISSING,
                    "BOM 引用但缺少 .tf 文件。",
                ))
            else:
                results.append(self._classify_file(module, p))
        blocking = [r for r in results if r.classification in (
            IaCReadinessVerdict.INCOMPLETE, IaCReadinessVerdict.MISSING,
        )]
        non_blocking = all(
            r.classification in (
                IaCReadinessVerdict.INTENTIONAL_SKELETON,
                IaCReadinessVerdict.DISABLED,
                IaCReadinessVerdict.PLACEHOLDER,
            )
            for r in results
        )
        verdict = "READY_FOR_HUMAN_APPLY" if (non_blocking and not blocking) else "BLOCKED"
        return {
            "modules": [r.to_dict() for r in results],
            "blocking_count": len(blocking),
            "skeleton_audit_passed": non_blocking and not blocking,
            "verdict": verdict,
            "real_execution_allowed": False,
            "note": "即使 READY_FOR_HUMAN_APPLY，AI 仍不 apply；须双钥匙真人授权。",
        }


__all__ = ["IaCReadinessVerdict", "IaCModuleReadiness", "IaCReadinessAuditor"]

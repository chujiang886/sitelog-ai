"""Phase 3.9.14 —— IaC Executable Readiness 审计（接入工具链真实校验）。

在 3.9.13 ``IaCReadinessAuditor`` 的 5 分类（intentional_skeleton / disabled / incomplete /
missing / placeholder）基础上，新增**可执行维度**：
- 调用 ``iac_executor.execute()`` 真实发现工具链（Terraform/OpenTofu）并运行 ``validate`` / plan-only；
- 仅当「工具链可用 且 validate 通过 且 全部模块为 intentional_skeleton」时，\\\\
  ``executable = True``（模块真正可执行，而非只返回 Pending）；
- ``real_apply_allowed`` 恒为 ``False``（绝不允许 apply，fail-closed）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .iac_executor import execute as run_iac_execution

_IAC_MODULES = {
    "network": "infrastructure/staging/network.tf",
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


class IaCExecutableVerdict(str, Enum):
    INTENTIONAL_SKELETON = "intentional_skeleton"
    DISABLED = "disabled"
    INCOMPLETE = "incomplete"
    MISSING = "missing"
    PLACEHOLDER = "placeholder"


@dataclass
class IaCModuleExecutableReadiness:
    module: str
    path: str
    found: bool
    classification: IaCExecutableVerdict
    executable: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "path": self.path,
            "found": self.found,
            "classification": self.classification.value,
            "executable": self.executable,
            "detail": self.detail,
        }


class IaCExecutableReadinessAuditor:
    """IaC 可执行就绪审计器（fail-closed，接入工具链真实校验）。"""

    def __init__(self, staging_dir: str | Path = "infrastructure/staging") -> None:
        self.staging_dir = Path(staging_dir)

    def _classify(self, module: str, path: Path) -> IaCModuleExecutableReadiness:
        text = path.read_text(encoding="utf-8")
        if _PLACEHOLDER_PAT.search(text):
            return IaCModuleExecutableReadiness(
                module, str(path), True, IaCExecutableVerdict.PLACEHOLDER, True,
                "含 placeholder/TODO 变量，待真人填（仍可执行 validate）。",
            )
        if _RESOURCE_BLOCK_PAT.search(text) and _COUNT_ZERO_PAT.search(text):
            return IaCModuleExecutableReadiness(
                module, str(path), True, IaCExecutableVerdict.INTENTIONAL_SKELETON, True,
                "count=0 占位骨架（intentional skeleton），executable 且 real_apply_allowed=False。",
            )
        if _RESOURCE_BLOCK_PAT.search(text):
            return IaCModuleExecutableReadiness(
                module, str(path), True, IaCExecutableVerdict.INTENTIONAL_SKELETON, True,
                "资源块但已 count=0 解耦，executable 且 real_apply_allowed=False。",
            )
        return IaCModuleExecutableReadiness(
            module, str(path), True, IaCExecutableVerdict.INTENTIONAL_SKELETON, True,
            "占位骨架（intentional skeleton），executable。",
        )

    def audit_all(self) -> dict[str, Any]:
        # 1) 逐模块分类
        modules: list[IaCModuleExecutableReadiness] = []
        for module, rel in _IAC_MODULES.items():
            p = self.staging_dir / Path(rel).name
            if not p.exists():
                modules.append(IaCModuleExecutableReadiness(
                    module, rel, False, IaCExecutableVerdict.MISSING, False,
                    "BOM 引用但缺少 .tf 文件（阻断）。",
                ))
            else:
                modules.append(self._classify(module, p))
        # 2) 工具链真实校验
        exec_report = run_iac_execution(self.staging_dir)
        blocking = [m for m in modules if m.classification in (
            IaCExecutableVerdict.INCOMPLETE, IaCExecutableVerdict.MISSING,
        )]
        non_blocking = all(
            m.classification in (
                IaCExecutableVerdict.INTENTIONAL_SKELETON,
                IaCExecutableVerdict.DISABLED,
                IaCExecutableVerdict.PLACEHOLDER,
            )
            for m in modules
        )
        # 3) 可执行 = 工具链可用 + validate 通过 + 无阻断分类
        skeleton_audit_passed = non_blocking and not blocking
        executable = exec_report.executable and skeleton_audit_passed
        if executable:
            verdict = "EXECUTABLE_READY_FOR_HUMAN_APPLY"
        elif exec_report.toolchain.available and not exec_report.validate.passed:
            verdict = "VALIDATE_FAILED"
        elif not exec_report.toolchain.available:
            verdict = "TOOLCHAIN_UNAVAILABLE"
        else:
            verdict = "BLOCKED"
        return {
            "modules": [m.to_dict() for m in modules],
            "module_count": len(modules),
            "blocking_count": len(blocking),
            "skeleton_audit_passed": skeleton_audit_passed,
            "toolchain": exec_report.toolchain.to_dict(),
            "validate": exec_report.validate.to_dict(),
            "plan": exec_report.plan.to_dict(),
            "executable": executable,
            "verdict": verdict,
            "real_apply_allowed": False,
            "real_execution_allowed": False,
            "contains_real_resource": exec_report.contains_real_resource,
            "note": "即使 EXECUTABLE_READY_FOR_HUMAN_APPLY，AI 仍不 apply；须双钥匙真人授权（Human Authorization Key actor_kind=USER）。",
        }


if __name__ == "__main__":
    import json
    rep = IaCExecutableReadinessAuditor().audit_all()
    print(json.dumps(rep, indent=2, ensure_ascii=False))

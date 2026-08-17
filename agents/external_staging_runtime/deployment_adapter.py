"""Phase 3.9.14 —— Staging Runtime Deployment Adapter（plan-only，fail-closed）。

将「IaC 可执行校验」与「运行时部署清单」编排为一份 plan-only 部署计划。适配器**只产出计划**，
绝不执行 apply / deploy：本模块刻意不定义 ``apply()`` / ``deploy()`` 方法——真实部署由主理人
在双钥匙（Human Authorization Key, actor_kind=USER）授权后于带外执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .iac_executor import execute as run_iac_execution
from .runtime_manifest import build_staging_runtime_manifest


class StagingRuntimeDeploymentForbiddenError(RuntimeError):
    """部署被 fail-closed 禁止时抛出（例如检测到真实资源泄漏）。"""


@dataclass
class RuntimeDeploymentPlan:
    plan_only: bool
    iac_executable: bool
    real_apply_allowed: bool
    manifest_hash: str
    external_resource_count: int
    runtime_qualification_count: int
    verdict: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_only": self.plan_only,
            "iac_executable": self.iac_executable,
            "real_apply_allowed": self.real_apply_allowed,
            "manifest_hash": self.manifest_hash,
            "external_resource_count": self.external_resource_count,
            "runtime_qualification_count": self.runtime_qualification_count,
            "verdict": self.verdict,
            "note": self.note,
        }


class StagingRuntimeDeploymentAdapter:
    """运行时部署适配器：仅 plan-only，禁止 apply。"""

    def __init__(self, staging_dir: str = "infrastructure/staging") -> None:
        self.staging_dir = staging_dir
        self._exec = run_iac_execution(staging_dir)

    def plan(self) -> RuntimeDeploymentPlan:
        """生成 plan-only 部署计划（从不 apply）。"""
        if self._exec.contains_real_resource:
            raise StagingRuntimeDeploymentForbiddenError(
                "检测到真实资源泄漏，部署被禁止（fail-closed）。"
            )
        manifest = build_staging_runtime_manifest(self.staging_dir)
        verdict = "PLAN_ONLY_READY_FOR_HUMAN_APPLY" if manifest.iac_executable else "BLOCKED"
        return RuntimeDeploymentPlan(
            plan_only=True,
            iac_executable=manifest.iac_executable,
            real_apply_allowed=False,
            manifest_hash=manifest.compute_hash(),
            external_resource_count=len(manifest.external_resources),
            runtime_qualification_count=len(manifest.runtime_qualifications),
            verdict=verdict,
            note=manifest.note,
        )

    def validate_gate(self) -> dict[str, Any]:
        """fail-closed 部署闸门：恒拒 apply。"""
        return {
            "real_apply_allowed": False,
            "real_execution_allowed": False,
            "engineering_enabled": False,
            "is_production": False,
            "iac_executable": self._exec.executable,
            "contains_real_resource": self._exec.contains_real_resource,
            "gate": "PLAN_ONLY" if not self._exec.contains_real_resource else "BLOCKED_REAL_RESOURCE",
        }

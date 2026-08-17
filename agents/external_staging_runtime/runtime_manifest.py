"""Phase 3.9.14 —— Staging Runtime Deployment Manifest（fail-closed）。

构建「运行时部署资格」确定性清单：8 个 External Resource 全部 PENDING（未真实供给），
13 项 Runtime Qualification 全部 NOT_EXECUTED（plan-only，未真实运行），部署模式恒 PLAN_ONLY，
``real_apply_allowed`` 恒 False。清单内容经 SHA-256 确定性哈希，供证据包 / SSOT 复用。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .iac_executor import execute as run_iac_execution

# 8 个 External Staging 资源类型（与 3.9.13 ResourceRegistry 一致）
EXTERNAL_RESOURCE_KINDS = [
    "database",
    "secret_provider",
    "identity_provider",
    "object_storage",
    "telemetry",
    "alert_sandbox",
    "domain_tls",
    "deployment_target",
]

# 13 项 Runtime Qualification（对应 staging_runtime 包的能力域；本 Phase 仅记为 plan-only 待执行）
RUNTIME_QUALIFICATION_CHECKS = [
    "environment_classification",
    "fingerprint_isolation",
    "isolation_guard",
    "config_readiness",
    "secret_isolation",
    "local_profile",
    "execution_scope",
    "db_safety",
    "data_policy",
    "identity_isolation",
    "token_isolation",
    "observability_health",
    "gate_validation",
]

TERMINAL_STATE = "PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO"
CANONICAL_PHASE_ID = "3.9.14-external-staging-runtime-deployment-e2e-qualification"


@dataclass
class _ResourceEntry:
    kind: str
    status: str = "PENDING_EXTERNAL_STAGING_RESOURCE"
    registered: bool = False
    provisioned: bool = False
    verified: bool = False


@dataclass
class _QualificationEntry:
    check: str
    status: str = "NOT_EXECUTED"
    executed: bool = False
    result: str = "PLAN_ONLY"


@dataclass
class StagingRuntimeManifest:
    phase: str = "3.9.14"
    canonical_phase_id: str = CANONICAL_PHASE_ID
    terminal_state: str = TERMINAL_STATE
    engineering_enabled: bool = False
    is_production: bool = False
    real_apply_allowed: bool = False
    real_execution_allowed: bool = False
    deployment_mode: str = "PLAN_ONLY"
    iac_executable: bool = False
    external_resources: list[_ResourceEntry] = field(default_factory=list)
    runtime_qualifications: list[_QualificationEntry] = field(default_factory=list)
    toolchain: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def compute_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_staging_runtime_manifest(staging_dir: str = "infrastructure/staging") -> StagingRuntimeManifest:
    """构建 fail-closed 运行时部署清单。IaC 可执行性由工具链真实校验注入。"""
    exec_report = run_iac_execution(staging_dir)
    resources = [_ResourceEntry(kind=k) for k in EXTERNAL_RESOURCE_KINDS]
    quals = [_QualificationEntry(check=c) for c in RUNTIME_QUALIFICATION_CHECKS]
    manifest = StagingRuntimeManifest(
        iac_executable=exec_report.executable,
        external_resources=resources,
        runtime_qualifications=quals,
        toolchain=exec_report.toolchain.to_dict(),
        note=(
            "8 External Resources 全部 PENDING（Track B 真人供给）；13 Runtime Qualification 全部 "
            "NOT_EXECUTED（plan-only）。部署模式 PLAN_ONLY，real_apply_allowed=False。IaC 模块已可执行"
            f"（verdict={exec_report.verdict}），但真实 apply 须双钥匙真人授权。"
        ),
    )
    # fail-closed 自检：任何违反即抛错
    assert manifest.engineering_enabled is False
    assert manifest.is_production is False
    assert manifest.real_apply_allowed is False
    assert manifest.real_execution_allowed is False
    return manifest


if __name__ == "__main__":
    m = build_staging_runtime_manifest()
    print(json.dumps(m.to_dict(), indent=2, ensure_ascii=False))
    print("MANIFEST_HASH=", m.compute_hash())

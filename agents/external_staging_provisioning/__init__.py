"""Phase 3.9.12 External Staging Provisioning Operator Readiness 包。

把 8 类真实外部资源从 ``pending_external_staging_resource`` 推进到「可被真人/运维按
明确 Runbook 与 IaC 模板实际 Provision」的就绪状态（**不实际 Provision**）。

终态：``EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO``。
最高红线：``engineering_enabled=false``；8 资源真实输入统一
``PENDING_EXTERNAL_STAGING_RESOURCE``；Operator Gate 仅 3 态（禁 GO/APPROVED）；
StagingProvisioningExecutionMode 仅 PLAN/VALIDATE/DRY_RUN/HUMAN_AUTHORIZED_APPLY（禁 AUTO/PRODUCTION）。
"""

from __future__ import annotations

from agents.external_staging_provisioning.models import (
    EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE,
    ExternalStagingProvisioningError,
    OperatorGateStatus,
    ProvisioningPlan,
    ProvisioningStep,
    ProvisioningStepStatus,
    StagingProvisioningExecutionMode,
)
from agents.external_staging_provisioning.bom import (
    ProvisioningBom,
    ProvisioningBomEntry,
)
from agents.external_staging_provisioning.dry_run_guard import (
    DryRunGuardError,
    IacDryRunGuard,
)
from agents.external_staging_provisioning.gate import (
    ExternalStagingProvisioningOperatorGate,
    OperatorGateResult,
)
from agents.external_staging_provisioning.validator import (
    ExternalStagingProvisioningValidator,
)
from agents.external_staging_provisioning.package import (
    build_provisioning_package,
    package_hash,
)
from agents.external_staging_provisioning.api_contract import build_api_contract
from agents.external_staging_provisioning.security import (
    ExternalStagingProvisioningSecurityValidator,
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
)
from agents.external_staging_provisioning.cost_guard import (
    StagingCostGuard,
    DEFAULT_COST_BUDGET,
    CostCheckResult,
)
from agents.external_staging_provisioning.audit import (
    PROVISIONING_AUDIT_CATEGORIES,
    ProvisioningAuditEvent,
    build_provisioning_audit_event,
)

__all__ = [
    "EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE",
    "ExternalStagingProvisioningError",
    "OperatorGateStatus",
    "ProvisioningPlan",
    "ProvisioningStep",
    "ProvisioningStepStatus",
    "StagingProvisioningExecutionMode",
    "ProvisioningBom",
    "ProvisioningBomEntry",
    "DryRunGuardError",
    "IacDryRunGuard",
    "ExternalStagingProvisioningOperatorGate",
    "OperatorGateResult",
    "ExternalStagingProvisioningValidator",
    "build_provisioning_package",
    "package_hash",
    "build_api_contract",
    "ExternalStagingProvisioningSecurityValidator",
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    "StagingCostGuard",
    "DEFAULT_COST_BUDGET",
    "CostCheckResult",
    "PROVISIONING_AUDIT_CATEGORIES",
    "ProvisioningAuditEvent",
    "build_provisioning_audit_event",
]

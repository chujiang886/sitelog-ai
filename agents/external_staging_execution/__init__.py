"""Phase 3.9.11 External Staging Execution & Qualification Layer。

对外统一导出本层公共 API。详见各子模块。
"""

from agents.external_staging_execution.adapters import (
    AdapterProbeResult,
    ExternalStagingExecutionAdapter,
    adapters_contract_test_all_pass,
    assert_no_real_execution_claimed,
    build_adapter_registry,
    probe_all,
)
from agents.external_staging_execution.api_contract import (
    EXPECTED_TOTAL_ROUTES,
    build_api_contract,
)
from agents.external_staging_execution.config import (
    fingerprint_collision_with_production,
    load_external_staging_identity,
)
from agents.external_staging_execution.evidence import (
    ExecutionEvidenceChain,
    ExecutionEvidenceItem,
)
from agents.external_staging_execution.gate import ExternalStagingExecutionGate
from agents.external_staging_execution.models import (
    EXTERNAL_STAGING_ENVIRONMENT,
    EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStepKind,
    ExecutionStepStatus,
    ExternalStagingExecutionError,
    assert_not_forbidden_step_state,
    build_default_execution_plan,
)
from agents.external_staging_execution.package import (
    build_execution_package,
    package_hash,
)
from agents.external_staging_execution.pipeline import ExecutionPipeline
from agents.external_staging_execution.preflight import (
    PreflightCheck,
    PreflightReport,
    run_preflight,
)
from agents.external_staging_execution.security import (
    ALLOWED_ACTIONS,
    ALLOWED_SCOPES,
    ExecutionSecurityCheckResult,
    ExternalStagingExecutionSecurityValidator,
    FORBIDDEN_ACTIONS,
)

__all__ = [
    "EXTERNAL_STAGING_ENVIRONMENT",
    "EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE",
    "ExecutionStepKind",
    "ExecutionStepStatus",
    "ExecutionStep",
    "ExecutionPlan",
    "build_default_execution_plan",
    "assert_not_forbidden_step_state",
    "ExternalStagingExecutionError",
    "AdapterProbeResult",
    "ExternalStagingExecutionAdapter",
    "build_adapter_registry",
    "probe_all",
    "adapters_contract_test_all_pass",
    "assert_no_real_execution_claimed",
    "ExecutionEvidenceItem",
    "ExecutionEvidenceChain",
    "ExternalStagingExecutionGate",
    "ExecutionPipeline",
    "PreflightCheck",
    "PreflightReport",
    "run_preflight",
    "build_execution_package",
    "package_hash",
    "load_external_staging_identity",
    "fingerprint_collision_with_production",
    "build_api_contract",
    "EXPECTED_TOTAL_ROUTES",
    "ALLOWED_SCOPES",
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    "ExecutionSecurityCheckResult",
    "ExternalStagingExecutionSecurityValidator",
]

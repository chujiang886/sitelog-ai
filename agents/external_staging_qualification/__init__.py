"""Phase 3.9.10 External Staging Qualification & Evidence Integration Layer。

对外统一导出本层公共 API。详见各子模块。
"""

from agents.external_staging_qualification.config import (
    fingerprint_collision_with_production,
    load_external_staging_identity,
)
from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_qualification.deployment import (
    DeploymentTarget,
    ExternalStagingDeploymentEvidence,
    ExternalStagingDeploymentProvider,
)
from agents.external_staging_qualification.denylist import (
    DEFAULT_PRODUCTION_DENYLIST,
    ProductionDenylistEntry,
    ProductionDenylistViolation,
    ProductionReferenceDenylist,
    ProductionResourceKind,
    RESOURCE_TO_PRODUCTION_KIND,
)
from agents.external_staging_qualification.evidence import (
    EvidenceChain,
    EvidenceScope,
    EvidenceType,
    ExternalStagingQualificationEvidence,
    make_evidence,
)
from agents.external_staging_qualification.gate import (
    ExternalStagingQualificationGate,
    GateResult,
)
from agents.external_staging_qualification.isolation import (
    CrossEnvironmentIsolationEvidence,
    CrossEnvironmentIsolationProver,
    IsolationVerdict,
)
from agents.external_staging_qualification.models import (
    CredentialReference,
    EXTERNAL_STAGING_ENVIRONMENT,
    EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE,
    ExternalStagingEnvironmentIdentity,
    ExternalStagingIdentityError,
    ExternalStagingResource,
    ExternalStagingResourceRegistry,
    GateStatus,
    ResourceQualificationStatus,
    ResourceType,
    RuntimeHealthStatus,
    RESOURCE_TYPE_ORDER,
)
from agents.external_staging_qualification.package import (
    build_qualification_package,
    package_hash,
)
from agents.external_staging_qualification.pipeline import QualificationPipeline
from agents.external_staging_qualification.probes import (
    ExternalStagingConnectivityProbe,
    ProbeContext,
    ProbeResult,
)
from agents.external_staging_qualification.qualification import (
    ExternalStagingQualifier,
    ResourceQualificationResult,
)
from agents.external_staging_qualification.runtime import (
    ComponentHealth,
    RUNTIME_COMPONENTS,
    RuntimeHealthReport,
    RuntimeQualification,
)
from agents.external_staging_qualification.scenarios import (
    assert_no_production_recovery,
    ExternalStagingFailureSimulator,
    ExternalStagingRecoverySimulator,
    FailureScenario,
    RecoveryOutcome,
)
from agents.external_staging_qualification.security import (
    Actor,
    ExternalStagingSecurityValidator,
    RequestScope,
    SecurityCheckResult,
)

__all__ = [
    "EXTERNAL_STAGING_ENVIRONMENT",
    "EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE",
    "ResourceType",
    "RESOURCE_TYPE_ORDER",
    "RuntimeHealthStatus",
    "ResourceQualificationStatus",
    "GateStatus",
    "ExternalStagingResource",
    "ExternalStagingResourceRegistry",
    "ExternalStagingEnvironmentIdentity",
    "ExternalStagingIdentityError",
    "CredentialReference",  # noqa: F401  (defined in models, imported below)
    "load_external_staging_identity",
    "fingerprint_collision_with_production",
    "assert_no_credential_leak",
    "CredentialLeakError",
    "DeploymentTarget",
    "ExternalStagingDeploymentEvidence",
    "ExternalStagingDeploymentProvider",
    "DEFAULT_PRODUCTION_DENYLIST",
    "ProductionDenylistEntry",
    "ProductionDenylistViolation",
    "ProductionReferenceDenylist",
    "ProductionResourceKind",
    "RESOURCE_TO_PRODUCTION_KIND",
    "EvidenceChain",
    "EvidenceScope",
    "EvidenceType",
    "ExternalStagingQualificationEvidence",
    "make_evidence",
    "ExternalStagingQualificationGate",
    "GateResult",
    "CrossEnvironmentIsolationEvidence",
    "CrossEnvironmentIsolationProver",
    "IsolationVerdict",
    "build_qualification_package",
    "package_hash",
    "QualificationPipeline",
    "ExternalStagingConnectivityProbe",
    "ProbeContext",
    "ProbeResult",
    "ExternalStagingQualifier",
    "ResourceQualificationResult",
    "ComponentHealth",
    "RUNTIME_COMPONENTS",
    "RuntimeHealthReport",
    "RuntimeQualification",
    "FailureScenario",
    "RecoveryOutcome",
    "ExternalStagingFailureSimulator",
    "ExternalStagingRecoverySimulator",
    "assert_no_production_recovery",
    "Actor",
    "RequestScope",
    "SecurityCheckResult",
    "ExternalStagingSecurityValidator",
]

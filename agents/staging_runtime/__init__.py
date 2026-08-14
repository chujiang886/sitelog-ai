"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— 运行环境包。

本包提供「代码级证明 Staging != Production」的三件套 + 护栏：
- ``environment``：``RuntimeEnvironment`` / ``EnvironmentIdentity`` / ``EnvironmentResources`` / ``classify_environment``
- ``fingerprint``：``EnvironmentFingerprint`` / ``compute_environment_fingerprint``
- ``isolation_guard``：``EnvironmentIsolationGuard`` / ``IsolationVerdict`` / ``StagingIsolationViolationError``
- ``config``：``load_staging_identity`` / ``StagingResourceReadiness`` / ``staging_resource_readiness``
- ``secret_provider``：``StagingSecretProvider`` / ``StagingSecretIsolationError``
- ``local_profile``：``LocalStagingProfile`` / ``LocalStagingService`` / ``LocalStagingProfileError``

最高红线（fail-closed，覆盖本阶段 22 条之核心）：
① 全程 ``engineering_enabled=false``（护栏构造即断言 ``safety_invariants_ok()``）。
② 不输出 ``engineering_approved``。
③ 不真实部署 / 不真实 DB migration / 不改 Production 配置 / 不写真实 Secret / 不改 Production DB /
   不真实回滚 / 不输出 GO / 不代四角色签署 / 不改 ``engineering_enabled``。
④ 不把 Staging 说成 Production；不复用 Production 的 DB/Secret/IdP/Storage/Alert；
   不自动关 Incident / 不跑 Runbook / 不 skip 掩盖失败 / 不删断言换绿 / 不伪造结果 /
   不推导 Production Approved。
"""

from __future__ import annotations

from agents.staging_runtime.environment import (
    EnvironmentClassificationError,
    EnvironmentIdentity,
    EnvironmentResources,
    PRODUCTION_FORBIDDEN_RESOURCE_KINDS,
    RuntimeEnvironment,
    classify_environment,
)
from agents.staging_runtime.fingerprint import (
    compute_environment_fingerprint,
    EnvironmentFingerprint,
    fingerprint_environment,
)
from agents.staging_runtime.isolation_guard import (
    EnvironmentIsolationGuard,
    IsolationVerdict,
    IsolationViolation,
    StagingIsolationViolationError,
)
from agents.staging_runtime.config import (
    load_staging_identity,
    load_forbidden_production_fingerprints,
    staging_resource_readiness,
    StagingResourceReadiness,
    StagingConfigError,
)
from agents.staging_runtime.secret_provider import (
    StagingSecretProvider,
    StagingSecretIsolationError,
    StagingSecretResolution,
)
from agents.staging_runtime.local_profile import (
    LocalStagingProfile,
    LocalStagingService,
    LocalStagingProfileError,
)
from agents.staging_runtime.manifest import (
    StagingRuntimeManifest,
    StagingManifestProductionError,
    build_staging_runtime_manifest,
)
from agents.staging_runtime.deployment import (
    StagingDeploymentForbiddenError,
    StagingDeploymentPlan,
    StagingDeploymentProvider,
)
from agents.staging_runtime.execution_scope import (
    FORBIDDEN_PRODUCTION_ACTIONS,
    ALLOWED_STAGING_ACTIONS,
    StagingExecutionScopeViolation,
    StagingExecutionVerdict,
    StagingExecutionScope,
)
from agents.staging_runtime.db import (
    StagingDatabaseError,
    StagingMigrationForbiddenError,
    StagingDatabaseDescriptor,
    StagingDatabaseProvider,
    StagingDatabaseSafety,
    MigrationPlan,
    MigrationVerdict,
    StagingMigrationValidator,
    StagingMigrationSafety,
)
from agents.staging_runtime.data_policy import (
    ALLOWED_STAGING_DATA_CLASSES,
    FORBIDDEN_STAGING_DATA_CLASSES,
    StagingDataPolicyViolation,
    DataClassificationVerdict,
    StagingDataPolicy,
)
from agents.staging_runtime.identity_provider import (
    StagingIdentityProviderError,
    StagingIdentityDescriptor,
    StagingIdentityProvider,
)
from agents.staging_runtime.token_isolation import (
    StagingTokenIsolationError,
    TokenIsolationVerdict,
    StagingTokenIsolation,
)
from agents.staging_runtime.observability import (
    StagingObservabilityError,
    HealthCheckDescriptor,
    TelemetryDescriptor,
    StagingRuntimeHealth,
    StagingTelemetry,
)
from agents.staging_runtime.alerting import (
    StagingAlertingError,
    StagingAlertDescriptor,
    StagingAlertChannel,
    StagingOnCallSandbox,
)
from agents.staging_runtime.llm_voice import (
    StagingLLMVoiceError,
    ValidationDescriptor,
    StagingLLMValidation,
    StagingVoiceValidation,
)
from agents.staging_runtime.evidence import (
    StagingEvidenceItem,
    StagingEvidenceModel,
    build_staging_evidence,
)
from agents.staging_runtime.gate import (
    TERMINAL_STATE,
    StagingGateCheck,
    StagingGateVerdict,
    StagingGateError,
    StagingValidationGate,
)
from agents.staging_runtime.packet import (
    SCHEMA_VERSION,
    StagingEvidencePacket,
    build_staging_packet,
    validate_packet,
    PacketValidationVerdict,
    StagingPacketValidationError,
    StagingPacketScanner,
    PacketScanVerdict,
    StagingPacketScanError,
    HUMAN_VERIFICATION_CHECKLIST,
)

__all__ = [
    "RuntimeEnvironment",
    "EnvironmentIdentity",
    "EnvironmentResources",
    "EnvironmentClassificationError",
    "PRODUCTION_FORBIDDEN_RESOURCE_KINDS",
    "classify_environment",
    "EnvironmentFingerprint",
    "compute_environment_fingerprint",
    "fingerprint_environment",
    "EnvironmentIsolationGuard",
    "IsolationVerdict",
    "IsolationViolation",
    "StagingIsolationViolationError",
    "load_staging_identity",
    "load_forbidden_production_fingerprints",
    "staging_resource_readiness",
    "StagingResourceReadiness",
    "StagingConfigError",
    "StagingSecretProvider",
    "StagingSecretIsolationError",
    "StagingSecretResolution",
    "LocalStagingProfile",
    "LocalStagingService",
    "LocalStagingProfileError",
    "StagingRuntimeManifest",
    "StagingManifestProductionError",
    "build_staging_runtime_manifest",
    "StagingDeploymentForbiddenError",
    "StagingDeploymentPlan",
    "StagingDeploymentProvider",
    "FORBIDDEN_PRODUCTION_ACTIONS",
    "ALLOWED_STAGING_ACTIONS",
    "StagingExecutionScopeViolation",
    "StagingExecutionVerdict",
    "StagingExecutionScope",
    "StagingDatabaseError",
    "StagingMigrationForbiddenError",
    "StagingDatabaseDescriptor",
    "StagingDatabaseProvider",
    "StagingDatabaseSafety",
    "MigrationPlan",
    "MigrationVerdict",
    "StagingMigrationValidator",
    "StagingMigrationSafety",
    "ALLOWED_STAGING_DATA_CLASSES",
    "FORBIDDEN_STAGING_DATA_CLASSES",
    "StagingDataPolicyViolation",
    "DataClassificationVerdict",
    "StagingDataPolicy",
    "StagingIdentityProviderError",
    "StagingIdentityDescriptor",
    "StagingIdentityProvider",
    "StagingTokenIsolationError",
    "TokenIsolationVerdict",
    "StagingTokenIsolation",
    "StagingObservabilityError",
    "HealthCheckDescriptor",
    "TelemetryDescriptor",
    "StagingRuntimeHealth",
    "StagingTelemetry",
    "StagingAlertingError",
    "StagingAlertDescriptor",
    "StagingAlertChannel",
    "StagingOnCallSandbox",
    "StagingLLMVoiceError",
    "ValidationDescriptor",
    "StagingLLMValidation",
    "StagingVoiceValidation",
    "StagingEvidenceItem",
    "StagingEvidenceModel",
    "build_staging_evidence",
    "TERMINAL_STATE",
    "StagingGateCheck",
    "StagingGateVerdict",
    "StagingGateError",
    "StagingValidationGate",
    "SCHEMA_VERSION",
    "StagingEvidencePacket",
    "build_staging_packet",
    "validate_packet",
    "PacketValidationVerdict",
    "StagingPacketValidationError",
    "StagingPacketScanner",
    "PacketScanVerdict",
    "StagingPacketScanError",
    "HUMAN_VERIFICATION_CHECKLIST",
]

"""Phase 3.9.10 —— External Staging Identity Loader（Tasks 4, 8）。

构造 ``ExternalStagingEnvironmentIdentity``（production=false）并生成结构指纹。
指纹用于与 Production fingerprint 比对；相同 → 拒绝（BLOCKED）。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ExternalStagingIdentityError,
)
from agents.staging_runtime.environment import (
    EnvironmentResources,
    RuntimeEnvironment,
)
from agents.staging_runtime.fingerprint import (
    compute_environment_fingerprint,
    EnvironmentFingerprint,
)


def load_external_staging_identity(
    *,
    organization_id: str = "",
    domain_reference: str = "",
    deployment_target_reference: str = "",
    database_reference: str = "",
    idp_reference: str = "",
    storage_reference: str = "",
    telemetry_reference: str = "",
    alert_reference: str = "",
) -> ExternalStagingEnvironmentIdentity:
    """构造外部预生产环境身份（production=false）+ 指纹。"""

    identity = ExternalStagingEnvironmentIdentity(
        environment=RuntimeEnvironment.EXTERNAL_STAGING.value,
        production=False,
        organization_id=organization_id,
        domain_reference=domain_reference,
        deployment_target_reference=deployment_target_reference,
        database_reference=database_reference,
        idp_reference=idp_reference,
        storage_reference=storage_reference,
        telemetry_reference=telemetry_reference,
        alert_reference=alert_reference,
    )
    fp = compute_environment_fingerprint(
        kind=RuntimeEnvironment.EXTERNAL_STAGING,
        name="external-staging",
        purpose="external-preproduction-qualification",
        resources=EnvironmentResources(
            database=database_reference or None,
            secret=None,
            identity_provider=idp_reference or None,
            storage=storage_reference or None,
            alert=alert_reference or None,
        ),
    )
    identity = ExternalStagingEnvironmentIdentity(
        **{**identity.to_dict(), "fingerprint": fp.value}
    )
    return identity


def fingerprint_collision_with_production(
    identity: ExternalStagingEnvironmentIdentity,
    production_fingerprint: str,
) -> bool:
    """判断外部预生产指纹是否与 Production 指纹相同（相同 → 拒绝）。"""

    if not identity.fingerprint or not production_fingerprint:
        return False
    return identity.fingerprint == production_fingerprint


__all__ = [
    "load_external_staging_identity",
    "fingerprint_collision_with_production",
]

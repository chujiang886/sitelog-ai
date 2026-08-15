"""Phase 3.9.10 —— External Staging Resource Qualification（Tasks 7-16）。

对 8 类资源逐项做：Connectivity（探针） → Isolation（隔离） → Qualification 综合，
回填 ``ExternalStagingResource`` 的状态字段并产出证据。

fail-closed：
- 真实资源/引用缺失 → 状态回落 ``PENDING_EXTERNAL_STAGING_RESOURCE``，
  **不**伪造 ``CONNECTIVITY_VERIFIED`` / ``QUALIFIED_EXTERNAL_STAGING``；
- 命中 Production Denylist → ``BLOCKED``；
- 绝不触碰 Production 资源、绝不读取 Secret 原值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.denylist import (
    ProductionDenylistViolation,
    ProductionReferenceDenylist,
    RESOURCE_TO_PRODUCTION_KIND,
)
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ExternalStagingResource,
    ExternalStagingResourceRegistry,
    ResourceQualificationStatus,
    ResourceType,
)
from agents.external_staging_qualification.probes import (
    ExternalStagingConnectivityProbe,
    ProbeContext,
    ProbeResult,
)


@dataclass
class ResourceQualificationResult:
    """单资源资格验证结果（含证据引用）。"""

    resource: ExternalStagingResource
    probe: ProbeResult | None = None
    isolation_status: str = ResourceQualificationStatus.ISOLATION_PENDING.value
    qualification_status: str = (
        ResourceQualificationStatus.QUALIFICATION_PENDING.value
    )
    blocked: bool = False
    blocked_reason: str = ""
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource.resource_id,
            "resource_type": self.resource.resource_type.value,
            "connectivity_status": (
                self.probe.status.value if self.probe else self.resource.connectivity_status
            ),
            "isolation_status": self.isolation_status,
            "qualification_status": self.qualification_status,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "evidence_refs": list(self.evidence_refs),
        }


class ExternalStagingQualifier:
    """外部预生产资源资格验证编排器。"""

    def __init__(
        self,
        environment: ExternalStagingEnvironmentIdentity,
        denylist: ProductionReferenceDenylist | None = None,
    ) -> None:
        self._env = environment
        self._denylist = denylist or ProductionReferenceDenylist()
        self._probe = ExternalStagingConnectivityProbe(
            ProbeContext(environment=environment, denylist=self._denylist)
        )

    def qualify_resource(
        self,
        resource: ExternalStagingResource,
        *,
        reference: str = "",
        configured: bool = False,
    ) -> ResourceQualificationResult:
        """对单资源做 Connectivity → Isolation → Qualification。"""

        # 1) Connectivity（探针）
        try:
            probe = self._run_probe(
                resource.resource_type, reference, configured=configured
            )
        except ProductionDenylistViolation as exc:
            # 命中 Production Denylist：整资源 BLOCKED
            updated = ExternalStagingResource(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                environment=resource.environment,
                required=resource.required,
                configured=configured,
                verified=False,
                owner_role=resource.owner_role,
                source_reference=reference,
                credential_reference=resource.credential_reference,
                isolation_status=ResourceQualificationStatus.BLOCKED.value,
                connectivity_status=ResourceQualificationStatus.BLOCKED.value,
                qualification_status=ResourceQualificationStatus.BLOCKED.value,
                evidence_refs=(),
                last_checked_at=resource.last_checked_at,
            )
            return ResourceQualificationResult(
                resource=updated,
                probe=None,
                isolation_status=ResourceQualificationStatus.BLOCKED.value,
                qualification_status=ResourceQualificationStatus.BLOCKED.value,
                blocked=True,
                blocked_reason=str(exc),
                evidence_refs=(),
            )

        # 2) Isolation（隔离）
        isolation_status, blocked, blocked_reason = self._check_isolation(
            resource.resource_type, reference
        )
        if blocked:
            # 命中 Production Denylist：整资源 BLOCKED
            updated = ExternalStagingResource(
                **{**resource.to_dict(), "configured": configured}
            )
            updated.isolation_status = ResourceQualificationStatus.BLOCKED.value
            updated.connectivity_status = (
                probe.status.value if probe else ResourceQualificationStatus.BLOCKED.value
            )
            updated.qualification_status = ResourceQualificationStatus.BLOCKED.value
            updated.verified = False
            return ResourceQualificationResult(
                resource=updated,
                probe=probe,
                isolation_status=ResourceQualificationStatus.BLOCKED.value,
                qualification_status=ResourceQualificationStatus.BLOCKED.value,
                blocked=True,
                blocked_reason=blocked_reason,
                evidence_refs=(probe.evidence_id,) if probe else (),
            )

        # 3) Qualification 综合（缺真实资源 → 不越级到 QUALIFIED）
        if not configured or not reference:
            qual_status = (
                ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE.value
            )
            verified = False
        else:
            # 已登记引用但未完成线下真实验证 → 停留在 pending 验证态
            if probe is not None and probe.status in (
                ResourceQualificationStatus.CONNECTIVITY_VERIFIED,
                ResourceQualificationStatus.CONNECTIVITY_PENDING,
            ):
                qual_status = ResourceQualificationStatus.QUALIFICATION_PENDING.value
            else:
                qual_status = (
                    ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE.value
                )
            verified = False  # 无真实验证证据前不得置 verified=True

        updated = ExternalStagingResource(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            environment=resource.environment,
            required=resource.required,
            configured=configured,
            verified=verified,
            owner_role=resource.owner_role,
            source_reference=reference,
            credential_reference=resource.credential_reference,
            isolation_status=isolation_status,
            connectivity_status=(
                probe.status.value if probe else resource.connectivity_status
            ),
            qualification_status=qual_status,
            evidence_refs=(probe.evidence_id,) if probe else (),
            last_checked_at=resource.last_checked_at,
        )
        return ResourceQualificationResult(
            resource=updated,
            probe=probe,
            isolation_status=isolation_status,
            qualification_status=qual_status,
            evidence_refs=(probe.evidence_id,) if probe else (),
        )

    def qualify_registry(
        self,
        registry: ExternalStagingResourceRegistry,
        *,
        references: dict[ResourceType, str] | None = None,
        configured_flags: dict[ResourceType, bool] | None = None,
    ) -> tuple[ExternalStagingResourceRegistry, tuple[ResourceQualificationResult, ...]]:
        """对登记簿 8 资源批量资格验证。"""

        references = references or {}
        configured_flags = configured_flags or {}
        results: list[ResourceQualificationResult] = []
        updated: list[ExternalStagingResource] = []
        for r in registry.resources:
            ref = references.get(r.resource_type, "")
            cfg = configured_flags.get(r.resource_type, False)
            res = self.qualify_resource(r, reference=ref, configured=cfg)
            results.append(res)
            updated.append(res.resource)
        return ExternalStagingResourceRegistry(resources=tuple(updated)), tuple(results)

    # ---- 内部 ----

    def _run_probe(
        self, rtype: ResourceType, reference: str, *, configured: bool
    ) -> ProbeResult:
        method = {
            ResourceType.DATABASE: self._probe.probe_database,
            ResourceType.SECRET_PROVIDER: self._probe.probe_secret_provider,
            ResourceType.IDENTITY_PROVIDER: self._probe.probe_idp,
            ResourceType.OBJECT_STORAGE: self._probe.probe_storage,
            ResourceType.TELEMETRY: self._probe.probe_telemetry,
            ResourceType.ALERT_SANDBOX: self._probe.probe_alert,
            ResourceType.DOMAIN_TLS: self._probe.probe_domain_tls,
            ResourceType.DEPLOYMENT_TARGET: self._probe.probe_deployment_target,
        }[rtype]
        return method(reference, configured=configured)

    def _check_isolation(
        self, rtype: ResourceType, reference: str
    ) -> tuple[str, bool, str]:
        kind = RESOURCE_TO_PRODUCTION_KIND[rtype]
        try:
            self._denylist.check(kind, reference)
        except ProductionDenylistViolation as exc:
            return ResourceQualificationStatus.BLOCKED.value, True, str(exc)
        # 无 Production 引用可比对时：隔离无法证明 → ISOLATION_PENDING
        if not reference:
            return ResourceQualificationStatus.ISOLATION_PENDING.value, False, ""
        return ResourceQualificationStatus.ISOLATION_PENDING.value, False, ""


__all__ = [
    "ResourceQualificationResult",
    "ExternalStagingQualifier",
]

"""Phase 3.9.10 —— Qualification Pipeline / E2E Framework（Task 33, 30）。

串联全链路（resource-less 与 resource-ful 两条路径）：

Resource Registration → Connectivity → Isolation → Deploy(plan) → Runtime Health →
Telemetry → Alert → Failure/Recovery → Evidence → Gate → Human Review。

- ``run_qualification_pipeline``：resource-less dry-run（默认）→ 正确识别 pending、
  不 fallback production、不伪造 connectivity/validation、Gate 保持 pending；
- 传入 ``references`` / ``configured_flags`` 时走 resource-ful 路径（仍不伪造验证）。

复用既有模型，不造第二套。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.config import (
    load_external_staging_identity,
)
from agents.external_staging_qualification.deployment import (
    DeploymentTarget,
    ExternalStagingDeploymentProvider,
)
from agents.external_staging_qualification.denylist import ProductionReferenceDenylist
from agents.external_staging_qualification.evidence import (
    EvidenceChain,
    EvidenceType,
    make_evidence,
)
from agents.external_staging_qualification.gate import (
    ExternalStagingQualificationGate,
)
from agents.external_staging_qualification.isolation import (
    CrossEnvironmentIsolationProver,
)
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ExternalStagingResourceRegistry,
    ResourceType,
)
from agents.external_staging_qualification.package import build_qualification_package
from agents.external_staging_qualification.qualification import (
    ExternalStagingQualifier,
)
from agents.external_staging_qualification.runtime import RuntimeQualification


@dataclass
class QualificationPipelineResult:
    """管线结果聚合。"""

    environment_identity: ExternalStagingEnvironmentIdentity
    registry: ExternalStagingResourceRegistry
    isolation_summary: dict[str, Any]
    runtime_summary: dict[str, Any]
    evidence_chain: EvidenceChain
    gate_status: str
    gate_checks: tuple[dict[str, Any], ...]
    package: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_identity": self.environment_identity.to_dict(),
            "registry_summary": self.registry.summary(),
            "isolation_summary": self.isolation_summary,
            "runtime_summary": self.runtime_summary,
            "evidence_summary": self.evidence_chain.summary(),
            "gate_status": self.gate_status,
            "gate_checks": list(self.gate_checks),
            "package": self.package,
        }


class QualificationPipeline:
    """外部预生产资格验证管线（含 resource-less dry-run）。"""

    def __init__(
        self,
        *,
        source_commit: str,
        environment_identity: ExternalStagingEnvironmentIdentity | None = None,
        denylist: "ProductionReferenceDenylist | None" = None,
        baseline_commit: str | None = None,
        package_generated_from_commit: str | None = None,
    ) -> None:
        self._source_commit = source_commit
        self._baseline_commit = baseline_commit
        self._generated_from_commit = package_generated_from_commit
        self._env = environment_identity or load_external_staging_identity()
        self._denylist = denylist or ProductionReferenceDenylist()
        self._gate = ExternalStagingQualificationGate()

    def run(
        self,
        *,
        references: dict[ResourceType, str] | None = None,
        configured_flags: dict[ResourceType, bool] | None = None,
        production_references: dict[str, str] | None = None,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
    ) -> QualificationPipelineResult:
        references = references or {}
        configured_flags = configured_flags or {}

        # 1) Resource Registration
        registry = ExternalStagingResourceRegistry.build_default()

        # 2) Connectivity + Qualification
        qualifier = ExternalStagingQualifier(environment=self._env, denylist=self._denylist)
        registry, qual_results = qualifier.qualify_registry(
            registry, references=references, configured_flags=configured_flags
        )

        # 3) Isolation
        staging_refs = {r.resource_type.value: references.get(r.resource_type, "") for r in registry.resources}
        isolation = CrossEnvironmentIsolationProver().prove(
            staging_refs, production_references=production_references
        )

        # 4) Deploy（仅 plan，不执行）
        deployment_summary = {"target": "none", "deployed": False, "plan_only": True}

        # 5) Runtime Health
        runtime = RuntimeQualification().evaluate()

        # 6) Telemetry / Alert（基线 not_configured）
        telemetry_status = "not_configured"
        alerting_status = "not_configured"

        # 7) Evidence Chain
        chain = EvidenceChain()
        for qr in qual_results:
            chain = chain.append(
                make_evidence(
                    evidence_id=f"ev-{qr.resource.resource_id}",
                    resource_id=qr.resource.resource_id,
                    evidence_type=EvidenceType.CONNECTIVITY,
                    source="qualification_pipeline",
                    actor="AI_CHIEF_ARCHITECT",
                    verification_status=qr.qualification_status,
                    source_reference=qr.resource.source_reference,
                )
            )

        # 8) Gate
        gate_result = self._gate.evaluate(
            registry=registry,
            isolation=isolation,
            runtime=runtime,
            evidence_chain=chain,
            environment_identity=self._env.to_dict(),
            security_ok=security_ok,
            regression_ok=regression_ok,
            repo_clean=repo_clean,
            additional_pending_resources=tuple(
                r.resource_id for r in registry.resources if not r.configured
            ),
        )

        # 9) Package
        package = build_qualification_package(
            source_commit=self._source_commit,
            baseline_commit=self._baseline_commit,
            evidence_source_commit=self._source_commit,
            package_generated_from_commit=self._generated_from_commit,
            environment_identity=self._env,
            registry=registry,
            isolation=isolation,
            runtime=runtime,
            evidence_chain=chain,
            gate=gate_result,
            pending_resources=tuple(
                r.resource_id for r in registry.resources if not r.verified
            ),
            human_pending=("external_resource_provisioning", "four_role_signoff"),
            telemetry_status=telemetry_status,
            alerting_status=alerting_status,
            deployment_summary=deployment_summary,
        )

        return QualificationPipelineResult(
            environment_identity=self._env,
            registry=registry,
            isolation_summary=isolation.summary(),
            runtime_summary=runtime.summary(),
            evidence_chain=chain,
            gate_status=gate_result.status.value,
            gate_checks=tuple(c.to_dict() for c in gate_result.checks),
            package=package,
        )


__all__ = [
    "QualificationPipeline",
    "QualificationPipelineResult",
]

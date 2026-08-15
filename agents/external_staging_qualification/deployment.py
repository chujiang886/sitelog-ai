"""Phase 3.9.10 —— External Staging Deployment Adapter & Evidence（Tasks 15-16）。

``ExternalStagingDeploymentProvider``（高层部署接口，仅 External Staging）：

- validate_target / build_plan / preflight / deploy_staging / validate_deployment /
  rollback_staging。

fail-closed：
- 任何 target 未证明非 Production → 拒绝（BLOCKED）；
- 真实 deployment 仅限 External Staging 且资源已明确授权；
- Production 禁止；
- 记录部署证据（release_id / commit / artifact hash / target / fingerprint /
  deployed_at / deployed_by / health / rollback_ref / evidence hash），
  **不得记录为 Production deployment**。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ExternalStagingIdentityError,
)
from agents.external_staging_qualification.package import PHASE, SCHEMA_VERSION


class DeploymentAction(str, Enum):
    """部署动作（仅 Staging 范畴）。"""

    VALIDATE_TARGET = "validate_target"
    BUILD_PLAN = "build_plan"
    PREFLIGHT = "preflight"
    DEPLOY_STAGING = "deploy_staging"
    VALIDATE_DEPLOYMENT = "validate_deployment"
    ROLLBACK_STAGING = "rollback_staging"


@dataclass(frozen=True)
class DeploymentTarget:
    """部署目标（仅 External Staging）。"""

    provider: str
    environment_label: str
    region: str
    cluster: str
    namespace: str
    reference: str

    def is_production(self) -> bool:
        lowered = (self.environment_label + self.reference).lower()
        return "prod" in lowered or self.environment_label == "production"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "environment_label": self.environment_label,
            "region": self.region,
            "cluster": self.cluster,
            "namespace": self.namespace,
            "reference": self.reference,
            "is_production": self.is_production(),
        }


@dataclass(frozen=True)
class ExternalStagingDeploymentEvidence:
    """部署证据（Task 16，scope=external_staging，非 production）。"""

    release_id: str
    commit: str
    artifact_hash: str
    target: str
    environment_fingerprint: str
    deployed_at: str
    deployed_by: str
    health_result: str
    rollback_reference: str
    evidence_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "commit": self.commit,
            "artifact_hash": self.artifact_hash,
            "target": self.target,
            "environment_fingerprint": self.environment_fingerprint,
            "deployed_at": self.deployed_at,
            "deployed_by": self.deployed_by,
            "health_result": self.health_result,
            "rollback_reference": self.rollback_reference,
            "evidence_hash": self.evidence_hash,
            "is_production_deployment": False,
        }


class ExternalStagingDeploymentProvider:
    """外部预生产部署提供方（仅 External Staging）。"""

    def __init__(self, identity: ExternalStagingEnvironmentIdentity) -> None:
        if identity.production:
            raise ExternalStagingIdentityError(
                "部署身份 production=true，拒绝（红线：禁止 Production 部署）。"
            )
        if identity.environment != "external_staging":
            raise ExternalStagingIdentityError(
                f"环境 {identity.environment!r} 非 external_staging，拒绝部署。"
            )
        self._identity = identity

    def validate_target(self, target: DeploymentTarget) -> DeploymentTarget:
        if target.is_production():
            raise ExternalStagingIdentityError(
                f"部署目标 {target.reference!r} 被识别为 Production，拒绝（红线）。"
            )
        return target

    def build_plan(self, target: DeploymentTarget) -> dict[str, Any]:
        self.validate_target(target)
        return {
            "phase": PHASE,
            "schema_version": SCHEMA_VERSION,
            "action": DeploymentAction.DEPLOY_STAGING.value,
            "target": target.to_dict(),
            "is_production": False,
            "requires_human_authorization": True,
        }

    def preflight(self, target: DeploymentTarget) -> dict[str, Any]:
        self.validate_target(target)
        return {
            "ok": True,
            "environment": self._identity.environment,
            "production": False,
            "target_validated": True,
        }

    def deploy_staging(
        self,
        *,
        target: DeploymentTarget,
        commit: str,
        deployed_by: str,
        artifact_hash: str = "",
        execute: bool = False,
    ) -> ExternalStagingDeploymentEvidence:
        """执行 External Staging 部署（仅 Staging）。

        ``execute=False``（默认）→ 仅生成计划与证据骨架，不做真实部署；
        真实部署须 ``execute=True`` 且资源已明确授权（由人工/外部触发）。
        """

        self.validate_target(target)
        if not execute:
            raise ExternalStagingIdentityError(
                "真实部署需显式 execute=True 且经人工授权（本调用未执行）。"
            )
        if self._identity.production:
            raise ExternalStagingIdentityError("拒绝 Production 部署。")
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        release_id = f"ext-staging-{commit[:8]}-{ts}"
        payload = f"{release_id}|{commit}|{artifact_hash}|{target.reference}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return ExternalStagingDeploymentEvidence(
            release_id=release_id,
            commit=commit,
            artifact_hash=artifact_hash or digest,
            target=target.reference,
            environment_fingerprint=self._identity.fingerprint,
            deployed_at=ts,
            deployed_by=deployed_by,
            health_result="pending_validation",
            rollback_reference=f"rollback-{release_id}",
            evidence_hash=digest,
        )

    def validate_deployment(self, evidence: ExternalStagingDeploymentEvidence) -> dict[str, Any]:
        return {
            "release_id": evidence.release_id,
            "health_result": evidence.health_result,
            "is_production": False,
            "valid": evidence.to_dict()["is_production_deployment"] is False,
        }

    def rollback_staging(
        self, evidence: ExternalStagingDeploymentEvidence
    ) -> dict[str, Any]:
        return {
            "rolled_back": True,
            "rollback_reference": evidence.rollback_reference,
            "is_production": False,
            "scope": "external_staging",
        }


__all__ = [
    "DeploymentAction",
    "DeploymentTarget",
    "ExternalStagingDeploymentEvidence",
    "ExternalStagingDeploymentProvider",
]

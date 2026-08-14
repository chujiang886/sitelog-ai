"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Manifest（Task 7）。

``StagingRuntimeManifest`` 汇总本地预生产运行时证据（环境身份指纹、Local Staging
形态、Secret 配置存在性），产出**机器可读**且**不含真实密钥**的 manifest。

fail-closed：manifest 永远 ``is_production=False`` 且 ``non_production_bound=True``；
任何试图把它标记为 production 的操作都会抛错。manifest 只描述形态与证据，不执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from agents.staging_runtime.config import load_staging_identity, staging_resource_readiness
from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.local_profile import LocalStagingProfile
from agents.staging_runtime.secret_provider import StagingSecretProvider, StagingSecretResolution

PHASE = "3.9.9"


@dataclass(frozen=True)
class StagingRuntimeManifest:
    """本地预生产运行时 manifest（机器可读、不含真实密钥）。"""

    environment: str
    is_production: bool
    non_production_bound: bool
    identity_fingerprint: str
    purpose: str
    profile: Mapping[str, Any] = field(default_factory=dict)
    secret_presence: Mapping[str, bool] = field(default_factory=dict)
    resource_readiness: str = "pending_external_staging_resource"
    phase: str = PHASE
    evidence_note: str = (
        "本 manifest 仅描述本地预生产（非生产）运行时接入与验证形态与证据，"
        "不执行真实部署、不写真实 Secret、不修改生产配置。"
    )

    def require_non_production(self) -> None:
        """断言非生产（fail-closed）。"""

        if self.is_production or not self.non_production_bound:
            raise StagingManifestProductionError(
                "StagingRuntimeManifest 不得被标记为 production（它永远是本地预生产）。"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "environment": self.environment,
            "is_production": self.is_production,
            "non_production_bound": self.non_production_bound,
            "identity_fingerprint": self.identity_fingerprint,
            "purpose": self.purpose,
            "resource_readiness": self.resource_readiness,
            "profile": dict(self.profile),
            "secret_presence": dict(self.secret_presence),
            "evidence_note": self.evidence_note,
        }


class StagingManifestProductionError(ValueError):
    """Manifest 被要求承载 production 语义（fail-closed 拒绝）。"""


def build_staging_runtime_manifest(
    identity: EnvironmentIdentity | None = None,
    profile: LocalStagingProfile | None = None,
    secret_names: Iterable[str] = (),
    *,
    strict: bool = False,
) -> StagingRuntimeManifest:
    """汇总本地预生产证据，产出 manifest（不执行任何动作）。"""

    ident = identity or load_staging_identity(strict=strict)
    prof = profile or LocalStagingProfile()
    provider = StagingSecretProvider(ident)
    snap: Sequence[StagingSecretResolution] = provider.snapshot(list(secret_names))
    secret_presence = {r.name: r.resolved for r in snap}

    return StagingRuntimeManifest(
        environment=ident.kind.value,
        is_production=ident.kind.is_production,
        non_production_bound=ident.kind is RuntimeEnvironment.LOCAL_STAGING
        or ident.kind is RuntimeEnvironment.EXTERNAL_STAGING,
        identity_fingerprint=(ident.fingerprint.value if ident.fingerprint else ""),
        purpose=ident.purpose,
        profile=prof.build_manifest(),
        secret_presence=secret_presence,
        resource_readiness=staging_resource_readiness(ident).value,
    )


__all__ = [
    "PHASE",
    "StagingRuntimeManifest",
    "StagingManifestProductionError",
    "build_staging_runtime_manifest",
]

"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Local Staging Profile（Task 6）。

``LocalStagingProfile`` 描述一个**本机预生产**（非生产）的 Docker Compose 形态，
用于真实预生产运行时接入与验证：它永远是 ``RuntimeEnvironment.LOCAL_STAGING``，
结构上拒绝被标记为 production（fail-closed）。

注意边界：
- 本类只**描述**本地预生产形态并产出 manifest 证据，**不**执行真实部署、
  **不**启动容器、**不**修改生产配置；真实部署由人工在授权后执行（红线）。
- 配套资产 ``docker-compose.staging.yml`` / ``.env.staging.example`` 仅含占位与
  ``${STAGING_*}`` 环境变量引用，无任何真实密钥/生产资源。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment

# 仓库内本地预生产配套资产（相对 BOIP 仓库根）。
_LOCAL_PROFILE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LocalStagingService:
    """本地预生产中的一个服务描述（非生产）。"""

    name: str
    image: str
    ports: tuple[str, ...] = ()
    non_production: bool = True  # 永远 True：本地预生产服务不构成生产。

    def to_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "image": self.image,
            "ports": list(self.ports),
            "non_production": self.non_production,
        }


class LocalStagingProfileError(ValueError):
    """Local Staging Profile 非法（如被要求标记为 production）。"""


@dataclass(frozen=True)
class LocalStagingProfile:
    """本地预生产（非生产）Docker Compose 形态描述。

    永远 ``RuntimeEnvironment.LOCAL_STAGING``；构造即固化该事实，任何试图把它
    当作 production 的操作都会抛 ``LocalStagingProfileError``。
    """

    name: str = "phase3.9.9-local-staging"
    purpose: str = "Real non-production pre-prod runtime integration & validation (Phase 3.9.9)"
    compose_file: str = "docker-compose.staging.yml"
    env_example: str = ".env.staging.example"
    services: tuple[LocalStagingService, ...] = field(
        default_factory=lambda: (
            LocalStagingService(
                name="boip-staging-api",
                image="boip/staging-api:local",
                ports=("8081:8080",),
            ),
            LocalStagingService(
                name="boip-staging-postgres",
                image="postgres:16-alpine",
                ports=("5433:5432",),
            ),
            LocalStagingService(
                name="boip-staging-redis",
                image="redis:7-alpine",
                ports=("6380:6379",),
            ),
        )
    )

    @property
    def kind(self) -> RuntimeEnvironment:
        """本地预生产环境分类（恒定 LOCAL_STAGING）。"""

        return RuntimeEnvironment.LOCAL_STAGING

    def assert_local_only(self) -> None:
        """断言本形态为非生产；任何 production 诉求都抛错（fail-closed）。"""

        if self.kind.is_production:
            raise LocalStagingProfileError(
                "LocalStagingProfile 不得是 PRODUCTION（它永远是 LOCAL_STAGING）。"
            )

    def to_identity(self) -> EnvironmentIdentity:
        """导出为环境身份（kind 恒为 LOCAL_STAGING），供隔离护栏统一校验。"""

        self.assert_local_only()
        from agents.staging_runtime.environment import EnvironmentResources

        return EnvironmentIdentity(
            kind=self.kind,
            name=self.name,
            purpose=self.purpose,
            resources=EnvironmentResources(),
        ).with_fingerprint()

    def build_manifest(self) -> dict[str, Any]:
        """产出本地预生产 manifest（用于证据/SSOT，不含真实密钥）。"""

        self.assert_local_only()
        return {
            "profile": self.name,
            "environment": self.kind.value,
            "purpose": self.purpose,
            "compose_file": self.compose_file,
            "env_example": self.env_example,
            "is_production": False,
            "non_production_bound": True,  # 结构上绑定非生产，拒绝被当 production
            "services": [s.to_manifest() for s in self.services],
            "note": (
                "本 manifest 仅描述本地预生产形态，不执行真实部署、不启动容器、"
                "不修改生产配置；真实部署由人工在授权后执行。"
            ),
        }

    def compose_path(self) -> Path:
        return _LOCAL_PROFILE_DIR / self.compose_file

    def env_example_path(self) -> Path:
        return _LOCAL_PROFILE_DIR / self.env_example


__all__ = [
    "LocalStagingService",
    "LocalStagingProfile",
    "LocalStagingProfileError",
]

"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Deployment Provider（Task 8）。

``StagingDeploymentProvider`` **只描述**本地预生产部署计划（供人工在授权后执行），
**绝不**执行真实部署、启动容器或连接生产。

fail-closed：``apply()`` 永远抛 ``StagingDeploymentForbiddenError``（红线：不真实部署）；
``plan()`` 返回的是「人类在授权后应执行的步骤」清单，不是系统自动动作。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard
from agents.staging_runtime.local_profile import LocalStagingProfile


class StagingDeploymentForbiddenError(Exception):
    """禁止系统自动执行真实部署（红线：不真实部署 / 不激活生产）。"""


@dataclass(frozen=True)
class StagingDeploymentPlan:
    """本地预生产部署计划（供人工在授权后执行，非系统自动动作）。"""

    target_environment: str
    is_production: bool
    compose_file: str
    env_example: str
    steps: tuple[str, ...]
    requires_human_authorization: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_environment": self.target_environment,
            "is_production": self.is_production,
            "compose_file": self.compose_file,
            "env_example": self.env_example,
            "steps": list(self.steps),
            "requires_human_authorization": self.requires_human_authorization,
        }


class StagingDeploymentProvider:
    """本地预生产部署提供方（只描述计划，绝不自动执行）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        profile: LocalStagingProfile | None = None,
    ) -> None:
        # 红线前置：staging 身份必须经护栏校验。
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._profile = profile or LocalStagingProfile()

    def plan(self) -> StagingDeploymentPlan:
        """返回人类在授权后应执行的本地预生产部署步骤（非系统自动动作）。"""

        return StagingDeploymentPlan(
            target_environment=self._identity.kind.value,
            is_production=self._identity.kind.is_production,
            compose_file=self._profile.compose_file,
            env_example=self._profile.env_example,
            steps=(
                "cp .env.staging.example .env.staging",
                "在 .env.staging 填入本地预生产非生产资源（禁止等于生产）",
                "docker compose -f docker-compose.staging.yml --env-file .env.staging up",
                "运行本地预生产健康检查与隔离校验",
                "（生产部署须由四角色线下授权后单独执行，不在本计划内）",
            ),
        )

    def apply(self) -> StagingDeploymentPlan:
        """**永不**执行真实部署；调用即抛 ``StagingDeploymentForbiddenError``。

        真实部署由人工在授权后执行（红线：不真实部署 / 不激活生产）。
        """

        raise StagingDeploymentForbiddenError(
            "StagingDeploymentProvider.apply() 被调用：系统禁止自动执行真实部署。"
            "本地/生产部署须由人工在授权后执行。"
        )


__all__ = [
    "StagingDeploymentForbiddenError",
    "StagingDeploymentPlan",
    "StagingDeploymentProvider",
]

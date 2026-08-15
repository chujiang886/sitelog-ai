"""Phase 3.9.10 External Staging Qualification & Evidence Integration Layer —— 核心模型（Tasks 2-5）。

定义外部预生产环境资格验证的核心数据模型：

- ``ResourceType``：8 类外部预生产资源（DB / Secret / IdP / Storage / Telemetry /
  Alert / Domain-TLS / Deployment Target）。
- ``ResourceQualificationStatus``：统一资格状态枚举（**禁止** ``PRODUCTION_READY`` /
  ``APPROVED`` / ``GO``）。
- ``ExternalStagingResource``：单资源登记项（**禁止**存 Secret 明文值）。
- ``ExternalStagingResourceRegistry``：8 资源登记簿（v2）。
- ``CredentialReference``：凭据引用（仅 reference/provider/id/rotation 元数据）。
- ``ExternalStagingEnvironmentIdentity``：外部预生产环境身份（production=false）。

fail-closed 红线：
- 本模块**不**打开 ``engineering_enabled``、**不**输出 ``engineering_approved``；
- 任何资源缺真实凭据/连接时，状态回落到 ``NOT_CONFIGURED`` / ``PENDING_*``，
  **绝不**伪造 ``CONNECTIVITY_VERIFIED`` / ``QUALIFIED_EXTERNAL_STAGING``；
- 凭据引用**绝不**持有明文 Secret / Token / 私钥 / 含密码的 DSN。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from agents.staging_runtime.environment import (
    EnvironmentIdentity,
    EnvironmentResources,
    RuntimeEnvironment,
)

# 本阶段语义态常量（仅在 External Staging 范畴内，禁止 Production 语义）。
EXTERNAL_STAGING_ENVIRONMENT = RuntimeEnvironment.EXTERNAL_STAGING
EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE = (
    "EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO"
)


class ResourceType(str, Enum):
    """外部预生产资源种类（8 类，对应 Task 2 建模）。"""

    DATABASE = "database"
    SECRET_PROVIDER = "secret_provider"
    IDENTITY_PROVIDER = "identity_provider"
    OBJECT_STORAGE = "object_storage"
    TELEMETRY = "telemetry"
    ALERT_SANDBOX = "alert_sandbox"
    DOMAIN_TLS = "domain_tls"
    DEPLOYMENT_TARGET = "deployment_target"


# 8 资源顺序（用于登记簿稳定遍历 / 契约机器生成）。
RESOURCE_TYPE_ORDER: tuple[ResourceType, ...] = (
    ResourceType.DATABASE,
    ResourceType.SECRET_PROVIDER,
    ResourceType.IDENTITY_PROVIDER,
    ResourceType.OBJECT_STORAGE,
    ResourceType.TELEMETRY,
    ResourceType.ALERT_SANDBOX,
    ResourceType.DOMAIN_TLS,
    ResourceType.DEPLOYMENT_TARGET,
)


class ResourceQualificationStatus(str, Enum):
    """统一资源资格状态（Task 3）。

    fail-closed 状态机：从 ``NOT_CONFIGURED`` 逐级推进；任何真实证据缺失必须
    停在未验证态，**禁止**跃迁到 ``QUALIFIED_EXTERNAL_STAGING``。
    """

    NOT_CONFIGURED = "not_configured"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    CONNECTIVITY_PENDING = "connectivity_pending"
    CONNECTIVITY_VERIFIED = "connectivity_verified"
    ISOLATION_PENDING = "isolation_pending"
    ISOLATION_VERIFIED = "isolation_verified"
    QUALIFICATION_PENDING = "qualification_pending"
    QUALIFIED_EXTERNAL_STAGING = "qualified_external_staging"
    FAILED = "failed"
    BLOCKED = "blocked"
    PENDING_EXTERNAL_STAGING_RESOURCE = "pending_external_staging_resource"

    @property
    def is_verified(self) -> bool:
        """是否已通过某项真实验证（connectivity / isolation / qualification）。"""

        return self in (
            ResourceQualificationStatus.CONNECTIVITY_VERIFIED,
            ResourceQualificationStatus.ISOLATION_VERIFIED,
            ResourceQualificationStatus.QUALIFIED_EXTERNAL_STAGING,
        )

    @property
    def is_pending(self) -> bool:
        """是否处在等待真实资源/人工的状态。"""

        return self in (
            ResourceQualificationStatus.CONNECTIVITY_PENDING,
            ResourceQualificationStatus.ISOLATION_PENDING,
            ResourceQualificationStatus.QUALIFICATION_PENDING,
            ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
        )


# 被明确禁止的状态（任何资源/环境均不得落入）。
_FORBIDDEN_STATES = frozenset(
    {
        "production_ready",
        "production_verified",
        "approved",
        "go",
        "PRODUCTION_READY",
        "PRODUCTION_VERIFIED",
        "APPROVED",
        "GO",
    }
)


class GateStatus(str, Enum):
    """资格闸门状态（Task 21，仅 4 态，禁止 APPROVED/PRODUCTION_READY/GO）。"""

    BLOCKED = "blocked"
    PENDING_EXTERNAL_STAGING_RESOURCE = "pending_external_staging_resource"
    PENDING_HUMAN_VERIFICATION = "pending_human_verification"
    READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW = "ready_for_external_staging_human_review"


class RuntimeHealthStatus(str, Enum):
    """运行时健康状态（Task 17）。``UNKNOWN`` 不得等同 ``HEALTHY``。"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"

    @property
    def is_healthy(self) -> bool:
        """是否健康（严格：仅 ``HEALTHY`` 为真）。"""

        return self is RuntimeHealthStatus.HEALTHY


@dataclass(frozen=True)
class CredentialReference:
    """凭据引用（Task 5，Credential Reference Safety）。

    仅保存引用/提供方/凭据 id/轮换元数据/验证元数据。**绝不**保存明文
    Secret / Password / Token / 私钥 / 含密码的 DSN。
    """

    resource_id: str
    credential_id: str
    provider_reference: str
    secret_reference: str = ""
    rotation_metadata: Mapping[str, Any] = field(default_factory=dict)
    verification_metadata: Mapping[str, Any] = field(default_factory=dict)

    def contains_raw_secret(self) -> bool:
        """本引用是否意外携带明文凭据（扫描用，恒应返回 False）。"""

        for value in (
            self.secret_reference,
            self.credential_id,
            self.provider_reference,
        ):
            if value and _looks_like_raw_secret(str(value)):
                return True
        return False


@dataclass
class ExternalStagingResource:
    """单资源登记项（Task 2，ExternalStagingResourceRegistry v2 条目）。

    **禁止**在任意字段存 Secret 明文值。
    """

    resource_id: str
    resource_type: ResourceType
    environment: str = EXTERNAL_STAGING_ENVIRONMENT.value
    required: bool = True
    configured: bool = False
    verified: bool = False
    owner_role: str = ""
    source_reference: str = ""
    credential_reference: str = ""  # 仅存引用字符串，不存值
    isolation_status: str = ResourceQualificationStatus.NOT_CONFIGURED.value
    connectivity_status: str = ResourceQualificationStatus.NOT_CONFIGURED.value
    qualification_status: str = ResourceQualificationStatus.NOT_CONFIGURED.value
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    last_checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "environment": self.environment,
            "required": self.required,
            "configured": self.configured,
            "verified": self.verified,
            "owner_role": self.owner_role,
            "source_reference": self.source_reference,
            "credential_reference": self.credential_reference,
            "isolation_status": self.isolation_status,
            "connectivity_status": self.connectivity_status,
            "qualification_status": self.qualification_status,
            "evidence_refs": list(self.evidence_refs),
            "last_checked_at": self.last_checked_at,
            "contains_real_secret": False,
        }


@dataclass
class ExternalStagingResourceRegistry:
    """8 资源登记簿（Task 2，v2）。

    构造即填 8 项资源骨架；真实配置/验证由 qualification 层回填。
    """

    resources: tuple[ExternalStagingResource, ...] = field(default_factory=tuple)

    @classmethod
    def build_default(cls) -> "ExternalStagingResourceRegistry":
        """建立默认 8 资源骨架（全 NOT_CONFIGURED / PENDING）。"""

        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        defaults: list[ExternalStagingResource] = []
        for idx, rtype in enumerate(RESOURCE_TYPE_ORDER, start=1):
            defaults.append(
                ExternalStagingResource(
                    resource_id=f"ext-staging-{rtype.value}",
                    resource_type=rtype,
                    configured=False,
                    verified=False,
                    owner_role=_default_owner_role(rtype),
                    isolation_status=ResourceQualificationStatus.NOT_CONFIGURED.value,
                    connectivity_status=ResourceQualificationStatus.NOT_CONFIGURED.value,
                    qualification_status=ResourceQualificationStatus.NOT_CONFIGURED.value,
                    last_checked_at=now,
                )
            )
        return cls(resources=tuple(defaults))

    def by_type(self, rtype: ResourceType) -> ExternalStagingResource | None:
        for r in self.resources:
            if r.resource_type is rtype:
                return r
        return None

    def by_id(self, resource_id: str) -> ExternalStagingResource | None:
        for r in self.resources:
            if r.resource_id == resource_id:
                return r
        return None

    def summary(self) -> dict[str, Any]:
        configured = sum(1 for r in self.resources if r.configured)
        verified = sum(1 for r in self.resources if r.verified)
        return {
            "total": len(self.resources),
            "configured": configured,
            "verified": verified,
            "pending": len(self.resources) - verified,
            "resource_ids": [r.resource_id for r in self.resources],
        }


@dataclass(frozen=True)
class ExternalStagingEnvironmentIdentity:
    """外部预生产环境身份（Task 4）。

    - ``environment`` 固定 ``EXTERNAL_STAGING``；
    - ``production`` 恒为 ``False``；
    - 与 Production fingerprint 相同 → 拒绝（BLOCKED）。
    """

    environment: str = EXTERNAL_STAGING_ENVIRONMENT.value
    production: bool = False
    organization_id: str = ""
    domain_reference: str = ""
    deployment_target_reference: str = ""
    database_reference: str = ""
    idp_reference: str = ""
    storage_reference: str = ""
    telemetry_reference: str = ""
    alert_reference: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "production": self.production,
            "organization_id": self.organization_id,
            "domain_reference": self.domain_reference,
            "deployment_target_reference": self.deployment_target_reference,
            "database_reference": self.database_reference,
            "idp_reference": self.idp_reference,
            "storage_reference": self.storage_reference,
            "telemetry_reference": self.telemetry_reference,
            "alert_reference": self.alert_reference,
            "fingerprint": self.fingerprint,
        }

    def as_runtime_environment(self) -> RuntimeEnvironment:
        """映射为 staging_runtime 的 ``RuntimeEnvironment``（恒 EXTERNAL_STAGING）。"""

        if self.production:
            raise ExternalStagingIdentityError(
                "External Staging 环境身份 production=true，拒绝（红线）。"
            )
        return EXTERNAL_STAGING_ENVIRONMENT


class ExternalStagingIdentityError(ValueError):
    """外部预生产环境身份违例。"""


def _default_owner_role(rtype: ResourceType) -> str:
    mapping = {
        ResourceType.DATABASE: "production-owner",
        ResourceType.SECRET_PROVIDER: "security-owner",
        ResourceType.IDENTITY_PROVIDER: "security-owner",
        ResourceType.OBJECT_STORAGE: "production-owner",
        ResourceType.TELEMETRY: "release-manager",
        ResourceType.ALERT_SANDBOX: "release-manager",
        ResourceType.DOMAIN_TLS: "production-owner",
        ResourceType.DEPLOYMENT_TARGET: "production-owner",
    }
    return mapping.get(rtype, "production-owner")


def _looks_like_raw_secret(value: str) -> bool:
    """启发式：字符串是否疑似明文凭据（用于凭据引用安全检查）。

    fail-closed：仅对明显模式报警，不误伤正常引用字符串。
    """

    lowered = value.lower()
    patterns = (
        "password=",
        "pwd=",
        "secret=",
        "token=",
        "apikey=",
        "api_key=",
        "private_key",
        "-----begin",
        "sk-",
        "ak-",
    )
    if any(p in lowered for p in patterns):
        return True
    # 长随机串（>32 无空格）疑似密文
    if len(value) >= 32 and " " not in value and value.isalnum():
        return True
    return False


def assert_not_forbidden_state(state: str) -> None:
    """断言状态不落入禁止态（fail-closed）。"""

    if state in _FORBIDDEN_STATES:
        raise ExternalStagingIdentityError(
            f"资源/环境状态 {state!r} 落入禁止态（PRODUCTION_READY/APPROVED/GO 等），拒绝。"
        )


__all__ = [
    "EXTERNAL_STAGING_ENVIRONMENT",
    "EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE",
    "ResourceType",
    "RESOURCE_TYPE_ORDER",
    "ResourceQualificationStatus",
    "GateStatus",
    "RuntimeHealthStatus",
    "CredentialReference",
    "ExternalStagingResource",
    "ExternalStagingResourceRegistry",
    "ExternalStagingEnvironmentIdentity",
    "ExternalStagingIdentityError",
    "assert_not_forbidden_state",
]

"""Phase 3.9.13 —— 逐资源状态机（13 正常态 + 4 失败态，T5-T12, T21-T29）。

每个真实外部资源有独立状态机。AI 不得跳状态（fail-closed：非法跃迁拒绝）。
真实资源未提供时，8 资源全部停在 ``PENDING_EXTERNAL_STAGING_RESOURCE``。

本模块**自包含**：内置 8 资源类型与 BOM 定义，不依赖 qualification/execution/
staging_runtime 等跨阶段模块（避免沙箱未跟踪文件被清导致的导入断裂）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResourceType(str, Enum):
    """外部预生产资源类型（与 3.9.12 BOM 同源）。"""

    DATABASE = "database"
    SECRET_PROVIDER = "secret_provider"
    IDENTITY_PROVIDER = "identity_provider"
    OBJECT_STORAGE = "object_storage"
    TELEMETRY = "telemetry"
    ALERT_SANDBOX = "alert_sandbox"
    DOMAIN_TLS = "domain_tls"
    DEPLOYMENT_TARGET = "deployment_target"


# 8 资源固定顺序（与 3.9.12 BOM 一致）。
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

PENDING_STATUS = "pending_external_staging_resource"

_OWNER_ROLE = {
    ResourceType.DATABASE: "production-owner",
    ResourceType.SECRET_PROVIDER: "security-owner",
    ResourceType.IDENTITY_PROVIDER: "security-owner",
    ResourceType.OBJECT_STORAGE: "production-owner",
    ResourceType.TELEMETRY: "release-manager",
    ResourceType.ALERT_SANDBOX: "release-manager",
    ResourceType.DOMAIN_TLS: "production-owner",
    ResourceType.DEPLOYMENT_TARGET: "production-owner",
}
_PROVIDER_SERVICE = {
    ResourceType.DATABASE: "Tencent Cloud CDB for PostgreSQL",
    ResourceType.SECRET_PROVIDER: "Tencent Cloud Secrets Manager (SSM)",
    ResourceType.IDENTITY_PROVIDER: "OIDC / SSO IdP tenant",
    ResourceType.OBJECT_STORAGE: "Tencent Cloud COS",
    ResourceType.TELEMETRY: "Tencent Cloud CLS / Prometheus",
    ResourceType.ALERT_SANDBOX: "Tencent Cloud Monitor / Alert",
    ResourceType.DOMAIN_TLS: "Tencent Cloud DNSPod + SSL",
    ResourceType.DEPLOYMENT_TARGET: "Tencent Cloud TKE + TCR",
}
_IAC_MODULE = {
    ResourceType.DATABASE: "infrastructure/staging/database.tf",
    ResourceType.SECRET_PROVIDER: "infrastructure/staging/secret_provider.tf",
    ResourceType.IDENTITY_PROVIDER: "infrastructure/staging/identity_provider.tf",
    ResourceType.OBJECT_STORAGE: "infrastructure/staging/object_storage.tf",
    ResourceType.TELEMETRY: "infrastructure/staging/telemetry.tf",
    ResourceType.ALERT_SANDBOX: "infrastructure/staging/alert_sandbox.tf",
    ResourceType.DOMAIN_TLS: "infrastructure/staging/domain_tls.tf",
    ResourceType.DEPLOYMENT_TARGET: "infrastructure/staging/deployment_target.tf",
}
_RESOURCE_ID = {
    ResourceType.DATABASE: "ext-staging-database",
    ResourceType.SECRET_PROVIDER: "ext-staging-secret_provider",
    ResourceType.IDENTITY_PROVIDER: "ext-staging-identity_provider",
    ResourceType.OBJECT_STORAGE: "ext-staging-object_storage",
    ResourceType.TELEMETRY: "ext-staging-telemetry",
    ResourceType.ALERT_SANDBOX: "ext-staging-alert_sandbox",
    ResourceType.DOMAIN_TLS: "ext-staging-domain_tls",
    ResourceType.DEPLOYMENT_TARGET: "ext-staging-deployment_target",
}


@dataclass(frozen=True)
class ExternalStagingResourceEntry:
    """单资源 BOM 条目（3.9.13 自包含版）。"""

    resource_id: str
    resource_type: ResourceType
    required: bool
    owner_role: str
    default_provider_service: str
    iac_module: str
    status: str = PENDING_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "required": self.required,
            "owner_role": self.owner_role,
            "default_provider_service": self.default_provider_service,
            "iac_module": self.iac_module,
            "status": self.status,
        }


def build_default_bom() -> tuple[ExternalStagingResourceEntry, ...]:
    """构建默认 8 资源 BOM（全 PENDING）。"""

    return tuple(
        ExternalStagingResourceEntry(
            resource_id=_RESOURCE_ID[rt],
            resource_type=rt,
            required=True,
            owner_role=_OWNER_ROLE[rt],
            default_provider_service=_PROVIDER_SERVICE[rt],
            iac_module=_IAC_MODULE[rt],
        )
        for rt in RESOURCE_TYPE_ORDER
    )


class ResourceProvisioningState(str, Enum):
    """逐资源供给态（13 正常 + 4 失败）。"""

    PENDING_EXTERNAL_STAGING_RESOURCE = "pending_external_staging_resource"
    INPUT_RECEIVED = "input_received"
    REFERENCE_VALIDATED = "reference_validated"
    PLAN_READY = "plan_ready"
    PLAN_VALIDATED = "plan_validated"
    HUMAN_AUTHORIZATION_PENDING = "human_authorization_pending"
    AUTHORIZED_FOR_STAGING_APPLY = "authorized_for_staging_apply"
    PROVISIONING = "provisioning"
    PROVISIONED = "provisioned"
    REGISTERED = "registered"
    CONNECTIVITY_VERIFIED = "connectivity_verified"
    ISOLATION_VERIFIED = "isolation_verified"
    QUALIFIED_EXTERNAL_STAGING = "qualified_external_staging"

    FAILED_REFERENCE_VALIDATION = "failed_reference_validation"
    FAILED_PROVISIONING = "failed_provisioning"
    FAILED_CONNECTIVITY = "failed_connectivity"
    FAILED_ISOLATION = "failed_isolation"

    @property
    def is_failure(self) -> bool:
        return self.name.startswith("FAILED_")

    @property
    def is_real_provisioned(self) -> bool:
        return False


RESOURCE_STATE_TRANSITIONS: dict[
    ResourceProvisioningState, frozenset[ResourceProvisioningState]
] = {
    ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE: frozenset({
        ResourceProvisioningState.INPUT_RECEIVED,
        ResourceProvisioningState.FAILED_REFERENCE_VALIDATION,
    }),
    ResourceProvisioningState.INPUT_RECEIVED: frozenset({
        ResourceProvisioningState.REFERENCE_VALIDATED,
        ResourceProvisioningState.FAILED_REFERENCE_VALIDATION,
    }),
    ResourceProvisioningState.REFERENCE_VALIDATED: frozenset({
        ResourceProvisioningState.PLAN_READY,
        ResourceProvisioningState.FAILED_REFERENCE_VALIDATION,
    }),
    ResourceProvisioningState.PLAN_READY: frozenset({
        ResourceProvisioningState.PLAN_VALIDATED,
    }),
    ResourceProvisioningState.PLAN_VALIDATED: frozenset({
        ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING,
    }),
    ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING: frozenset({
        ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY,
    }),
    ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY: frozenset({
        ResourceProvisioningState.PROVISIONING,
        ResourceProvisioningState.FAILED_PROVISIONING,
    }),
    ResourceProvisioningState.PROVISIONING: frozenset({
        ResourceProvisioningState.PROVISIONED,
        ResourceProvisioningState.FAILED_PROVISIONING,
    }),
    ResourceProvisioningState.PROVISIONED: frozenset({
        ResourceProvisioningState.REGISTERED,
        ResourceProvisioningState.FAILED_PROVISIONING,
    }),
    ResourceProvisioningState.REGISTERED: frozenset({
        ResourceProvisioningState.CONNECTIVITY_VERIFIED,
        ResourceProvisioningState.FAILED_CONNECTIVITY,
    }),
    ResourceProvisioningState.CONNECTIVITY_VERIFIED: frozenset({
        ResourceProvisioningState.ISOLATION_VERIFIED,
        ResourceProvisioningState.FAILED_ISOLATION,
    }),
    ResourceProvisioningState.ISOLATION_VERIFIED: frozenset({
        ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
    }),
}

FAILURE_STATES = frozenset({
    ResourceProvisioningState.FAILED_REFERENCE_VALIDATION,
    ResourceProvisioningState.FAILED_PROVISIONING,
    ResourceProvisioningState.FAILED_CONNECTIVITY,
    ResourceProvisioningState.FAILED_ISOLATION,
})


class ResourceStateMachineError(ValueError):
    """状态机非法跃迁/越级拒绝。"""


@dataclass
class ResourceStateMachine:
    """单资源状态机。"""

    resource_id: str
    resource_type: ResourceType
    state: ResourceProvisioningState = (
        ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE
    )
    last_event: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def can_transition_to(self, target: ResourceProvisioningState) -> bool:
        if target is self.state:
            return True
        allowed = RESOURCE_STATE_TRANSITIONS.get(self.state, frozenset())
        return target in allowed

    def transition_to(
        self, target: ResourceProvisioningState, *, event: str = "", note: str = ""
    ) -> None:
        if target is self.state:
            return
        if not self.can_transition_to(target):
            raise ResourceStateMachineError(
                f"资源 {self.resource_id} 从 {self.state.value} 跃迁到 "
                f"{target.value} 非法（跳状态/越级），拒绝。"
            )
        self.state = target
        self.last_event = event
        if note:
            self.notes = self.notes + (note,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "state": self.state.value,
            "is_failure": self.state.is_failure,
            "last_event": self.last_event,
            "notes": list(self.notes),
        }


class ProvisioningStateRegistry:
    """8 资源状态机登记簿（默认全 PENDING）。"""

    def __init__(self, bom: tuple[ExternalStagingResourceEntry, ...] | None = None) -> None:
        self.bom = bom or build_default_bom()
        self._machines: dict[str, ResourceStateMachine] = {}
        for entry in self.bom:
            self._machines[entry.resource_id] = ResourceStateMachine(
                resource_id=entry.resource_id, resource_type=entry.resource_type
            )

    def get(self, resource_id: str) -> ResourceStateMachine:
        if resource_id not in self._machines:
            raise ResourceStateMachineError(f"未知资源 {resource_id}")
        return self._machines[resource_id]

    def all_pending(self) -> bool:
        return all(
            m.state is ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE
            for m in self._machines.values()
        )

    def summary(self) -> dict[str, Any]:
        states = [m.state.value for m in self._machines.values()]
        by_state = dict(Counter(states))
        return {
            "total": len(self._machines),
            "by_state": by_state,
            "all_pending": self.all_pending(),
            "any_failure": any(m.state.is_failure for m in self._machines.values()),
            "machines": [m.to_dict() for m in self._machines.values()],
        }


__all__ = [
    "ResourceType",
    "RESOURCE_TYPE_ORDER",
    "PENDING_STATUS",
    "ExternalStagingResourceEntry",
    "build_default_bom",
    "ResourceProvisioningState",
    "ResourceStateMachineError",
    "ResourceStateMachine",
    "ProvisioningStateRegistry",
    "RESOURCE_STATE_TRANSITIONS",
    "FAILURE_STATES",
]

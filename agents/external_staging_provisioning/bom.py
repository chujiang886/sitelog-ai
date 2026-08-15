"""Phase 3.9.12 —— 供给 BOM（Tasks 18，复用 ResourceType）。

机器可读的 8 资源供给就绪清单（Track A 完成）。每类资源的真实账号/密钥/权限/预算/
域名/IdP tenant 等 Track B 输入统一 ``pending_external_staging_resource``。

与 ``.ai/staging/external_staging_resource_bom.json``（T5）同源；本模块给出
可程序化断言的 Python 表示，供 validator / gate / package 复用。

fail-closed：任何 BOM 条目一旦落入 ``provisioned`` / ``configured`` / 含明文
Secret / 非 PENDING 状态，即视为违例。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.models import (
    ResourceType,
    RESOURCE_TYPE_ORDER,
)
from agents.external_staging_provisioning.models import (
    ExternalStagingProvisioningError,
)

# 统一 PENDING 态（Track B 真实输入全部待真人）。
PENDING_STATUS = "pending_external_staging_resource"

# 每类资源默认 owner role（与 qualification._default_owner_role 一致）。
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

# 每类资源默认 provider service（provider-agnostic，腾讯云为 RECORDED 首选）。
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

# 每类资源对应的 IaC 模块（infrastructure/staging/）。
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


@dataclass(frozen=True)
class ProvisioningBomEntry:
    """单资源供给清单条目。"""

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


@dataclass
class ProvisioningBom:
    """8 资源供给就绪清单。"""

    entries: tuple[ProvisioningBomEntry, ...] = field(default_factory=tuple)

    @classmethod
    def build_default(cls) -> "ProvisioningBom":
        entries = tuple(
            ProvisioningBomEntry(
                resource_id=f"ext-staging-{rtype.value}",
                resource_type=rtype,
                required=True,
                owner_role=_OWNER_ROLE[rtype],
                default_provider_service=_PROVIDER_SERVICE[rtype],
                iac_module=_IAC_MODULE[rtype],
                status=PENDING_STATUS,
            )
            for rtype in RESOURCE_TYPE_ORDER
        )
        return cls(entries=tuple(entries))

    def by_type(self, rtype: ResourceType) -> ProvisioningBomEntry | None:
        for e in self.entries:
            if e.resource_type is rtype:
                return e
        return None

    def all_pending(self) -> bool:
        """8 资源是否全部诚实 PENDING（fail-closed）。"""

        return all(e.status == PENDING_STATUS for e in self.entries)

    def assert_all_pending(self) -> None:
        """断言 8 资源全部 PENDING（fail-closed）。"""

        non_pending = [e.resource_id for e in self.entries if e.status != PENDING_STATUS]
        if non_pending:
            raise ExternalStagingProvisioningError(
                f"存在非 PENDING 的供给资源（Track B 必须全 PENDING）：{non_pending}"
            )
        if len(self.entries) != 8:
            raise ExternalStagingProvisioningError(
                f"供给 BOM 资源数={len(self.entries)}（应为 8）。"
            )

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.entries),
            "required": sum(1 for e in self.entries if e.required),
            "pending": sum(1 for e in self.entries if e.status == PENDING_STATUS),
            "resource_ids": [e.resource_id for e in self.entries],
        }


__all__ = [
    "PENDING_STATUS",
    "ProvisioningBomEntry",
    "ProvisioningBom",
]

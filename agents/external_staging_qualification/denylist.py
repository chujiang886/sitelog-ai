"""Phase 3.9.10 —— Production Reference Denylist v2（Task 35）。

任何引用/连接目标若命中 Production Denylist，资格验证**拒绝**（BLOCKED），
杜绝把 Production 资源当作 External Staging 复用。

fail-closed：命中即拒，不做模糊放行。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from agents.external_staging_qualification.models import ResourceType


class ProductionResourceKind(str, Enum):
    """受 Denylist 约束的 Production 资源种类。"""

    DATABASE = "database"
    IDENTITY_PROVIDER = "identity_provider"
    SECRET_NAMESPACE = "secret_namespace"
    OBJECT_STORAGE = "object_storage"
    TELEMETRY = "telemetry"
    ALERT = "alert"
    DOMAIN = "domain"
    DEPLOYMENT_TARGET = "deployment_target"


@dataclass(frozen=True)
class ProductionDenylistEntry:
    """单条 Production 拒绝条目。"""

    kind: ProductionResourceKind
    reference: str  # 受保护的 Production 引用（精确匹配优先）
    description: str = ""


# 默认空 Denylist：真实 Production 引用由主理人 + 四角色线下登记后注入。
# 校验逻辑对所有 kind 生效；命中逻辑为「引用出现在已登记 Production 引用集合」。
DEFAULT_PRODUCTION_DENYLIST: tuple[ProductionDenylistEntry, ...] = ()


class ProductionDenylistViolation(ValueError):
    """命中 Production Denylist。"""


@dataclass(frozen=True)
class ProductionReferenceDenylist:
    """Production 引用拒绝表（v2）。"""

    entries: tuple[ProductionDenylistEntry, ...] = DEFAULT_PRODUCTION_DENYLIST

    def references_for(self, kind: ProductionResourceKind) -> frozenset[str]:
        return frozenset(e.reference for e in self.entries if e.kind is kind)

    def check(
        self,
        kind: ProductionResourceKind,
        reference: str,
        *,
        allow_prefix_match: bool = True,
    ) -> None:
        """校验某引用是否命中 Production Denylist。命中抛 ``ProductionDenylistViolation``。

        fail-closed：空引用不视为命中（pending），但明确 Production 引用必拒。
        """

        if not reference:
            return
        exact = self.references_for(kind)
        if reference in exact:
            raise ProductionDenylistViolation(
                f"引用 {reference!r} 命中 Production Denylist（{kind.value}），拒绝复用。"
            )
        if allow_prefix_match:
            for prod_ref in exact:
                if reference.startswith(prod_ref) or prod_ref.startswith(reference):
                    raise ProductionDenylistViolation(
                        f"引用 {reference!r} 与 Production 引用 {prod_ref!r} 前缀冲突，"
                        f"拒绝（{kind.value}）。"
                    )

    @classmethod
    def from_references(
        cls, references: Iterable[ProductionDenylistEntry]
    ) -> "ProductionReferenceDenylist":
        return cls(entries=tuple(references))


# 资源种类 → Production 资源种类映射（供 qualification 层调用）。
RESOURCE_TO_PRODUCTION_KIND = {
    ResourceType.DATABASE: ProductionResourceKind.DATABASE,
    ResourceType.IDENTITY_PROVIDER: ProductionResourceKind.IDENTITY_PROVIDER,
    ResourceType.SECRET_PROVIDER: ProductionResourceKind.SECRET_NAMESPACE,
    ResourceType.OBJECT_STORAGE: ProductionResourceKind.OBJECT_STORAGE,
    ResourceType.TELEMETRY: ProductionResourceKind.TELEMETRY,
    ResourceType.ALERT_SANDBOX: ProductionResourceKind.ALERT,
    ResourceType.DOMAIN_TLS: ProductionResourceKind.DOMAIN,
    ResourceType.DEPLOYMENT_TARGET: ProductionResourceKind.DEPLOYMENT_TARGET,
}


__all__ = [
    "ProductionResourceKind",
    "ProductionDenylistEntry",
    "ProductionReferenceDenylist",
    "ProductionDenylistViolation",
    "RESOURCE_TO_PRODUCTION_KIND",
    "DEFAULT_PRODUCTION_DENYLIST",
]

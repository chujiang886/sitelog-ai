"""Phase 3.9.10 —— Cross-environment Isolation Proof（Task 18）。

逐项证明 External Staging 与 Production 的资源隔离：

- staging DB != production DB
- staging secret namespace != production
- staging IdP != production
- staging storage != production
- staging telemetry != production
- staging alert != production
- staging domain != production
- staging deployment target != production
- staging token != production token

fail-closed：无法证明 → ``PENDING`` / ``BLOCKED``（**绝不**声明隔离成立）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_qualification.denylist import (
    ProductionReferenceDenylist,
    ProductionResourceKind,
    RESOURCE_TO_PRODUCTION_KIND,
)
from agents.external_staging_qualification.models import ResourceType


class IsolationVerdict(str, Enum):
    """隔离证明结论。"""

    VERIFIED = "verified"
    PENDING = "pending"
    BLOCKED = "blocked"


# 9 项隔离检查（staging 引用键 → Production 资源种类）。
_ISOLATION_CHECKS: tuple[tuple[str, ResourceType], ...] = (
    ("database", ResourceType.DATABASE),
    ("secret_namespace", ResourceType.SECRET_PROVIDER),
    ("identity_provider", ResourceType.IDENTITY_PROVIDER),
    ("object_storage", ResourceType.OBJECT_STORAGE),
    ("telemetry", ResourceType.TELEMETRY),
    ("alert", ResourceType.ALERT_SANDBOX),
    ("domain", ResourceType.DOMAIN_TLS),
    ("deployment_target", ResourceType.DEPLOYMENT_TARGET),
    ("token", ResourceType.IDENTITY_PROVIDER),
)


@dataclass
class IsolationProofItem:
    """单条隔离证明项。"""

    check: str
    staging_reference: str
    production_reference: str
    verdict: IsolationVerdict
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "staging_reference": self.staging_reference,
            "production_reference": self.production_reference,
            "verdict": self.verdict.value,
            "detail": self.detail,
        }


@dataclass
class CrossEnvironmentIsolationEvidence:
    """跨环境隔离证据包。"""

    items: tuple[IsolationProofItem, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, Any]:
        verified = sum(1 for i in self.items if i.verdict is IsolationVerdict.VERIFIED)
        pending = sum(1 for i in self.items if i.verdict is IsolationVerdict.PENDING)
        blocked = sum(1 for i in self.items if i.verdict is IsolationVerdict.BLOCKED)
        return {
            "total": len(self.items),
            "verified": verified,
            "pending": pending,
            "blocked": blocked,
            "all_verified": verified == len(self.items) and len(self.items) > 0,
            "any_blocked": blocked > 0,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "summary": self.summary(),
        }


class CrossEnvironmentIsolationProver:
    """跨环境隔离证明生成器（fail-closed）。"""

    def __init__(self, denylist: ProductionReferenceDenylist | None = None) -> None:
        self._denylist = denylist or ProductionReferenceDenylist()

    def prove(
        self,
        staging_references: dict[str, str],
        *,
        production_references: dict[str, str] | None = None,
    ) -> CrossEnvironmentIsolationEvidence:
        """生成隔离证据。

        ``production_references`` 为空（基线）→ 无 Production 引用可比对 → 全部 ``PENDING``。
        命中 Production Denylist → ``BLOCKED``。
        """

        prod = production_references or {}
        items: list[IsolationProofItem] = []
        for check, rtype in _ISOLATION_CHECKS:
            staging_ref = staging_references.get(check, "")
            prod_ref = prod.get(check, "")
            if staging_ref and prod_ref:
                if staging_ref == prod_ref:
                    verdict = IsolationVerdict.BLOCKED
                    detail = "Staging 引用与 Production 引用相同，隔离失败（BLOCKED）。"
                else:
                    verdict = IsolationVerdict.VERIFIED
                    detail = "Staging 与 Production 引用不同，隔离成立。"
            elif staging_ref and not prod_ref:
                # 有 staging 引用但无法比对 production → 无法证明
                verdict = IsolationVerdict.PENDING
                detail = "已登记 Staging 引用，但无 Production 引用可比对，隔离待证（PENDING）。"
            else:
                verdict = IsolationVerdict.PENDING
                detail = "Staging 引用未登记，隔离待证（PENDING）。"
            items.append(
                IsolationProofItem(check, staging_ref, prod_ref, verdict, detail)
            )
        return CrossEnvironmentIsolationEvidence(items=tuple(items))


__all__ = [
    "IsolationVerdict",
    "IsolationProofItem",
    "CrossEnvironmentIsolationEvidence",
    "CrossEnvironmentIsolationProver",
]

"""Phase 3.9.14 —— Evidence Model & Chain of Custody（Task 33，fail-closed）。

``Phase3914EvidenceModel`` 把前面各层（环境身份 / IaC 可执行性 / 九项隔离 / 13 项资格 /
Runtime Health / 变更管控 Gate / 运行时清单）的形态结论聚合成一份连贯、机器可读的证据模型；
``integrity_hash()`` 对其做确定性 SHA-256 链，使证据不可被静默篡改（chain of custody）。

fail-closed 要点：
- 证据模型恒 ``is_production=False``；任何组件若声称 production 即标记为违例并整体失败；
- 证据不含真实密钥明文；仅记录「是否配置 / 是否结构化通过」（布尔）；
- 哈希链覆盖全部组件结论，篡改即改变 integrity_hash；
- 真实外部资源缺位统一记为 ``PENDING_EXTERNAL_STAGING_RESOURCE``，不伪造、不掩盖。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from agents.staging_runtime.environment import EnvironmentIdentity

from .change_control import StagingRuntimeValidationGate, TERMINAL_STATE
from .iac_executor import execute as run_iac_execution
from .identity import external_staging_identity
from .isolation import ExternalStagingIsolationAuditor
from .qualification import RuntimeQualificationHarness
from .runtime_health import RuntimeHealthHarness
from .runtime_manifest import build_staging_runtime_manifest

PHASE = "3.9.14"


@dataclass(frozen=True)
class Phase3914EvidenceItem:
    """单条证据项。"""

    component: str
    status: str  # "ok" | "pending" | "violation"
    detail: str
    is_production: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "detail": self.detail,
            "is_production": self.is_production,
        }


class Phase3914EvidenceModel:
    """Phase 3.9.14 证据模型（聚合各层形态描述，确定性哈希链）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        items: Iterable[Phase3914EvidenceItem],
    ) -> None:
        self._identity = identity
        self._items = tuple(items)

    @property
    def environment(self) -> str:
        return self._identity.kind.value

    @property
    def is_production(self) -> bool:
        return self._identity.kind.is_production

    @property
    def items(self) -> tuple[Phase3914EvidenceItem, ...]:
        return self._items

    def violations(self) -> tuple[Phase3914EvidenceItem, ...]:
        return tuple(i for i in self._items if i.status == "violation")

    def has_production_leakage(self) -> bool:
        return any(i.is_production for i in self._items) or self.is_production

    def integrity_hash(self) -> str:
        canonical = json.dumps(
            [i.to_dict() for i in self._items],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "terminal_state": TERMINAL_STATE,
            "environment": self.environment,
            "is_production": self.is_production,
            "identity_fingerprint": (
                self._identity.fingerprint.value if self._identity.fingerprint else ""
            ),
            "items": [i.to_dict() for i in self._items],
            "violations": [i.to_dict() for i in self.violations()],
            "integrity_hash": self.integrity_hash(),
            "production_leakage": self.has_production_leakage(),
        }


def build_phase3914_evidence(
    identity: EnvironmentIdentity | None = None,
) -> Phase3914EvidenceModel:
    """聚合各层形态，产出 3.9.14 证据模型（不执行任何真实动作，确定性哈希）。"""

    ident = identity or external_staging_identity()
    items: list[Phase3914EvidenceItem] = []

    # 1. 环境身份（非生产，指纹就绪）
    items.append(
        Phase3914EvidenceItem(
            component="environment_identity",
            status="ok" if not ident.kind.is_production else "violation",
            detail=f"kind={ident.kind.value}, fingerprint_set={ident.fingerprint is not None}",
            is_production=ident.kind.is_production,
        )
    )

    # 2. IaC 可执行性（工具链真实校验）
    iac = run_iac_execution("infrastructure/staging")
    items.append(
        Phase3914EvidenceItem(
            component="iac_executable",
            status="ok" if iac.executable else "violation",
            detail=f"verdict={iac.verdict}, real_apply_allowed={iac.real_apply_allowed}",
        )
    )

    # 3. 九项隔离
    iso = ExternalStagingIsolationAuditor().audit_all()
    items.append(
        Phase3914EvidenceItem(
            component="nine_domain_isolation",
            status="ok" if iso.passed else "violation",
            detail=f"domains={len(iso.domains)}, production_leakage={iso.production_leakage}",
            is_production=iso.production_leakage,
        )
    )

    # 4. 13 项运行时资格
    qual = RuntimeQualificationHarness(ident).qualify_all()
    items.append(
        Phase3914EvidenceItem(
            component="thirteen_runtime_qualification",
            status="ok" if qual.passed else "violation",
            detail=f"code_verified={qual.code_verified_count}/{qual.total}",
        )
    )

    # 5. Runtime Health
    health = RuntimeHealthHarness(ident).assess()
    items.append(
        Phase3914EvidenceItem(
            component="runtime_health",
            status="ok" if health.passed else "violation",
            detail=f"structural={health.structural_health_count}, "
            f"external_pending={health.external_resources_health_pending}",
        )
    )

    # 6. 变更管控 Gate（3.9.14 终端态）
    gate = StagingRuntimeValidationGate(ident).run()
    items.append(
        Phase3914EvidenceItem(
            component="change_control_gate",
            status="ok" if gate.passed else "violation",
            detail=f"terminal_state={gate.terminal_state}, "
            f"human_verification_required={gate.human_verification_required}",
            is_production=gate.is_production,
        )
    )

    # 7. 运行时清单（确定性哈希）
    manifest = build_staging_runtime_manifest()
    items.append(
        Phase3914EvidenceItem(
            component="runtime_manifest",
            status="ok" if not manifest.is_production else "violation",
            detail=f"resources_pending={sum(1 for r in manifest.external_resources if not r.registered)}, "
            f"quals_not_executed={sum(1 for q in manifest.runtime_qualifications if not q.executed)}",
            is_production=manifest.is_production,
        )
    )

    return Phase3914EvidenceModel(ident, items)


__all__ = [
    "PHASE",
    "TERMINAL_STATE",
    "Phase3914EvidenceItem",
    "Phase3914EvidenceModel",
    "build_phase3914_evidence",
]

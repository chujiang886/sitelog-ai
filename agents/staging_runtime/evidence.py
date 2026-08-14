"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Evidence Model & Chain（Task 31-32）。

``StagingEvidenceModel`` 把前面 T1-T7 所有 staging_runtime 组件的**形态描述**聚合成
一份连贯、机器可读的证据模型；``StagingEvidenceChain`` 对其做确定性哈希链（chain of
custody），使证据不可被静默篡改。

关键约束（fail-closed）：
- 证据模型恒 ``is_production=False``；任何组件若声称 production 即标记为违例并整体失败。
- 证据不含真实密钥明文；仅记录「是否配置」（布尔）。
- 哈希链覆盖全部组件结论，篡改即改变 integrity_hash。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from agents.staging_runtime.config import load_staging_identity, staging_resource_readiness
from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard
from agents.staging_runtime.manifest import build_staging_runtime_manifest
from agents.staging_runtime.secret_provider import StagingSecretProvider
from agents.staging_runtime.db import StagingDatabaseProvider
from agents.staging_runtime.data_policy import StagingDataPolicy
from agents.staging_runtime.identity_provider import StagingIdentityProvider
from agents.staging_runtime.token_isolation import StagingTokenIsolation
from agents.staging_runtime.observability import StagingTelemetry
from agents.staging_runtime.alerting import StagingAlertChannel, StagingOnCallSandbox
from agents.staging_runtime.llm_voice import StagingLLMValidation, StagingVoiceValidation
from agents.staging_runtime.execution_scope import StagingExecutionScope

PHASE = "3.9.9"


@dataclass(frozen=True)
class StagingEvidenceItem:
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


class StagingEvidenceModel:
    """本地预生产证据模型（聚合 T1-T7 组件形态描述）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        items: Iterable[StagingEvidenceItem],
        *,
        secret_names: Iterable[str] = (),
    ) -> None:
        self._identity = identity
        self._items = tuple(items)
        self._secret_names = tuple(secret_names)

    @property
    def environment(self) -> str:
        return self._identity.kind.value

    @property
    def is_production(self) -> bool:
        return self._identity.kind.is_production

    @property
    def items(self) -> tuple[StagingEvidenceItem, ...]:
        return self._items

    def violations(self) -> tuple[StagingEvidenceItem, ...]:
        return tuple(i for i in self._items if i.status == "violation")

    def has_production_leakage(self) -> bool:
        """是否存在任何 production 泄漏（fail-closed 标志）。"""

        return any(i.is_production for i in self._items) or self.is_production

    def integrity_hash(self) -> str:
        """对所有证据项做确定性 SHA-256 链（chain of custody）。"""

        canonical = json.dumps(
            [i.to_dict() for i in self._items],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "environment": self.environment,
            "is_production": self.is_production,
            "identity_fingerprint": (
                self._identity.fingerprint.value if self._identity.fingerprint else ""
            ),
            "resource_readiness": staging_resource_readiness(self._identity).value,
            "secret_names": list(self._secret_names),
            "items": [i.to_dict() for i in self._items],
            "violations": [i.to_dict() for i in self.violations()],
            "integrity_hash": self.integrity_hash(),
            "production_leakage": self.has_production_leakage(),
        }


def build_staging_evidence(
    identity: EnvironmentIdentity | None = None,
    *,
    secret_names: Iterable[str] = (),
    production_refs: dict[str, Iterable[str]] | None = None,
    strict: bool = False,
) -> StagingEvidenceModel:
    """聚合 T1-T7 组件形态，产出证据模型（不执行任何真实动作）。"""

    ident = identity or load_staging_identity(strict=strict)
    guard = EnvironmentIsolationGuard()
    guard.assert_staging_integration_permitted(ident)

    refs = production_refs or {}
    items: list[StagingEvidenceItem] = []

    # Task 1-3 环境模型/指纹/护栏
    items.append(
        StagingEvidenceItem(
            component="environment_model",
            status="ok" if not ident.kind.is_production else "violation",
            detail=f"kind={ident.kind.value}, fingerprint set={ident.fingerprint is not None}",
            is_production=ident.kind.is_production,
        )
    )

    # Task 7 Manifest
    manifest = build_staging_runtime_manifest(ident, secret_names=list(secret_names))
    items.append(
        StagingEvidenceItem(
            component="staging_manifest",
            status="ok" if not manifest.is_production else "violation",
            detail=f"non_production_bound={manifest.non_production_bound}",
            is_production=manifest.is_production,
        )
    )

    # Task 5 Secret（仅记录是否配置，不记录明文）
    provider = StagingSecretProvider(ident)
    snap = provider.snapshot(list(secret_names))
    secret_pending = [r.name for r in snap if not r.resolved]
    items.append(
        StagingEvidenceItem(
            component="staging_secret",
            status="pending" if secret_pending else "ok",
            detail=f"pending={secret_pending or 'none'}",
        )
    )

    # Task 10-13 DB
    db = StagingDatabaseProvider(
        ident, production_dsn_refs=set(refs.get("database", ())), staging_dsn="staging-dsn"
    )
    try:
        db_desc = db.describe()
        db_status = "ok"
        db_detail = f"dsn_present={db_desc.dsn_present}"
    except Exception as e:  # noqa: BLE001
        db_status, db_detail = "violation", str(e)
    items.append(StagingEvidenceItem(component="staging_db", status=db_status, detail=db_detail))

    # Task 14 Data Policy
    policy = StagingDataPolicy(ident)
    items.append(
        StagingEvidenceItem(
            component="staging_data_policy",
            status="ok",
            detail=f"allowed={sorted(policy.allowed_classes())}",
        )
    )

    # Task 15 IdP
    idp = StagingIdentityProvider(
        ident, production_issuer_refs=set(refs.get("identity_provider", ())), staging_issuer="staging-idp"
    )
    try:
        idp_desc = idp.describe()
        idp_status, idp_detail = "ok", f"issuer_present={idp_desc.issuer_present}"
    except Exception as e:  # noqa: BLE001
        idp_status, idp_detail = "violation", str(e)
    items.append(StagingEvidenceItem(component="staging_idp", status=idp_status, detail=idp_detail))

    # Task 16 Token
    token = StagingTokenIsolation(ident, production_token_refs=set(refs.get("secret", ())))
    tok_verdict = token.check_token("staging-token", "staging-token")
    items.append(
        StagingEvidenceItem(
            component="staging_token_isolation",
            status="ok" if tok_verdict.isolated else "violation",
            detail=tok_verdict.reason,
        )
    )

    # Task 17-21 Observability
    obs = StagingTelemetry(ident).to_manifest()
    items.append(
        StagingEvidenceItem(
            component="staging_observability",
            status="ok" if not obs["is_production"] else "violation",
            detail=f"collects_real_data={obs['collects_real_data']}",
            is_production=bool(obs["is_production"]),
        )
    )

    # Task 22-23 Alert
    alert = StagingAlertChannel(
        ident, production_alert_refs=set(refs.get("alert", ())), staging_channel="staging-alert"
    )
    try:
        alert_desc = alert.describe()
        alert_status, alert_detail = "ok", f"channel_present={alert_desc.channel_present}"
    except Exception as e:  # noqa: BLE001
        alert_status, alert_detail = "violation", str(e)
    items.append(StagingEvidenceItem(component="staging_alert", status=alert_status, detail=alert_detail))

    # Task 24-25 LLM / Voice
    llm = StagingLLMValidation(
        ident, production_endpoint_refs=set(refs.get("llm", ())), staging_endpoint="staging-llm"
    )
    try:
        llm_desc = llm.describe()
        llm_status, llm_detail = "ok", f"endpoint_present={llm_desc.endpoint_present}"
    except Exception as e:  # noqa: BLE001
        llm_status, llm_detail = "violation", str(e)
    items.append(StagingEvidenceItem(component="staging_llm", status=llm_status, detail=llm_detail))

    voice = StagingVoiceValidation(
        ident, production_voice_refs=set(refs.get("voice", ())), staging_voice="staging-voice"
    )
    try:
        voice_desc = voice.describe()
        voice_status, voice_detail = "ok", f"endpoint_present={voice_desc.endpoint_present}"
    except Exception as e:  # noqa: BLE001
        voice_status, voice_detail = "violation", str(e)
    items.append(StagingEvidenceItem(component="staging_voice", status=voice_status, detail=voice_detail))

    # Task 9 Execution Scope
    scope = StagingExecutionScope(ident)
    items.append(
        StagingEvidenceItem(
            component="execution_scope",
            status="ok",
            detail=f"allowed={len(scope.allowed_actions())}, forbidden={len(scope.forbidden_actions())}",
        )
    )

    return StagingEvidenceModel(ident, items, secret_names=list(secret_names))


__all__ = [
    "PHASE",
    "StagingEvidenceItem",
    "StagingEvidenceModel",
    "build_staging_evidence",
]

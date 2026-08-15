"""Phase 3.9.10 —— Machine-readable Qualification Package（Tasks 22-23）。

生成 ``.ai/staging/external_staging_qualification_package.json``：

- schema_version / phase / source_commit / environment identity / fingerprint
- resource registry summary / connectivity summary / isolation summary
- deployment summary / runtime health / telemetry / alerting
- evidence refs / gate / pending resources / human pending
- ``contains_real_secret = false``
- ``production_activation_prohibited = true``

canonical payload 稳定 → SHA-256 稳定（相同事实 → 相同哈希）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from agents.external_staging_qualification.evidence import EvidenceChain
from agents.external_staging_qualification.gate import GateResult
from agents.external_staging_qualification.isolation import (
    CrossEnvironmentIsolationEvidence,
)
from agents.external_staging_qualification.models import (
    EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE,
    ExternalStagingEnvironmentIdentity,
    ExternalStagingResourceRegistry,
)
from agents.external_staging_qualification.runtime import RuntimeHealthReport


SCHEMA_VERSION = "1.0.0"
PHASE = "3.9.10"


def _canonical_json(payload: dict[str, Any]) -> str:
    """稳定序列化（排序键 + 无多余空白），用于哈希与 diff。"""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _strip_non_fact(value: Any) -> Any:
    """递归剔除非事实元数据键（哈希本身、生成时间戳），保留全部事实字段。

    ``generated_at`` 可能出现在嵌套结构（如 evidence_refs 各条目的采集时间戳），
    必须逐层剥离，否则会破坏「相同事实 → 相同哈希」的确定性包不变量。
    """

    if isinstance(value, dict):
        return {
            k: _strip_non_fact(v)
            for k, v in value.items()
            if k not in ("package_hash", "generated_at")
        }
    if isinstance(value, list):
        return [_strip_non_fact(v) for v in value]
    return value


def _hashable_body(payload: dict[str, Any]) -> dict[str, Any]:
    """用于完整性哈希的事实主体：剔除非事实元数据（哈希本身、生成时间戳）。

    保证「相同事实 → 相同哈希」（确定性包），``generated_at`` 仅作可读元数据保留。
    """

    return _strip_non_fact(payload)


def build_qualification_package(
    *,
    source_commit: str,
    environment_identity: ExternalStagingEnvironmentIdentity,
    registry: ExternalStagingResourceRegistry,
    isolation: CrossEnvironmentIsolationEvidence | None = None,
    runtime: RuntimeHealthReport | None = None,
    evidence_chain: EvidenceChain | None = None,
    gate: GateResult | None = None,
    pending_resources: tuple[str, ...] = (),
    human_pending: tuple[str, ...] = (),
    telemetry_status: str = "not_configured",
    alerting_status: str = "not_configured",
    deployment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建机器可读资格包（确定性）。"""

    generated_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "phase_name": "External Staging Qualification & Evidence Integration Layer",
        "terminal_state": EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE,
        "source_commit": source_commit,
        "generated_at": generated_at,
        "environment_identity": environment_identity.to_dict(),
        "resource_registry_summary": registry.summary(),
        "connectivity_summary": {
            "configured": registry.summary()["configured"],
            "verified": registry.summary()["verified"],
        },
        "isolation_summary": (
            isolation.summary() if isolation else {"total": 0, "verified": 0, "pending": 0, "blocked": 0}
        ),
        "runtime_health": runtime.to_dict() if runtime else {},
        "telemetry_status": telemetry_status,
        "alerting_status": alerting_status,
        "deployment_summary": deployment_summary or {"target": "none", "deployed": False},
        "evidence_refs": evidence_chain.to_dict() if evidence_chain else {},
        "gate": gate.to_dict() if gate else {},
        "pending_resources": list(pending_resources),
        "human_pending": list(human_pending),
        "contains_real_secret": False,
        "production_activation_prohibited": True,
        "engineering_enabled": False,
    }
    payload["package_hash"] = hashlib.sha256(
        _canonical_json(_hashable_body(payload)).encode("utf-8")
    ).hexdigest()
    return payload


def package_hash(payload: dict[str, Any]) -> str:
    """重算 canonical 哈希（用于校验/ diff）。"""

    body = _hashable_body(payload)
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


__all__ = [
    "SCHEMA_VERSION",
    "PHASE",
    "build_qualification_package",
    "package_hash",
]

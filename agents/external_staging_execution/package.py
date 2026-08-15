"""Phase 3.9.11 —— Machine-readable Execution Package（Tasks 27-28）。

生成 ``.ai/staging/external_staging_execution_qualification_package.json``：

- schema_version / phase / source_commit / environment identity / fingerprint
- execution plan summary / isolation summary / runtime health summary
- deployment summary / telemetry / alerting / evidence refs / gate
- pending resources / human pending
- ``contains_real_secret = false``
- ``production_activation_prohibited = true``
- ``engineering_enabled = false``

canonical payload 稳定 → SHA-256 稳定（相同事实 → 相同哈希）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from agents.external_staging_execution.evidence import ExecutionEvidenceChain
from agents.external_staging_execution.gate import GateResult
from agents.external_staging_execution.models import (
    EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE,
    ExecutionPlan,
)
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
)

SCHEMA_VERSION = "1.0.0"
PHASE = "3.9.11"


def _canonical_json(payload: dict[str, Any]) -> str:
    """稳定序列化（排序键 + 无多余空白）。"""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _strip_non_fact(value: Any) -> Any:
    """递归剔除非事实元数据键（哈希本身、生成时间戳）。"""

    if isinstance(value, dict):
        return {
            k: _strip_non_fact(v)
            for k, v in value.items()
            if k not in ("package_hash", "generated_at")
        }
    if isinstance(value, list):
        return [_strip_non_fact(v) for v in value]
    return value


def build_execution_package(
    *,
    source_commit: str,
    environment_identity: ExternalStagingEnvironmentIdentity | dict[str, Any],
    plan: ExecutionPlan | None = None,
    evidence_chain: ExecutionEvidenceChain | None = None,
    gate: GateResult | None = None,
    isolation_summary: dict[str, Any] | None = None,
    runtime_summary: dict[str, Any] | None = None,
    pending_resources: tuple[str, ...] = (),
    human_pending: tuple[str, ...] = (),
    telemetry_status: str = "not_configured",
    alerting_status: str = "not_configured",
    deployment_summary: dict[str, Any] | None = None,
    baseline_commit: str | None = None,
    evidence_source_commit: str | None = None,
    package_generated_from_commit: str | None = None,
) -> dict[str, Any]:
    """构建机器可读执行包（确定性）。

    commit 语义拆分（与 3.9.10 一致）：
    - ``baseline_commit``：本阶段所基于的基线 commit（Phase 3.9.10-R1 tip）。
    - ``evidence_source_commit``：执行框架所证明的软件版本（真正包含 3.9.11 实现的 commit）。
    - ``package_generated_from_commit``：实际生成本包的 HEAD。
    """

    evidence_commit = evidence_source_commit or source_commit
    baseline = baseline_commit or source_commit
    generated_from = package_generated_from_commit or source_commit

    generated_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    identity_dict = (
        environment_identity.to_dict()
        if hasattr(environment_identity, "to_dict")
        else environment_identity
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "phase_name": "External Staging Execution & Qualification Layer",
        "terminal_state": EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE,
        "source_commit": evidence_commit,
        "baseline_commit": baseline,
        "evidence_source_commit": evidence_commit,
        "package_generated_from_commit": generated_from,
        "generated_at": generated_at,
        "environment_identity": identity_dict,
        "execution_plan_summary": plan.summary() if plan else {},
        "isolation_summary": isolation_summary
        or {"total": 9, "verified": 0, "pending": 9, "blocked": 0},
        "runtime_health_summary": runtime_summary
        or {
            "total": 13,
            "healthy": 0,
            "not_configured": 13,
            "unknown": 0,
            "all_healthy": False,
            "unknown_treated_as_healthy": False,
        },
        "telemetry_status": telemetry_status,
        "alerting_status": alerting_status,
        "deployment_summary": deployment_summary
        or {"target": "none", "deployed": False, "plan_only": True},
        "evidence_refs": evidence_chain.to_dict() if evidence_chain else {},
        "gate": gate.to_dict() if gate else {},
        "pending_resources": list(pending_resources),
        "human_pending": list(human_pending),
        "contains_real_secret": False,
        "production_activation_prohibited": True,
        "engineering_enabled": False,
    }
    payload["package_hash"] = hashlib.sha256(
        _canonical_json(_strip_non_fact(payload)).encode("utf-8")
    ).hexdigest()
    return payload


def package_hash(payload: dict[str, Any]) -> str:
    """重算 canonical 哈希（用于校验/ diff）。"""

    return hashlib.sha256(_canonical_json(_strip_non_fact(payload)).encode("utf-8")).hexdigest()


__all__ = [
    "SCHEMA_VERSION",
    "PHASE",
    "build_execution_package",
    "package_hash",
]

"""Live-qualification machine package (T30) — deterministic, tamper-evident.

Aggregates the full live-qualification evidence set into one package with a SHA-256
that is deterministic over everything EXCEPT volatile audit timestamps. The package
honestly reflects the real state: with no human input + dual-key, the 8 resources are
PENDING and real_resources_qualified = 0.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict

# Keys excluded from the deterministic hash (audit-only volatility).
_VOLATILE_KEYS = {
    "built_at",
    "generated_at",
    "received_at",
    "executed_at",
    "verified_at",
}


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def deterministic_hash(payload: Any) -> str:
    """SHA-256 over a volatility-stripped, key-sorted canonical form."""
    canon = json.dumps(_strip_volatile(payload), sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class LiveQualificationPackage:
    phase: str
    terminal_state: str
    provider_init_result: str  # "FAIL" | "BLOCKED" | "PASS"
    provider_init_evidence: Dict = field(default_factory=dict)
    resource_states: Dict[str, str] = field(default_factory=dict)
    isolation_snapshot: Dict[str, str] = field(default_factory=dict)
    runtime_live_snapshot: Dict[str, str] = field(default_factory=dict)
    deployment_status: str = "NOT_DEPLOYED"
    e2e_status: str = "NOT_EXECUTED"
    failure_state: str = "NONE"
    evidence_digest: str = ""
    real_resources_qualified: int = 0
    real_resources_total: int = 8
    # audit-only (excluded from hash)
    built_at: str = ""
    package_hash: str = ""


def build_live_package(
    *,
    phase: str,
    terminal_state: str,
    provider_init_result: str,
    provider_init_evidence: Dict,
    resource_states: Dict[str, str],
    isolation_snapshot: Dict[str, str],
    runtime_live_snapshot: Dict[str, str],
    deployment_status: str,
    e2e_status: str,
    failure_state: str,
    evidence_digest: str,
) -> LiveQualificationPackage:
    qualified = sum(
        1 for v in resource_states.values() if v == "QUALIFIED_EXTERNAL_STAGING"
    )
    pkg = LiveQualificationPackage(
        phase=phase,
        terminal_state=terminal_state,
        provider_init_result=provider_init_result,
        provider_init_evidence=provider_init_evidence or {},
        resource_states=resource_states,
        isolation_snapshot=isolation_snapshot,
        runtime_live_snapshot=runtime_live_snapshot,
        deployment_status=deployment_status,
        e2e_status=e2e_status,
        failure_state=failure_state,
        evidence_digest=evidence_digest,
        real_resources_qualified=qualified,
        real_resources_total=8,
    )
    # compute hash over everything except volatile audit fields
    d = pkg.__dict__.copy()
    d.pop("built_at", None)
    d.pop("package_hash", None)
    pkg.package_hash = deterministic_hash(d)
    pkg.built_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return pkg

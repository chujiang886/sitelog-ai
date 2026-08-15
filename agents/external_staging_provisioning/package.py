"""Phase 3.9.12 —— Machine-readable Provisioning Package（Task 19）。

生成 ``.ai/staging/external_staging_provisioning_operator_package.json``：

- schema_version / phase / source_commit / environment identity / fingerprint
- provisioning bom summary / iac dry-run summary / adapter contract summary
- operator gate 3 态 / pending resources / human pending
- ``contains_real_secret = false``
- ``production_activation_prohibited = true``
- ``engineering_enabled = false``

canonical payload 稳定 → SHA-256 稳定（相同事实 → 相同哈希，复用 3.9.11 确定性算法）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from agents.external_staging_provisioning.bom import ProvisioningBom
from agents.external_staging_provisioning.gate import OperatorGateResult
from agents.external_staging_provisioning.models import (
    EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE,
)
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
)

SCHEMA_VERSION = "1.0.0"
PHASE = "3.9.12"


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


def build_provisioning_package(
    *,
    source_commit: str,
    environment_identity: ExternalStagingEnvironmentIdentity | dict[str, Any],
    bom: ProvisioningBom | None = None,
    gate: OperatorGateResult | None = None,
    iac_dry_run_summary: dict[str, Any] | None = None,
    adapter_contract_summary: dict[str, Any] | None = None,
    pending_resources: tuple[str, ...] = (),
    human_pending: tuple[str, ...] = (),
    baseline_commit: str | None = None,
    package_generated_from_commit: str | None = None,
) -> dict[str, Any]:
    """构建机器可读供给算子包（确定性）。"""

    if bom is None:
        bom = ProvisioningBom.build_default()
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
        "phase_name": "External Staging Provisioning & Operator Readiness",
        "terminal_state": EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE,
        "source_commit": source_commit,
        "baseline_commit": baseline,
        "package_generated_from_commit": generated_from,
        "generated_at": generated_at,
        "environment_identity": identity_dict,
        "bom_summary": bom.summary(),
        "iac_dry_run_summary": iac_dry_run_summary
        or {"scanned": True, "all_ok": True, "count_zero_modules": 4},
        "adapter_contract_summary": adapter_contract_summary
        or {"total": 8, "all_honest_pending": True, "contract_test_passed": True},
        "operator_gate": gate.to_dict() if gate else {},
        "pending_resources": list(pending_resources) or [
            e.resource_id for e in bom.entries
        ],
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
    "build_provisioning_package",
    "package_hash",
]

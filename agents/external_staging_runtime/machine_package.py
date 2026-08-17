"""Phase 3.9.14 —— 确定性运行时执行包（machine_package，T34-T35 支撑）。

生成**确定性**的运行时执行包：同一 7 层结论 + 固定常量 → 同一 SHA-256。
包内含 7 层 harness 结论（隔离/资格/健康/E2E/恢复/变更/证据，全 plan-only / PENDING 资源）、
``engineering_enabled=False``、``real_resources_provisioned=0``（8 External Resources 全 Pending）。
此包用于 SSOT / 审计 / CI 比对，证明 AI 未伪造任何真实资源或真实执行。

fail-closed 自检（``validate_package``）：
- 确定性：重建哈希须等于 ``package_hash``（篡改即变）；
- 红线：``engineering_enabled=False`` / ``real_apply_allowed=False`` / ``is_production=False``；
- 逐层不变量：7 层全部 plan-only、无 production 泄漏、变更管控永不 GO/APPROVED；
- 凭据深扫：序列化包不得含明文密钥（fail-closed 抛错）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.external_staging_runtime.credential_deep_scanner import (
    assert_no_deep_credential_leak,
)
from agents.external_staging_runtime.change_control import (
    TERMINAL_STATE,
    evaluate_change_control,
)
from agents.external_staging_runtime.e2e_harness import EndToEndQualificationHarness
from agents.external_staging_runtime.evidence import build_phase3914_evidence
from agents.external_staging_runtime.failure_recovery import FailureRecoveryRollbackPlan
from agents.external_staging_runtime.identity import external_staging_identity
from agents.external_staging_runtime.isolation import ExternalStagingIsolationAuditor
from agents.external_staging_runtime.qualification import RuntimeQualificationHarness
from agents.external_staging_runtime.runtime_health import RuntimeHealthHarness
from agents.external_staging_runtime.runtime_manifest import (
    EXTERNAL_RESOURCE_KINDS,
    build_staging_runtime_manifest,
)

PACKAGE_SCHEMA = "boip.ext_staging.runtime_e2e.1"
GENERATED_BY = "phase3.9.14.ai_autonomous_execution"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _strip_generated_at(obj: Any) -> Any:
    """递归剔除 ``generated_at`` 时间戳，使包内容仅由结构结论 + 常量决定（确定性）。"""

    if isinstance(obj, dict):
        return {k: _strip_generated_at(v) for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, (list, tuple)):
        return [_strip_generated_at(v) for v in obj]
    return obj


def _build_layers(identity: Any) -> dict[str, Any]:
    """聚合 7 层 harness 结论（全部 plan-only，不执行真实动作）。"""

    isolation = ExternalStagingIsolationAuditor().audit_all()
    qualification = RuntimeQualificationHarness(identity).qualify_all()
    health = RuntimeHealthHarness(identity).assess()
    e2e = EndToEndQualificationHarness(identity).build_plan()
    recovery = FailureRecoveryRollbackPlan(identity).build()
    # 无双钥匙授权 → PENDING_HUMAN_AUTHORIZATION（real_apply 恒禁止）
    change_control = evaluate_change_control()
    evidence = build_phase3914_evidence(identity)
    return {
        "isolation": _strip_generated_at(isolation.to_dict()),
        "qualification": _strip_generated_at(qualification.to_dict()),
        "runtime_health": _strip_generated_at(health.to_dict()),
        "e2e_qualification": _strip_generated_at(e2e.to_dict()),
        "failure_recovery": _strip_generated_at(recovery.to_dict()),
        "change_control": _strip_generated_at(change_control.to_dict()),
        "evidence": _strip_generated_at(evidence.to_dict()),
    }


def build_machine_package(identity: Any = None) -> dict[str, Any]:
    """构建确定性运行时执行包（聚合 7 层 + manifest + iac 可执行性）。"""

    ident = identity or external_staging_identity()
    layers = _build_layers(ident)
    manifest = build_staging_runtime_manifest()

    package = {
        "schema": PACKAGE_SCHEMA,
        "generated_by": GENERATED_BY,
        "layer_count": len(layers),
        "engineering_enabled": bool(load_engineering_enabled()),
        "real_resources_provisioned": 0,
        "total_resources": len(EXTERNAL_RESOURCE_KINDS),
        "resources_pending": len(EXTERNAL_RESOURCE_KINDS),
        "iac_executable": manifest.iac_executable,
        "terminal_state": TERMINAL_STATE,
        "layers": layers,
        "manifest_summary": {
            "phase": manifest.phase,
            "canonical_phase_id": manifest.canonical_phase_id,
            "engineering_enabled": manifest.engineering_enabled,
            "is_production": manifest.is_production,
            "real_apply_allowed": manifest.real_apply_allowed,
            "real_execution_allowed": manifest.real_execution_allowed,
            "deployment_mode": manifest.deployment_mode,
            "iac_executable": manifest.iac_executable,
            "external_resources": len(manifest.external_resources),
            "runtime_qualifications": len(manifest.runtime_qualifications),
        },
        "note": "plan-only; 7-layer structural conclusions only; no real external staging resource provisioned/executed by AI",
    }

    # fail-closed：递归深扫嵌入的明文凭据（不含真实密钥 → PASS）。
    assert_no_deep_credential_leak(text=_canonical_json(package))

    package_hash = hashlib.sha256(_canonical_json(package).encode("utf-8")).hexdigest()
    return {
        "package": package,
        "package_hash": package_hash,
        "deterministic": True,
        # built_at 仅为审计元数据，不计入确定性哈希（时间戳非包身份）。
        "built_at": _utc_now(),
    }


def _assert_layer_invariants(layers: dict[str, Any]) -> None:
    """逐层断言 fail-closed 不变量（任一违反即抛错）。"""

    # isolation
    iso = layers["isolation"]
    assert iso["passed"] is True, "isolation audit must pass"
    assert iso["production_leakage"] is False, "isolation must have no production leakage"
    assert iso["real_resources_present"] == 0, "no real resource may be present"
    for d in iso["domains"]:
        assert d["structurally_isolated"] is True, f"domain {d['domain']} not structurally isolated"
        assert d["production_leakage"] is False, f"domain {d['domain']} has production leakage"

    # qualification
    qual = layers["qualification"]
    assert qual["is_production"] is False
    assert qual["real_apply_allowed"] is False
    assert qual["code_verified_count"] == qual["total"], "all 13 checks must be code-verified"
    assert qual["runtime_executed_count"] == 0, "no runtime execution allowed"

    # runtime_health
    health = layers["runtime_health"]
    assert health["is_production"] is False
    assert health["real_apply_allowed"] is False
    assert health["overall_status"] == "PLAN_ONLY", "health must be PLAN_ONLY"

    # e2e
    e2e = layers["e2e_qualification"]
    assert e2e["is_production"] is False
    assert e2e["real_apply_allowed"] is False
    assert e2e["terminal_state"] == TERMINAL_STATE
    for s in e2e["steps"]:
        assert s["status"] == "PLAN_ONLY_STRUCTURAL_OK", f"E2E step {s['order']} not structurally OK"

    # failure_recovery
    rec = layers["failure_recovery"]
    assert rec["is_production"] is False
    assert rec["real_apply_allowed"] is False
    assert rec["production_rollback_forbidden"] is True, "production rollback must be forbidden"

    # change_control
    cc = layers["change_control"]
    assert cc["is_production"] is False
    assert cc["real_apply_allowed"] is False
    assert cc["is_go_or_approved"] is False, "change control must never be GO/APPROVED"
    assert cc["terminal_state"] == TERMINAL_STATE

    # evidence
    ev = layers["evidence"]
    assert ev["is_production"] is False
    assert ev["production_leakage"] is False
    assert len(ev["violations"]) == 0, "evidence must have zero violations"


def validate_package(pkg: dict[str, Any]) -> dict[str, Any]:
    """fail-closed 自检：确定性 + 全部红线不变量 + 无凭据泄漏。

    返回 ``{"valid": True, "package_hash": ..., "terminal_state": ...}``；
    任一违反即抛 ``AssertionError``（fail-closed，不返回 False 软失败）。
    """

    assert isinstance(pkg, dict) and "package" in pkg and "package_hash" in pkg, "malformed package"
    package = pkg["package"]

    # 1. 确定性：重建哈希须一致（篡改即变；包内容已剔除 generated_at）
    expected_hash = hashlib.sha256(_canonical_json(package).encode("utf-8")).hexdigest()
    assert expected_hash == pkg["package_hash"], "package hash mismatch (tampered or non-deterministic)"
    assert pkg.get("deterministic") is True

    # 2. 工程开关红线
    assert package["engineering_enabled"] is False, "engineering_enabled must be False"

    # 3. 逐层红线不变量
    _assert_layer_invariants(package["layers"])

    # 4. manifest 摘要红线
    ms = package["manifest_summary"]
    assert ms["engineering_enabled"] is False
    assert ms["is_production"] is False
    assert ms["real_apply_allowed"] is False
    assert ms["real_execution_allowed"] is False

    # 5. 凭据深扫（重扫序列化包，确保无明文密钥）
    assert_no_deep_credential_leak(text=_canonical_json(package))

    return {
        "valid": True,
        "package_hash": pkg["package_hash"],
        "terminal_state": package["terminal_state"],
    }


__all__ = ["build_machine_package", "validate_package"]

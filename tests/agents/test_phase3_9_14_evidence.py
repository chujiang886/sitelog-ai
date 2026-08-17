"""Phase 3.9.14 —— 证据链（Task 33）确定性哈希 + fail-closed 测试。"""

from __future__ import annotations

from agents.external_staging_runtime.change_control import TERMINAL_STATE
from agents.external_staging_runtime.evidence import (
    Phase3914EvidenceModel,
    build_phase3914_evidence,
)
from agents.external_staging_runtime.identity import external_staging_identity


def test_evidence_no_production_leakage() -> None:
    model = build_phase3914_evidence(external_staging_identity())
    assert isinstance(model, Phase3914EvidenceModel)
    assert model.has_production_leakage() is False
    assert model.is_production is False


def test_evidence_integrity_hash_deterministic() -> None:
    h1 = build_phase3914_evidence(external_staging_identity()).integrity_hash()
    h2 = build_phase3914_evidence(external_staging_identity()).integrity_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_evidence_dict_contains_terminal_state() -> None:
    d = build_phase3914_evidence(external_staging_identity()).to_dict()
    assert d["terminal_state"] == TERMINAL_STATE
    assert d["phase"] == "3.9.14"
    assert d["is_production"] is False
    assert d["production_leakage"] is False
    # 7 个证据组件齐全
    components = {i["component"] for i in d["items"]}
    assert {
        "environment_identity",
        "iac_executable",
        "nine_domain_isolation",
        "thirteen_runtime_qualification",
        "runtime_health",
        "change_control_gate",
        "runtime_manifest",
    }.issubset(components)


def test_evidence_no_real_secret_plaintext() -> None:
    # 证据不得包含真实密钥明文（仅布尔/形态描述）。
    d = build_phase3914_evidence(external_staging_identity()).to_dict()
    blob = str(d).lower()
    assert "password" not in blob
    assert "secret_value" not in blob

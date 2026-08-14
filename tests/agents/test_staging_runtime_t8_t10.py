"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— T8-T10 测试（Task 31-38）。

覆盖：
- Task 31-32 Evidence Model & Chain：聚合 T1-T7 组件、哈希链、production 泄漏检测。
- Task 33-34 Validation Gate：结构性校验电池、终端态恒 BUILT_NO_GO、不输出 GO/APPROVED。
- Task 35-38 Packet / Validator / Scanner / Checklist：机器可读包、完整性校验、
  fail-closed 扫描（production 标记拒绝认证）、人工清单存在。

红线约定：不修改 engineering_enabled；需要模拟启用态时 monkeypatch red_line 函数。
"""

from __future__ import annotations

import pytest

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.environment import RuntimeEnvironment
from agents.staging_runtime.evidence import build_staging_evidence, StagingEvidenceModel
from agents.staging_runtime.gate import (
    StagingValidationGate,
    TERMINAL_STATE,
    StagingGateError,
)
from agents.staging_runtime.packet import (
    build_staging_packet,
    validate_packet,
    StagingPacketScanner,
    StagingPacketScanError,
    HUMAN_VERIFICATION_CHECKLIST,
)


@pytest.fixture
def identity():
    return load_staging_identity()


# ─────────────────────── Task 31-32: Evidence Model & Chain ───────────────────────


def test_evidence_model_non_production(identity):
    model = build_staging_evidence(identity, secret_names=["llm_api_key"])
    assert isinstance(model, StagingEvidenceModel)
    assert model.is_production is False
    assert model.has_production_leakage() is False
    assert model.integrity_hash()


def test_evidence_model_lists_all_components(identity):
    model = build_staging_evidence(identity)
    components = {i.component for i in model.items}
    expected = {
        "environment_model", "staging_manifest", "staging_secret", "staging_db",
        "staging_data_policy", "staging_idp", "staging_token_isolation",
        "staging_observability", "staging_alert", "staging_llm", "staging_voice",
        "execution_scope",
    }
    assert expected.issubset(components)


def test_evidence_integrity_changes_on_tamper(identity):
    model = build_staging_evidence(identity)
    h1 = model.integrity_hash()
    # 篡改一个证据项的 detail → 哈希应改变（chain of custody 生效）。
    tampered = StagingEvidenceModel(
        identity,
        [__import__("copy").copy(i) for i in model.items],
    )
    # 直接重建并修改一项 detail
    items = list(model.items)
    items[0] = __import__("agents.staging_runtime.evidence", fromlist=["StagingEvidenceItem"]).StagingEvidenceItem(
        component=items[0].component, status=items[0].status, detail="TAMPERED", is_production=items[0].is_production
    )
    tampered = StagingEvidenceModel(identity, items)
    assert tampered.integrity_hash() != h1


# ─────────────────────── Task 33-34: Validation Gate ───────────────────────


def test_gate_runs_and_terminal_state_built_no_go(identity):
    verdict = StagingValidationGate(identity).run(secret_names=["llm_api_key"])
    assert verdict.terminal_state == TERMINAL_STATE
    assert verdict.terminal_state.endswith("BUILT_NO_GO")
    assert verdict.is_production is False
    assert verdict.external_pending is True
    assert verdict.human_verification_required is True


def test_gate_all_checks_pass_for_local_staging(identity):
    verdict = StagingValidationGate(identity).run()
    assert all(c.passed for c in verdict.checks), [c for c in verdict.checks if not c.passed]


def test_gate_rejects_non_staging_environment():
    # 显式传入 TESTING 身份 → Gate 应拒绝运行并抛 StagingGateError。
    from agents.staging_runtime.environment import EnvironmentIdentity, EnvironmentResources

    dev = EnvironmentIdentity(
        kind=RuntimeEnvironment.TESTING, name="d", purpose="p",
        resources=EnvironmentResources(),
    )
    with pytest.raises(StagingGateError):
        StagingValidationGate(dev)


# ─────────────────────── Task 35-38: Packet / Validator / Scanner / Checklist ───────────────────────


def test_packet_build_and_validate_roundtrip(identity):
    packet = build_staging_packet(identity, secret_names=["llm_api_key"])
    data = packet.to_dict()
    verdict = validate_packet(data)
    assert verdict.valid is True
    assert data["is_production"] is False
    assert data["terminal_state"] == TERMINAL_STATE


def test_packet_validator_rejects_production_is_production(identity):
    packet = build_staging_packet(identity)
    data = packet.to_dict()
    data["is_production"] = True
    verdict = validate_packet(data)
    assert verdict.valid is False


def test_packet_validator_rejects_tampered_hash(identity):
    packet = build_staging_packet(identity)
    data = packet.to_dict()
    data["integrity_hash"] = "0" * 64
    verdict = validate_packet(data)
    assert verdict.valid is False


def test_scanner_refuses_production_marker():
    from agents.staging_runtime.packet import StagingEvidencePacket

    packet = StagingEvidencePacket(
        schema_version="1.0.0", phase="3.9.9", terminal_state=TERMINAL_STATE,
        environment="local_staging", is_production=True, external_pending=True,
        human_verification_required=True, evidence={}, gate={}, integrity_hash="x",
    )
    scanner = StagingPacketScanner()
    with pytest.raises(StagingPacketScanError):
        scanner.scan(packet).require_certifiable()


def test_scanner_refuses_prohibited_terminal_state():
    from agents.staging_runtime.packet import StagingEvidencePacket

    packet = StagingEvidencePacket(
        schema_version="1.0.0", phase="3.9.9", terminal_state="GO",
        environment="local_staging", is_production=False, external_pending=True,
        human_verification_required=True, evidence={}, gate={}, integrity_hash="x",
    )
    scanner = StagingPacketScanner()
    with pytest.raises(StagingPacketScanError):
        scanner.scan(packet).require_certifiable()


def test_human_checklist_present_and_covers_four_roles():
    roles = {c["owner_role"] for c in HUMAN_VERIFICATION_CHECKLIST}
    assert "production-owner" in roles
    assert "release-manager" in roles
    assert "security-owner" in roles
    assert "auditor" in roles
    assert len(HUMAN_VERIFICATION_CHECKLIST) >= 5


def test_current_staging_status_read_only(identity):
    from agents.staging_runtime.status import current_staging_status, build_staging_contract

    status = current_staging_status(identity)
    assert status.is_production is False
    assert status.terminal_state == TERMINAL_STATE
    assert status.gate_passed is True
    assert status.external_pending is True
    assert status.human_verification_required is True

    contract = build_staging_contract()
    assert contract["forbidden_environment"] == "production"
    assert contract["terminal_state"] == TERMINAL_STATE
    assert contract["reads_only"] is True
    assert "engineering_enabled 恒为 false" in contract["red_lines"]

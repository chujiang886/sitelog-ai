"""Phase 3.9.14 —— Runtime Health（Task 29）与 E2E 编排（Task 30）fail-closed 测试。"""

from __future__ import annotations

from agents.external_staging_runtime.change_control import TERMINAL_STATE
from agents.external_staging_runtime.e2e_harness import EndToEndQualificationHarness
from agents.external_staging_runtime.identity import external_staging_identity
from agents.external_staging_runtime.runtime_health import RuntimeHealthHarness


def test_runtime_health_structural_and_pending() -> None:
    rep = RuntimeHealthHarness(external_staging_identity()).assess()
    assert rep.passed is True
    assert rep.structural_health_count == 4
    assert rep.external_resources_health_pending == 8
    assert rep.overall_status == "PLAN_ONLY"
    assert rep.is_production is False
    assert rep.real_apply_allowed is False


def test_runtime_health_no_production_leakage() -> None:
    rep = RuntimeHealthHarness(external_staging_identity()).assess()
    assert all(r.is_production is False for r in rep.resource_health)
    assert all(r.status == "PENDING_EXTERNAL_STAGING_RESOURCE" for r in rep.resource_health)


def test_e2e_plan_passes_structurally() -> None:
    plan = EndToEndQualificationHarness(external_staging_identity()).build_plan()
    assert plan.passed is True
    assert len(plan.steps) == 6
    assert plan.terminal_state == TERMINAL_STATE
    assert plan.is_production is False
    assert plan.real_apply_allowed is False


def test_e2e_steps_all_structural_ok() -> None:
    plan = EndToEndQualificationHarness(external_staging_identity()).build_plan()
    for s in plan.steps:
        assert s.status == "PLAN_ONLY_STRUCTURAL_OK"
    names = [s.name for s in plan.steps]
    assert names == [
        "environment_classification",
        "nine_domain_isolation_audit",
        "thirteen_runtime_qualification",
        "runtime_health",
        "change_control_gate",
        "evidence_chain",
    ]


def test_e2e_evidence_hash_deterministic() -> None:
    h1 = EndToEndQualificationHarness(external_staging_identity()).build_plan().evidence_hash
    h2 = EndToEndQualificationHarness(external_staging_identity()).build_plan().evidence_hash
    assert h1 == h2
    assert len(h1) == 64  # SHA-256

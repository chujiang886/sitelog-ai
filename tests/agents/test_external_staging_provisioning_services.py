"""Phase 3.9.12 —— 供给层服务模块测试（Tasks 29/30/31，fail-closed）。

覆盖：安全校验（凭据扫描 / API 契约 / 环境身份）/ 成本护栏 StagingCostGuard /
供给审计类别（自包含 12 类，不污染企业枚举）/ API 契约一致性。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_provisioning import (  # noqa: E402
    ExternalStagingProvisioningSecurityValidator,
    StagingCostGuard,
    DEFAULT_COST_BUDGET,
    PROVISIONING_AUDIT_CATEGORIES,
    build_provisioning_audit_event,
    build_api_contract,
)


# --------------------------------------------------------------------------
# 安全校验（T29）
# --------------------------------------------------------------------------
def test_security_no_secret_ok():
    v = ExternalStagingProvisioningSecurityValidator()
    v.assert_no_secret({"ext-staging-database": {"iac_module": "infrastructure/staging/database.tf"}})


def test_security_detects_secret():
    v = ExternalStagingProvisioningSecurityValidator()
    with pytest.raises(Exception):
        v.assert_no_secret({"secret": "password=leaked123"})


def test_security_api_contract_valid():
    v = ExternalStagingProvisioningSecurityValidator()
    assert v.validate_api_contract(build_api_contract()) is True


def test_security_env_identity_must_be_false():
    v = ExternalStagingProvisioningSecurityValidator()
    with pytest.raises(ValueError):
        v.validate_environment_identity({"production": True})


def test_security_full_check_pass():
    v = ExternalStagingProvisioningSecurityValidator()
    res = v.full_check(
        bom_mapping={"ext-staging-database": {"iac_module": "x"}},
        environment_identity={"production": False},
    )
    assert res["all_ok"] is True


# --------------------------------------------------------------------------
# 成本护栏（T30）
# --------------------------------------------------------------------------
def test_cost_guard_within_budget():
    g = StagingCostGuard(budget=DEFAULT_COST_BUDGET)
    res = g.check()
    assert res.within_budget is True
    assert res.estimated_min <= DEFAULT_COST_BUDGET


def test_cost_guard_over_budget_blocks():
    g = StagingCostGuard(budget=1)  # 极小预算必然超
    res = g.check()
    assert res.within_budget is False
    with pytest.raises(ValueError):
        g.assert_within_budget()


def test_cost_guard_estimate_min_positive():
    g = StagingCostGuard()
    assert g.estimate_min() > 0


# --------------------------------------------------------------------------
# 供给审计（T31，自包含 12 类）
# --------------------------------------------------------------------------
def test_audit_categories_count_12():
    assert len(PROVISIONING_AUDIT_CATEGORIES) == 12


def test_audit_event_build_ok():
    ev = build_provisioning_audit_event(
        record_id="r1",
        actor_kind="USER",
        actor_id="u1",
        category="external_staging_provisioning_runbook_viewed",
        action="view",
        target="docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md",
    )
    d = ev.to_dict()
    assert d["actor_kind"] == "USER"
    assert d["contains_real_secret"] is False
    assert "engineering_enabled=false" in d["red_line_marker"]


def test_audit_event_rejects_bad_category():
    with pytest.raises(ValueError):
        build_provisioning_audit_event(
            record_id="r2", actor_kind="USER", actor_id="u1", category="bogus"
        )


def test_audit_event_rejects_bad_actor():
    with pytest.raises(ValueError):
        build_provisioning_audit_event(
            record_id="r3",
            actor_kind="ROBOT",
            actor_id="x",
            category="external_staging_provisioning_runbook_viewed",
        )


def test_audit_does_not_mutate_enterprise_enum():
    # 自包含类别不应出现在企业级 AuditActionCategory（保护冻结账本 129）。
    from agents.enterprise.audit import AuditActionCategory

    enum_names = {m.name for m in AuditActionCategory}
    overlap = PROVISIONING_AUDIT_CATEGORIES & enum_names
    assert overlap == set(), f"3.9.12 类别不应污染企业枚举：{overlap}"


# --------------------------------------------------------------------------
# API 契约一致性（T19/T28）
# --------------------------------------------------------------------------
def test_api_contract_seven_routes():
    c = build_api_contract()
    assert c["total_routes"] == 7
    assert set(c["allowed_actions"]) == {"read", "human_record"}
    assert "provision" in c["forbidden_actions"]
    assert "apply" in c["forbidden_actions"]
    assert "activate" in c["forbidden_actions"]
    assert set(c["operator_gate_states"]) == {
        "blocked",
        "pending_human_input",
        "ready_for_human_provisioning_review",
    }
    assert c["forbidden_provisioning_modes"] == ["auto", "production"]

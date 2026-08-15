"""Phase 3.9.12 —— External Staging Provisioning & Operator Readiness 全量 fail-closed 测试矩阵（Tasks 18-19）。

覆盖：terminal state / 供给执行模式 / Operator Gate 3 态 / 供给步状态 / 禁止态断言 /
8 资源 BOM（诚实 PENDING）/ Dry-run Guard（IaC 扫描 + 适配器契约）/ Operator Gate 评估 /
供给包（确定性 + 无真实密钥）/ API 契约 / validate 脚本。

规则：所有测试 fail-closed；缺真实资源必须回落 pending，绝不伪造验证；
绝不出现 GO / APPROVED / PRODUCTION_READY / AUTO / PRODUCTION。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_provisioning import (  # noqa: E402
    EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE,
    ExternalStagingProvisioningError,
    OperatorGateStatus,
    ProvisioningPlan,
    ProvisioningStepStatus,
    StagingProvisioningExecutionMode,
    ProvisioningBom,
    IacDryRunGuard,
    ExternalStagingProvisioningOperatorGate,
    OperatorGateResult,
    ExternalStagingProvisioningValidator,
    build_provisioning_package,
    package_hash,
    build_api_contract,
)
from agents.external_staging_provisioning.models import (  # noqa: E402
    assert_not_forbidden_provisioning_state,
)
from agents.external_staging_qualification.models import (  # noqa: E402
    RESOURCE_TYPE_ORDER,
    ResourceType,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BRANCH = "feat/phase3.9.12-external-staging-provisioning-operator-readiness"
PKG_PATH = (
    REPO_ROOT
    / ".ai"
    / "staging"
    / "external_staging_provisioning_operator_package.json"
)


# --------------------------------------------------------------------------
# 1) 常量 / 模型
# --------------------------------------------------------------------------
def test_terminal_state_constant():
    assert EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE == (
        "EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO"
    )


def test_provisioning_execution_modes_no_real():
    for m in StagingProvisioningExecutionMode:
        assert m.is_real_provisioning is False


def test_provisioning_execution_modes_exhaustive():
    vals = {m.value for m in StagingProvisioningExecutionMode}
    assert vals == {"plan", "validate", "dry_run", "human_authorized_apply"}


def test_operator_gate_status_3_state_only():
    vals = {s.value for s in OperatorGateStatus}
    assert vals == {
        "blocked",
        "pending_human_input",
        "ready_for_human_provisioning_review",
    }
    # 禁 GO/APPROVED/PRODUCTION_READY
    assert "go" not in vals
    assert "approved" not in vals
    assert "production_ready" not in vals
    for s in OperatorGateStatus:
        assert s.is_go_or_approved is False


def test_assert_forbidden_provisioning_state_raises():
    for bad in ("go", "approved", "production_ready", "auto", "production", "provisioned"):
        with pytest.raises(ExternalStagingProvisioningError):
            assert_not_forbidden_provisioning_state(bad)


def test_assert_forbidden_provisioning_state_ok():
    assert_not_forbidden_provisioning_state("plan_only")
    assert_not_forbidden_provisioning_state("pending_external_staging_resource")


def test_provisioning_step_status_enum_no_real():
    for st in ProvisioningStepStatus:
        assert st.is_real_execution is False


def test_build_default_plan_step_count():
    plan = ProvisioningPlan.build_default()
    assert len(plan.steps) == 8


def test_plan_no_real_execution():
    plan = ProvisioningPlan.build_default()
    assert plan.summary()["any_real_execution"] is False
    assert plan.summary()["all_plan_only"] is True


def test_plan_step_statuses_fail_closed():
    plan = ProvisioningPlan.build_default()
    for s in plan.steps:
        assert s.status.value not in (
            "go",
            "approved",
            "production_ready",
            "executed",
            "provisioned",
            "deployed_production",
        )


# --------------------------------------------------------------------------
# 2) 8 资源 BOM（诚实 PENDING）
# --------------------------------------------------------------------------
def test_bom_entry_count():
    bom = ProvisioningBom.build_default()
    assert len(bom.entries) == 8


def test_bom_all_pending():
    bom = ProvisioningBom.build_default()
    assert bom.all_pending() is True
    assert bom.summary()["pending"] == 8


def test_bom_assert_all_pending_ok():
    ProvisioningBom.build_default().assert_all_pending()  # 不抛


def test_bom_resource_types_match_order():
    bom = ProvisioningBom.build_default()
    assert [e.resource_type for e in bom.entries] == list(RESOURCE_TYPE_ORDER)


def test_bom_owner_roles_present():
    bom = ProvisioningBom.build_default()
    for e in bom.entries:
        assert e.owner_role in (
            "production-owner",
            "security-owner",
            "release-manager",
        )


# --------------------------------------------------------------------------
# 3) Dry-run Guard（IaC 扫描 + 适配器契约）
# --------------------------------------------------------------------------
def test_iac_scan_passes():
    result = IacDryRunGuard().evaluate()
    assert result.all_ok is True
    assert result.credential_leak_hits == ()
    assert len(result.count_zero_modules) == 4
    assert result.default_provider == "tencentcloud"


def test_iac_scan_no_leak_hits():
    from agents.external_staging_provisioning.dry_run_guard import scan_iac_directory

    result = scan_iac_directory(REPO_ROOT / "infrastructure" / "staging")
    assert result.credential_leak_hits == ()


def test_adapter_contract_reused_honest():
    # 复用 execution adapters：8 资源仍诚实 PENDING
    from agents.external_staging_execution.adapters import (
        adapters_contract_test_all_pass,
        probe_all,
    )

    assert len(probe_all()) == 8
    assert adapters_contract_test_all_pass() is True


# --------------------------------------------------------------------------
# 4) Operator Gate（独立 3 态裁决）
# --------------------------------------------------------------------------
def _gate_kwargs(**overrides):
    base = dict(
        bom=ProvisioningBom.build_default(),
        environment_identity={"production": False},
        iac_dry_run_ok=True,
        adapter_contract_ok=True,
        engineering_enabled=False,
        security_ok=True,
        regression_ok=True,
        repo_clean=True,
        human_input_required=True,
    )
    base.update(overrides)
    return base


def test_operator_gate_evaluate_returns_3_state():
    gate = ExternalStagingProvisioningOperatorGate()
    res = gate.evaluate(**_gate_kwargs())
    assert isinstance(res, OperatorGateResult)
    assert res.status in set(OperatorGateStatus)


def test_operator_gate_pending_human_input_when_inputs_required():
    res = ExternalStagingProvisioningOperatorGate().evaluate(**_gate_kwargs())
    # 默认 human_input_required=True → PENDING_HUMAN_INPUT（非 GO/APPROVED）
    assert res.status is OperatorGateStatus.PENDING_HUMAN_INPUT


def test_operator_gate_ready_when_no_inputs():
    res = ExternalStagingProvisioningOperatorGate().evaluate(
        **_gate_kwargs(human_input_required=False)
    )
    assert res.status is OperatorGateStatus.READY_FOR_HUMAN_PROVISIONING_REVIEW


def test_operator_gate_blocked_on_iac_fail():
    res = ExternalStagingProvisioningOperatorGate().evaluate(
        **_gate_kwargs(iac_dry_run_ok=False)
    )
    assert res.status is OperatorGateStatus.BLOCKED


def test_operator_gate_blocked_on_engineering_enabled():
    res = ExternalStagingProvisioningOperatorGate().evaluate(
        **_gate_kwargs(engineering_enabled=True)
    )
    assert res.status is OperatorGateStatus.BLOCKED


def test_operator_gate_never_go_or_approved():
    gate = ExternalStagingProvisioningOperatorGate()
    for human in (True, False):
        res = gate.evaluate(**_gate_kwargs(human_input_required=human))
        assert res.status.value not in ("go", "approved", "production_ready", "ready")


# --------------------------------------------------------------------------
# 5) Validator
# --------------------------------------------------------------------------
def test_validator_validate_returns_gate():
    v = ExternalStagingProvisioningValidator()
    res = v.validate()
    assert isinstance(res, OperatorGateResult)
    assert res.status in set(OperatorGateStatus)


def test_validator_assert_operator_ready_pending_ok():
    # PENDING_HUMAN_INPUT 是合法就绪态（非 BLOCKED），但 assert_operator_ready 要求
    # READY_FOR_HUMAN_PROVISIONING_REVIEW；PENDING 应抛（fail-closed 显式）。
    v = ExternalStagingProvisioningValidator()
    with pytest.raises(ExternalStagingProvisioningError):
        v.assert_operator_ready()


# --------------------------------------------------------------------------
# 6) 供给包（确定性 + 无真实密钥）
# --------------------------------------------------------------------------
def test_build_package_deterministic():
    import datetime as _dt

    bom = ProvisioningBom.build_default()
    identity = {"production": False}
    p1 = build_provisioning_package(
        source_commit="abc123", environment_identity=identity, bom=bom
    )
    p2 = build_provisioning_package(
        source_commit="abc123", environment_identity=identity, bom=bom
    )
    assert p1["package_hash"] == p2["package_hash"]


def test_build_package_no_secret_no_go():
    bom = ProvisioningBom.build_default()
    p = build_provisioning_package(
        source_commit="abc123", environment_identity={"production": False}, bom=bom
    )
    assert p["contains_real_secret"] is False
    assert p["production_activation_prohibited"] is True
    assert p["engineering_enabled"] is False
    assert p["phase"] == "3.9.12"
    assert p["terminal_state"] == EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE
    assert len(p["pending_resources"]) == 8
    # 重算 hash 一致
    assert package_hash(p) == p["package_hash"]


# --------------------------------------------------------------------------
# 7) API 契约
# --------------------------------------------------------------------------
def test_api_contract_no_execution_endpoint():
    c = build_api_contract()
    assert c["no_execution_endpoint"] is True
    assert c["engineering_enabled"] is False
    assert c["phase"] == "3.9.12"
    for r in c["routes"]:
        assert r["action"] in ("read", "human_record")
        assert r["performs_execution"] is False
    assert "provision" in c["forbidden_actions"]
    assert "apply" in c["forbidden_actions"]
    assert "activate" in c["forbidden_actions"]
    assert set(c["operator_gate_states"]) == {
        "blocked",
        "pending_human_input",
        "ready_for_human_provisioning_review",
    }
    assert c["forbidden_provisioning_modes"] == ["auto", "production"]


# --------------------------------------------------------------------------
# 8) validate 脚本（fail-closed PASS）
# --------------------------------------------------------------------------
def test_validate_script_pass():
    if not PKG_PATH.is_file():
        pytest.skip("package json not generated; run generator first")
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_external_staging_provisioning.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "[PASS]" in r.stdout

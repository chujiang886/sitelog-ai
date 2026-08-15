"""Phase 3.9.11 —— External Staging Execution & Qualification 全量 fail-closed 测试矩阵（Task 44）。

覆盖：terminal state / environment / plan / step statuses / forbidden-state 断言 /
8 资源 fake adapter（诚实 PENDING）/ preflight / pipeline 证据链 / 执行闸门 /
执行包（确定性 + 无真实密钥）/ 安全校验 / API 契约 / 分支完整性脚本。

规则：所有测试 fail-closed；缺真实资源必须回落 pending，绝不伪造验证；
绝不出现 GO / APPROVED / PRODUCTION_READY。
"""

from __future__ import annotations

import json
import subprocess
import sys
import os
import re
from pathlib import Path

import pytest

# 允许以 agents 包导入（test runner 通常已注入 repo 根）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_execution import (  # noqa: E402
    EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE,
    EXTERNAL_STAGING_ENVIRONMENT,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStepKind,
    ExecutionStepStatus,
    ExternalStagingExecutionError,
    assert_not_forbidden_step_state,
    build_default_execution_plan,
    AdapterProbeResult,
    ExternalStagingExecutionAdapter,
    adapters_contract_test_all_pass,
    assert_no_real_execution_claimed,
    probe_all,
    ExecutionEvidenceChain,
    ExecutionEvidenceItem,
    ExecutionPipeline,
    ExternalStagingExecutionGate,
    PreflightReport,
    run_preflight,
    build_execution_package,
    package_hash,
    load_external_staging_identity,
    build_api_contract,
    EXPECTED_TOTAL_ROUTES,
    ExternalStagingExecutionSecurityValidator,
    ExecutionSecurityCheckResult,
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
)
from agents.external_staging_qualification.models import (  # noqa: E402
    ExternalStagingResource,
    ExternalStagingResourceRegistry,
    GateStatus,
    RESOURCE_TYPE_ORDER,
    ResourceType,
)
from agents.external_staging_qualification.credential_scanner import (  # noqa: E402
    assert_no_credential_leak,
    CredentialLeakError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BRANCH = "feat/phase3.9.11-external-staging-execution-qualification"


# --------------------------------------------------------------------------
# 1) 模型 / 常量
# --------------------------------------------------------------------------
def test_terminal_state_constant():
    assert EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE == (
        "EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO"
    )


def test_environment_is_external_staging():
    assert EXTERNAL_STAGING_ENVIRONMENT.value == "external_staging"


def test_build_default_plan_step_count():
    plan = build_default_execution_plan()
    assert len(plan.steps) == 10


def test_plan_no_real_execution():
    plan = build_default_execution_plan()
    assert plan.summary()["any_real_execution"] is False


def test_plan_step_statuses_all_fail_closed():
    plan = build_default_execution_plan()
    for s in plan.steps:
        assert s.status.value not in (
            "go",
            "approved",
            "production_ready",
            "executed",
            "deployed_production",
        )
        assert s.status.is_real_execution is False


def test_execution_step_status_enum_no_real():
    for st in ExecutionStepStatus:
        assert st.is_real_execution is False


def test_assert_forbidden_step_state_raises():
    with pytest.raises(ExternalStagingExecutionError):
        assert_not_forbidden_step_state("go")


def test_assert_forbidden_step_state_ok():
    # 合法态不应抛
    assert_not_forbidden_step_state("plan_only")
    assert_not_forbidden_step_state("pending_external_staging_resource")


def test_execution_step_to_dict_no_secret():
    d = ExecutionStep(
        ExecutionStepKind.DEPLOY, ExecutionStepStatus.PLAN_ONLY
    ).to_dict()
    assert d["contains_real_secret"] is False
    assert d["is_real_execution"] is False


# --------------------------------------------------------------------------
# 2) 8 资源 Fake Adapter（诚实 PENDING）
# --------------------------------------------------------------------------
def test_all_8_resources_probed():
    assert len(probe_all()) == 8


def test_probe_result_honest():
    r = probe_all()[0]
    assert r.status == "pending_external_staging_resource"
    assert r.configured is False
    assert r.verified is False
    assert r.contract_test_passed is True


def test_adapter_contract_test_all_pass():
    assert adapters_contract_test_all_pass() is True


def test_adapter_contract_test_single():
    a = ExternalStagingExecutionAdapter(ResourceType.DATABASE)
    assert a.contract_test() is True


def test_assert_no_real_execution_claimed_ok():
    assert_no_real_execution_claimed(probe_all())  # 不抛


def test_assert_no_real_execution_claimed_raises():
    bad = [
        AdapterProbeResult(
            resource_type="database",
            configured=True,
            verified=True,
            status="qualified_external_staging",
        )
    ]
    with pytest.raises(ExternalStagingExecutionError):
        assert_no_real_execution_claimed(bad)


def test_adapter_result_to_dict_no_secret():
    d = probe_all()[0].to_dict()
    assert d["contains_real_secret"] is False
    assert d["is_real_execution"] is False


# --------------------------------------------------------------------------
# 3) Preflight
# --------------------------------------------------------------------------
def _preflight_kwargs(**overrides):
    base = dict(
        environment_identity={"production": False},
        registry_resource_ids=tuple(f"ext-staging-{t.value}" for t in RESOURCE_TYPE_ORDER),
        current_branch=EXPECTED_BRANCH,
        audit_total=129,
        repo_clean=True,
    )
    base.update(overrides)
    return base


def test_preflight_pass():
    rep = run_preflight(**_preflight_kwargs())
    assert isinstance(rep, PreflightReport)
    assert rep.passed is True


def test_preflight_wrong_branch_fail():
    rep = run_preflight(**_preflight_kwargs(current_branch="main"))
    assert rep.passed is False


def test_preflight_production_identity_fail():
    rep = run_preflight(**_preflight_kwargs(environment_identity={"production": True}))
    assert rep.passed is False


def test_preflight_audit_drift_fail():
    rep = run_preflight(**_preflight_kwargs(audit_total=130))
    assert rep.passed is False


def test_preflight_repo_dirty_fail():
    rep = run_preflight(**_preflight_kwargs(repo_clean=False))
    assert rep.passed is False


def test_preflight_report_to_dict():
    rep = run_preflight(**_preflight_kwargs())
    d = rep.to_dict()
    assert "passed" in d and "checks" in d
    assert all("name" in c and "passed" in c for c in d["checks"])


# --------------------------------------------------------------------------
# 4) Pipeline / 证据链
# --------------------------------------------------------------------------
def test_pipeline_execute_plan():
    plan = ExecutionPipeline().execute_plan()
    assert len(plan.steps) == 10


def test_pipeline_evidence_count():
    chain = ExecutionPipeline().run_evidence_chain()
    # 1 preflight + 1 deploy + 8 resources + 1 failure + 1 recovery + 1 rollback = 13
    assert chain.summary()["count"] == 13


def test_pipeline_evidence_no_secret():
    chain = ExecutionPipeline().run_evidence_chain()
    assert chain.summary()["none_contains_secret"] is True


def test_pipeline_evidence_all_external_staging():
    chain = ExecutionPipeline().run_evidence_chain()
    assert chain.summary()["all_scope_external_staging"] is True


def test_pipeline_evidence_chain_hash_stable():
    c1 = ExecutionPipeline().run_evidence_chain()
    c2 = ExecutionPipeline().run_evidence_chain()
    assert c1.chain_hash() == c2.chain_hash()


def test_evidence_item_hash_stable():
    i = ExecutionEvidenceItem(
        evidence_id="x", step_kind="preflight", evidence_type="contract_test",
        environment="external_staging", actor="AI", verification_status="pending", detail="d",
    )
    assert i.compute_hash() == i.compute_hash()


# --------------------------------------------------------------------------
# 5) 执行闸门
# --------------------------------------------------------------------------
def _build_gate_inputs():
    ident = load_external_staging_identity()
    registry = ExternalStagingResourceRegistry.build_default()
    plan = build_default_execution_plan()
    chain = ExecutionPipeline().run_evidence_chain()
    pending = tuple(r.resource_id for r in registry.resources)
    return dict(
        plan=plan, evidence_chain=chain, environment_identity=ident.to_dict(),
        registry=registry, additional_pending_resources=pending,
        human_verification_required=True,
    )


def test_gate_pending_when_resources_pending():
    gate = ExternalStagingExecutionGate().evaluate(**_build_gate_inputs())
    assert gate.status == GateStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_gate_blocked_when_production_identity():
    inp = _build_gate_inputs()
    inp["environment_identity"] = {"production": True}
    gate = ExternalStagingExecutionGate().evaluate(**inp)
    assert gate.status == GateStatus.BLOCKED


def test_gate_credential_check_reads_real_references():
    """闸门应从登记簿读取真实凭据引用并纳入扫描（契约点）。

    说明：qualification 层的 ``assert_no_credential_leak`` 仅扫描 **top-level
    敏感键**；本闸门传入的 ``ref_map`` 为 ``resource_id -> {credential_reference,
    source_reference}`` 嵌套结构，嵌套值不被递归扫描——这是与 3.9.10 资格闸门
    共享的既有局限（见 test_credential_scanner_nested_value_not_scanned）。
    本测试仅验证：闸门确实把登记簿的真实引用喂给扫描器、且诚实引用下该项 PASS。
    """
    gate = ExternalStagingExecutionGate().evaluate(**_build_gate_inputs())
    names = {c.name for c in gate.checks}
    assert "credential_reference_safety" in names
    cred = next(c for c in gate.checks if c.name == "credential_reference_safety")
    assert cred.passed is True


def test_credential_scanner_text_leak_detected():
    """凭据扫描器在 text= 模式下应捕获明文泄漏（如 password=... 模式）。"""
    with pytest.raises(CredentialLeakError):
        assert_no_credential_leak(text="password=leaked-secret")


def test_credential_scanner_mapping_leak_detected():
    """凭据扫描器在 flat 敏感键 + 值似明文 Secret 时应捕获泄漏。

    ``_looks_like_raw_secret`` 仅对 ``sk-...`` 等特定形态返回 True，故这里用
    一个能通过启发式的测试值，验证 scan_mapping 的 top-level 敏感键路径真实工作。
    """
    with pytest.raises(CredentialLeakError):
        assert_no_credential_leak(mapping={"password": "sk-ABCDEFGHIJKLMNOPQRST"})


def test_credential_scanner_nested_value_not_scanned():
    """显式记录共享局限：嵌套值不被递归扫描（与 3.9.10 资格闸门同款）。

    闸门传入的 ref_map 顶层键为 ``credential_reference``/``source_reference``
    （不在 _SENSITIVE_KEYS），其嵌套值不被扫描，故不抛异常。此测试将局限
    固化为已知行为，避免将来误判为回归。
    """
    # 不抛：顶层键非敏感键 + 嵌套值不递归扫描
    assert_no_credential_leak(mapping={"credential_reference": "password=leaked-secret"})


def test_gate_blocked_on_repo_pollution():
    """仓库不清洁 / 安全未过 / 回归失败 → BLOCKED（闸门真实拦截路径）。"""
    inp = _build_gate_inputs()
    inp["repo_clean"] = False
    gate = ExternalStagingExecutionGate().evaluate(**inp)
    assert gate.status == GateStatus.BLOCKED
    assert any(c.name == "repository_clean" and not c.passed for c in gate.checks)

    inp2 = _build_gate_inputs()
    inp2["security_ok"] = False
    gate2 = ExternalStagingExecutionGate().evaluate(**inp2)
    assert gate2.status == GateStatus.BLOCKED

    inp3 = _build_gate_inputs()
    inp3["regression_ok"] = False
    gate3 = ExternalStagingExecutionGate().evaluate(**inp3)
    assert gate3.status == GateStatus.BLOCKED


def test_gate_never_go():
    for human in (True, False):
        inp = _build_gate_inputs()
        inp["human_verification_required"] = human
        gate = ExternalStagingExecutionGate().evaluate(**inp)
        assert gate.status.value not in ("go", "approved", "production_ready")
        assert gate.status != GateStatus.READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW or human is False


def test_gate_passed_field_true_for_pending():
    gate = ExternalStagingExecutionGate().evaluate(**_build_gate_inputs())
    assert gate.to_dict()["passed"] is True


def test_gate_no_real_execution_check_present():
    gate = ExternalStagingExecutionGate().evaluate(**_build_gate_inputs())
    names = {c.name for c in gate.checks}
    assert "no_real_execution_claimed" in names
    assert "environment_not_production" in names


# --------------------------------------------------------------------------
# 6) 执行包（确定性 + 无真实密钥）
# --------------------------------------------------------------------------
def _build_package():
    ident = load_external_staging_identity()
    registry = ExternalStagingResourceRegistry.build_default()
    plan = build_default_execution_plan()
    chain = ExecutionPipeline().run_evidence_chain()
    gate = ExternalStagingExecutionGate().evaluate(
        plan=plan, evidence_chain=chain, environment_identity=ident.to_dict(),
        registry=registry, additional_pending_resources=tuple(r.resource_id for r in registry.resources),
        human_verification_required=True,
    )
    pending = tuple(r.resource_id for r in registry.resources)
    return build_execution_package(
        pending_resources=pending,
        source_commit="9b0970a", environment_identity=ident, plan=plan,
        evidence_chain=chain, gate=gate, baseline_commit="2f4a9838",
        evidence_source_commit="9b0970a", package_generated_from_commit="9b0970a",
    )


def test_package_deterministic():
    p1 = _build_package()
    p2 = _build_package()
    assert p1["package_hash"] == p2["package_hash"]


def test_package_hash_recompute():
    p = _build_package()
    assert package_hash(p) == p["package_hash"]


def test_package_no_real_secret():
    assert _build_package()["contains_real_secret"] is False


def test_package_production_activation_prohibited():
    assert _build_package()["production_activation_prohibited"] is True


def test_package_engineering_enabled_false():
    assert _build_package()["engineering_enabled"] is False


def test_package_gate_pending():
    assert _build_package()["gate"]["status"] == "pending_external_staging_resource"


def test_package_pending_resources_8():
    assert len(_build_package()["pending_resources"]) == 8


def test_package_terminal_state():
    assert _build_package()["terminal_state"] == EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE


def test_package_environment_not_production():
    assert _build_package()["environment_identity"]["production"] is False


def test_package_execution_plan_summary_no_real():
    p = _build_package()
    assert p["execution_plan_summary"]["any_real_execution"] is False


# --------------------------------------------------------------------------
# 7) 安全校验
# --------------------------------------------------------------------------
@pytest.fixture
def validator():
    return ExternalStagingExecutionSecurityValidator()


def test_security_read_ok(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="read")
    assert isinstance(r, ExecutionSecurityCheckResult)
    assert r.passed is True


def test_security_human_record_ok(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="human_record")
    assert r.passed is True


def test_security_execute_rejected(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="execute")
    assert r.passed is False


def test_security_deploy_rejected(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="deploy")
    assert r.passed is False


def test_security_activate_rejected(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="activate")
    assert r.passed is False


def test_security_wrong_scope_rejected(validator):
    r = validator.validate_request(scope="production", actor="a", action="read")
    assert r.passed is False


def test_security_unknown_action_rejected(validator):
    r = validator.validate_request(scope="external_staging", actor="a", action="weird")
    assert r.passed is False  # fail-closed 默认拒绝


def test_security_production_action_flag_rejected(validator):
    r = validator.validate_request(
        scope="external_staging", actor="a", action="read", is_production_action=True
    )
    assert r.passed is False


def test_security_allowed_actions_set():
    assert set(ALLOWED_ACTIONS) == {"read", "human_record"}


def test_security_forbidden_actions_set():
    assert "execute" in FORBIDDEN_ACTIONS
    assert "deploy" in FORBIDDEN_ACTIONS
    assert "activate" in FORBIDDEN_ACTIONS


# --------------------------------------------------------------------------
# 8) API 契约
# --------------------------------------------------------------------------
def test_api_contract_routes_count():
    c = build_api_contract()
    assert c["total_routes"] == EXPECTED_TOTAL_ROUTES == 7


def test_api_contract_no_exec_endpoint():
    assert build_api_contract()["no_execution_endpoint"] is True


def test_api_contract_all_read_or_human_record():
    c = build_api_contract()
    for r in c["routes"]:
        assert r["action"] in ALLOWED_ACTIONS


def test_api_contract_no_forbidden_action_in_routes():
    c = build_api_contract()
    for r in c["routes"]:
        assert r["action"] not in FORBIDDEN_ACTIONS


def test_api_contract_no_performs_execution():
    c = build_api_contract()
    assert all(r["performs_execution"] is False for r in c["routes"])


def test_api_contract_production_false():
    c = build_api_contract()
    assert c["production"] is False
    assert c["production_activation_prohibited"] is True
    assert c["engineering_enabled"] is False


# --------------------------------------------------------------------------
# 9) 分支完整性脚本（在合法分支上应 PASS）
# --------------------------------------------------------------------------
def test_branch_integrity_script_passes():
    # 阶段无关：依据当前分支名派生对应 phase 编号，运行该 phase 专属的 Branch Integrity 脚本。
    # 意图（Branch Integrity 守约）保留，但不绑定具体 Phase 编号——3.9.11 / 3.9.12 分支均能正确校验
    # （治理 §4 冲突裁决延续 3.9.11 §8 范式：硬编码分支名改派生校验）。
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    m = re.search(r"phase3\.9\.(\d+)-", branch)
    assert m, f"无法从分支名派生 phase 编号：{branch}"
    phase_tag = "39" + m.group(1)  # 3.9.11 -> 3911, 3.9.12 -> 3912
    script = os.path.join(REPO_ROOT, f"scripts/check_phase{phase_tag}_branch_integrity.py")
    assert os.path.exists(script), f"缺少分支完整性脚本：{script}"
    result = subprocess.run(
        [sys.executable, script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr

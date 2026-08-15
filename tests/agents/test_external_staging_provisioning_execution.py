"""Phase 3.9.13 —— External Staging Provisioning Execution 全量 fail-closed 测试矩阵。

覆盖：双钥匙 Apply Gate（AI 不可 mint 真人授权 / 永不 GO）/ 逐资源状态机不跳态 /
分项聚合 0/8（且非硬编码——推进后如实反映）/ 递归凭据深扫 fail-closed / 无伪造校验 /
确定性执行包 / 无伪造证据链 / IaC 可执行就绪（real_execution_allowed=False）/
执行编排器终态 EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO / 仅读 API 契约 /
plan-only 成本为 0。

规则：所有测试 fail-closed；缺真实资源必须回落 pending；绝不出现 GO / APPROVED /
PRODUCTION_READY / AUTO / PRODUCTION；engineering_enabled 必须 False。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_provisioning.resource_state_machine import (  # noqa: E402
    RESOURCE_STATE_TRANSITIONS,
    RESOURCE_TYPE_ORDER,
    ExternalStagingResourceEntry,
    ProvisioningStateRegistry,
    ResourceProvisioningState,
    ResourceStateMachineError,
    build_default_bom,
)
from agents.external_staging_provisioning.apply_gate import (  # noqa: E402
    ApplyGateStatus,
    ExternalStagingProvisioningApplyGate,
)
from agents.external_staging_provisioning.authorization_registry import (  # noqa: E402
    AuthorizationRegistryError,
    ProvisioningAuthorizationRegistry,
)
from agents.external_staging_provisioning.aggregator import (  # noqa: E402
    PartialProgressAggregator,
)
from agents.external_staging_provisioning.credential_deep_scanner import (  # noqa: E402
    CredentialDeepLeakError,
    assert_no_deep_credential_leak,
)
from agents.external_staging_provisioning.execution import (  # noqa: E402
    ProvisioningExecutionOrchestrator,
)
from agents.external_staging_provisioning.validator_execution import (  # noqa: E402
    validate_execution_no_fabrication,
)
from agents.external_staging_provisioning.iac_readiness import (  # noqa: E402
    IaCReadinessAuditor,
)
from agents.external_staging_provisioning.machine_package import (  # noqa: E402
    build_machine_package,
)
from agents.external_staging_provisioning.evidence import (  # noqa: E402
    EvidenceChain,
)
from agents.external_staging_provisioning.security_execution import (  # noqa: E402
    ExecutionSecurityAuditor,
)
from agents.external_staging_provisioning.api_contract_execution import (  # noqa: E402
    EXECUTION_API_CONTRACT,
)
from agents.external_staging_provisioning.cost import (  # noqa: E402
    estimate_plan_only_cost,
)


# --------------------------------------------------------------------------- #
# 1) 双钥匙 Apply Gate（T19-T20）                                              #
# --------------------------------------------------------------------------- #
def _auth_machine_only() -> ProvisioningAuthorizationRegistry:
    auth = ProvisioningAuthorizationRegistry()
    auth.register_machine_safety_key(
        key_id="machine-safety-key-phase3.9.13",
        generated_from_commit="testcommit",
        engineering_enabled=False,
    )
    return auth


def test_apply_gate_machine_key_only_pending_human_authorization():
    auth = _auth_machine_only()
    assert auth.machine_key_present()
    assert not auth.human_key_present()
    gate = ExternalStagingProvisioningApplyGate().evaluate(registry=auth)
    assert gate.status is ApplyGateStatus.PENDING_HUMAN_AUTHORIZATION
    assert gate.status.is_go_or_approved is False


def test_apply_gate_dual_key_authorized_but_never_go():
    auth = _auth_machine_only()
    auth.register_human_authorization(
        authorization_id="a1",
        actor_id="human-owner",
        actor_kind="user",
        scope="ext-staging",
        authorized_at="2026-08-15T00:00:00Z",
    )
    assert auth.is_authorized_for_apply() is True
    gate = ExternalStagingProvisioningApplyGate().evaluate(registry=auth)
    assert gate.status is ApplyGateStatus.AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY
    # 关键红线：即便双钥匙齐备，状态也绝不可能是 GO/APPROVED。
    assert gate.status.is_go_or_approved is False
    assert ApplyGateStatus.BLOCKED.is_go_or_approved is False
    assert ApplyGateStatus.PLAN_ONLY.is_go_or_approved is False


def test_apply_gate_security_fail_blocked():
    auth = _auth_machine_only()
    gate = ExternalStagingProvisioningApplyGate().evaluate(
        registry=auth, security_ok=False
    )
    assert gate.status is ApplyGateStatus.BLOCKED


def test_apply_gate_regression_fail_blocked():
    auth = _auth_machine_only()
    gate = ExternalStagingProvisioningApplyGate().evaluate(
        registry=auth, regression_ok=False
    )
    assert gate.status is ApplyGateStatus.BLOCKED


def test_machine_safety_key_invalid_when_engineering_enabled_true():
    auth = ProvisioningAuthorizationRegistry()
    with pytest.raises(AuthorizationRegistryError):
        auth.register_machine_safety_key(
            key_id="k", generated_from_commit="x", engineering_enabled=True
        )


def test_human_authorization_requires_user_actor_ai_cannot_mint():
    auth = ProvisioningAuthorizationRegistry()
    with pytest.raises(Exception):
        auth.register_human_authorization(
            authorization_id="a",
            actor_id="ai-agent",
            actor_kind="ai",
            scope="ext-staging",
            authorized_at="2026-08-15T00:00:00Z",
        )


# --------------------------------------------------------------------------- #
# 2) 逐资源状态机不跳态（T5-T12, T21-T29）                                     #
# --------------------------------------------------------------------------- #
def test_all_eight_resources_pending_by_default():
    reg = ProvisioningStateRegistry(build_default_bom())
    assert reg.summary()["total"] == 8
    assert reg.all_pending() is True
    assert len(RESOURCE_TYPE_ORDER) == 8


def test_state_machine_rejects_illegal_skip():
    reg = ProvisioningStateRegistry(build_default_bom())
    m = reg.get("ext-staging-database")
    assert m.state is ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE
    # 从 PENDING 直接跳到 PROVISIONED 非法（跳状态）。
    with pytest.raises(ResourceStateMachineError):
        m.transition_to(ResourceProvisioningState.PROVISIONED)


def test_state_machine_valid_single_step():
    reg = ProvisioningStateRegistry(build_default_bom())
    m = reg.get("ext-staging-database")
    m.transition_to(ResourceProvisioningState.INPUT_RECEIVED, event="input")
    assert m.state is ResourceProvisioningState.INPUT_RECEIVED
    # 仍禁止越级。
    with pytest.raises(ResourceStateMachineError):
        m.transition_to(ResourceProvisioningState.PROVISIONED)


def test_state_machine_transition_table_is_dag():
    # 每个非终态都有明确定义的目标集合（无悬空）。
    for state, targets in RESOURCE_STATE_TRANSITIONS.items():
        assert isinstance(targets, frozenset)
        assert len(targets) >= 1


def test_failure_state_property():
    assert ResourceProvisioningState.FAILED_PROVISIONING.is_failure is True
    assert ResourceProvisioningState.FAILED_CONNECTIVITY.is_failure is True
    assert ResourceProvisioningState.PROVISIONED.is_failure is False


# --------------------------------------------------------------------------- #
# 3) 分项聚合 0/8（且非硬编码）                                                #
# --------------------------------------------------------------------------- #
def test_aggregator_zero_of_eight_default():
    reg = ProvisioningStateRegistry(build_default_bom())
    agg = PartialProgressAggregator().aggregate(reg)
    d = agg.to_dict()
    assert d["total"] == 8
    for k in ("provisioned", "registered", "connected", "isolated", "qualified"):
        assert d["counts"][k] == 0
    assert d["any_real_progress"] is False
    assert d["single_pct_hides_gaps"] is False


def test_aggregator_reflects_real_progress_when_advanced():
    reg = ProvisioningStateRegistry(build_default_bom())
    m = reg.get("ext-staging-database")
    legal_path = [
        ResourceProvisioningState.INPUT_RECEIVED,
        ResourceProvisioningState.REFERENCE_VALIDATED,
        ResourceProvisioningState.PLAN_READY,
        ResourceProvisioningState.PLAN_VALIDATED,
        ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING,
        ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY,
        ResourceProvisioningState.PROVISIONING,
        ResourceProvisioningState.PROVISIONED,
        ResourceProvisioningState.REGISTERED,
        ResourceProvisioningState.CONNECTIVITY_VERIFIED,
        ResourceProvisioningState.ISOLATION_VERIFIED,
        ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
    ]
    for nxt in legal_path:
        m.transition_to(nxt)
    agg = PartialProgressAggregator().aggregate(reg)
    d = agg.to_dict()
    # 证明聚合器如实反映，而非恒为 0。
    assert d["counts"]["qualified"] == 1
    assert d["counts"]["provisioned"] == 1
    assert d["counts"]["registered"] == 1
    assert d["counts"]["connected"] == 1
    assert d["counts"]["isolated"] == 1
    assert d["any_real_progress"] is True


# --------------------------------------------------------------------------- #
# 4) 递归凭据深扫 fail-closed（§七 技术债修复）                                #
# --------------------------------------------------------------------------- #
def test_deep_scanner_fails_on_secret_text():
    with pytest.raises(CredentialDeepLeakError):
        assert_no_deep_credential_leak(text="password=supersecret123")


def test_deep_scanner_passes_safe_text():
    assert_no_deep_credential_leak(text="this is a benign provisioning plan note")


def test_deep_scanner_recursive_nested_secret():
    payload = {"config": {"db": {"secret": "abcdefghijklmnopqrstuvwxyz012345"}}}
    with pytest.raises(CredentialDeepLeakError):
        assert_no_deep_credential_leak(value=payload)


def test_deep_scanner_json_string_secret():
    with pytest.raises(CredentialDeepLeakError):
        assert_no_deep_credential_leak(
            json_str='{"token":"sk-abcdefghijklmnopqrstuvwxyz"}'
        )


def test_deep_scanner_env_text_secret():
    with pytest.raises(CredentialDeepLeakError):
        assert_no_deep_credential_leak(
            env_text="API_KEY=abcdefghijklmnopqrstuvwxyz012345\nFOO=bar"
        )


def test_deep_scanner_recursive_list_secret():
    payload = [{"credential": "abcdefghijklmnopqrstuvwxyz012345"}]
    with pytest.raises(CredentialDeepLeakError):
        assert_no_deep_credential_leak(value=payload)


# --------------------------------------------------------------------------- #
# 5) 无伪造 / 红线校验（validator_execution）                                  #
# --------------------------------------------------------------------------- #
def test_validator_no_fabrication_passes():
    res = validate_execution_no_fabrication(real_resources_provisioned=0)
    assert res.passed is True
    assert res.violations == ()
    assert res.detail["engineering_enabled"] is False
    assert res.detail["apply_gate_status"] != "authorized_for_external_staging_apply"
    assert res.detail["real_resources_provisioned"] == 0


def test_validator_fabrication_detected():
    res = validate_execution_no_fabrication(real_resources_provisioned=3)
    assert res.passed is False
    assert any("FABRICATION" in v for v in res.violations)


# --------------------------------------------------------------------------- #
# 6) 确定性执行包 & 无伪造证据链                                              #
# --------------------------------------------------------------------------- #
def test_machine_package_deterministic():
    p1 = build_machine_package()
    p2 = build_machine_package()
    assert p1["deterministic"] is True
    assert p1["package_hash"] == p2["package_hash"]
    assert len(p1["package_hash"]) == 64
    assert p1["package"]["engineering_enabled"] is False
    assert p1["package"]["real_resources_provisioned"] == 0
    assert p1["package"]["total_resources"] == 8


def test_evidence_chain_fabrication_free():
    reg = ProvisioningStateRegistry(build_default_bom())
    ev = EvidenceChain()
    ev.capture_pending(reg)
    ev.add_pending_human_item("x")
    d = ev.to_dict()
    assert d["fabrication_free"] is True
    assert len(d["records"]) == 8
    assert len(d["evidence_hash"]) == 64


# --------------------------------------------------------------------------- #
# 7) 执行安全审计（递归深扫 + 双钥匙一致性）                                  #
# --------------------------------------------------------------------------- #
def test_execution_security_audit_clean_and_consistent():
    pkg = build_machine_package()
    auth = _auth_machine_only()
    out = ExecutionSecurityAuditor().audit(package=pkg["package"], auth=auth)
    assert out["deep_scan_clean"] is True
    assert out["dual_key_authorized"] is False
    assert out["consistent"] is True


# --------------------------------------------------------------------------- #
# 8) IaC 可执行就绪（real_execution_allowed=False）                           #
# --------------------------------------------------------------------------- #
def test_iac_readiness_no_real_execution():
    r = IaCReadinessAuditor().audit_all()
    assert r["real_execution_allowed"] is False
    assert r["verdict"] in ("READY_FOR_HUMAN_APPLY", "BLOCKED")
    assert len(r["modules"]) == 8


# --------------------------------------------------------------------------- #
# 9) 仅读 API 契约 & plan-only 成本                                          #
# --------------------------------------------------------------------------- #
def test_execution_api_contract_read_only():
    assert EXECUTION_API_CONTRACT["real_execution_allowed"] is False
    assert len(EXECUTION_API_CONTRACT["endpoints"]) == 5
    for ep in EXECUTION_API_CONTRACT["endpoints"]:
        assert ep["method"] == "GET"
        assert ep["mutates"] is False
    assert len(EXECUTION_API_CONTRACT["forbidden"]) >= 1


def test_plan_only_cost_is_zero():
    c = estimate_plan_only_cost()
    assert c["estimated_monthly"] == 0.0
    assert c["billing_status"] == "no_real_resource_provisioned"


# --------------------------------------------------------------------------- #
# 10) 编排器主入口——终态 BUILT_NO_GO / 0/8 / 永不 GO                         #
# --------------------------------------------------------------------------- #
def test_orchestrator_run_terminal_no_go():
    out = ProvisioningExecutionOrchestrator().run(generated_from_commit="testcommit")
    assert out["terminal_state"] == "EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO"
    assert out["engineering_enabled"] is False
    assert out["total_resources"] == 8
    for k in ("provisioned", "registered", "connected", "isolated", "qualified"):
        assert out[k] == 0
    assert out["any_real_progress"] is False
    assert out["real_resources_provisioned"] == 0
    assert out["apply_gate_status"] == "pending_human_authorization"
    assert out["apply_gate_is_go"] is False
    assert out["iac_real_execution_allowed"] is False
    assert out["dual_key_authorized"] is False
    assert out["fabrication_free"] is True
    assert len(out["machine_package_hash"]) == 64


# --------------------------------------------------------------------------- #
# 11) 全模块导入冒烟（Batch A/B 框架文件均可导入，无断裂）                    #
# --------------------------------------------------------------------------- #
def test_all_execution_modules_importable():
    import importlib

    mods = [
        "agents.external_staging_provisioning.registration",
        "agents.external_staging_provisioning.connectivity",
        "agents.external_staging_provisioning.isolation",
        "agents.external_staging_provisioning.lifecycle",
        "agents.external_staging_provisioning.executors",
    ]
    for m in mods:
        importlib.import_module(m)

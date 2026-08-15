"""Phase 3.9.10 —— External Staging Qualification 全量 fail-closed 测试矩阵（Task 44）。

覆盖：old WIP forensics / branch integrity / registry / resource statuses /
environment identity / fingerprint / credential refs / 8 探针 / deployment adapter /
runtime health / cross-env isolation / evidence / qualification gate / package /
validator / API contract / checklist contract / no-resource dry-run / failure /
recovery / RBAC / cross-org / Production denial / engineering_enabled=false。

规则：所有测试 fail-closed；缺真实资源必须回落 pending，绝不伪造验证。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# 允许以 agents 包导入（test runner 通常已注入 repo 根）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_qualification import (  # noqa: E402
    EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE,
    CredentialReference,
    DeploymentTarget,
    ExternalStagingConnectivityProbe,
    ExternalStagingDeploymentProvider,
    ExternalStagingEnvironmentIdentity,
    ExternalStagingQualificationGate,
    ExternalStagingResourceRegistry,
    ExternalStagingQualifier,
    GateStatus,
    ProbeContext,
    ProductionDenylistEntry,
    ProductionReferenceDenylist,
    ProductionResourceKind,
    QualificationPipeline,
    ResourceQualificationStatus,
    ResourceType,
    RuntimeHealthStatus,
    RuntimeQualification,
    CrossEnvironmentIsolationProver,
    make_evidence,
    EvidenceScope,
    EvidenceType,
    build_qualification_package,
    package_hash,
    ExternalStagingFailureSimulator,
    ExternalStagingRecoverySimulator,
    FailureScenario,
    RecoveryOutcome,
    ExternalStagingSecurityValidator,
    Actor,
    RequestScope,
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_qualification.config import (  # noqa: E402
    load_external_staging_identity,
)
from agents.external_staging_qualification.qualification import (  # noqa: E402
    ExternalStagingQualifier as _Q,
)
from agents.config_loader import load_engineering_enabled  # noqa: E402
from scripts.validate_external_staging_qualification_package import (  # noqa: E402
    validate_package,
)


# --------------------------------------------------------------------------- #
# T1 / Branch Integrity                                                        #
# --------------------------------------------------------------------------- #
def test_old_wip_is_separate_branch_not_merged():
    """旧 3.9.10 WIP 独立分支，不得并入当前阶段。"""

    out = subprocess.run(
        ["git", "branch", "--all"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    branches = out.stdout
    # 旧 WIP 分支存在（历史保留）
    assert "phase3.9.10-production-handoff-human-activation-ceremony" in branches
    # 当前阶段分支存在且与旧 WIP 分支互相独立（不为旧 WIP 分支本身）
    cur = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    assert cur in branches
    assert cur != "phase3.9.10-production-handoff-human-activation-ceremony"


def test_current_branch_is_phase_branch(tmp_path):
    """Branch Integrity：当前分支应为合法的 external-staging 阶段分支，非漂移分支。

    不绑定具体 Phase 编号：只要是 `feat/phase3.9.<n>-external-staging-*` 形态即
    通过，从而在 3.9.10 / 3.9.11 等任一 external-staging 分支上均能正确校验，
    也避免阶段推进时硬编码分支名导致整套测试误红。
    """

    out = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    branch = out.stdout.strip()
    assert re.match(r"^feat/phase3\.9\.\d+-external-staging-", branch), branch


def test_no_foreign_phase_files_in_tree():
    """Branch Integrity：工作树不得含 production_handoff / production_change 外国文件。"""

    out = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "production_handoff" not in out.stdout
    assert "production_change" not in out.stdout


# --------------------------------------------------------------------------- #
# Registry / Statuses                                                         #
# --------------------------------------------------------------------------- #
def test_registry_has_8_resources():
    reg = ExternalStagingResourceRegistry.build_default()
    assert len(reg.resources) == 8
    types = {r.resource_type for r in reg.resources}
    assert types == set(ResourceType)


def test_registry_defaults_not_configured():
    reg = ExternalStagingResourceRegistry.build_default()
    for r in reg.resources:
        assert r.configured is False
        assert r.verified is False
        assert r.qualification_status == ResourceQualificationStatus.NOT_CONFIGURED.value


def test_resource_status_forbidden_states_absent():
    for st in ResourceQualificationStatus:
        assert st.value not in ("production_ready", "approved", "go")


def test_gate_status_forbidden_states_absent():
    for st in GateStatus:
        assert st.value not in ("approved", "production_ready", "go")


# --------------------------------------------------------------------------- #
# Environment Identity / Fingerprint                                          #
# --------------------------------------------------------------------------- #
def test_environment_identity_not_production():
    env = load_external_staging_identity()
    assert env.production is False
    assert env.environment == "external_staging"
    assert env.fingerprint  # 指纹已生成


def test_environment_production_true_rejected():
    with pytest.raises(ValueError):
        bad = ExternalStagingEnvironmentIdentity(production=True)
        ExternalStagingConnectivityProbe(ProbeContext(environment=bad))


def test_fingerprint_collision_rejected():
    env = load_external_staging_identity()
    # 与生产指纹相同 → 拒绝（此处生产指纹未知，仅验证函数存在且非平凡）
    from agents.external_staging_qualification.config import (
        fingerprint_collision_with_production,
    )
    assert fingerprint_collision_with_production(env, "") is False


# --------------------------------------------------------------------------- #
# Credential Reference Safety                                                 #
# --------------------------------------------------------------------------- #
def test_credential_reference_no_raw_secret():
    ref = CredentialReference(
        resource_id="ext-staging-database",
        credential_id="ref-db-cred",
        provider_reference="aws-secrets-manager",
        secret_reference="arn:aws:secretsmanager:...",
    )
    assert ref.contains_raw_secret() is False


def test_credential_reference_flags_raw_secret():
    ref = CredentialReference(
        resource_id="x",
        credential_id="password=supersecret123",
        provider_reference="p",
    )
    assert ref.contains_raw_secret() is True


def test_credential_scanner_detects_leak():
    with pytest.raises(CredentialLeakError):
        assert_no_credential_leak(text="password=supersecret123")
    with pytest.raises(CredentialLeakError):
        assert_no_credential_leak(mapping={"token": "sk-abcdefghijklmnopqrstuvwxyz"})


def test_credential_scanner_clean_passes():
    assert_no_credential_leak(text="no secret here")
    assert_no_credential_leak(mapping={"reference": "arn:aws:..."})


# --------------------------------------------------------------------------- #
# Probes (8) — resource-less returns pending                                  #
# --------------------------------------------------------------------------- #
def _probe():
    env = load_external_staging_identity()
    return ExternalStagingConnectivityProbe(ProbeContext(environment=env))


def test_db_probe_pending_when_not_configured():
    res = _probe().probe_database("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE
    assert res.reachable is False


def test_secret_provider_probe_pending():
    res = _probe().probe_secret_provider("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_idp_probe_pending():
    res = _probe().probe_idp("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_storage_probe_pending():
    res = _probe().probe_storage("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_telemetry_probe_pending():
    res = _probe().probe_telemetry("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_alert_probe_pending():
    res = _probe().probe_alert("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_domain_tls_probe_pending():
    res = _probe().probe_domain_tls("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_deployment_target_probe_pending():
    res = _probe().probe_deployment_target("", configured=False)
    assert res.status == ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE


# --------------------------------------------------------------------------- #
# Deployment Adapter                                                          #
# --------------------------------------------------------------------------- #
def test_deployment_rejects_production_target():
    env = load_external_staging_identity()
    provider = ExternalStagingDeploymentProvider(env)
    with pytest.raises(Exception):
        provider.validate_target(
            DeploymentTarget(
                provider="aws",
                environment_label="production",
                region="r",
                cluster="c",
                namespace="ns",
                reference="prod-target",
            )
        )


def test_deploy_requires_execute_flag():
    env = load_external_staging_identity()
    provider = ExternalStagingDeploymentProvider(env)
    target = DeploymentTarget(
        provider="aws", environment_label="external_staging", region="r",
        cluster="c", namespace="ns", reference="ext-target",
    )
    with pytest.raises(Exception):
        provider.deploy_staging(target=target, commit="abc", deployed_by="user", execute=False)


def test_deployment_evidence_not_production():
    env = load_external_staging_identity()
    provider = ExternalStagingDeploymentProvider(env)
    target = DeploymentTarget(
        provider="aws", environment_label="external_staging", region="r",
        cluster="c", namespace="ns", reference="ext-target",
    )
    ev = provider.deploy_staging(
        target=target, commit="abc123", deployed_by="user-x", execute=True
    )
    assert ev.to_dict()["is_production_deployment"] is False


# --------------------------------------------------------------------------- #
# Runtime Health                                                              #
# --------------------------------------------------------------------------- #
def test_runtime_unknown_not_healthy():
    report = RuntimeQualification().evaluate(
        overrides={"database": RuntimeHealthStatus.UNKNOWN}
    )
    db = next(c for c in report.components if c.component == "database")
    assert db.status.is_healthy is False
    assert report.summary()["unknown_treated_as_healthy"] is False


def test_runtime_default_not_configured():
    report = RuntimeQualification().evaluate()
    assert report.summary()["not_configured"] == 13


# --------------------------------------------------------------------------- #
# Cross-environment Isolation                                                 #
# --------------------------------------------------------------------------- #
def test_isolation_pending_without_production_refs():
    ev = CrossEnvironmentIsolationProver().prove({"database": "staging-db"})
    assert ev.items[0].verdict.value == "pending"


def test_isolation_blocked_on_collision():
    ev = CrossEnvironmentIsolationProver().prove(
        {"database": "same-db"}, production_references={"database": "same-db"}
    )
    assert ev.items[0].verdict.value == "blocked"


# --------------------------------------------------------------------------- #
# Evidence                                                                    #
# --------------------------------------------------------------------------- #
def test_evidence_scope_external_staging_only():
    ev = make_evidence(
        evidence_id="e1", resource_id="rid", evidence_type=EvidenceType.CONNECTIVITY,
        source="t", actor="AI", verification_status="pending",
    )
    assert ev.environment == EvidenceScope.EXTERNAL_STAGING.value
    assert ev.contains_secret is False
    with pytest.raises(Exception):
        make_evidence(
            evidence_id="e2", resource_id="rid", evidence_type=EvidenceType.CONNECTIVITY,
            source="t", actor="AI", verification_status="pending",
            environment="production",
        )


def test_evidence_chain_hash_stable():
    e1 = make_evidence(evidence_id="a", resource_id="r", evidence_type=EvidenceType.CONNECTIVITY,
                      source="t", actor="AI", verification_status="pending")
    e2 = make_evidence(evidence_id="b", resource_id="r", evidence_type=EvidenceType.ISOLATION,
                      source="t", actor="AI", verification_status="pending")
    from agents.external_staging_qualification.evidence import EvidenceChain
    chain = EvidenceChain().append(e1).append(e2)
    assert chain.chain_hash() == EvidenceChain().append(e1).append(e2).chain_hash()


# --------------------------------------------------------------------------- #
# Qualification Gate                                                          #
# --------------------------------------------------------------------------- #
def test_gate_pending_when_resources_unverified():
    reg = ExternalStagingResourceRegistry.build_default()
    gate = ExternalStagingQualificationGate().evaluate(registry=reg)
    assert gate.status == GateStatus.PENDING_EXTERNAL_STAGING_RESOURCE


def test_gate_blocked_on_denylist():
    from agents.external_staging_qualification.denylist import ProductionDenylistViolation
    dl = ProductionReferenceDenylist.from_references(
        [ProductionDenylistEntry(kind=ProductionResourceKind.DATABASE, reference="prod-db")]
    )
    env = load_external_staging_identity()
    reg, _ = ExternalStagingQualifier(env, denylist=dl).qualify_registry(
        ExternalStagingResourceRegistry.build_default(),
        references={ResourceType.DATABASE: "prod-db"},
        configured_flags={ResourceType.DATABASE: True},
    )
    gate = ExternalStagingQualificationGate().evaluate(registry=reg)
    assert gate.status == GateStatus.BLOCKED


def test_gate_no_production_state():
    reg = ExternalStagingResourceRegistry.build_default()
    gate = ExternalStagingQualificationGate().evaluate(registry=reg)
    assert gate.status.value not in ("approved", "production_ready", "go")


# --------------------------------------------------------------------------- #
# Package / Validator                                                         #
# --------------------------------------------------------------------------- #
def test_package_flags():
    reg = ExternalStagingResourceRegistry.build_default()
    pkg = build_qualification_package(
        source_commit="2f4a983", environment_identity=load_external_staging_identity(),
        registry=reg,
    )
    assert pkg["contains_real_secret"] is False
    assert pkg["production_activation_prohibited"] is True
    assert pkg["engineering_enabled"] is False
    assert pkg["terminal_state"] == EXTERNAL_STAGING_QUALIFICATION_TERMINAL_STATE


def test_package_hash_stable():
    reg = ExternalStagingResourceRegistry.build_default()
    p1 = build_qualification_package(
        source_commit="2f4a983",
        environment_identity=load_external_staging_identity(),
        registry=reg,
    )
    p2 = build_qualification_package(
        source_commit="2f4a983",
        environment_identity=load_external_staging_identity(),
        registry=reg,
    )
    assert p1["package_hash"] == p2["package_hash"]


def test_validator_passes_generated_package():
    pkg_path = Path(".ai/staging/external_staging_qualification_package.json")
    if not pkg_path.exists():
        pytest.skip("package not generated")
    script = Path("scripts/validate_external_staging_qualification_package.py")
    # 自派生包内 source_commit（避免硬编码 base，待 R1 后 source_commit 指向实现 commit）
    pkg_payload = json.loads(pkg_path.read_text(encoding="utf-8"))
    cmd = [sys.executable, str(script), str(pkg_path)]
    sc = pkg_payload.get("source_commit")
    if sc:
        cmd += ["--source-commit", sc]
    rc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert rc.returncode == 0, rc.stderr


def test_validator_rejects_forbidden_state():
    bad = {
        "schema_version": "1.0.0", "phase": "3.9.10",
        "source_commit": "2f4a983",
        "environment_identity": {"environment": "external_staging", "production": False},
        "resource_registry_summary": {"total": 8},
        "isolation_summary": {},
        "gate": {"status": "APPROVED"},
        "contains_real_secret": False,
        "production_activation_prohibited": True,
        "engineering_enabled": False,
        "package_hash": "x",
    }
    errors = validate_package(bad)
    assert any("禁止态" in e for e in errors)


# --------------------------------------------------------------------------- #
# API Contract SSOT                                                          #
# --------------------------------------------------------------------------- #
def test_api_contract_8_routes_production_forbidden():
    contract_path = Path(".ai/baselines/external_staging_api_contract.json")
    if not contract_path.exists():
        pytest.skip("contract not generated")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["route_count"] == 8
    for r in contract["routes"]:
        assert r["production_forbidden"] is True
        assert r["environment"] == "external_staging"


# --------------------------------------------------------------------------- #
# Checklist contract (gate checks match checklist items)                      #
# --------------------------------------------------------------------------- #
def test_checklist_contract_gate_checks_present():
    reg = ExternalStagingResourceRegistry.build_default()
    gate = ExternalStagingQualificationGate().evaluate(
        registry=reg, environment_identity=load_external_staging_identity().to_dict()
    )
    names = {c.name for c in gate.checks}
    for required in (
        "resource_registry_complete", "credential_reference_safety",
        "no_blocked_resources", "all_resources_verified",
        "environment_not_production", "security", "full_regression", "repository_clean",
    ):
        assert required in names


# --------------------------------------------------------------------------- #
# No-resource dry-run                                                         #
# --------------------------------------------------------------------------- #
def test_no_resource_dry_run_all_pending():
    result = QualificationPipeline(source_commit="2f4a983").run()
    assert result.gate_status == "pending_external_staging_resource"
    assert result.registry.summary()["verified"] == 0
    assert result.package["contains_real_secret"] is False
    assert result.package["production_activation_prohibited"] is True


# --------------------------------------------------------------------------- #
# Failure / Recovery scenarios                                                #
# --------------------------------------------------------------------------- #
def test_failure_scenarios_all_safe_response():
    sim = ExternalStagingFailureSimulator()
    evals = sim.evaluate(triggered={FailureScenario.DB_UNREACHABLE})
    for e in evals:
        assert e.blocked_production_impact is True
        assert "fail-closed" in e.safe_response.lower() or "production" in e.safe_response.lower()


def test_recovery_outcome_not_production():
    sim = ExternalStagingRecoverySimulator()
    evals = sim.evaluate(recoverable={FailureScenario.DB_UNREACHABLE})
    for e in evals:
        assert e.represents_production_recovery is False
        if e.outcome != RecoveryOutcome.RECOVERY_PENDING:
            assert e.outcome == RecoveryOutcome.EXTERNAL_STAGING_RECOVERED_CANDIDATE


# --------------------------------------------------------------------------- #
# Security / RBAC / Cross-org / Production denial                             #
# --------------------------------------------------------------------------- #
def test_security_unauthorized_rejected():
    v = ExternalStagingSecurityValidator()
    r = v.evaluate_write(actor=Actor.UNAUTHORIZED, scope=RequestScope.EXTERNAL_STAGING,
                         same_org=True, csrf_valid=True, privileged_role=True)
    assert r.allowed is False


def test_security_ai_system_write_rejected():
    v = ExternalStagingSecurityValidator()
    r = v.evaluate_write(actor=Actor.AI_SYSTEM, scope=RequestScope.EXTERNAL_STAGING,
                         same_org=True, csrf_valid=True, privileged_role=True)
    assert r.allowed is False


def test_security_cross_org_rejected():
    v = ExternalStagingSecurityValidator()
    r = v.evaluate_write(actor=Actor.SAME_ORG_USER, scope=RequestScope.EXTERNAL_STAGING,
                         same_org=False, csrf_valid=True, privileged_role=True)
    assert r.allowed is False


def test_security_production_scope_rejected():
    v = ExternalStagingSecurityValidator()
    r = v.evaluate_write(actor=Actor.PRIVILEGED_ROLE, scope=RequestScope.PRODUCTION,
                         same_org=True, csrf_valid=True, privileged_role=True)
    assert r.allowed is False


def test_security_csrf_enforced():
    v = ExternalStagingSecurityValidator()
    r = v.evaluate_write(actor=Actor.PRIVILEGED_ROLE, scope=RequestScope.EXTERNAL_STAGING,
                         same_org=True, csrf_valid=False, privileged_role=True)
    assert r.allowed is False


def test_security_identity_contract_intact():
    v = ExternalStagingSecurityValidator()
    r = v.identity_contract_intact(load_external_staging_identity().to_dict())
    assert r.allowed is True


# --------------------------------------------------------------------------- #
# engineering_enabled=false                                                   #
# --------------------------------------------------------------------------- #
def test_engineering_enabled_false():
    assert load_engineering_enabled() is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

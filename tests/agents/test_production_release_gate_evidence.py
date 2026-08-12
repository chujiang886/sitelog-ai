"""企业生产发布闸门与证据包层 核验测试（Phase 3.9.2）。

覆盖（agents/enterprise/production_release + audit 4 个 RELEASE_* 枚举）：
- T1 ``ProductionReleaseEvidence``：默认 PENDING_VERIFICATION；SHA-256 重算完整性
  （INTACT / TAMPERED / PENDING / UNKNOWN）；人工依赖证据（human_signoff /
  production_secret）恒 PENDING_VERIFICATION（红线⑨/⑩，AI 不代填）。
- T2 ``ProductionReleaseCandidate``：AI 只造 DRAFT，``release_approved`` 恒 False；
  mark_awaiting_human_review 仍保持 release_approved=False。
- T3 ``ProductionReleaseGate``：13 项 CHECK_KEYS，evaluate 三态
  （BLOCKED / PENDING_VERIFICATION / READY_FOR_HUMAN_REVIEW），**永不** APPROVED。
- T4 ``ReleaseSignoff``：契约只由真实 USER 构造（服务 forbidden 名 create_human_signoff
  结构拦截 AI 代签）。
- T5 ``ReleaseDecisionDraft``：build_decision_draft 只产出草稿态，绝不出 GO_LIVE_APPROVED。
- T6 ``ReleasePackageManifest``：build_manifest 对存在文件算 SHA-256，缺文件标 ``<missing>``
  （不伪造）。
- T7 ``ReleaseRollbackReference``：build_rollback_reference 仅验证引用完整性
  （verified 仅表示引用齐备，不执行真实回滚）。
- 审计增强：RELEASE_CANDIDATE_CREATED / RELEASE_GATE_EVALUATED /
  RELEASE_SIGNOFF_RECORDED / RELEASE_MANIFEST_GENERATED 四个枚举存在且 service
  record_* 方法强制 actor=USER（红线⑥/⑧）。
- 红线验证：结构级禁名（真部署 / 出 approved / 自动批准 / 代签 / 写真实密钥 / 授真实权限 /
  翻转 engineering_enabled）一律被 ``_RedLineForbiddenMixin`` 拦截；全程
  ``engineering_enabled`` 保持 False。

遵守治理完整性检查器规则 4：审计总数仅用**存在性契约**断言（不写总数断言）。
全部仅读不写，不触碰生产 verified.json / 授权库 / 真实密钥 / 真实数据。
"""

from __future__ import annotations

import hashlib
import os

import pytest
from dataclasses import FrozenInstanceError

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.production_release import (
    PRODUCTION_RELEASE_FORBIDDEN_COUNT,
    ProductionReleaseEvidenceService,
    ProductionReleaseGate,
    ProductionReleaseService,
    ReleasePackageBuilder,
)
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
    ProductionReleaseCandidate,
    ProductionReleaseEvidence,
    ReleaseCandidateStatus,
    ReleaseDecisionDraftStatus,
    ReleaseGateStatus,
    ReleaseSignoff,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.service import EnterpriseOperationLayer

# 发布闸门层专属禁名（确认来自 forbidden.py _PRODUCTION_RELEASE_EXTRA_FORBIDDEN）。
_FORBIDDEN_CALLS = (
    "deploy_production_for_real",
    "release_to_production",
    "activate_production_now",
    "run_live_release",
    "auto_approve_release",
    "auto_go_live",
    "declare_production_go",
    "emit_release_approved",
    "conclude_gate_as_go",
    "mark_release_verified",
    "flip_engineering_for_release",
    "write_real_production_secret",
    "grant_real_production_permission",
    "sign_for_user",
    "create_human_signoff",
    "attest_release_ready",
)

# 非权威文件：仅用存在性契约断言枚举（遵守治理完整性检查器规则 4）。
_REQUIRED_AUDIT_CATEGORIES = {
    "release_candidate_created",
    "release_gate_evaluated",
    "release_signoff_recorded",
    "release_manifest_generated",
}

_ROOT = os.path.abspath(".")


def _service() -> ProductionReleaseService:
    return ProductionReleaseService(
        org_id="org-1", audit=AuditService(org_id="org-1")
    )


def _ev(
    ev_type: str, status: EvidenceVerificationStatus
) -> ProductionReleaseEvidence:
    return ProductionReleaseEvidence(
        evidence_id=f"e-{ev_type}",
        evidence_type=ev_type,
        source="test",
        source_reference="ref",
        created_at="2026-08-10T00:00:00Z",
        verification_status=status,
    )


def _chain_of(items) -> dict:
    return ProductionReleaseEvidenceService().build_evidence_chain(items)


def _all_true_scan() -> dict:
    return {
        "git_workspace_integrity": True,
        "commit_sha_exists": True,
        "full_test_results_green": True,
        "production_security_scanner": True,
        "identity_security_scanner": True,
        "governance_quality_gate": True,
        "rollback_drill": True,
        "recovery_validation": True,
        "database_migration_status": True,
        "configuration_baseline": True,
        "deployment_documentation": True,
    }


# =========================================================================== #
# T0 包级契约
# =========================================================================== #
def test_package_imports_and_forbidden_count() -> None:
    # __init__ 正确导出所有公共符号；import 不再抛 ImportError。
    assert PRODUCTION_RELEASE_FORBIDDEN_COUNT > 0
    # 本层专属增量至少 29 个（与 forbidden.py _PRODUCTION_RELEASE_EXTRA_FORBIDDEN 对齐）。
    assert PRODUCTION_RELEASE_FORBIDDEN_COUNT >= 29


def test_gate_has_13_check_keys() -> None:
    assert len(ProductionReleaseGate.CHECK_KEYS) == 13
    assert set(ProductionReleaseGate.CHECK_KEYS) == {
        "git_workspace_integrity",
        "commit_sha_exists",
        "full_test_results_green",
        "production_security_scanner",
        "identity_security_scanner",
        "governance_quality_gate",
        "staging_validation",
        "rollback_drill",
        "recovery_validation",
        "database_migration_status",
        "configuration_baseline",
        "deployment_documentation",
        "evidence_completeness",
    }


# =========================================================================== #
# T1 证据：默认待核验 + SHA-256 完整性 + 红线⑨
# =========================================================================== #
def test_evidence_default_pending_verification() -> None:
    svc = _service()
    ev = svc._evidence_svc.create_evidence(
        evidence_id="e1",
        evidence_type="security_scan",
        source="filesystem",
        source_reference="scripts/lint/check_production_security.py",
    )
    assert ev.verification_status == EvidenceVerificationStatus.PENDING_VERIFICATION
    assert ev.integrity_status == EvidenceIntegrityStatus.PENDING


def test_evidence_verify_integrity_intact_tampered_pending_unknown() -> None:
    svc = _service()
    rel = "agents/enterprise/production_release/forbidden.py"
    path = os.path.join(_ROOT, rel)
    with open(path, "rb") as f:
        actual = hashlib.sha256(f.read()).hexdigest()

    # INTACT：sha256 匹配真实文件
    ev = svc._evidence_svc.create_evidence(
        evidence_id="e-intact",
        evidence_type="x",
        source="filesystem",
        source_reference=rel,
        sha256=actual,
    )
    assert svc._evidence_svc.verify_integrity(ev) == EvidenceIntegrityStatus.INTACT

    # TAMPERED：sha256 不匹配
    ev_bad = svc._evidence_svc.create_evidence(
        evidence_id="e-tam",
        evidence_type="x",
        source="filesystem",
        source_reference=rel,
        sha256="0" * 64,
    )
    assert svc._evidence_svc.verify_integrity(ev_bad) == EvidenceIntegrityStatus.TAMPERED

    # PENDING：无 sha256
    ev_none = svc._evidence_svc.create_evidence(
        evidence_id="e-pend",
        evidence_type="x",
        source="filesystem",
        source_reference=rel,
    )
    assert svc._evidence_svc.verify_integrity(ev_none) == EvidenceIntegrityStatus.PENDING

    # UNKNOWN：sha256 存在但文件不可达
    ev_missing = svc._evidence_svc.create_evidence(
        evidence_id="e-unknown",
        evidence_type="x",
        source="filesystem",
        source_reference="no/such/file.py",
        sha256=actual,
    )
    assert svc._evidence_svc.verify_integrity(ev_missing) == EvidenceIntegrityStatus.UNKNOWN


def test_collect_evidence_keeps_human_dependencies_pending() -> None:
    svc = _service()
    items = svc.collect_evidence(
        release_id="r1", test_baseline={"passed": 1}, audit_count=83,
        engineering_enabled=False,
    )
    by_type = {e.evidence_type: e for e in items}
    # 红线⑨/⑩：真实责任人签署 / 真实生产密钥恒 PENDING_VERIFICATION，AI 不代填。
    assert by_type["human_signoff"].verification_status == (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    assert by_type["production_secret"].verification_status == (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    # 客观事实（工程护栏 / 审计总数 / 测试基线）可核验为 VERIFIED。
    assert by_type["engineering_guard"].verification_status == (
        EvidenceVerificationStatus.VERIFIED
    )
    assert by_type["audit_reference"].verification_status == (
        EvidenceVerificationStatus.VERIFIED
    )


# =========================================================================== #
# T2 发布候选：release_approved 恒 False
# =========================================================================== #
def test_release_candidate_approved_false_and_draft() -> None:
    svc = _service()
    rc = svc.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc123", branch="main",
    )
    assert rc.status == ReleaseCandidateStatus.DRAFT
    assert rc.release_approved is False  # fail-closed
    assert "RC_ONLY" in rc.note


def test_mark_awaiting_human_review_keeps_approved_false() -> None:
    svc = _service()
    rc = svc.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc123", branch="main",
    )
    awaiting = svc.mark_awaiting_human_review(rc)
    assert awaiting.status == ReleaseCandidateStatus.AWAITING_HUMAN_REVIEW
    assert awaiting.release_approved is False


# =========================================================================== #
# T3 / T5 闸门三态 + 决策草稿（永不 APPROVED / GO_LIVE_APPROVED）
# =========================================================================== #
def test_gate_blocked_when_check_false() -> None:
    gate = ProductionReleaseGate()
    rc = ProductionReleaseCandidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    scan = _all_true_scan()
    scan["git_workspace_integrity"] = False
    chain = _chain_of([_ev("staging_validation", EvidenceVerificationStatus.VERIFIED)])
    res = gate.evaluate(candidate=rc, evidence_chain=chain, scan=scan)
    assert res.status == ReleaseGateStatus.BLOCKED
    assert "git_workspace_integrity" in res.missing
    assert "APPROVED" not in res.status.value


def test_gate_pending_verification_when_evidence_pending() -> None:
    gate = ProductionReleaseGate()
    rc = ProductionReleaseCandidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    scan = _all_true_scan()
    chain = _chain_of([
        _ev("staging_validation", EvidenceVerificationStatus.PENDING_VERIFICATION),
        _ev("production_readiness", EvidenceVerificationStatus.VERIFIED),
        _ev("security_scan", EvidenceVerificationStatus.VERIFIED),
        _ev("human_signoff", EvidenceVerificationStatus.PENDING_VERIFICATION),
    ])
    res = gate.evaluate(candidate=rc, evidence_chain=chain, scan=scan)
    assert res.status == ReleaseGateStatus.PENDING_VERIFICATION
    assert "APPROVED" not in res.status.value


def test_gate_ready_for_human_review_when_all_verified() -> None:
    gate = ProductionReleaseGate()
    rc = ProductionReleaseCandidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    scan = _all_true_scan()
    chain = _chain_of([
        _ev("staging_validation", EvidenceVerificationStatus.VERIFIED),
        _ev("production_readiness", EvidenceVerificationStatus.VERIFIED),
        _ev("security_scan", EvidenceVerificationStatus.VERIFIED),
    ])
    res = gate.evaluate(candidate=rc, evidence_chain=chain, scan=scan)
    assert res.status == ReleaseGateStatus.READY_FOR_HUMAN_REVIEW
    assert res.missing == []
    # 即便全部客观通过，也只给人工前置态，绝不 APPROVED。
    assert "APPROVED" not in res.status.value


def test_service_evaluate_gate_never_approved() -> None:
    svc = _service()
    rc = svc.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    evidence = svc.collect_evidence(release_id="r1", engineering_enabled=False)
    # 用全 True scan 覆盖仓库事实，使环境可控（不依赖工作树是否干净）。
    res = svc.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_true_scan(),
    )
    allowed = {
        ReleaseGateStatus.READY_FOR_HUMAN_REVIEW,
        ReleaseGateStatus.BLOCKED,
        ReleaseGateStatus.PENDING_VERIFICATION,
    }
    assert res.status in allowed
    assert "APPROVED" not in res.status.value
    # 服务层不保留任何放行语义：结果只含 status/checks/missing，无 approved 键。
    assert "approved" not in res.to_dict()


def test_build_decision_draft_never_go_live_approved() -> None:
    svc = _service()
    rc = svc.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    evidence = svc.collect_evidence(release_id="r1", engineering_enabled=False)
    gate = svc.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_true_scan(),
    )
    draft = svc.build_decision_draft(
        release_id="r1", candidate=rc, evidence=evidence, gate=gate,
    )
    allowed = {
        ReleaseDecisionDraftStatus.READY_FOR_HUMAN_GO_NO_GO,
        ReleaseDecisionDraftStatus.BLOCKED,
        ReleaseDecisionDraftStatus.NEEDS_MORE_EVIDENCE,
    }
    assert draft.status in allowed
    assert draft.status != "go_live_approved"
    assert "GO_LIVE_APPROVED" not in draft.to_dict()["status"]
    # 风险清单显式声明最终 GO 只能源于真实签署。
    assert any("ReleaseSignoff" in r for r in draft.risks)


# =========================================================================== #
# T4 人工签署契约（AI 不得代签）
# =========================================================================== #
def test_signoff_contract_requires_real_user() -> None:
    # 契约只描述字段；本测试仅验证逻辑形参存在且 actor_kind 应为 user。
    so = ReleaseSignoff(
        signoff_id="s1",
        release_id="r1",
        actor_id="user-owner",
        actor_kind="user",
        role=SignoffRole.PRODUCTION_OWNER,
        decision=SignoffDecision.GO,
        reason="human decision",
        timestamp="2026-08-10T00:00:00Z",
    )
    assert so.role == SignoffRole.PRODUCTION_OWNER
    assert so.decision == SignoffDecision.GO
    assert so.actor_kind == "user"
    assert "CONTRACT_ONLY" in so.note


def test_service_forbids_create_human_signoff() -> None:
    svc = _service()
    # AI 不得代生产负责人构造签署实例。
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_human_signoff()  # type: ignore[attr-defined]


# =========================================================================== #
# T6 清单 SHA-256 + T7 回滚引用（只描述）
# =========================================================================== #
def test_manifest_sha256_for_existing_and_missing_artifacts() -> None:
    builder = ReleasePackageBuilder(root_dir=".")
    rel = "agents/enterprise/production_release/forbidden.py"
    man = builder.build_manifest(
        release_version="1.0.0",
        commit_sha="abc123",
        artifacts={"main_module": rel, "ghost": "no/such/file.py"},
    )
    assert man.release_version == "1.0.0"
    assert man.commit_sha == "abc123"
    # 存在文件 → 64 位 hex sha256
    h = man.artifact_hashes["main_module"]
    assert len(h) == 64 and int(h, 16) is not None
    # 缺失文件 → 诚实标记 <missing>，不伪造
    assert man.artifact_hashes["ghost"] == "<missing>"
    assert "MANIFEST_ONLY" in man.note


def test_rollback_reference_verified_only_when_refs_present() -> None:
    builder = ReleasePackageBuilder(root_dir=".")
    complete = builder.build_rollback_reference(
        last_known_good_version="0.9.0",
        last_known_good_commit="def456",
        database_revision="alembic@rev-1",
        config_baseline="config.yaml@3.9.2",
        rollback_steps_reference="docs/rollback.md",
        recovery_validation_reference="docs/recovery.md",
    )
    assert complete.verified is True  # 引用齐备
    incomplete = builder.build_rollback_reference(
        last_known_good_version="0.9.0",
        last_known_good_commit="",  # 缺 commit 引用
    )
    assert incomplete.verified is False
    assert "ROLLBACK_REF_ONLY" in complete.note


# =========================================================================== #
# 模型不可变 + to_dict 字段
# =========================================================================== #
def test_models_are_frozen_and_have_dict() -> None:
    rc = ProductionReleaseCandidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    with pytest.raises(FrozenInstanceError):
        rc.release_approved = True  # type: ignore[misc]
    d = rc.to_dict()
    assert d["release_approved"] is False
    assert d["status"] == "draft"

    ev = _ev("security_scan", EvidenceVerificationStatus.VERIFIED)
    with pytest.raises(FrozenInstanceError):
        ev.verification_status = EvidenceVerificationStatus.FAILED  # type: ignore[misc]
    assert ev.to_dict()["verification_status"] == "verified"


# =========================================================================== #
# 审计增强（actor 真实）
# =========================================================================== #
def test_new_audit_categories_exist() -> None:
    members = {c.value for c in AuditActionCategory}
    assert _REQUIRED_AUDIT_CATEGORIES <= members  # 存在性契约，不写总数断言
    for name, value in (
        ("RELEASE_CANDIDATE_CREATED", "release_candidate_created"),
        ("RELEASE_GATE_EVALUATED", "release_gate_evaluated"),
        ("RELEASE_SIGNOFF_RECORDED", "release_signoff_recorded"),
        ("RELEASE_MANIFEST_GENERATED", "release_manifest_generated"),
    ):
        assert hasattr(AuditActionCategory, name)
        assert getattr(AuditActionCategory, name).value == value


def test_record_methods_enforce_user_actor() -> None:
    svc = _service()
    rec = svc.record_release_candidate_created(actor_id="user-1", release_id="r1")
    assert rec.actor_kind == AuditActorKind.USER
    assert rec.category == AuditActionCategory.RELEASE_CANDIDATE_CREATED

    rec2 = svc.record_release_gate_evaluated(
        actor_id="user-2", release_id="r1", status="ready_for_human_review",
    )
    assert rec2.actor_kind == AuditActorKind.USER
    assert rec2.category == AuditActionCategory.RELEASE_GATE_EVALUATED

    rec3 = svc.record_release_manifest_generated(actor_id="user-3", release_id="r1")
    assert rec3.actor_kind == AuditActorKind.USER
    assert rec3.category == AuditActionCategory.RELEASE_MANIFEST_GENERATED

    rec4 = svc.record_release_signoff_recorded(
        actor_id="user-4",
        role=SignoffRole.PRODUCTION_OWNER,
        decision=SignoffDecision.GO,
        release_id="r1",
    )
    assert rec4.actor_kind == AuditActorKind.USER
    assert rec4.category == AuditActionCategory.RELEASE_SIGNOFF_RECORDED


def test_record_methods_reject_empty_actor() -> None:
    svc = _service()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_release_candidate_created(actor_id="", release_id="r1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_release_gate_evaluated(
            actor_id="", release_id="r1", status="x",
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_release_manifest_generated(actor_id="", release_id="r1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_release_signoff_recorded(
            actor_id="",
            role=SignoffRole.PRODUCTION_OWNER,
            decision=SignoffDecision.GO,
            release_id="r1",
        )


# =========================================================================== #
# 红线验证
# =========================================================================== #
def test_red_line_forbidden_calls_blocked() -> None:
    svc = _service()
    for name in _FORBIDDEN_CALLS:
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()


def test_engineering_enabled_unchanged_after_release_operations() -> None:
    before = load_engineering_enabled()
    assert before is False
    svc = _service()
    svc.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    svc.collect_evidence(release_id="r1", engineering_enabled=False)
    svc.build_manifest(release_version="1.0.0", commit_sha="abc")
    svc.build_rollback_reference(
        last_known_good_version="0.9.0", last_known_good_commit="def",
    )
    # 发布闸门操作绝不翻转 engineering_enabled（红线①）。
    assert load_engineering_enabled() is False


def test_service_wired_in_operation_layer() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_production_release, ProductionReleaseService)
    rc = layer.agent_production_release.create_release_candidate(
        release_id="r1", version="1.0.0", commit_sha="abc", branch="main",
    )
    assert rc.release_approved is False

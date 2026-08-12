"""Phase 3.9.2 企业生产发布闸门与证据包层 —— fail-closed 测试（T12 / agents 层）。

本测试专注**闸门层自身**的可验证不变量（红线①~⑩）。所有断言都围绕一件事：
无论输入如何，AI 路径**绝不**产出任何生产放行语义（APPROVED / 自动 GO / 代签 /
翻 engineering_enabled / 写密钥 / 执行部署），最终放行只能源于真实 USER 线下签署
``ReleaseSignoff``。

覆盖：
- T1 证据三态（verified / pending_verification / failed），AI 不把 pending 自动提升为 verified；
- T8 完整性校验（SHA-256 重算 / 缺哈希 / 文件不可达）；
- T2 发布候选 ``release_approved`` 恒 False（fail-closed）；
- T3 闸门三态（BLOCKED / PENDING_VERIFICATION / READY_FOR_HUMAN_REVIEW），永不 APPROVED；
- T4 人工签署：AI 构造禁名 ``create_human_signoff`` 被结构拦截；真实 USER 签署记录落审计；
  空 actor 拒绝；
- T6 清单 SHA-256；缺文件标 ``<missing>``；
- T7 回滚引用 ``verified`` 仅表示引用齐备，不执行真实回滚；
- T11 审计：4 个新增大类存在；actor_kind 恒 USER；审计总数 == 83；
- 禁名集基数；engineering_enabled 全程 False。

跨组织隔离 / RBAC 拒绝由 API 层负责（见 backend 测试）。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.production_release.forbidden import (
    PRODUCTION_RELEASE_FORBIDDEN_COUNT,
)
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
    ProductionReleaseCandidate,
    ProductionReleaseEvidence,
    ReleaseCandidateStatus,
    ReleaseDecisionDraftStatus,
    ReleaseGateStatus,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.production_release.service import ProductionReleaseService
from agents.enterprise.red_line import EnterpriseRedLineViolationError


ORG_A = "test-org-a"
ORG_B = "test-org-b"
RELEASE_ID = "RC-3.9.2"


@pytest.fixture()
def audit_a():
    # 真实 USER 上下文：AuditService 仅接受 safety_invariants_ok() 通过时构造。
    return AuditService(org_id=ORG_A)


@pytest.fixture()
def svc_a(audit_a):
    return ProductionReleaseService(org_id=ORG_A, audit=audit_a)


def _all_checks_true() -> dict:
    return {k: True for k in ProductionReleaseGateCheckKeys()}


def ProductionReleaseGateCheckKeys():  # 避免与 gate 模块强耦合，复制 13 键
    return [
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
    ]


# --------------------------------------------------------------------------- #
# 红线①：engineering_enabled 必须全程 False；构造受 safety_invariants_ok() 保护      #
# --------------------------------------------------------------------------- #
def test_engineering_enabled_is_false_in_test_env():
    """整个测试环境都建立在 engineering_enabled=False 之上（红线①）。"""
    assert load_engineering_enabled() is False


def test_service_construction_rejected_when_safety_invariants_broken(monkeypatch):
    """若 safety_invariants_ok() 失败（eng 启用），禁止构建发布闸门层（红线①）。"""

    # safety_invariants_ok() 在 red_line 模块内绑定 load_engineering_enabled，
    # 必须 patch 该模块级引用才能真正改变其返回值。
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        ProductionReleaseService(org_id=ORG_A, audit=AuditService(org_id=ORG_A))


# --------------------------------------------------------------------------- #
# T2：发布候选 release_approved 恒 False                                         #
# --------------------------------------------------------------------------- #
def test_release_candidate_created_with_release_approved_false(svc_a):
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID,
        version="3.9.2",
        commit_sha="abc123",
        branch="feat/phase3.9.2-production-release-gate",
    )
    assert rc.release_approved is False
    assert rc.status == ReleaseCandidateStatus.DRAFT
    assert rc.to_dict()["release_approved"] is False


def test_mark_awaiting_human_review_keeps_release_approved_false(svc_a):
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID,
        version="3.9.2",
        commit_sha="abc123",
        branch="b",
    )
    rc2 = svc_a.mark_awaiting_human_review(rc)
    assert rc2.release_approved is False
    assert rc2.status == ReleaseCandidateStatus.AWAITING_HUMAN_REVIEW


# --------------------------------------------------------------------------- #
# T1：证据三态 + AI 不自动提升 pending → verified                               #
# --------------------------------------------------------------------------- #
def test_evidence_three_verification_states(svc_a):
    ev_svc = svc_a._evidence_svc
    v = ev_svc.create_evidence(
        evidence_id="e1",
        evidence_type="security_scan",
        source="filesystem",
        source_reference="scripts/lint/check_production_security.py",
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    p = ev_svc.create_evidence(
        evidence_id="e2",
        evidence_type="human_signoff",
        source="human",
        source_reference="ReleaseSignoff",
    )
    f = ev_svc.create_evidence(
        evidence_id="e3",
        evidence_type="missing_report",
        source="filesystem",
        source_reference="does/not/exist.md",
        verification_status=EvidenceVerificationStatus.FAILED,
    )
    assert v.verification_status == EvidenceVerificationStatus.VERIFIED
    # 默认 PENDING_VERIFICATION（AI 不代填人工证据）
    assert p.verification_status == EvidenceVerificationStatus.PENDING_VERIFICATION
    assert f.verification_status == EvidenceVerificationStatus.FAILED


def test_collect_evidence_keeps_human_dependencies_pending(svc_a):
    """collect_release_evidence 把人工责任节点（签署 / 密钥）保持 PENDING，
    不冒称为 production verified（红线⑨/⑩）。"""
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID,
        test_baseline={"passed": "pending_verification"},
        audit_count=len(AuditActionCategory.__members__),
        engineering_enabled=load_engineering_enabled(),
    )
    by_type = {e.evidence_type: e for e in evidence}
    assert by_type["human_signoff"].verification_status == (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    assert by_type["production_secret"].verification_status == (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    # 客观事实（安全扫描器存在）可核验为 VERIFIED
    assert by_type["security_scan"].verification_status == (
        EvidenceVerificationStatus.VERIFIED
    )


# --------------------------------------------------------------------------- #
# T8：完整性校验（SHA-256 重算）                                                #
# --------------------------------------------------------------------------- #
def test_evidence_integrity_recompute(svc_a):
    ev_svc = svc_a._evidence_svc
    with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
        tf.write(b"release-artifact-3.9.2")
        path = tf.name
    try:
        import hashlib

        expected = hashlib.sha256(b"release-artifact-3.9.2").hexdigest()
        ev = ev_svc.create_evidence(
            evidence_id="e",
            evidence_type="artifact",
            source="filesystem",
            source_reference=path,
            sha256=expected,
        )
        assert ev_svc.verify_integrity(ev) == EvidenceIntegrityStatus.INTACT

        # 哈希不匹配 → TAMPERED
        ev_bad = ev_svc.create_evidence(
            evidence_id="e2",
            evidence_type="artifact",
            source="filesystem",
            source_reference=path,
            sha256="0" * 64,
        )
        assert ev_svc.verify_integrity(ev_bad) == EvidenceIntegrityStatus.TAMPERED
    finally:
        os.unlink(path)

    # 无 sha256 → PENDING
    ev_none = ev_svc.create_evidence(
        evidence_id="e3",
        evidence_type="artifact",
        source="filesystem",
        source_reference="/nope",
    )
    assert ev_svc.verify_integrity(ev_none) == EvidenceIntegrityStatus.PENDING

    # 文件不可达 → UNKNOWN
    ev_missing = ev_svc.create_evidence(
        evidence_id="e4",
        evidence_type="artifact",
        source="filesystem",
        source_reference="/no/such/file",
        sha256="a" * 64,
    )
    assert ev_svc.verify_integrity(ev_missing) == EvidenceIntegrityStatus.UNKNOWN


# --------------------------------------------------------------------------- #
# T3：闸门三态，永不 APPROVED                                                    #
# --------------------------------------------------------------------------- #
def test_gate_blocked_when_a_check_is_false(svc_a):
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID, engineering_enabled=False
    )
    scan = _all_checks_true()
    scan["full_test_results_green"] = False  # 真实 CI 未提供 → 阻断
    result = svc_a.evaluate_release_gate(candidate=rc, evidence=evidence, scan=scan)
    assert result.status == ReleaseGateStatus.BLOCKED
    assert "full_test_results_green" in result.missing
    assert result.status.value != "approved"


def test_gate_pending_when_evidence_still_pending(svc_a):
    """客观检查全过，但 human_signoff / production_secret 仍 PENDING → PENDING_VERIFICATION。"""
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID, engineering_enabled=False
    )
    result = svc_a.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_checks_true()
    )
    assert result.status == ReleaseGateStatus.PENDING_VERIFICATION
    assert result.status.value != "approved"


def test_gate_ready_for_human_review_but_never_approved(svc_a):
    """当所有证据均 VERIFIED（含模拟人工已签）且检查全过，闸门只给人工前置态，
    绝不 APPROVED / AUTO_APPROVED。"""
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    # 构造全 VERIFIED 证据链（含 human_signoff 已 verified 的模拟）
    evidence = [
        ProductionReleaseEvidence(
            evidence_id="ev-1",
                evidence_type="staging_validation",
                source="filesystem",
                source_reference=".ai/reviews/phase3.9.1_...md",
                created_at="2026-08-10T00:00:00Z",
                verification_status=EvidenceVerificationStatus.VERIFIED,
            ),
            ProductionReleaseEvidence(
                evidence_id="ev-2",
                evidence_type="human_signoff",
                source="human",
                source_reference="ReleaseSignoff",
                created_at="2026-08-10T00:00:00Z",
                verification_status=EvidenceVerificationStatus.VERIFIED,
            ),
            ProductionReleaseEvidence(
                evidence_id="ev-3",
                evidence_type="production_secret",
                source="human",
                source_reference="secret",
                created_at="2026-08-10T00:00:00Z",
                verification_status=EvidenceVerificationStatus.VERIFIED,
            ),
        ]
    result = svc_a.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_checks_true()
    )
    assert result.status == ReleaseGateStatus.READY_FOR_HUMAN_REVIEW
    # 关键不变量：任何情况下 AI 终态都不是 APPROVED
    assert result.status.value not in (
        "approved",
        "auto_approved",
        "engineering_approved",
    )


def test_gate_never_returns_approved_across_statuses(svc_a):
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID, engineering_enabled=False
    )
    for bad in ProductionReleaseGateCheckKeys():
        scan = _all_checks_true()
        scan[bad] = False
        r = svc_a.evaluate_release_gate(candidate=rc, evidence=evidence, scan=scan)
        assert r.status.value != "approved"


# --------------------------------------------------------------------------- #
# T4：人工签署 —— AI 不可代签；真实 USER 签署落审计                              #
# --------------------------------------------------------------------------- #
def test_ai_cannot_construct_human_signoff_via_forbidden_name(svc_a):
    """结构级拦截：禁名 create_human_signoff 调用即抛（红线⑦/⑧）。"""
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_a.create_human_signoff(  # type: ignore[attr-defined]
            role=SignoffRole.PRODUCTION_OWNER,
            decision=SignoffDecision.GO,
            reason="ai-trying",
        )


def test_ai_cannot_auto_approve_release(svc_a):
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_a.auto_approve_release()  # type: ignore[attr-defined]


def test_record_signoff_requires_real_user_actor(svc_a):
    """空 actor（非真实 USER）被拒绝（红线⑥/⑧）。"""
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_a.record_release_signoff_recorded(
            actor_id="",
            role=SignoffRole.PRODUCTION_OWNER,
            decision=SignoffDecision.GO,
            release_id=RELEASE_ID,
        )


def test_record_signoff_persists_as_user_audit(svc_a, audit_a):
    svc_a.record_release_signoff_recorded(
        actor_id="user-prod-owner",
        role=SignoffRole.PRODUCTION_OWNER,
        decision=SignoffDecision.NO_GO,
        release_id=RELEASE_ID,
        reason="待补充演练报告",
    )
    recs = audit_a.query(category=AuditActionCategory.RELEASE_SIGNOFF_RECORDED)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.actor_kind == AuditActorKind.USER
    assert rec.actor_id == "user-prod-owner"
    assert "signoff_production-owner_no_go" in rec.action


def test_cross_org_signoff_audit_isolation(svc_a, audit_a):
    """同一审计服务按 org 作用域隔离（跨组织查询看不到对方记录）。"""
    svc_a.record_release_signoff_recorded(
        actor_id="user-a",
        role=SignoffRole.AUDITOR,
        decision=SignoffDecision.GO,
        release_id=RELEASE_ID,
    )
    audit_b = AuditService(org_id=ORG_B)
    assert audit_b.query(category=AuditActionCategory.RELEASE_SIGNOFF_RECORDED) == []
    assert len(audit_a.query(category=AuditActionCategory.RELEASE_SIGNOFF_RECORDED)) == 1


# --------------------------------------------------------------------------- #
# T5：Go/No-Go 草稿只生成草稿，不生成 GO_LIVE_APPROVED                         #
# --------------------------------------------------------------------------- #
def test_decision_draft_is_never_go_live_approved(svc_a):
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID, engineering_enabled=False
    )
    gate = svc_a.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_checks_true()
    )
    draft = svc_a.build_decision_draft(
        release_id=RELEASE_ID, candidate=rc, evidence=evidence, gate=gate
    )
    assert draft.status.value != "go_live_approved"
    assert draft.status.value in (
        "ready_for_human_go_no_go",
        "blocked",
        "needs_more_evidence",
    )
    assert len(draft.risks) >= 1


# --------------------------------------------------------------------------- #
# T6：清单 SHA-256；缺文件标 <missing>                                        #
# --------------------------------------------------------------------------- #
def test_manifest_sha256_for_existing_artifact(svc_a):
    manifest = svc_a.build_manifest(
        release_version="3.9.2",
        commit_sha="abc",
        artifacts={"models": "agents/enterprise/production_release/models.py"},
    )
    h = manifest.artifact_hashes["models"]
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_manifest_missing_artifact_is_not_faked(svc_a):
    manifest = svc_a.build_manifest(
        release_version="3.9.2",
        commit_sha="abc",
        artifacts={"ghost": "path/does/not/exist.txt"},
    )
    assert manifest.artifact_hashes["ghost"] == "<missing>"


# --------------------------------------------------------------------------- #
# T7：回滚引用 verified 仅表示引用齐备，不执行真实回滚                          #
# --------------------------------------------------------------------------- #
def test_rollback_reference_verified_means_refs_complete(svc_a):
    ref = svc_a.build_rollback_reference(
        last_known_good_version="3.9.1",
        last_known_good_commit="def456",
        database_revision="alembic@head",
        config_baseline="agents/config.yaml",
        rollback_steps_reference=".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
        recovery_validation_reference=".ai/reviews/phase3.9.1_...md",
    )
    assert ref.verified is True
    assert ref.to_dict()["note"].startswith("ROLLBACK_REF_ONLY")


def test_rollback_reference_incomplete_is_not_verified(svc_a):
    ref = svc_a.build_rollback_reference(
        last_known_good_version="3.9.1",
        last_known_good_commit="def456",
        # 其余引用缺失 → verified=False
    )
    assert ref.verified is False


# --------------------------------------------------------------------------- #
# T11：审计 4 新增大类 + 总数 83 + actor_kind 恒 USER                          #
# --------------------------------------------------------------------------- #
def test_new_release_audit_categories_exist():
    for cat in (
        "RELEASE_CANDIDATE_CREATED",
        "RELEASE_GATE_EVALUATED",
        "RELEASE_SIGNOFF_RECORDED",
        "RELEASE_MANIFEST_GENERATED",
    ):
        assert hasattr(AuditActionCategory, cat), f"缺少审计大类 {cat}"


def test_audit_category_total_not_regressed():
    """审计总数权威断言只保留在
    tests/agents/test_enterprise_knowledge_governance_audit.py（== 83）。
    本层仅做非递减护栏：3.9.2 在 3.9.1(79) 基础上 +4 = 83，不得倒退。"""
    assert len(AuditActionCategory.__members__) >= 83


def test_release_audit_record_category_and_actor(svc_a, audit_a):
    svc_a.record_release_candidate_created(
        actor_id="user-pm", release_id=RELEASE_ID
    )
    svc_a.record_release_gate_evaluated(
        actor_id="user-pm", release_id=RELEASE_ID, status="ready_for_human_review"
    )
    svc_a.record_release_manifest_generated(
        actor_id="user-pm", release_id=RELEASE_ID
    )
    for cat in (
        AuditActionCategory.RELEASE_CANDIDATE_CREATED,
        AuditActionCategory.RELEASE_GATE_EVALUATED,
        AuditActionCategory.RELEASE_MANIFEST_GENERATED,
    ):
        recs = audit_a.query(category=cat)
        assert len(recs) == 1
        assert recs[0].actor_kind == AuditActorKind.USER


# --------------------------------------------------------------------------- #
# 禁名集 / 结构拦截完整性                                                       #
# --------------------------------------------------------------------------- #
def test_forbidden_name_set_is_substantial():
    assert PRODUCTION_RELEASE_FORBIDDEN_COUNT >= 300


def test_service_forbidden_set_contains_release_specific_names(svc_a):
    for name in (
        "create_human_signoff",
        "auto_approve_release",
        "deploy_production_for_real",
        "write_real_production_secret",
        "grant_real_production_permission",
    ):
        assert name in svc_a._FORBIDDEN


# --------------------------------------------------------------------------- #
# 端到端：全程 engineering_enabled 仍 False，release_approved 仍 False         #
# --------------------------------------------------------------------------- #
def test_end_to_end_no_production_release_emitted(svc_a):
    assert load_engineering_enabled() is False
    rc = svc_a.create_release_candidate(
        release_id=RELEASE_ID, version="3.9.2", commit_sha="abc", branch="b"
    )
    evidence = svc_a.collect_evidence(
        release_id=RELEASE_ID, engineering_enabled=False
    )
    gate = svc_a.evaluate_release_gate(
        candidate=rc, evidence=evidence, scan=_all_checks_true()
    )
    manifest = svc_a.build_manifest(
        release_version="3.9.2",
        commit_sha="abc",
        artifacts={"models": "agents/enterprise/production_release/models.py"},
    )
    rollback = svc_a.build_rollback_reference(
        last_known_good_version="3.9.1",
        last_known_good_commit="def456",
        database_revision="alembic@head",
        config_baseline="agents/config.yaml",
        rollback_steps_reference=".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
        recovery_validation_reference=".ai/reviews/phase3.9.1_...md",
    )
    draft = svc_a.build_decision_draft(
        release_id=RELEASE_ID, candidate=rc, evidence=evidence, gate=gate
    )
    # 全链路不变量
    assert rc.release_approved is False
    assert gate.status.value != "approved"
    assert draft.status.value != "go_live_approved"
    assert "3.9.1" in rollback.last_known_good_version
    assert len(manifest.artifact_hashes["models"]) == 64
    # 环境未因本测试被改变
    assert load_engineering_enabled() is False

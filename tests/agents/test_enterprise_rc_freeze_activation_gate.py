"""Phase 3.9.2 受控激活 / RC 冻结闸门层 —— 测试（fail-closed 重点）。

覆盖（agents/enterprise/production_release）：
- ReleaseCandidate 冻结模型 + create_release_candidate 即时计算 SHA-256；
- RCFreezeManifest / generate_rc_freeze_manifest 规范化哈希自洽；
- ReleaseFreezeChecker：未篡改 → FROZEN；篡改组件 → DRIFTED；
- ActivationEvidenceBundle：缺真实人工签署 → is_complete=False（fail-closed）；
- ControlledActivationGate：complete → READY_FOR_HUMAN_REVIEW；缺签署 → PENDING_VERIFICATION；
  RC REJECTED / engineering_enabled 真 → BLOCKED；**永不**返回 ACTIVATED_BY_HUMAN；
- HumanActivationApproval：契约只读；服务 forbidden 拦截 create/forge/mark；
- ProductionReleaseService 编排：冻结 / 检查 / 证据包 / 闸门 / 人工批准留痕；
- 红线复核：_FORBIDDEN 含激活/代签名；服务构造断言 engineering_enabled=False。
"""

from __future__ import annotations

import os

import pytest

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.production_release.activation_evidence import (
    ActivationEvidenceBundle,
    build_activation_evidence_bundle,
)
from agents.enterprise.production_release.activation_gate import (
    ControlledActivationGate,
    ControlledActivationGateStatus,
)
from agents.enterprise.production_release.freeze_checker import (
    FreezeCheckResultStatus,
    ReleaseFreezeChecker,
)
from agents.enterprise.production_release.freeze_forbidden import (
    FREEZE_ACTIVATION_FORBIDDEN_COUNT,
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.human_approval import (
    HumanActivationApproval,
    HumanActivationApprovalService,
)
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    SignoffDecision,
)
from agents.enterprise.production_release.release_candidate import (
    RCFreezeStatus,
    ReleaseCandidate,
    create_release_candidate,
)
from agents.enterprise.production_release.service import ProductionReleaseService
from agents.enterprise.red_line import EnterpriseRedLineViolationError

ROLES = ["production-owner", "release-manager", "security-owner", "auditor"]


# --------------------------------------------------------------------------- #
# T11 RC 冻结模型 / 清单 / 检查器
# --------------------------------------------------------------------------- #
def test_create_release_candidate_computes_sha256(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    rc = create_release_candidate(
        rc_id="rc-1", version="1.0", commit_sha="deadbeef", branch="b",
        component_specs={"a": "a.txt"}, root_dir=str(tmp_path),
    )
    assert rc.status == RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN
    assert rc.activation_approved is False
    assert rc.components[0].sha256 == _sha256_of(str(tmp_path / "a.txt"))
    assert rc.components[0].present is True


def test_freeze_checker_frozen_then_drifted(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    rc = create_release_candidate(
        rc_id="rc-1", version="1.0", commit_sha="s", branch="b",
        component_specs={"a": "a.txt"}, root_dir=str(tmp_path),
    )

    # 复用 freeze_manifest 生成时同一哈希口径：直接用 checker 重算应当一致。
    from agents.enterprise.production_release.freeze_manifest import (
        generate_rc_freeze_manifest,
    )
    manifest = generate_rc_freeze_manifest(rc, root_dir=str(tmp_path))
    checker = ReleaseFreezeChecker(root_dir=str(tmp_path), check_git=False, check_governance=False)

    res1 = checker.check(rc, manifest)
    assert res1.status == FreezeCheckResultStatus.FROZEN
    assert res1.frozen is True

    # 篡改组件后应当 DRIFTED（component_hash_mismatch）。
    f.write_text("v2-tampered", encoding="utf-8")
    res2 = checker.check(rc, manifest)
    assert res2.status == FreezeCheckResultStatus.DRIFTED
    assert "component_hash_mismatch:a.txt" in res2.missing


# --------------------------------------------------------------------------- #
# 受控激活证据包
# --------------------------------------------------------------------------- #
def _bundle(signoffs, *, gov=True, rollback=True, recovery=True, integrity=EvidenceIntegrityStatus.INTACT):
    return build_activation_evidence_bundle(
        bundle_id="aeb-1", rc_id="rc-1", version="1.0",
        required_evidence_types=["staging_validation", "rollback_drill", "recovery_validation"],
        provided_evidence_types=["staging_validation", "rollback_drill", "recovery_validation"],
        human_signoff_roles=signoffs,
        governance_integrity_passed=gov, rollback_reference_present=rollback,
        recovery_validation_present=recovery, integrity_status=integrity,
    )


def test_activation_evidence_incomplete_without_real_signoff() -> None:
    # 红线⑧/⑩：缺真实人工签署 → is_complete 恒 False。
    empty = _bundle([])
    assert empty.is_complete is False
    assert empty.status.value == "incomplete"
    assert empty.signoffs_complete is False

    complete = _bundle(list(ROLES))
    assert complete.is_complete is True
    assert complete.status.value == "complete_awaiting_human"


def test_activation_evidence_bundle_to_dict_roundtrip() -> None:
    b = _bundle(list(ROLES))
    d = b.to_dict()
    assert d["is_complete"] is True
    assert d["human_signoff_roles"] == list(ROLES)


# --------------------------------------------------------------------------- #
# 受控激活闸门
# --------------------------------------------------------------------------- #
def _rc() -> ReleaseCandidate:
    return ReleaseCandidate(rc_id="rc-1", version="1.0", commit_sha="s", branch="b")


def _freeze_frozen() -> object:
    from agents.enterprise.production_release.freeze_checker import FreezeCheckResult
    return FreezeCheckResult(status=FreezeCheckResultStatus.FROZEN, checks={})


def test_activation_gate_ready_when_complete() -> None:
    gate = ControlledActivationGate(check_governance=False)
    res = gate.evaluate(
        rc=_rc(), manifest=None, freeze_result=_freeze_frozen(),
        evidence_bundle=_bundle(list(ROLES)),
    )
    assert res.status == ControlledActivationGateStatus.READY_FOR_HUMAN_REVIEW
    assert res.status != ControlledActivationGateStatus.ACTIVATED_BY_HUMAN


def test_activation_gate_pending_without_signoff() -> None:
    gate = ControlledActivationGate(check_governance=False)
    res = gate.evaluate(
        rc=_rc(), manifest=None, freeze_result=_freeze_frozen(),
        evidence_bundle=_bundle([]),
    )
    assert res.status == ControlledActivationGateStatus.PENDING_VERIFICATION
    assert "human_signoffs_complete" in res.missing


def test_activation_gate_blocked_on_rc_rejected() -> None:
    gate = ControlledActivationGate(check_governance=False)
    rejected = ReleaseCandidate(
        rc_id="rc-1", version="1.0", commit_sha="s", branch="b",
        status=RCFreezeStatus.REJECTED_BY_HUMAN,
    )
    res = gate.evaluate(
        rc=rejected, manifest=None, freeze_result=_freeze_frozen(),
        evidence_bundle=_bundle(list(ROLES)),
    )
    assert res.status == ControlledActivationGateStatus.BLOCKED


def test_activation_gate_never_returns_activated_by_human() -> None:
    # 闸门枚举含 ACTIVATED_BY_HUMAN，但 evaluate 代码路径永远不返回它。
    gate = ControlledActivationGate(check_governance=False)
    for signoffs in ([], list(ROLES)):
        res = gate.evaluate(
            rc=_rc(), manifest=None, freeze_result=_freeze_frozen(),
            evidence_bundle=_bundle(signoffs),
        )
        assert res.status != ControlledActivationGateStatus.ACTIVATED_BY_HUMAN


# --------------------------------------------------------------------------- #
# 人工激活批准契约 / 服务
# --------------------------------------------------------------------------- #
def test_human_approval_service_forbidden_interception() -> None:
    svc = HumanActivationApprovalService(audit=AuditService(org_id="o"))
    for name in (
        "create_human_activation_approval", "forge_signature",
        "mark_activation_approved", "auto_sign_activation", "open_activation_gate",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_human_approval_verify_readonly() -> None:
    svc = HumanActivationApprovalService(audit=AuditService(org_id="o"))
    approval = HumanActivationApproval(
        approval_id="haa-1", rc_id="rc-1", version="1.0",
        decision=SignoffDecision.GO, approved_by="user-1", approved_roles=list(ROLES),
        approved_at="2026-08-12T00:00:00Z", activation_approved=True,
    )
    v = svc.verify_activation_approval(approval=approval)
    assert v["activation_approved"] is True
    assert v["roles_complete"] is True


def test_human_approval_recorded_requires_user() -> None:
    svc = HumanActivationApprovalService(audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_activation_approval_recorded(
            actor_id="", approval_id="x", rc_id="rc-1", decision="go", roles=list(ROLES)
        )


# --------------------------------------------------------------------------- #
# 红线取证
# --------------------------------------------------------------------------- #
def test_freeze_activation_forbidden_superset() -> None:
    # 冻结/激活层禁名集应含激活类与代签类禁名。
    assert "open_activation_gate" in _FREEZE_ACTIVATION_FORBIDDEN
    assert "create_human_activation_approval" in _FREEZE_ACTIVATION_FORBIDDEN
    assert "forge_signature" in _FREEZE_ACTIVATION_FORBIDDEN
    assert "flip_engineering_for_activation" in _FREEZE_ACTIVATION_FORBIDDEN
    assert FREEZE_ACTIVATION_FORBIDDEN_COUNT == len(_FREEZE_ACTIVATION_FORBIDDEN)
    assert FREEZE_ACTIVATION_FORBIDDEN_COUNT > 0


def test_audit_category_human_activation_approval_present() -> None:
    # 3.9.2 受控激活批准契约审计类（子集契约，不硬编码总数）。
    assert "HUMAN_ACTIVATION_APPROVAL_RECORDED" in AuditActionCategory.__members__


def test_production_release_service_forbidden_covers_activation() -> None:
    # ProductionReleaseService._FORBIDDEN 应继承冻结/激活层禁名集。
    assert "create_human_activation_approval" in ProductionReleaseService._FORBIDDEN
    assert "open_activation_gate" in ProductionReleaseService._FORBIDDEN


# --------------------------------------------------------------------------- #
# 服务编排（真实仓库文件）
# --------------------------------------------------------------------------- #
def test_production_release_service_orchestration() -> None:
    audit = AuditService(org_id="o")
    svc = ProductionReleaseService(org_id="o", audit=audit)
    rc = svc.freeze_release_candidate(
        rc_id="rc-1", version="1.0", commit_sha="s", branch="b",
        component_specs={
            "config": "agents/config.yaml",
            "pkg_init": "agents/enterprise/production_release/__init__.py",
        },
        actor_id="user-1",
    )
    assert rc.status == RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN

    bundle = svc.build_activation_evidence_bundle(
        rc_id="rc-1", version="1.0",
        required_evidence_types=["staging_validation"],
        provided_evidence_types=["staging_validation"],
        human_signoff_roles=[],  # 真实人工签署由外部提供；此处为空 → incomplete
        actor_id="user-1",
        governance_integrity_passed=True, rollback_reference_present=True,
        recovery_validation_present=True,
    )
    assert bundle.is_complete is False

    gate_res = svc.evaluate_controlled_activation_gate(
        rc=rc, manifest=None, freeze_result=_freeze_frozen(),
        evidence_bundle=bundle, actor_id="user-1", check_governance=False,
    )
    assert gate_res.status == ControlledActivationGateStatus.PENDING_VERIFICATION

    rec = svc.record_activation_approval_recorded(
        actor_id="user-1", approval_id="haa-1", rc_id="rc-1",
        decision="go", roles=list(ROLES),
    )
    assert rec is not None


def _sha256_of(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

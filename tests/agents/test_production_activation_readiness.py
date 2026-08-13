"""Phase 3.9.6 生产激活证据准备层 —— fail-closed 测试套件（Task 28）。

全部用例守 fail-closed 纪律：AI 永不宣称 APPROVED / GO / PRODUCTION_READY / 自动激活；
任何 fail-closed 行为变更均不得用 skip / xfail 绕过至绿（红线⑧）。

覆盖：
- dossier 组装与终端态（BUILT_NO_GO / engineering_enabled=false / 闸门 blocked / 契约未放行）；
- ProductionActivationReadinessGate（8 检查，永不 APPROVED，fail-closed）；
- EngineeringActivationContract；
- HumanSignoffRegistry / build_human_signoff_record（强制 user 主体）；
- SoDValidator；
- EvidenceScope（合成演练 PASS ≠ 生产已验证）；
- 结构级禁名（340 项，含 set_engineering_enabled / activate_production / deploy_production）；
- 后端 API 8 路由且无 /activate / /deploy-production；
- 前端看板契约（无自动 GO / 激活 / 部署）；
- CI 门禁 yml 引用与 job 数；
- 机器可读复核包 JSON（contains_real_secret=False）。
- Layer B 服务层（T5/T8）：ActivationEvidenceIntakeService 提交/裁决/汇总、build_review_package；
- Layer B fail-closed：AI 不可 approved、GO 需 READY 评审包、human_go_recorded 仅标志不激活；
- T13 证据存储安全（只存引用与哈希，拒 inline 正文/裸密钥）；
- T12 权限边界（deny-by-default 白名单，AI/SYSTEM 一律 403）；
- 后端 API 14 路由且无 /activate / /deploy-production（含新增 GET /evidence-list）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.production_release import activation_readiness as ar
from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
)
from agents.enterprise.production_release.activation_intake import (
    ActivationEvidenceSubmissionStatus,
    build_chain_of_custody,
    build_evidence_provenance,
    REQUIRED_ACTIVATION_EVIDENCE_TYPES,
)
from agents.enterprise.production_release.evidence_storage_safety import (
    EvidenceStoragePolicy,
    EvidenceStorageSafetyError,
    compute_evidence_sha256,
)
from agents.enterprise.production_release.final_decision import (
    FinalDecisionOutcome,
    FinalHumanDecisionError,
    FinalHumanDecisionLedger,
    build_final_human_activation_decision,
)
from agents.enterprise.production_release.human_signoff import (
    HumanSignoffRegistry,
    build_human_signoff_record,
)
from agents.enterprise.production_release.intake_service import (
    ActivationEvidenceIntakeService,
    ActivationIntakeServiceError,
)
from agents.enterprise.production_release.models import SignoffDecision, SignoffRole
from agents.enterprise.production_release.permission_boundary import (
    ActivationOperation,
    ActivationPermissionBoundary,
    ActivationPermissionBoundaryError,
    PERM_RELEASE_READ,
    PERM_RELEASE_SIGNOFF,
    require_activation_operation,
)
from agents.enterprise.production_release.review_package import (
    FinalActivationReviewPackage,
    ReviewPackageReadiness,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError

ROOT = Path(__file__).resolve().parents[2]
RC_ID = "RC-3.9.6"
TERMINAL = "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO"


# ---------------------------------------------------------------------------
# 1. dossier 组装与终端态
# ---------------------------------------------------------------------------
class TestDossierAssembly:
    def _d(self) -> dict:
        return ar.assemble_activation_readiness_dossier(
            rc_id=RC_ID, root_dir=str(ROOT), signoff_registry=HumanSignoffRegistry(rc_id=RC_ID)
        )

    def test_terminal_status_built_no_go(self) -> None:
        assert self._d()["status_terminal"] == TERMINAL

    def test_engineering_enabled_false(self) -> None:
        assert self._d()["engineering_enabled"] is False

    def test_readiness_gate_blocked(self) -> None:
        assert self._d()["readiness_gate"]["status"] == "blocked"

    def test_contract_activation_not_allowed(self) -> None:
        assert self._d()["contract"]["activation_allowed_for_human"] is False

    def test_evidence_bundle_incomplete(self) -> None:
        assert self._d()["evidence_bundle"]["production_evidence_complete"] is False

    def test_six_blockers(self) -> None:
        assert len(self._d()["blockers"]) == 6

    def test_six_pending(self) -> None:
        assert len(self._d()["pending_verification"]) == 6

    def test_four_signoff_requirements(self) -> None:
        reqs = self._d()["signoff_requirements"]
        assert len(reqs) == 4
        roles = {r["required_role"] for r in reqs}
        assert roles == set(REQUIRED_SIGNOFF_ROLES)

    def test_sod_present(self) -> None:
        sod = self._d()["sod"]
        assert "ok" in sod and "four_roles_present" in sod


# ---------------------------------------------------------------------------
# 2. ProductionActivationReadinessGate
# ---------------------------------------------------------------------------
class TestProductionActivationReadinessGate:
    def _gate(self) -> ar.ProductionActivationReadinessGate:
        return ar.ProductionActivationReadinessGate()

    def test_check_keys_exactly_eight(self) -> None:
        assert ar.ProductionActivationReadinessGate.CHECK_KEYS == (
            "engineering_enabled_false",
            "evidence_bundle_complete",
            "governance_integrity_9_9",
            "rollback_reference_present",
            "recovery_validation_present",
            "no_activation_blockers",
            "human_signoffs_complete",
            "no_pending_verification",
        )

    def test_never_returns_approved(self) -> None:
        gate = self._gate()
        obj = all_true = dict(
            engineering_enabled=False,
            evidence_bundle_complete=True,
            governance_integrity_ok=True,
            rollback_reference_present=True,
            recovery_validation_present=True,
            blockers=[],
            pending_items=[],
            signoff_complete=True,
        )
        # 即便全 true（客观 + 签署 + 无 pending），也只到 READY_FOR_HUMAN_SIGNOFF，绝不 APPROVED。
        res = gate.evaluate(**obj)
        assert res.status.value == "ready_for_human_signoff"
        assert "approved" not in res.status.value
        # 穷举若干组合，确认永不出现 approved。
        for eng in (False, True):
            for ev in (False, True):
                for sig in (False, True):
                    for pend in (False, True):
                        r = gate.evaluate(
                            engineering_enabled=eng,
                            evidence_bundle_complete=ev,
                            governance_integrity_ok=True,
                            rollback_reference_present=True,
                            recovery_validation_present=True,
                            blockers=[] if ev else [object()],
                            pending_items=[] if not pend else [object()],
                            signoff_complete=sig,
                        )
                        assert r.status.value != "approved"

    def test_hard_missing_blocks(self) -> None:
        gate = self._gate()
        res = gate.evaluate(
            engineering_enabled=False,
            evidence_bundle_complete=False,  # 硬检查缺失
            governance_integrity_ok=False,
            rollback_reference_present=True,
            recovery_validation_present=True,
            blockers=[],
            pending_items=[],
            signoff_complete=True,
        )
        assert res.status == ar.ActivationReadinessStatus.BLOCKED

    def test_engineering_enabled_true_blocks_even_if_others_pass(self) -> None:
        gate = self._gate()
        res = gate.evaluate(
            engineering_enabled=True,  # 红线①：即便其余全过也必须失败
            evidence_bundle_complete=True,
            governance_integrity_ok=True,
            rollback_reference_present=True,
            recovery_validation_present=True,
            blockers=[],
            pending_items=[],
            signoff_complete=True,
        )
        assert res.status == ar.ActivationReadinessStatus.BLOCKED
        assert res.checks["engineering_enabled_false"] is False

    def test_pending_or_signoff_incomplete_yields_pending_verification(self) -> None:
        gate = self._gate()
        res = gate.evaluate(
            engineering_enabled=False,
            evidence_bundle_complete=True,
            governance_integrity_ok=True,
            rollback_reference_present=True,
            recovery_validation_present=True,
            blockers=[],
            pending_items=[object()],  # 仍有 pending
            signoff_complete=True,
        )
        assert res.status == ar.ActivationReadinessStatus.PENDING_VERIFICATION

    def test_forbidden_contains_set_engineering_enabled(self) -> None:
        assert "set_engineering_enabled" in ar.ProductionActivationReadinessGate._FORBIDDEN

    def test_forbidden_contains_activate_and_deploy_production(self) -> None:
        f = ar.ProductionActivationReadinessGate._FORBIDDEN
        assert "activate_production" in f
        assert "deploy_production" in f
        assert "write_production_secret" in f


# ---------------------------------------------------------------------------
# 3. 结构级禁名
# ---------------------------------------------------------------------------
class TestForbiddenCatalog:
    def test_activation_readiness_forbidden_count_340(self) -> None:
        assert ar.ACTIVATION_READINESS_FORBIDDEN_COUNT == 340

    def test_extra_forbidden_nonempty(self) -> None:
        assert ar.ACTIVATION_READINESS_EXTRA_FORBIDDEN_COUNT > 0


# ---------------------------------------------------------------------------
# 4. EngineeringActivationContract
# ---------------------------------------------------------------------------
class TestEngineeringActivationContract:
    def test_dataclass_fields_present(self) -> None:
        import dataclasses

        fields = {f.name for f in dataclasses.fields(ar.EngineeringActivationContract)}
        assert {
            "required_gates",
            "required_evidence",
            "required_signoffs",
            "blocker_count",
            "pending_count",
            "activation_allowed_for_human",
        } <= fields

    def test_to_dict_note_present_and_not_allowed(self) -> None:
        d = ar.assemble_activation_readiness_dossier(
            rc_id=RC_ID, root_dir=str(ROOT), signoff_registry=HumanSignoffRegistry(rc_id=RC_ID)
        )["contract"]
        assert d["activation_allowed_for_human"] is False
        assert "activation_allowed_for_human" in d
        assert isinstance(d["required_signoffs"], list) and len(d["required_signoffs"]) == 4


# ---------------------------------------------------------------------------
# 5. HumanSignoffRegistry / build_human_signoff_record
# ---------------------------------------------------------------------------
class TestHumanSignoff:
    def test_rejects_non_user_actor(self) -> None:
        with pytest.raises(Exception):
            build_human_signoff_record(
                signoff_id="s1",
                rc_id=RC_ID,
                role=SignoffRole.AUDITOR.value,
                decision=SignoffDecision.GO.value,
                actor_id="ai-bot",
                actor_kind="ai",  # 红线：非 user 必须拒绝
                signature_reference="SIG-1",
            )

    def test_rejects_empty_signature_reference(self) -> None:
        with pytest.raises(Exception):
            build_human_signoff_record(
                signoff_id="s2",
                rc_id=RC_ID,
                role=SignoffRole.AUDITOR.value,
                decision=SignoffDecision.GO.value,
                actor_id="user-1",
                actor_kind="user",
                signature_reference="",  # 空签名必须拒绝
            )

    def test_rejects_empty_actor_id(self) -> None:
        with pytest.raises(Exception):
            build_human_signoff_record(
                signoff_id="s3",
                rc_id=RC_ID,
                role=SignoffRole.AUDITOR.value,
                decision=SignoffDecision.GO.value,
                actor_id="",
                actor_kind="user",
                signature_reference="SIG-3",
            )

    def test_empty_registry_signoff_incomplete(self) -> None:
        snap = HumanSignoffRegistry(rc_id=RC_ID).snapshot()
        assert snap.signoff_complete is False
        assert snap.effective_records == ()

    def test_required_signoff_actor_kind_is_user(self) -> None:
        from agents.enterprise.production_release.human_signoff import (
            REQUIRED_SIGNOFF_ACTOR_KIND,
        )

        assert REQUIRED_SIGNOFF_ACTOR_KIND == "user"


# ---------------------------------------------------------------------------
# 6. SoDValidator
# ---------------------------------------------------------------------------
class TestSoDValidator:
    def test_empty_registry_not_ok(self) -> None:
        res = ar.SoDValidator.validate(HumanSignoffRegistry(rc_id=RC_ID))
        assert res.ok is False
        assert res.to_dict()["ok"] is False

    def test_empty_registry_four_roles_not_present(self) -> None:
        res = ar.SoDValidator.validate(HumanSignoffRegistry(rc_id=RC_ID))
        assert res.four_roles_present is False

    def test_result_has_required_keys(self) -> None:
        d = ar.SoDValidator.validate(HumanSignoffRegistry(rc_id=RC_ID)).to_dict()
        for k in (
            "four_roles_present",
            "all_real_user",
            "policy_distinct_natural_persons",
            "distinct_actor_ids",
            "ok",
        ):
            assert k in d


# ---------------------------------------------------------------------------
# 7. EvidenceScope（合成演练 PASS ≠ 生产已验证）
# ---------------------------------------------------------------------------
class TestEvidenceScope:
    def test_only_production_is_real(self) -> None:
        assert ar.EvidenceScope.PRODUCTION.is_real_production is True

    def test_synthetic_not_real(self) -> None:
        assert ar.EvidenceScope.SYNTHETIC.is_real_production is False

    def test_staging_and_human_not_real(self) -> None:
        assert ar.EvidenceScope.STAGING.is_real_production is False
        assert ar.EvidenceScope.HUMAN.is_real_production is False

    def test_synthetic_drill_pass_not_equivalent_production(self) -> None:
        # 红线⑯：合成演练通过不得被视作生产验证。
        assert ar.EvidenceScope.SYNTHETIC != ar.EvidenceScope.PRODUCTION


# ---------------------------------------------------------------------------
# 8. 枚举与角色常量
# ---------------------------------------------------------------------------
class TestEnumsAndRoles:
    def test_activation_readiness_status_has_no_approved(self) -> None:
        assert not hasattr(ar.ActivationReadinessStatus, "APPROVED")
        assert [m.name for m in ar.ActivationReadinessStatus] == [
            "BLOCKED",
            "PENDING_VERIFICATION",
            "READY_FOR_HUMAN_SIGNOFF",
        ]

    def test_required_signoff_roles_four(self) -> None:
        assert REQUIRED_SIGNOFF_ROLES == (
            "production-owner",
            "release-manager",
            "security-owner",
            "auditor",
        )

    def test_signoff_role_and_decision_values(self) -> None:
        assert [m.value for m in SignoffRole] == [
            "production-owner",
            "release-manager",
            "security-owner",
            "auditor",
        ]
        assert [m.value for m in SignoffDecision] == ["go", "no_go", "need_more_evidence"]


# ---------------------------------------------------------------------------
# 9. build_default 工厂
# ---------------------------------------------------------------------------
class TestBuildDefaults:
    def test_signoff_requirements_four_unsatisfied(self) -> None:
        reqs = ar.build_default_signoff_requirements(HumanSignoffRegistry(rc_id=RC_ID))
        assert len(reqs) == 4
        for r in reqs:
            assert r.is_satisfied is False

    def test_blockers_six(self) -> None:
        assert len(ar.build_default_activation_blockers()) == 6

    def test_pending_six(self) -> None:
        assert len(ar.build_default_pending_verification_registry()) == 6

    def test_review_packet_factory_exists(self) -> None:
        # ProductionHumanReviewPacket 必须由真实数据构造（API 层），此处仅确认类存在。
        assert hasattr(ar, "ProductionHumanReviewPacket")


# ---------------------------------------------------------------------------
# 10. 机器可读复核包 JSON
# ---------------------------------------------------------------------------
class TestReviewPacketArtifact:
    def test_packet_json_exists_and_no_real_secret(self) -> None:
        p = ROOT / ".ai" / "release-gate" / "production_activation_review_packet.json"
        assert p.is_file(), "复核包 JSON 未生成（先运行 generate_production_activation_review_packet.py）"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["contains_real_secret"] is False
        assert data["terminal_status"] == TERMINAL
        assert data["automated_approval_prohibited"] is True
        assert data["readiness_gate"]["status"] in ("blocked", "pending_verification")


# ---------------------------------------------------------------------------
# 11. 后端 API 路由契约
# ---------------------------------------------------------------------------
def _activation_router():
    backend_dir = str(ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from app.api.governance_activation import router

    return router


class TestActivationAPIRoutes:
    def test_routes_no_forbidden_endpoint(self) -> None:
        router = _activation_router()
        paths = sorted({getattr(r, "path", "") for r in router.routes})
        activation = [p for p in paths if p.startswith("/governance/activation")]
        # Layer A(7) + Layer B(7，含 T15 的 GET /evidence-list) + Layer C(9 最终评审只读)：
        #   Layer A: /readiness /blockers /pending-verifications /signoff-requirements
        #            /contract /review-packet /signoff(POST)
        #   Layer B: /intake-summary /decision-ledger /evidence(GET+POST 共享路径)
        #            /evidence-list(GET) /evidence-decision /review-package(POST) /final-decision
        #   Layer C: /final-review/{evidence-snapshot,completeness-matrix,signoff-matrix,
        #            signoff-conflicts,evidence-drift,review-packet,readiness,verify-decision,
        #            handoff-package}（9 个只读 GET，Phase 3.9.7 T14）
        # 注：/evidence 同时有 GET+POST，故 24 条路由对应 23 个去重路径。
        assert len(activation) == 23, activation
        # T15 新增的只读证据列表端点必须存在（供 Layer B 人工裁决下拉选 submission_id）。
        assert "/governance/activation/evidence-list" in activation
        # 禁设任何 /activate 或 /deploy-production 端点。
        assert not any(p.rstrip("/").endswith("activate") for p in activation)
        assert not any(p.rstrip("/").endswith("deploy-production") for p in activation)

    def test_post_routes_are_layer_b_governed(self) -> None:
        router = _activation_router()
        posts = sorted(
            getattr(r, "path", "")
            for r in router.routes
            if "POST" in (getattr(r, "methods", None) or set())
        )
        # 全部 POST 均为受治理的 Layer A/B 端点；不存在 /activate 或 /deploy-production。
        assert posts == [
            "/governance/activation/evidence",
            "/governance/activation/evidence-decision",
            "/governance/activation/final-decision",
            "/governance/activation/review-package",
            "/governance/activation/signoff",
        ], posts


# ---------------------------------------------------------------------------
# 12. 前端看板契约（静态）
# ---------------------------------------------------------------------------
class TestFrontendPageContract:
    def _src(self) -> str:
        p = ROOT / "frontend" / "src" / "app" / "governance-activation" / "page.tsx"
        assert p.is_file()
        return p.read_text(encoding="utf-8")

    def test_no_real_activate_or_deploy_endpoint_referenced(self) -> None:
        src = self._src()
        # 真实端点子路径不得出现（页面仅在说明性文案里提及裸 "/activate" / "/deploy-production"，
        # 那是"本看板不提供此类端点"的声明，并非实际 fetch 目标）。
        assert "/governance/activation/activate" not in src
        assert "/governance/activation/deploy-production" not in src

    def test_built_no_go_banner_present(self) -> None:
        src = self._src()
        assert "BUILT_NO_GO" in src

    def test_no_auto_go_button(self) -> None:
        # 看板不得含"自动 GO / 激活 / 部署"按钮文案。
        src = self._src().lower()
        assert "激活生产" not in src
        assert "deploy production" not in src


# ---------------------------------------------------------------------------
# 13. CI 门禁 yml 契约（静态）
# ---------------------------------------------------------------------------
class TestCIGateYaml:
    def _text(self) -> str:
        p = ROOT / ".github" / "workflows" / "activation-readiness-gate.yml"
        assert p.is_file()
        return p.read_text(encoding="utf-8")

    def test_references_suite_and_three_jobs(self) -> None:
        text = self._text()
        assert "test_production_activation_readiness.py" in text
        for job in (
            "activation-readiness-integrity",
            "activation-readiness-security",
            "activation-readiness-tests",
        ):
            assert job in text

    def test_covers_3_9_6_branch(self) -> None:
        text = self._text()
        assert "feat/phase3.9.6-production-activation-evidence-readiness" in text


# ---------------------------------------------------------------------------
# 14. Layer B 服务层（T5/T8）：提交 / 人工裁决 / 汇总 / 评审包
# ---------------------------------------------------------------------------
def _audit() -> "AuditService":
    return AuditService(org_id="org-phase3-9-6-test")


def _svc() -> "ActivationEvidenceIntakeService":
    return ActivationEvidenceIntakeService(rc_id=RC_ID, audit=_audit())


def _provenance(submitted_by: str = "alice", *, verifiable: bool = True):
    coc = (
        build_chain_of_custody(
            [
                {
                    "event_kind": "received",
                    "actor_id": submitted_by,
                    "actor_kind": "user",
                    "detail": "received by human",
                }
            ]
        )
        if verifiable
        else ()
    )
    return build_evidence_provenance(
        origin_system="ticket-system",
        origin_reference="TKT-1",
        submitted_by=submitted_by,
        submitted_by_kind="user",
        declared_sha256=("deadbeef" if verifiable else None),
        chain_of_custody=coc,
    )


def _submit(svc, evidence_type="rc_freeze_manifest", actor_id="alice", *, verifiable=True):
    return svc.submit_evidence(
        actor_kind=AuditActorKind.USER,
        actor_id=actor_id,
        evidence_type=evidence_type,
        title=f"{evidence_type} evidence",
        content_reference=f"ref-{evidence_type}",  # 非本地文件 → 哈希 None，≠ 失败
        provenance=_provenance(submitted_by=actor_id, verifiable=verifiable),
    )


def _flatten_non_note(obj, _note_keys=("note", "notes", "disclaimer", "human_action_required")):
    """递归收集非说明性字段里的字符串（与评审包自身的 _scan_forbidden 跳过规则一致）。"""
    out: list = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _note_keys or str(k).endswith("_note"):
                continue
            out.extend(_flatten_non_note(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            out.extend(_flatten_non_note(item))
    elif isinstance(obj, str):
        out.append(obj)
    return out


class TestLayerBIntakeService:
    def test_submit_requires_real_human_actor(self) -> None:
        svc = _svc()
        with pytest.raises(EnterpriseRedLineViolationError):
            svc.submit_evidence(
                actor_kind=AuditActorKind.AI,
                actor_id="bot",
                evidence_type="rc_freeze_manifest",
                title="t",
                content_reference="r",
                provenance=_provenance(),
            )

    def test_submit_actor_id_must_match_provenance(self) -> None:
        svc = _svc()
        with pytest.raises(ActivationIntakeServiceError):
            svc.submit_evidence(
                actor_kind=AuditActorKind.USER,
                actor_id="bob",
                evidence_type="rc_freeze_manifest",
                title="t",
                content_reference="r",
                provenance=_provenance(submitted_by="alice"),
            )

    def test_submit_reaches_structurally_validated_not_approved(self) -> None:
        sub = _submit(_svc())
        # AI 路径最高只能到 STRUCTURALLY_VALIDATED，绝不 APPROVED。
        assert sub.status is ActivationEvidenceSubmissionStatus.STRUCTURALLY_VALIDATED
        assert sub.structurally_valid is True
        assert sub.is_human_approved is False
        assert sub.is_human_rejected is False

    def test_record_human_decision_approves(self) -> None:
        svc = _svc()
        sub = _submit(svc)
        updated = svc.record_human_evidence_decision(
            actor_kind=AuditActorKind.USER,
            actor_id="alice",
            submission_id=sub.submission_id,
            approved=True,
            reason="verified by human",
        )
        assert updated.status is ActivationEvidenceSubmissionStatus.APPROVED_BY_HUMAN
        assert updated.is_human_approved is True
        assert updated.human_decision_by == "alice"

    def test_record_decision_requires_real_user(self) -> None:
        svc = _svc()
        sub = _submit(svc)
        with pytest.raises(EnterpriseRedLineViolationError):
            svc.record_human_evidence_decision(
                actor_kind=AuditActorKind.AI,
                actor_id="bot",
                submission_id=sub.submission_id,
                approved=True,
                reason="x",
            )

    def test_cannot_approve_structurally_invalid(self) -> None:
        svc = _svc()
        sub = _submit(svc, verifiable=False)
        assert sub.status is ActivationEvidenceSubmissionStatus.VALIDATION_FAILED
        assert sub.structurally_valid is False
        with pytest.raises(ActivationIntakeServiceError):
            svc.record_human_evidence_decision(
                actor_kind=AuditActorKind.USER,
                actor_id="alice",
                submission_id=sub.submission_id,
                approved=True,
                reason="forced",
            )

    def test_record_decision_requires_nonempty_reason(self) -> None:
        svc = _svc()
        sub = _submit(svc)
        with pytest.raises(ActivationIntakeServiceError):
            svc.record_human_evidence_decision(
                actor_kind=AuditActorKind.USER,
                actor_id="alice",
                submission_id=sub.submission_id,
                approved=True,
                reason="",
            )

    def test_summarize_intake_incomplete_until_all_approved(self) -> None:
        svc = _svc()
        for et in REQUIRED_ACTIVATION_EVIDENCE_TYPES:
            sub = _submit(svc, evidence_type=et)
            svc.record_human_evidence_decision(
                actor_kind=AuditActorKind.USER,
                actor_id="alice",
                submission_id=sub.submission_id,
                approved=True,
                reason=f"ok {et}",
            )
        summary = svc.summarize()
        assert summary.intake_complete is True
        assert summary.missing_types == ()
        assert summary.total_submissions == len(REQUIRED_ACTIVATION_EVIDENCE_TYPES)
        assert (
            len(summary.human_approved_ids) == len(REQUIRED_ACTIVATION_EVIDENCE_TYPES)
        )

        # 反向：仅提交未批准 → 未完成。
        svc2 = _svc()
        _submit(svc2)
        assert svc2.summarize().intake_complete is False

    def test_build_review_package_requires_real_user_and_carries_no_decision(self) -> None:
        svc = _svc()
        for et in REQUIRED_ACTIVATION_EVIDENCE_TYPES:
            sub = _submit(svc, evidence_type=et)
            svc.record_human_evidence_decision(
                actor_kind=AuditActorKind.USER,
                actor_id="alice",
                submission_id=sub.submission_id,
                approved=True,
                reason="ok",
            )
        # AI 不得生成评审包（审计不得谎称由人发起）。
        with pytest.raises(EnterpriseRedLineViolationError):
            svc.build_review_package(actor_kind=AuditActorKind.AI, actor_id="bot")

        pkg = svc.build_review_package(
            actor_kind=AuditActorKind.USER, actor_id="alice"
        )
        assert isinstance(pkg, FinalActivationReviewPackage)
        # 就绪度上限不含任何放行终态。
        assert pkg.readiness.value != "approved"
        assert pkg.to_dict()["human_final_decision"] is None
        # 非说明性字段不得含放行类词元（note 字段的"红线说明"本身可提及，故跳过）。
        serialized = " ".join(_flatten_non_note(pkg.to_dict())).lower()
        assert "engineering_approved" not in serialized
        assert "production_go" not in serialized


# ---------------------------------------------------------------------------
# 15. T13 证据存储安全（只存引用与哈希，永不存原文 / 裸密钥）
# ---------------------------------------------------------------------------
class TestLayerBEvidenceStorageSafety:
    def _policy(self) -> "EvidenceStoragePolicy":
        return EvidenceStoragePolicy(root_dir=str(ROOT))

    def test_rejects_inline_content(self) -> None:
        with pytest.raises(EvidenceStorageSafetyError):
            self._policy().ensure_no_inline_content(
                declared_content="这是一段不该被入库的证据正文"
            )

    def test_rejects_bare_secret_reference(self) -> None:
        for bad in (
            "sk-abcdefgh12345678",
            "api_key=supersecret",
            "password=hunter2",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "-----BEGIN PRIVATE KEY-----",
        ):
            with pytest.raises(EvidenceStorageSafetyError):
                self._policy().ensure_reference_not_secret(bad)

    def test_allows_path_reference(self) -> None:
        # 普通路径 / 工单号引用不触发拒绝。
        self._policy().ensure_reference_not_secret("tickets/TKT-123/rc-freeze.json")
        self._policy().ensure_reference_not_secret("/var/evidence/rc-freeze.json")

    def test_compute_sha256_streams_and_returns_none_for_missing(self) -> None:
        import os as _os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
            tf.write("hello evidence")
            path = tf.name
        try:
            h = compute_evidence_sha256(path, ".")
            assert h and len(h) == 64
            # 非本地引用返回 None（不伪造哈希）。
            assert compute_evidence_sha256("TKT-nonexistent-123", str(ROOT)) is None
        finally:
            _os.unlink(path)


# ---------------------------------------------------------------------------
# 16. T12 权限边界（deny-by-default 白名单；AI/SYSTEM 一律拒绝）
# ---------------------------------------------------------------------------
class TestLayerBPermissionBoundary:
    def test_read_permission_allows_read_operations(self) -> None:
        for op in (
            ActivationOperation.VIEW_READINESS,
            ActivationOperation.SUBMIT_EVIDENCE,
            ActivationOperation.BUILD_REVIEW_PACKAGE,
        ):
            require_activation_operation(
                operation=op,
                actor_kind="user",
                granted_permissions=[PERM_RELEASE_READ],
            )

    def test_signoff_required_for_decision(self) -> None:
        with pytest.raises(ActivationPermissionBoundaryError):
            require_activation_operation(
                operation=ActivationOperation.RECORD_EVIDENCE_DECISION,
                actor_kind="user",
                granted_permissions=[PERM_RELEASE_READ],
            )
        # 持有 signoff 则放行。
        require_activation_operation(
            operation=ActivationOperation.RECORD_EVIDENCE_DECISION,
            actor_kind="user",
            granted_permissions=[PERM_RELEASE_SIGNOFF],
        )

    def test_non_user_actor_denied(self) -> None:
        for kind in ("ai", "system", "service"):
            with pytest.raises(ActivationPermissionBoundaryError):
                require_activation_operation(
                    operation=ActivationOperation.VIEW_READINESS,
                    actor_kind=kind,
                    granted_permissions=[PERM_RELEASE_READ],
                )

    def test_deny_by_default_whitelist(self) -> None:
        desc = ActivationPermissionBoundary(rc_id=RC_ID).describe()
        assert len(desc["operations"]) == 16
        for op in desc["operations"]:
            assert op["required_actor_kind"] == "user"


# ---------------------------------------------------------------------------
# 17. Layer B fail-closed：AI 不可 approved / GO 需 READY 包 / human_go 仅标志
# ---------------------------------------------------------------------------
class TestLayerBFailClosed:
    def _ready_package(self, readiness=ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW):
        return FinalActivationReviewPackage(
            package_id="farp-test",
            rc_id=RC_ID,
            readiness=readiness,
            generated_at="2026-08-12T00:00:00Z",
            generated_for_actor="alice",
            evidence_summary={},
            signoff_snapshot={},
            redline_assertions={"engineering_enabled_false": True},
        )

    def test_go_requires_ready_package(self) -> None:
        pkg = self._ready_package(ReviewPackageReadiness.EVIDENCE_INCOMPLETE)
        with pytest.raises(FinalHumanDecisionError):
            build_final_human_activation_decision(
                decision_id="d1",
                outcome=FinalDecisionOutcome.GO,
                decided_by="principal",
                decided_by_kind="user",
                signature_reference="SIG-1",
                reason="want go",
                package=pkg,
            )

    def test_no_go_allowed_on_incomplete_package(self) -> None:
        pkg = self._ready_package(ReviewPackageReadiness.EVIDENCE_INCOMPLETE)
        dec = build_final_human_activation_decision(
            decision_id="d2",
            outcome=FinalDecisionOutcome.NO_GO,
            decided_by="principal",
            decided_by_kind="user",
            signature_reference="SIG-2",
            reason="blocked",
            package=pkg,
        )
        assert dec.is_blocking is True
        assert dec.is_go is False

    def test_decision_recorded_go_only_flags_not_activates(self) -> None:
        pkg = self._ready_package()
        dec = build_final_human_activation_decision(
            decision_id="d3",
            outcome=FinalDecisionOutcome.GO,
            decided_by="principal",
            decided_by_kind="user",
            signature_reference="SIG-3",
            reason="all good",
            package=pkg,
        )
        ledger = FinalHumanDecisionLedger(rc_id=RC_ID, audit=AuditService(org_id="org-x"))
        ledger.record(actor_kind=AuditActorKind.USER, decision=dec)

        # human_go_recorded 仅标志真实人工已登记 GO 裁决。
        assert ledger.human_go_recorded() is True
        eff = ledger.effective()
        assert eff is not None and eff.is_go is True
        # 裁决登记不翻转 engineering_enabled、不表达已激活。
        assert eff.engineering_enabled_at_decision is False
        assert eff.activation_execution.value == "pending_human_terminal_action"
        snap = ledger.snapshot()
        assert snap.human_go_recorded is True
        assert snap.total_decisions == 1

    def test_ledger_record_requires_real_user(self) -> None:
        pkg = self._ready_package()
        dec = build_final_human_activation_decision(
            decision_id="d4",
            outcome=FinalDecisionOutcome.NO_GO,
            decided_by="principal",
            decided_by_kind="user",
            signature_reference="SIG-4",
            reason="block",
            package=pkg,
        )
        ledger = FinalHumanDecisionLedger(rc_id=RC_ID, audit=AuditService(org_id="org-x"))
        with pytest.raises(EnterpriseRedLineViolationError):
            ledger.record(actor_kind=AuditActorKind.AI, decision=dec)

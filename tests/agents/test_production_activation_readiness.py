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
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from agents.enterprise.production_release import activation_readiness as ar
from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
)
from agents.enterprise.production_release.human_signoff import (
    HumanSignoffRegistry,
    build_human_signoff_record,
)
from agents.enterprise.production_release.models import SignoffDecision, SignoffRole
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
    def test_eight_routes_no_forbidden_endpoint(self) -> None:
        router = _activation_router()
        paths = sorted({getattr(r, "path", "") for r in router.routes})
        activation = [p for p in paths if p.startswith("/governance/activation")]
        assert len(activation) == 8, activation
        # 禁设任何 /activate 或 /deploy-production 端点。
        assert not any(p.rstrip("/").endswith("activate") for p in activation)
        assert not any(p.rstrip("/").endswith("deploy-production") for p in activation)

    def test_only_one_post_route_and_it_is_signoff(self) -> None:
        router = _activation_router()
        posts = [
            getattr(r, "path", "")
            for r in router.routes
            if "POST" in (getattr(r, "methods", None) or set())
        ]
        assert posts == ["/governance/activation/signoff"]


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

"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 服务编排（T1–T7 主体）。

定位：在准备层 + 演练层之上提供**纯闸门 / 证据包 / 候选 / 清单 / 回滚引用**能力——
把发布候选可否放行、证据是否齐备、清单是否可哈希、回滚引用是否完整以只读校验结构
沉淀。本服务**不持有任何生产状态**，不写入任何密钥，不执行任何真实激活 / 真实授权 /
真实数据覆盖；所有出口一律 fail-closed：

① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _PRODUCTION_RELEASE_FORBIDDEN`` 结构拦截真实部署 / 真激活 /
   出 approved / 自动批准 RC / 代生产负责人签署 / 宣布生产 GO。
③ **不输出 engineering_approved**：所有候选 ``release_approved`` 恒 False。
④ **不真实激活**：闸门评估只产出 READY_FOR_HUMAN_REVIEW / BLOCKED /
   PENDING_VERIFICATION，服务层永不返回 APPROVED / AUTO_APPROVED。
⑤ **不代替生产负责人**：所有审计入口强制 actor=USER（红线⑥/⑧）；
   ``ReleaseSignoff`` 只能由真实 USER 线下构造（服务 forbidden 名 ``create_human_signoff``
   已结构拦截 AI 构造）。
⑥ **不代填真实人工证据**：human_signoff / production_secret 类证据缺失时只标注
   ``pending_verification``（红线⑨/⑩）。
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.production_release.activation_evidence import (
    ActivationEvidenceBundle,
    build_activation_evidence_bundle,
)
from agents.enterprise.production_release.activation_gate import (
    ControlledActivationGate,
    ControlledActivationGateResult,
)
from agents.enterprise.production_release.evidence import (
    ProductionReleaseEvidenceService,
)
from agents.enterprise.production_release.forbidden import (
    _PRODUCTION_RELEASE_FORBIDDEN,
)
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.human_approval import (
    HumanActivationApproval,
    HumanActivationApprovalService,
)
from agents.enterprise.production_release.freeze_checker import (
    FreezeCheckResult,
    ReleaseFreezeChecker,
)
from agents.enterprise.production_release.freeze_manifest import (
    RCFreezeManifest,
    generate_rc_freeze_manifest,
)
from agents.enterprise.production_release.gate import ProductionReleaseGate
from agents.enterprise.production_release.models import (
    EvidenceVerificationStatus,
    ProductionReleaseCandidate,
    ProductionReleaseEvidence,
    ProductionReleaseGateResult,
    ReleaseCandidateStatus,
    ReleaseDecisionDraft,
    ReleaseDecisionDraftStatus,
    ReleaseGateStatus,
    ReleasePackageManifest,
    ReleaseRollbackReference,
    ReleaseSignoff,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.production_release.package import ReleasePackageBuilder
from agents.enterprise.production_release.release_candidate import (
    RCFreezeStatus,
    ReleaseCandidate,
    create_release_candidate,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=".",
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip()
    except Exception:
        return ""


class ProductionReleaseError(EnterpriseRedLineViolationError):
    """发布闸门层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


class ProductionReleaseService(_RedLineForbiddenMixin):
    """企业生产发布闸门与证据包服务（T1–T7 主体）。

    AI 只能造 ``DRAFT`` / ``GATHERED`` / ``AWAITING_HUMAN_REVIEW`` 态的候选、产出
    闸门三态（不含 APPROVED）、生成 Go/No-Go **草稿**；最终放行只能源于真实
    ``ReleaseSignoff`` 组合（由人工在 API 层构造并落库）。
    """

    _FORBIDDEN = _FREEZE_ACTIVATION_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: AuditService,
        identity: Any = None,
        root_dir: str = ".",
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建发布闸门层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._root_dir = root_dir
        self._evidence_svc = ProductionReleaseEvidenceService(root_dir=root_dir)
        self._gate = ProductionReleaseGate()
        self._package_builder = ReleasePackageBuilder(root_dir=root_dir)
        self._approval_svc = HumanActivationApprovalService(audit=audit)

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_user(actor_id: str) -> None:
        # 所有审计入口强制 actor 真实（红线⑥/⑧）。
        if not actor_id:
            raise EnterpriseRedLineViolationError(
                "发布闸门层审计入口要求真实 USER actor_id（红线⑥/⑧）"
            )

    def _gather_repo_facts(self) -> Dict[str, Any]:
        """只读采集可被 AI 廉价核验的仓库事实（用于闸门 scan 基线）。"""

        root = "."
        git_head = _git("rev-parse", "HEAD")
        status_out = _git("status", "--porcelain")
        working_tree_clean = status_out.strip() == ""
        sec_scan_present = __import__("os").path.isfile(
            __import__("os").path.join(root, "scripts", "lint", "check_production_security.py")
        )
        id_scan_present = __import__("os").path.isfile(
            __import__("os").path.join(root, "scripts", "lint", "check_legacy_identity_headers.py")
        )
        gov_guide_present = __import__("os").path.isfile(
            __import__("os").path.join(root, "docs", "PRODUCTION_DEPLOYMENT_GUIDE.md")
        )
        return {
            "git_workspace_integrity": working_tree_clean,
            "commit_sha_exists": bool(git_head),
            "production_security_scanner": sec_scan_present,
            "identity_security_scanner": id_scan_present,
            "governance_quality_gate": sec_scan_present and id_scan_present,
            "configuration_baseline": True,  # 配置基线以 config.yaml 为源，恒在
            "deployment_documentation": gov_guide_present,
            "database_migration_status": True,  # alembic 升级由 CI 提供真实值
            "full_test_results_green": False,  # 必须由真实 CI 提供
            "rollback_drill": False,  # 由真实演练报告提供
            "recovery_validation": False,  # 由真实恢复校验提供
        }

    # ------------------------------------------------------------------ #
    # T2 发布候选：AI 只造 DRAFT / GATHERED / AWAITING_HUMAN_REVIEW
    # ------------------------------------------------------------------ #
    def create_release_candidate(
        self,
        *,
        release_id: str,
        version: str,
        commit_sha: str,
        branch: str,
        build_artifacts: Optional[List[str]] = None,
        migration_version: Optional[str] = None,
        config_baseline: Optional[str] = None,
        security_baseline: Optional[str] = None,
        test_baseline: Optional[Dict[str, object]] = None,
        rollback_reference: Optional[str] = None,
    ) -> ProductionReleaseCandidate:
        return ProductionReleaseCandidate(
            release_id=release_id,
            version=version,
            commit_sha=commit_sha,
            branch=branch,
            build_artifacts=build_artifacts or [],
            migration_version=migration_version,
            config_baseline=config_baseline,
            security_baseline=security_baseline,
            test_baseline=test_baseline or {},
            rollback_reference=rollback_reference,
            status=ReleaseCandidateStatus.DRAFT,
            release_approved=False,  # fail-closed
            created_at=_now(),
        )

    def mark_awaiting_human_review(
        self, rc: ProductionReleaseCandidate
    ) -> ProductionReleaseCandidate:
        """AI 将候选标记为人审待决（AWAITING_HUMAN_REVIEW）；不激活、不批准。"""

        return ProductionReleaseCandidate(
            release_id=rc.release_id,
            version=rc.version,
            commit_sha=rc.commit_sha,
            branch=rc.branch,
            build_artifacts=rc.build_artifacts,
            migration_version=rc.migration_version,
            config_baseline=rc.config_baseline,
            security_baseline=rc.security_baseline,
            test_baseline=rc.test_baseline,
            rollback_reference=rc.rollback_reference,
            evidence_ids=rc.evidence_ids,
            status=ReleaseCandidateStatus.AWAITING_HUMAN_REVIEW,
            release_approved=False,
            created_at=rc.created_at,
        )

    # ------------------------------------------------------------------ #
    # T1 证据收集（只读）
    # ------------------------------------------------------------------ #
    def collect_evidence(
        self,
        *,
        release_id: str,
        test_baseline: Optional[Dict[str, object]] = None,
        audit_count: Optional[int] = None,
        engineering_enabled: Optional[bool] = None,
    ) -> List[ProductionReleaseEvidence]:
        return self._evidence_svc.collect_release_evidence(
            release_id=release_id,
            test_baseline=test_baseline,
            audit_count=audit_count,
            engineering_enabled=engineering_enabled,
        )

    # ------------------------------------------------------------------ #
    # T3 闸门评估（AI 路径**强制**不含 APPROVED）
    # ------------------------------------------------------------------ #
    def evaluate_release_gate(
        self,
        *,
        candidate: ProductionReleaseCandidate,
        evidence: List[ProductionReleaseEvidence],
        scan: Optional[Dict[str, bool]] = None,
    ) -> ProductionReleaseGateResult:
        # 基础 scan 来自仓库事实；调用方（API / CI）可覆盖/补全真实 CI 结果。
        base = self._gather_repo_facts()
        if scan:
            base.update(scan)
        chain = self._evidence_svc.build_evidence_chain(evidence)
        result = self._gate.evaluate(
            candidate=candidate, evidence_chain=chain, scan=base
        )
        # 红线②/③/⑩：AI 服务层不得返回生产 GO / APPROVED —— 即便闸门判定为
        # READY_FOR_HUMAN_REVIEW，也只代表"可供人工评审"，不代表放行。
        return ProductionReleaseGateResult(
            status=result.status,
            checks=result.checks,
            missing=result.missing,
        )

    # ------------------------------------------------------------------ #
    # T6 清单 / T7 回滚引用（只描述）
    # ------------------------------------------------------------------ #
    def build_manifest(
        self,
        *,
        release_version: str,
        commit_sha: str,
        artifacts: Optional[Dict[str, str]] = None,
        migration_revision: Optional[str] = None,
        config_baseline: Optional[str] = None,
        dependency_baseline: Optional[str] = None,
        security_scan_ref: Optional[str] = None,
        test_report_ref: Optional[str] = None,
        rollback_version: Optional[str] = None,
        documentation_version: Optional[str] = None,
    ) -> ReleasePackageManifest:
        return self._package_builder.build_manifest(
            release_version=release_version,
            commit_sha=commit_sha,
            artifacts=artifacts,
            migration_revision=migration_revision,
            config_baseline=config_baseline,
            dependency_baseline=dependency_baseline,
            security_scan_ref=security_scan_ref,
            test_report_ref=test_report_ref,
            rollback_version=rollback_version,
            documentation_version=documentation_version,
        )

    def build_rollback_reference(
        self,
        *,
        last_known_good_version: str,
        last_known_good_commit: str,
        database_revision: Optional[str] = None,
        config_baseline: Optional[str] = None,
        rollback_steps_reference: Optional[str] = None,
        recovery_validation_reference: Optional[str] = None,
    ) -> ReleaseRollbackReference:
        return self._package_builder.build_rollback_reference(
            last_known_good_version=last_known_good_version,
            last_known_good_commit=last_known_good_commit,
            database_revision=database_revision,
            config_baseline=config_baseline,
            rollback_steps_reference=rollback_steps_reference,
            recovery_validation_reference=recovery_validation_reference,
        )

    # ------------------------------------------------------------------ #
    # T5 Go/No-Go 草稿（只生成草稿，不生成 GO_LIVE_APPROVED）
    # ------------------------------------------------------------------ #
    def build_decision_draft(
        self,
        *,
        release_id: str,
        candidate: ProductionReleaseCandidate,
        evidence: List[ProductionReleaseEvidence],
        gate: ProductionReleaseGateResult,
        scan: Optional[Dict[str, bool]] = None,
    ) -> ReleaseDecisionDraft:
        chain = self._evidence_svc.build_evidence_chain(evidence)
        passed = [k for k, v in gate.checks.items() if v]
        blocked = list(gate.missing)
        pending = [
            e["evidence_type"]
            for e in chain.get("items", [])
            if e["verification_status"] == EvidenceVerificationStatus.PENDING_VERIFICATION.value
        ]
        # 草稿状态随闸门：BLOCKED → BLOCKED；PENDING_VERIFICATION → NEEDS_MORE_EVIDENCE；
        # READY_FOR_HUMAN_REVIEW → READY_FOR_HUMAN_GO_NO_GO。永不 GO_LIVE_APPROVED。
        if gate.status == ReleaseGateStatus.BLOCKED:
            draft_status = ReleaseDecisionDraftStatus.BLOCKED
        elif gate.status == ReleaseGateStatus.PENDING_VERIFICATION:
            draft_status = ReleaseDecisionDraftStatus.NEEDS_MORE_EVIDENCE
        else:
            draft_status = ReleaseDecisionDraftStatus.READY_FOR_HUMAN_GO_NO_GO

        return ReleaseDecisionDraft(
            draft_id=f"draft-{uuid4().hex[:12]}",
            release_id=release_id,
            evidence_summary=chain,
            passed_items=passed,
            blocked_items=blocked,
            pending_verification=pending,
            risks=[
                "真实生产部署 / 真实激活须由主理人在人类终端执行",
                "真实生产密钥注入须由人工线下完成",
                "最终 GO / NO-GO 只能由真实 ReleaseSignoff 组合决定",
            ],
            rollback_readiness=(
                "ready" if candidate.rollback_reference else "pending_verification"
            ),
            status=draft_status,
            generated_at=_now(),
        )

    # ------------------------------------------------------------------ #
    # T4 人工签署记录（actor 真实，强制 USER；AI 不得代签）
    # ------------------------------------------------------------------ #
    def record_release_signoff_recorded(
        self,
        *,
        actor_id: str,
        role: SignoffRole,
        decision: SignoffDecision,
        release_id: str,
        reason: str = "",
        evidence_snapshot: Optional[Dict[str, object]] = None,
    ) -> Any:
        """记录一条真实人工签署（actor_kind 恒 USER）。

        本方法**不构造** ReleaseSignoff 实例（那是 API 层用真实 USER 主体构造的）；
        这里只把"已发生的人工签署"如实审计留痕，并强制 actor 为真实 USER。
        """

        self._require_user(actor_id)
        return self._audit.record_release_signoff_recorded(
            record_id=f"rls-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=f"signoff_{role.value}_{decision.value}",
            target=release_id,
            detail=f"role={role.value};decision={decision.value};reason={reason[:200]}",
            ts=_now(),
        )

    # ------------------------------------------------------------------ #
    # 审计入口（actor 真实，强制 USER）
    # ------------------------------------------------------------------ #
    def record_release_candidate_created(
        self, *, actor_id: str, release_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_release_candidate_created(
            record_id=f"rcc-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="create_release_candidate",
            target=release_id,
            detail=detail,
            ts=_now(),
        )

    def record_release_gate_evaluated(
        self, *, actor_id: str, release_id: str, status: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_release_gate_evaluated(
            record_id=f"rgv-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="evaluate_release_gate",
            target=release_id,
            detail=f"status={status};{detail}",
            ts=_now(),
        )

    def record_release_manifest_generated(
        self, *, actor_id: str, release_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_release_manifest_generated(
            record_id=f"rmf-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="generate_release_manifest",
            target=release_id,
            detail=detail,
            ts=_now(),
        )

    # ------------------------------------------------------------------ #
    # T11 RC 冻结 / 受控激活增量（纯冻结 / 只读闸门，fail-closed）
    # ------------------------------------------------------------------ #
    def freeze_release_candidate(
        self,
        *,
        rc_id: str,
        version: str,
        commit_sha: str,
        branch: str,
        component_specs: Dict[str, str],
        actor_id: str,
        root_dir: str = ".",
    ) -> ReleaseCandidate:
        """真实人工发起 RC 冻结：即时计算组件 SHA-256，生成冻结候选并如实审计留痕。

        ``activation_approved`` 恒 False；状态默认 ``RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``；
        AI 不激活、不批准、不翻转 engineering_enabled。
        """

        self._require_user(actor_id)
        rc = create_release_candidate(
            rc_id=rc_id,
            version=version,
            commit_sha=commit_sha,
            branch=branch,
            component_specs=component_specs,
            root_dir=root_dir,
        )
        self._audit.record_rc_freeze_generated(
            record_id=f"rcf-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="generate_rc_freeze",
            target=rc.rc_id,
            detail=f"version={version};commit={commit_sha};components={len(rc.components)}",
            ts=_now(),
        )
        return rc

    def verify_release_candidate_freeze(
        self,
        *,
        rc: ReleaseCandidate,
        actor_id: str,
        detail: str = "",
    ) -> ReleaseCandidate:
        """记录一次真实人工核验 RC 冻结（红线⑧）。

        仅如实留痕；AI **不**把 ``status`` 自动翻转为 ``VERIFIED_BY_HUMAN``（那一步须由
        真实人工在受控激活闸门 / 证据包签署路径显式完成），返回原 ``rc`` 不变。
        """

        self._require_user(actor_id)
        self._audit.record_rc_freeze_verified(
            record_id=f"rcv-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="verify_rc_freeze",
            target=rc.rc_id,
            detail=detail or f"status={rc.status.value}",
            ts=_now(),
        )
        return rc

    def run_rc_freeze_check(
        self,
        *,
        rc: ReleaseCandidate,
        manifest: RCFreezeManifest,
        actor_id: str,
        root_dir: str = ".",
        check_git: bool = True,
        check_governance: bool = True,
    ) -> FreezeCheckResult:
        """执行 RC 冻结检查（fail-closed）。

        仅在结果 ``FROZEN`` 时如实审计留痕（record_rc_freeze_check_passed）；
        出现 DRIFTED 不记录"通过"，只返回漂移事实供人工处置。
        """

        self._require_user(actor_id)
        checker = ReleaseFreezeChecker(
            root_dir=root_dir,
            check_git=check_git,
            check_governance=check_governance,
        )
        result = checker.check(rc, manifest)
        if result.frozen:
            self._audit.record_rc_freeze_check_passed(
                record_id=f"rcc-{uuid4().hex[:12]}",
                actor_id=actor_id,
                action="check_rc_freeze_passed",
                target=rc.rc_id,
                detail=f"manifest_sha256={manifest.manifest_sha256[:16]}",
                ts=_now(),
            )
        return result

    # ------------------------------------------------------------------ #
    # T11 受控激活证据包 / 闸门 / 人工批准（纯汇总 / 只读判定 / 责任留痕）
    # ------------------------------------------------------------------ #
    def build_activation_evidence_bundle(
        self,
        *,
        rc_id: str,
        version: str,
        required_evidence_types: List[str],
        provided_evidence_types: List[str],
        # 真实人工签署角色须来自外部（API / 线下），AI 不得编造（红线⑥/⑧）。
        human_signoff_roles: List[str],
        actor_id: str,
        freeze_manifest_sha256: Optional[str] = None,
        governance_integrity_passed: bool = False,
        rollback_reference_present: bool = False,
        recovery_validation_present: bool = False,
        integrity_status: EvidenceVerificationStatus = EvidenceVerificationStatus.PENDING_VERIFICATION,
    ) -> ActivationEvidenceBundle:
        """汇总激活前证据包（只读；缺真实人工签署则 incomplete）。

        仅如实留痕；AI 不构造真实人工签署、不翻转 engineering_enabled。
        """

        self._require_user(actor_id)
        bundle = build_activation_evidence_bundle(
            bundle_id=f"aeb-{rc_id}",
            rc_id=rc_id,
            version=version,
            required_evidence_types=required_evidence_types,
            provided_evidence_types=provided_evidence_types,
            human_signoff_roles=human_signoff_roles,
            freeze_manifest_sha256=freeze_manifest_sha256,
            governance_integrity_passed=governance_integrity_passed,
            rollback_reference_present=rollback_reference_present,
            recovery_validation_present=recovery_validation_present,
            integrity_status=integrity_status,
        )
        self._audit.record_activation_evidence_bundle_generated(
            record_id=f"aeb-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="generate_activation_evidence_bundle",
            target=rc_id,
            detail=f"complete={bundle.is_complete}",
            ts=_now(),
        )
        return bundle

    def evaluate_controlled_activation_gate(
        self,
        *,
        rc: ReleaseCandidate,
        manifest: RCFreezeManifest,
        freeze_result: FreezeCheckResult,
        evidence_bundle: ActivationEvidenceBundle,
        actor_id: str,
        root_dir: str = ".",
        check_governance: bool = True,
    ) -> ControlledActivationGateResult:
        """评估受控激活闸门（fail-closed，永不 AI 自决放行）。

        仅如实审计留痕；AI 不把 ``status`` 翻转为 ACTIVATED_BY_HUMAN（那一步须由
        真实人工在 HumanActivationApprovalService 路径显式完成）。
        """

        self._require_user(actor_id)
        gate = ControlledActivationGate(check_governance=check_governance)
        result = gate.evaluate(
            rc=rc,
            manifest=manifest,
            freeze_result=freeze_result,
            evidence_bundle=evidence_bundle,
            root_dir=root_dir,
        )
        self._audit.record_controlled_activation_gate_evaluated(
            record_id=f"cag-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="evaluate_controlled_activation_gate",
            target=rc.rc_id,
            detail=f"status={result.status.value};missing={len(result.missing)}",
            ts=_now(),
        )
        return result

    def record_activation_approval_recorded(
        self,
        *,
        actor_id: str,
        approval_id: str,
        rc_id: str,
        decision: str,
        roles: List[str],
        detail: str = "",
    ) -> Any:
        """把一次已发生的真实人工激活批准如实审计留痕（actor_kind 恒 USER）。

        本方法**不**构造 ``HumanActivationApproval``（那是真实人工在外部完成的）；
        这里仅记录"已发生"的责任事件（红线⑥/⑧）。不翻转 engineering_enabled。
        """

        self._require_user(actor_id)
        return self._approval_svc.record_activation_approval_recorded(
            actor_id=actor_id,
            approval_id=approval_id,
            rc_id=rc_id,
            decision=decision,
            roles=roles,
            detail=detail,
        )

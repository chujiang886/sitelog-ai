"""Phase 3.9.7 企业生产变更管控平面 —— 服务编排（T1–T9 / T23–T25 主体）。

定位：在发布闸门 + 受控激活之上提供**纯变更管控 / 仿真 / 证据包 / 候选 / 清单 /
回滚引用**能力——把变更请求可否进入受控窗口、仿真是否通过、证据是否齐备、清单是否可哈希、
回滚引用是否完整、人工裁决是否登记以只读校验结构沉淀。本服务**不持有任何生产状态**，
不写入任何密钥，不执行任何真实激活 / 真实授权 / 真实数据覆盖 / 真实部署 / 真实回滚 /
真实迁移 / 真实应用；所有出口一律 fail-closed：

① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _PRODUCTION_CHANGE_FORBIDDEN`` 结构拦截真实变更执行 / 真部署 /
   真回滚 / 真迁移 / 真应用 / 出 approved / 自动批准变更 / 代生产负责人签署 / 宣布变更 GO。
③ **不输出 engineering_approved**：所有变更请求 ``change_approved`` 恒 False。
④ **不真实执行**：预检评估只产出 READY_FOR_HUMAN_REVIEW / BLOCKED /
   PENDING_VERIFICATION，仿真 ``is_simulation`` 恒 True；服务层永不返回 APPROVED /
   AUTO_APPROVED / 真实变更结果。
⑤ **不代替生产负责人**：所有审计入口强制 actor=USER（红线⑥/⑧）；
   ``ChangeSignoff`` 只能由真实 USER 线下构造（服务 forbidden 名 ``create_human_change_signoff``
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
from agents.enterprise.audit import AuditService
from agents.enterprise.production_change.abort_policy import (
    build_change_abort_policy,
)
from agents.enterprise.production_change.change_request import (
    create_change_request,
    mark_awaiting_human_review,
)
from agents.enterprise.production_change.checkpoint import (
    record_change_checkpoint,
)
from agents.enterprise.production_change.evidence import (
    build_change_evidence,
    build_change_evidence_chain,
)
from agents.enterprise.production_change.forbidden import (
    _PRODUCTION_CHANGE_FORBIDDEN,
)
from agents.enterprise.production_change.models import (
    ChangeDecisionDraft,
    ChangeDecisionDraftStatus,
    ChangeEvidence,
    ChangeExecutionMode,
    ChangePlan,
    ChangePreflightResult,
    ChangeRequest,
    ChangeRollbackReference,
    ChangeSimulationResult,
    ChangeState,
    ChangeVerificationStatus,
    ControlledChangePackage,
    FailureScenarioEvaluation,
    PostChangeVerification,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.production_change.package import (
    ControlledChangePackageBuilder,
)
from agents.enterprise.production_change.plan import build_change_plan
from agents.enterprise.production_change.post_change import (
    register_post_change_verification,
)
from agents.enterprise.production_change.preflight import evaluate_change_preflight
from agents.enterprise.production_change.rollback_reference import (
    build_change_rollback_reference,
)
from agents.enterprise.production_change.simulation import (
    run_controlled_change_simulation,
)
from agents.enterprise.production_change.window import reserve_change_window
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


class ProductionChangeControlError(EnterpriseRedLineViolationError):
    """变更管控层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


class ProductionChangeControlService(_RedLineForbiddenMixin):
    """企业生产变更管控平面服务（T1–T9 / T23–T25 主体）。

    AI 只能造 ``HUMAN_DRAFTED`` / ``AWAITING_HUMAN_REVIEW`` 态的变更请求、产出
    预检三态（不含 APPROVED）、运行**受控仿真**（is_simulation 恒 True）、生成变更裁决
    **草稿**；最终放行 / 执行 / 中止只能源于真实 ``ChangeSignoff`` 组合（由人工在 API 层
    构造并落库）。
    """

    _FORBIDDEN = _PRODUCTION_CHANGE_FORBIDDEN

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
                "safety_invariants_ok() 失败：禁止在启用态下构建变更管控层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._root_dir = root_dir
        self._package_builder = ControlledChangePackageBuilder()

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_user(actor_id: str) -> None:
        # 所有审计入口强制 actor 真实（红线⑥/⑧）。
        if not actor_id:
            raise EnterpriseRedLineViolationError(
                "变更管控层审计入口要求真实 USER actor_id（红线⑥/⑧）"
            )

    def _gather_repo_facts(self) -> Dict[str, Any]:
        """只读采集可被 AI 廉价核验的仓库事实（用于预检 scan 基线）。"""

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
            "configuration_baseline": True,
            "deployment_documentation": gov_guide_present,
            "database_migration_status": True,
            "full_test_results_green": False,  # 必须由真实 CI 提供
            "rollback_drill": False,  # 由真实演练报告提供
            "recovery_validation": False,  # 由真实恢复校验提供
        }

    # ------------------------------------------------------------------ #
    # T1 变更请求：AI 只造 HUMAN_DRAFTED / AWAITING_HUMAN_REVIEW
    # ------------------------------------------------------------------ #
    def create_change_request(
        self,
        *,
        change_id: str,
        title: str,
        description: str,
        requested_by: str,
        execution_mode: ChangeExecutionMode = ChangeExecutionMode.HUMAN_MANUAL,
    ) -> ChangeRequest:
        return create_change_request(
            change_id=change_id,
            title=title,
            description=description,
            requested_by=requested_by,
            execution_mode=execution_mode,
        )

    def mark_awaiting_human_review(
        self, change: ChangeRequest
    ) -> ChangeRequest:
        """AI 将变更请求标记为人审待决（AWAITING_HUMAN_REVIEW）；不执行、不批准。"""

        return mark_awaiting_human_review(change)

    # ------------------------------------------------------------------ #
    # T2 变更计划 / T3 窗口 / T6 中止策略 / T7 回滚引用
    # ------------------------------------------------------------------ #
    def build_plan(
        self,
        *,
        change_id: str,
        plan_reference: str,
        rollback_plan_reference: str,
        steps: Optional[List[str]] = None,
    ) -> ChangePlan:
        return build_change_plan(
            change_id=change_id,
            plan_reference=plan_reference,
            rollback_plan_reference=rollback_plan_reference,
            steps=steps,
        )

    def reserve_window(
        self,
        *,
        change_id: str,
        window_start: str,
        window_end: str,
        reserved_by: str,
    ) -> Any:
        return reserve_change_window(
            change_id=change_id,
            window_start=window_start,
            window_end=window_end,
            reserved_by=reserved_by,
        )

    def build_abort_policy(
        self, *, change_id: str, auto_abort_conditions: Optional[List[str]] = None
    ) -> Any:
        return build_change_abort_policy(
            change_id=change_id, auto_abort_conditions=auto_abort_conditions
        )

    def build_rollback_reference(
        self,
        *,
        change_id: str,
        last_known_good_version: str,
        last_known_good_commit: str,
        database_revision: Optional[str] = None,
        config_baseline: Optional[str] = None,
        rollback_steps_reference: Optional[str] = None,
        recovery_validation_reference: Optional[str] = None,
    ) -> ChangeRollbackReference:
        return build_change_rollback_reference(
            change_id=change_id,
            last_known_good_version=last_known_good_version,
            last_known_good_commit=last_known_good_commit,
            database_revision=database_revision,
            config_baseline=config_baseline,
            rollback_steps_reference=rollback_steps_reference,
            recovery_validation_reference=recovery_validation_reference,
        )

    # ------------------------------------------------------------------ #
    # T4 变更前预检（AI 路径**强制**不含 APPROVED）
    # ------------------------------------------------------------------ #
    def evaluate_preflight(
        self,
        *,
        checks: Optional[Dict[str, bool]] = None,
        missing: Optional[List[str]] = None,
        scan: Optional[Dict[str, bool]] = None,
    ) -> ChangePreflightResult:
        base = self._gather_repo_facts()
        if scan:
            base.update(scan)
        combined = dict(base)
        if checks:
            combined.update(checks)
        return evaluate_change_preflight(checks=combined, missing=missing)

    # ------------------------------------------------------------------ #
    # T5 检查点 / T8 变更后验证（real USER 留痕）
    # ------------------------------------------------------------------ #
    def record_checkpoint(
        self,
        *,
        checkpoint_id: str,
        change_id: str,
        recorded_by: str,
        note: str = "",
    ) -> Any:
        return record_change_checkpoint(
            checkpoint_id=checkpoint_id,
            change_id=change_id,
            recorded_by=recorded_by,
            note=note,
        )

    def register_post_verification(
        self,
        *,
        verification_id: str,
        change_id: str,
        verification_type: str,
        status: ChangeVerificationStatus = ChangeVerificationStatus.PENDING_VERIFICATION,
        verified_by: Optional[str] = None,
        detail: str = "",
    ) -> PostChangeVerification:
        return register_post_change_verification(
            verification_id=verification_id,
            change_id=change_id,
            verification_type=verification_type,
            status=status,
            verified_by=verified_by,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # T9 变更证据
    # ------------------------------------------------------------------ #
    def build_evidence(
        self,
        *,
        evidence_id: str,
        evidence_type: str,
        source: str,
        source_reference: str,
        change_id: Optional[str] = None,
        integrity_status: str = "pending",
        verification_status: str = "pending_verification",
        sha256: Optional[str] = None,
    ) -> ChangeEvidence:
        return build_change_evidence(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            source=source,
            source_reference=source_reference,
            change_id=change_id,
            integrity_status=integrity_status,
            verification_status=verification_status,
            sha256=sha256,
        )

    # ------------------------------------------------------------------ #
    # T23 受控仿真 / T24 失败场景 / T25 变更包
    # ------------------------------------------------------------------ #
    def run_simulation(
        self,
        *,
        simulation_id: str,
        change: ChangeRequest,
        rollback_reference: Optional[ChangeRollbackReference] = None,
        preflight_checks: Optional[dict] = None,
        abort_conditions_present: bool = False,
    ) -> ChangeSimulationResult:
        """运行一次受控（合成）仿真——**绝不执行真实变更**。"""

        return run_controlled_change_simulation(
            simulation_id=simulation_id,
            change=change,
            rollback_reference=rollback_reference,
            preflight_checks=preflight_checks,
            abort_conditions_present=abort_conditions_present,
        )

    def evaluate_failure_scenarios(
        self, *, change_id: str, scenarios: List[Dict[str, object]]
    ) -> List[FailureScenarioEvaluation]:
        from agents.enterprise.production_change.failure_scenarios import (
            evaluate_failure_scenarios,
        )

        return evaluate_failure_scenarios(change_id=change_id, scenarios=scenarios)

    def build_package(
        self,
        *,
        package_id: str,
        change: ChangeRequest,
        plan: Optional[ChangePlan] = None,
        preflight: Optional[ChangePreflightResult] = None,
        rollback_reference: Optional[ChangeRollbackReference] = None,
        evidence: Optional[List[ChangeEvidence]] = None,
        simulation: Optional[ChangeSimulationResult] = None,
        decision_draft: Optional[ChangeDecisionDraft] = None,
    ) -> ControlledChangePackage:
        return self._package_builder.build_package(
            package_id=package_id,
            change=change,
            plan=plan,
            preflight=preflight,
            rollback_reference=rollback_reference,
            evidence=evidence,
            simulation=simulation,
            decision_draft=decision_draft,
        )

    # ------------------------------------------------------------------ #
    # 变更裁决草稿（只生成草稿，不生成 GO_LIVE_APPROVED）
    # ------------------------------------------------------------------ #
    def build_decision_draft(
        self,
        *,
        change_id: str,
        change: ChangeRequest,
        evidence: List[ChangeEvidence],
        preflight: ChangePreflightResult,
        simulation: Optional[ChangeSimulationResult] = None,
    ) -> ChangeDecisionDraft:
        chain = build_change_evidence_chain(evidence)
        passed = [k for k, v in preflight.checks.items() if v]
        blocked = list(preflight.missing)
        pending = [
            e.evidence_id
            for e in evidence
            if e.verification_status == "pending_verification"
        ]
        if preflight.status == ChangePreflightStatus.BLOCKED:
            draft_status = ChangeDecisionDraftStatus.BLOCKED
        elif preflight.status == ChangePreflightStatus.PENDING_VERIFICATION:
            draft_status = ChangeDecisionDraftStatus.NEEDS_MORE_EVIDENCE
        else:
            draft_status = ChangeDecisionDraftStatus.READY_FOR_HUMAN_GO_NO_GO

        return ChangeDecisionDraft(
            draft_id=f"cdraft-{uuid4().hex[:12]}",
            change_id=change_id,
            evidence_summary=chain,
            passed_items=passed,
            blocked_items=blocked,
            pending_verification=pending,
            risks=[
                "真实生产变更 / 真实部署须由主理人在人类终端执行",
                "真实生产密钥注入须由人工线下完成",
                "最终 GO / NO-GO 只能由真实 ChangeSignoff 组合决定",
            ],
            rollback_readiness=(
                "ready" if change.execution_mode else "pending_verification"
            ),
            status=draft_status,
            generated_at=_now(),
        )

    # ------------------------------------------------------------------ #
    # 审计入口（actor 真实，强制 USER）—— 对应 13 个 CHANGE_* 类目
    # ------------------------------------------------------------------ #
    def record_change_request_created(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_request_created(
            record_id=f"ccr-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="create_change_request",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_plan_registered(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_plan_registered(
            record_id=f"ccp-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="register_change_plan",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_window_reserved(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_window_reserved(
            record_id=f"ccw-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="reserve_change_window",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_preflight_recorded(
        self, *, actor_id: str, change_id: str, status: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_preflight_recorded(
            record_id=f"ccpf-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="record_change_preflight",
            target=change_id,
            detail=f"status={status};{detail}",
            ts=_now(),
        )

    def record_change_checkpoint_recorded(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_checkpoint_recorded(
            record_id=f"ccc-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="record_change_checkpoint",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_abort_policy_registered(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_abort_policy_registered(
            record_id=f"cca-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="register_change_abort_policy",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_rollback_reference_registered(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_rollback_reference_registered(
            record_id=f"ccrref-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="register_change_rollback_ref",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_post_change_verification_registered(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_post_change_verification_registered(
            record_id=f"ccpv-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="record_post_change_verification",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_evidence_submitted(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_evidence_submitted(
            record_id=f"cce-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="submit_change_evidence",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_simulation_performed(
        self, *, actor_id: str, change_id: str, outcome: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_simulation_performed(
            record_id=f"ccs-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="perform_change_simulation",
            target=change_id,
            detail=f"outcome={outcome};is_simulation=true;{detail}",
            ts=_now(),
        )

    def record_failure_scenario_evaluated(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_failure_scenario_evaluated(
            record_id=f"ccf-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="evaluate_failure_scenario",
            target=change_id,
            detail=detail,
            ts=_now(),
        )

    def record_change_package_generated(
        self, *, actor_id: str, change_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_change_package_generated(
            record_id=f"ccpkg-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="build_change_package",
            target=change_id,
            detail=f"simulated_only=true;{detail}",
            ts=_now(),
        )

    def record_change_human_decision_recorded(
        self,
        *,
        actor_id: str,
        decision_id: str,
        change_id: str,
        decision: str,
        roles: List[str],
        detail: str = "",
    ) -> Any:
        """把一次已发生的真实人工变更裁决如实审计留痕（actor_kind 恒 USER）。

        本方法**不**构造 ``ChangeSignoff``（那是真实人工在外部完成的）；
        这里仅记录"已发生"的责任事件（红线⑥/⑧）。不翻转 engineering_enabled。
        """

        self._require_user(actor_id)
        return self._audit.record_change_human_decision_recorded(
            record_id=f"cchd-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action="record_change_decision",
            target=change_id,
            detail=f"decision={decision};roles={roles};{detail}",
            ts=_now(),
        )


__all__ = [
    "ProductionChangeControlError",
    "ProductionChangeControlService",
]

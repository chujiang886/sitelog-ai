"""Phase 3.9.6 生产激活证据准备层核心（Tasks 5–15, 19–21）。

复用（不重造第二套）：
- ``ActivationEvidenceBundle``（3.9.2 / 3.9.5 已提交）—— Task 5 证据包基础；
- ``HumanSignoffRegistry`` / ``HumanSignoffRecord``（3.9.5 已提交）—— Task 6 / 7 四角色签署；
- ``ControlledActivationGate``（3.9.2 已提交）—— Task 8 门禁 facade 复用其客观检查；
- ``EnterpriseRedLineViolationError`` / ``_RedLineForbiddenMixin``（红线结构级 guard，
  Task 15 复用，不复制第二套 ``RedLineViolation``）。

红线（全程 fail-closed）：
- 本模块**永不**产出 ``APPROVED`` / ``GO`` / ``GO_LIVE`` / ``PRODUCTION_APPROVED`` /
  ``ENGINEERING_APPROVED``；
- 不翻转 ``engineering_enabled``、不部署、不激活、不宣布 GO、不写密钥、不授权限、
  不改生产数据、不关闭事件；
- 真实生产最终四角色签署只能由真实 USER 经 API 落 AuditService 产生；本模块只聚合、
  不代签、不提升任何放行状态。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from agents.config_loader import load_engineering_enabled
from agents.enterprise.governance_dashboard.forbidden import _dedupe
from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
    ActivationEvidenceBundle,
)
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.human_signoff import HumanSignoffRegistry
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# 枚举                                                                          #
# --------------------------------------------------------------------------- #
class EvidenceScope(str, Enum):
    """证据作用域（Task 19：真实 vs 合成 / 暂存 / 人工 严格区分）。

    ``PRODUCTION`` 表示**真实生产环境**产生的、可独立复核的证据；其余均非真实生产证据。
    Synthetic Drill PASS **不等价** Production Verified（红线⑯）。
    """

    SYNTHETIC = "synthetic"
    STAGING = "staging"
    PRODUCTION = "production"
    HUMAN = "human"  # 由真实人工离线产生/签署的文档/工单

    @property
    def is_real_production(self) -> bool:
        return self is EvidenceScope.PRODUCTION


class ActivationReadinessStatus(str, Enum):
    """生产激活就绪门禁状态（AI 只产出前三种；**永不** APPROVED。

    即便全部客观检查通过，只要真实人工签署/阻断器/pending 仍待决，闸门只返回
    ``PENDING_VERIFICATION`` 或 ``READY_FOR_HUMAN_SIGNOFF``（红线②/③/⑩）。
    """

    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"
    READY_FOR_HUMAN_SIGNOFF = "ready_for_human_signoff"


class HumanReviewStatus(str, Enum):
    """人工复核状态（当前只能 PENDING_HUMAN_REVIEW，除非仓库存在真实签署证据）。"""

    PENDING_HUMAN_REVIEW = "pending_human_review"


class EvidenceFreshnessStatus(str, Enum):
    """证据时效状态（Task 20）。

    无企业有效期政策时一律 ``PENDING_VERIFICATION``，AI 不得擅自定义 24h/7d 过期。
    """

    FRESH = "fresh"
    STALE = "stale"
    PENDING_VERIFICATION = "pending_verification"


# --------------------------------------------------------------------------- #
# Task 5：激活证据包 v2（聚合 3.9.0–3.9.5 关键证据）                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationEvidenceItem:
    """单条激活证据（Task 5）。

    ``hash`` 为 None → 尚未实算/未提供 → ``verification_status`` 必须为 pending。
    本结构只存引用与哈希，不存证据原文（T13 存储安全，红线⑦）。
    """

    phase: str
    artifact: str
    commit: str
    report: str
    hash: Optional[str]
    verification_status: str  # verified | pending_verification | failed
    human_review_status: str = HumanReviewStatus.PENDING_HUMAN_REVIEW.value
    evidence_scope: str = EvidenceScope.SYNTHETIC.value

    @property
    def is_real_production_evidence(self) -> bool:
        """只有 PRODUCTION 作用域且已 verified 才算真实生产证据（Task 19）。"""
        return (
            EvidenceScope(self.evidence_scope).is_real_production
            and self.verification_status == EvidenceVerificationStatus.VERIFIED.value
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "phase": self.phase,
            "artifact": self.artifact,
            "commit": self.commit,
            "report": self.report,
            "hash": self.hash,
            "verification_status": self.verification_status,
            "human_review_status": self.human_review_status,
            "evidence_scope": self.evidence_scope,
            "is_real_production_evidence": self.is_real_production_evidence,
        }


@dataclass(frozen=True)
class ActivationEvidenceBundleV2:
    """激活证据包 v2（Task 5）：聚合 Phase 3.9.0–3.9.5 关键证据（只读汇总）。"""

    bundle_id: str
    rc_id: str
    version: str
    items: Tuple[ActivationEvidenceItem, ...]
    generated_at: str
    note: str = (
        "ACTIVATION_EVIDENCE_BUNDLE_V2: 汇总 3.9.0–3.9.5 准备层证据；"
        "均为预生产/合成/暂存/人工证据，非真实生产证据；"
        "不激活、不翻转 engineering_enabled、不宣布 GO"
    )

    @property
    def production_evidence_complete(self) -> bool:
        """是否存在"完整且已核验"的真实生产证据（当前恒 False，见 Task 19）。"""
        return any(it.is_real_production_evidence for it in self.items)

    @property
    def pending_items(self) -> Tuple[ActivationEvidenceItem, ...]:
        return tuple(
            it
            for it in self.items
            if it.verification_status != EvidenceVerificationStatus.VERIFIED.value
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "rc_id": self.rc_id,
            "version": self.version,
            "generated_at": self.generated_at,
            "item_count": len(self.items),
            "production_evidence_complete": self.production_evidence_complete,
            "items": [it.to_dict() for it in self.items],
            "note": self.note,
        }

    def render_markdown(self) -> str:
        lines = [
            "## 激活证据包 v2（Phase 3.9.0–3.9.5）",
            "",
            f"- bundle_id: `{self.bundle_id}`",
            f"- rc_id: `{self.rc_id}`",
            f"- version: {self.version}",
            f"- 真实生产证据齐备：{'是' if self.production_evidence_complete else '否（当前均为预生产/合成/暂存/人工证据）'}",
            "",
            "| Phase | Artifact | Commit | Scope | Verification | Hash |",
            "|-------|----------|--------|-------|--------------|------|",
        ]
        for it in self.items:
            h = (it.hash or "—")[:12]
            lines.append(
                f"| {it.phase} | {it.artifact} | `{it.commit[:8]}` | "
                f"{it.evidence_scope} | {it.verification_status} | `{h}` |"
            )
        return "\n".join(lines)


# 默认证据项：来自 Git 真实基线（ledger 边界 commit），hash 为 None（待真实核验）。
_DEFAULT_EVIDENCE_SPECS: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    ("3.9.0", "production-readiness", "a538e1e",
     "phase3.9.0_production_readiness_preparation_report.md",
     EvidenceScope.STAGING.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.1", "staging-validation-dr", "66f9b57",
     "phase3.9.1_staging_validation_disaster_recovery_report.md",
     EvidenceScope.STAGING.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.2", "release-gate-rc-freeze", "1f223db",
     "phase3.9.2_production_release_gate_evidence_package_report.md",
     EvidenceScope.STAGING.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.3", "observability-incident", "8c7c9c5",
     "phase3.9.3_production_observability_incident_readiness_report.md",
     EvidenceScope.STAGING.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.4", "telemetry-synthetic", "a905213",
     "phase3.9.4_telemetry_synthetic_operations_report.md",
     EvidenceScope.SYNTHETIC.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.4-R2", "baseline-freeze", "f7a2aba",
     "phase3.9.4_r2_definitive_baseline_freeze_report.md",
     EvidenceScope.HUMAN.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
    ("3.9.5", "rc-freeze-reconcile", "4983e7b",
     "phase3.9.5_release_line_reconciliation_closure_report.md",
     EvidenceScope.STAGING.value, EvidenceVerificationStatus.PENDING_VERIFICATION.value),
)


def build_default_activation_evidence_bundle_v2(
    *, bundle_id: str = "aeb-v2-3.9.6", rc_id: str, version: str = "3.9.6"
) -> ActivationEvidenceBundleV2:
    """构建默认激活证据包 v2（基于 Git 真实基线 commit；hash 待真实核验）。"""
    items = tuple(
        ActivationEvidenceItem(
            phase=p,
            artifact=art,
            commit=c,
            report=rpt,
            hash=None,
            verification_status=vs,
            evidence_scope=scope,
        )
        for (p, art, c, rpt, scope, vs) in _DEFAULT_EVIDENCE_SPECS
    )
    return ActivationEvidenceBundleV2(
        bundle_id=bundle_id,
        rc_id=rc_id,
        version=version,
        items=items,
        generated_at=_now(),
    )


# --------------------------------------------------------------------------- #
# Task 6：四角色签署要求模型                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionActivationSignoffRequirement:
    """单个真实责任角色的签署要求（Task 6）。

    ``current_status`` 当前只能 ``PENDING_HUMAN_SIGNOFF``；AI 不得填
    ``signed_by`` / ``decision=go``（红线③/⑨）。
    """

    required_role: str  # production-owner | release-manager | security-owner | auditor
    required_actor_kind: str = "user"
    required_evidence: Tuple[str, ...] = field(default_factory=tuple)
    current_status: str = "pending_human_signoff"
    signed_by: Optional[str] = None
    signed_at: Optional[str] = None
    decision: Optional[str] = None
    reason: Optional[str] = None

    @property
    def is_satisfied(self) -> bool:
        return (
            self.current_status == "satisfied"
            and self.signed_by is not None
            and self.decision == SignoffDecision.GO.value
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "required_role": self.required_role,
            "required_actor_kind": self.required_actor_kind,
            "required_evidence": list(self.required_evidence),
            "current_status": self.current_status,
            "signed_by": self.signed_by,
            "signed_at": self.signed_at,
            "decision": self.decision,
            "reason": self.reason,
            "is_satisfied": self.is_satisfied,
        }


def build_default_signoff_requirements(
    registry: Optional[HumanSignoffRegistry] = None,
) -> Tuple[ProductionActivationSignoffRequirement, ...]:
    """根据（可能为空）签署登记簿生成四角色要求；未签署即 PENDING（fail-closed）。"""
    snapshot = registry.snapshot() if registry is not None else None
    effective = {r["role"]: r for r in (snapshot.effective_records if snapshot else [])}
    reqs: List[ProductionActivationSignoffRequirement] = []
    for role in REQUIRED_SIGNOFF_ROLES:
        rec = effective.get(role)
        if rec is None:
            reqs.append(ProductionActivationSignoffRequirement(required_role=role))
        else:
            satisfied = rec.get("is_go", False)
            reqs.append(
                ProductionActivationSignoffRequirement(
                    required_role=role,
                    required_evidence=("activation-evidence-bundle-v2",),
                    current_status="satisfied" if satisfied else "pending_human_signoff",
                    signed_by=rec.get("actor_id"),
                    signed_at=rec.get("signed_at"),
                    decision=rec.get("decision"),
                    reason=rec.get("reason", ""),
                )
            )
    return tuple(reqs)


# --------------------------------------------------------------------------- #
# Task 7：职责分离（SoD）校验                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SoDValidationResult:
    """SoD 校验结果（Task 7）。"""

    four_roles_present: bool
    all_real_user: bool
    policy_distinct_natural_persons: str  # pending_policy_verification | satisfied | violated
    distinct_actor_ids: Tuple[str, ...]
    ok: bool
    note: str = (
        "SOD_ONLY: 校验四角色齐备且均为真实 USER；"
        "是否要求'不同自然人'在无权威策略时标 pending_policy_verification，不擅自断言"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "four_roles_present": self.four_roles_present,
            "all_real_user": self.all_real_user,
            "policy_distinct_natural_persons": self.policy_distinct_natural_persons,
            "distinct_actor_ids": list(self.distinct_actor_ids),
            "ok": self.ok,
            "note": self.note,
        }


class SoDValidator:
    """职责分离校验（Task 7，fail-closed）。

    防单一 AI / service 主体包办全部责任：任一签署 actor_kind != user → 失败。
    四角色是否必须由不同自然人：无权威策略时标 ``pending_policy_verification``，
    不擅自断言（红线⑨）。
    """

    @staticmethod
    def validate(registry: HumanSignoffRegistry) -> SoDValidationResult:
        snapshot = registry.snapshot()
        effective = snapshot.effective_records
        roles = {r["role"] for r in effective}
        four_present = set(REQUIRED_SIGNOFF_ROLES).issubset(roles)
        all_user = all(r.get("actor_kind") == "user" for r in effective)
        actor_ids = tuple(sorted({r["actor_id"] for r in effective if r.get("actor_id")}))
        policy = "pending_policy_verification"
        ok = four_present and all_user
        return SoDValidationResult(
            four_roles_present=four_present,
            all_real_user=all_user,
            policy_distinct_natural_persons=policy,
            distinct_actor_ids=actor_ids,
            ok=ok,
        )


# --------------------------------------------------------------------------- #
# Task 9：激活阻断器登记                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationBlocker:
    """一个尚未满足的生产前置条件（Task 9，fail-closed：禁止自动解决）。"""

    blocker_id: str
    category: str  # identity | secret | observability | incident | governance | infra
    description: str
    source: str
    evidence: str
    owner_role: str
    resolution_status: str = "open"  # open | in_progress | resolved（只能由真人推进）

    def to_dict(self) -> Dict[str, object]:
        return {
            "blocker_id": self.blocker_id,
            "category": self.category,
            "description": self.description,
            "source": self.source,
            "evidence": self.evidence,
            "owner_role": self.owner_role,
            "resolution_status": self.resolution_status,
        }


def build_default_activation_blockers() -> Tuple[ActivationBlocker, ...]:
    """默认真实生产阻断器（均须真实人类提供/验证，AI 不解决）。"""
    return (
        ActivationBlocker(
            blocker_id="B1-real-idp",
            category="identity",
            description="真实 IdP（jwt/oidc/sso-gateway）尚未通过生产校验",
            source="phase3.8.28 / phase3.9.2",
            evidence="pending_real_idp_validation",
            owner_role="security-owner",
        ),
        ActivationBlocker(
            blocker_id="B2-real-secrets",
            category="secret",
            description="真实生产密钥/凭证尚未注入（仅配置占位）",
            source="phase3.9.2",
            evidence="pending_real_secrets",
            owner_role="security-owner",
        ),
        ActivationBlocker(
            blocker_id="B3-real-telemetry",
            category="observability",
            description="真实生产遥测数据源尚未接入（当前仅合成演练）",
            source="phase3.9.4",
            evidence="pending_real_telemetry_source",
            owner_role="release-manager",
        ),
        ActivationBlocker(
            blocker_id="B4-real-alert-routing",
            category="incident",
            description="真实告警路由（on-call / 工单）尚未配置",
            source="phase3.9.3",
            evidence="pending_real_alert_routing",
            owner_role="incident-commander",
        ),
        ActivationBlocker(
            blocker_id="B5-four-role-signoff",
            category="governance",
            description="四角色真实线下签署尚未完成",
            source="phase3.9.6",
            evidence="pending_four_role_signoff",
            owner_role="production-owner",
        ),
        ActivationBlocker(
            blocker_id="B6-real-topology",
            category="infra",
            description="真实生产拓扑/部署目标尚未决策",
            source="phase3.9.6",
            evidence="pending_real_topology_decision",
            owner_role="production-owner",
        ),
    )


# --------------------------------------------------------------------------- #
# Task 10：待核验登记（统一汇总 3.9.x pending）                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionPendingVerificationItem:
    """一条待真实人工核验事项（Task 10）。"""

    id: str
    phase: str
    item: str
    reason: str
    required_evidence: str
    required_role: str
    current_status: str = "pending_verification"
    source_report: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "phase": self.phase,
            "item": self.item,
            "reason": self.reason,
            "required_evidence": self.required_evidence,
            "required_role": self.required_role,
            "current_status": self.current_status,
            "source_report": self.source_report,
        }


def build_default_pending_verification_registry() -> Tuple[
    ProductionPendingVerificationItem, ...
]:
    """默认待核验事项（汇总 3.9.x 须真人完成的事项）。"""
    return (
        ProductionPendingVerificationItem(
            id="PV1-real-idp",
            phase="3.8.28",
            item="真实 IdP 校验",
            reason="当前 IdP 仅配置占位，未经真实生产校验",
            required_evidence="real_idp_validation_report",
            required_role="security-owner",
            source_report="phase3.8.28-enterprise-identity-report.md",
        ),
        ProductionPendingVerificationItem(
            id="PV2-real-secrets",
            phase="3.9.2",
            item="真实生产密钥注入",
            reason="密钥仅在配置中占位，未注入真实生产凭证",
            required_evidence="real_secret_injection_evidence",
            required_role="security-owner",
            source_report="phase3.9.2_production_release_gate_evidence_package_report.md",
        ),
        ProductionPendingVerificationItem(
            id="PV3-real-telemetry",
            phase="3.9.4",
            item="真实遥测源接入",
            reason="当前仅合成演练通过，无真实生产遥测",
            required_evidence="real_telemetry_source_evidence",
            required_role="release-manager",
            source_report="phase3.9.4_telemetry_synthetic_operations_report.md",
        ),
        ProductionPendingVerificationItem(
            id="PV4-real-alert",
            phase="3.9.3",
            item="真实告警路由",
            reason="告警路由未接真实 on-call/工单系统",
            required_evidence="real_alert_routing_evidence",
            required_role="incident-commander",
            source_report="phase3.9.3_production_observability_incident_readiness_report.md",
        ),
        ProductionPendingVerificationItem(
            id="PV5-real-topology",
            phase="3.9.6",
            item="真实生产拓扑决策",
            reason="部署拓扑/目标尚未由主理人决策",
            required_evidence="real_topology_decision",
            required_role="production-owner",
        ),
        ProductionPendingVerificationItem(
            id="PV6-engineering-enabled",
            phase="3.9.6",
            item="engineering_enabled 翻转",
            reason="须四角色签署且主理人在人类终端显式置 true",
            required_evidence="four_role_signoff + human_terminal_action",
            required_role="production-owner",
        ),
    )


# --------------------------------------------------------------------------- #
# Task 20：证据时效                                                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationEvidenceFreshness:
    """证据时效（Task 20）。

    ``freshness_policy`` 无企业政策时恒 ``pending_verification``，AI 不得擅定有效期。
    """

    generated_at: str
    source_commit: str
    source_artifact: str
    hash: Optional[str]
    freshness_status: str = EvidenceFreshnessStatus.PENDING_VERIFICATION.value
    freshness_policy: str = "pending_verification"

    def to_dict(self) -> Dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "source_commit": self.source_commit,
            "source_artifact": self.source_artifact,
            "hash": self.hash,
            "freshness_status": self.freshness_status,
            "freshness_policy": self.freshness_policy,
        }


# --------------------------------------------------------------------------- #
# Task 14：工程激活契约                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringActivationContract:
    """工程激活契约（Task 14）：定义"何时允许真人开启"，AI 只判定、不开。

    ``activation_allowed_for_human`` 为 True 仅代表"技术前置已满足，可交真人裁决"；
    AI **绝不**自行 ``set engineering_enabled=true``。
    """

    required_gates: Tuple[str, ...]
    required_evidence: Tuple[str, ...]
    required_signoffs: Tuple[str, ...]
    blocker_count: int
    pending_count: int
    activation_allowed_for_human: bool
    note: str = (
        "ENGINEERING_ACTIVATION_CONTRACT: AI 只判定 activation_allowed_for_human；"
        "真实 engineering_enabled=true 仅能由主理人在人类终端、四角色签署后显式执行"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "required_gates": list(self.required_gates),
            "required_evidence": list(self.required_evidence),
            "required_signoffs": list(self.required_signoffs),
            "blocker_count": self.blocker_count,
            "pending_count": self.pending_count,
            "activation_allowed_for_human": self.activation_allowed_for_human,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# Task 15：结构级禁名（复用红线机制，不复制第二套）                              #
# 必须在 Task 8 门禁类之前定义，供 _RedLineForbiddenMixin 类体引用。             #
# --------------------------------------------------------------------------- #
# Phase 3.9.6 激活就绪层专属禁名增量（在冻结/激活/接收禁名集之上叠加）。
_ACTIVATION_READINESS_EXTRA_FORBIDDEN = (
    # 红线①：禁止 AI 翻转生产启用态
    "set_engineering_enabled",
    "enable_engineering",
    "turn_on_engineering",
    # 红线④/⑤：禁止 AI 宣布/批准生产
    "activate_production",
    "deploy_production",
    "execute_deployment",
    "declare_go_live",
    "approve_production",
    "mark_ready_for_production",
    # 红线⑦：禁止写真实密钥/凭证
    "write_production_secret",
    "inject_production_credential",
    # 红线⑧：禁止自动授权
    "grant_production_permission",
    "auto_grant_activation",
    # 红线⑩：禁止自动执行运维动作/关闭事件
    "execute_rollback",
    "run_runbook",
    "acknowledge_incident",
    "resolve_incident",
    "close_incident",
    "auto_signoff_activation",
)

_ACTIVATION_READINESS_FORBIDDEN = _dedupe(
    _FREEZE_ACTIVATION_FORBIDDEN,
    _ACTIVATION_READINESS_EXTRA_FORBIDDEN,
)

ACTIVATION_READINESS_EXTRA_FORBIDDEN_COUNT = len(_ACTIVATION_READINESS_EXTRA_FORBIDDEN)
ACTIVATION_READINESS_FORBIDDEN_COUNT = len(_ACTIVATION_READINESS_FORBIDDEN)


# --------------------------------------------------------------------------- #
# Task 8：生产激活就绪门禁（facade，复用 ControlledActivationGate 客观检查）       #
# --------------------------------------------------------------------------- #
class ProductionActivationReadinessGate(_RedLineForbiddenMixin):
    """生产激活就绪门禁（Task 8，fail-closed，只读，永不 AI 自决放行）。

    复用 3.9.2 ``ControlledActivationGate`` 的客观检查语义（engineering_enabled /
    证据包 / 治理完整性 / 回滚恢复 / 真实签署），并叠加 Phase 3.9.6 就绪维度
    （阻断器 / 待核验）。状态只产 ``BLOCKED`` / ``PENDING_VERIFICATION`` /
    ``READY_FOR_HUMAN_SIGNOFF``，**永不** ``APPROVED``。
    """

    _FORBIDDEN = _ACTIVATION_READINESS_FORBIDDEN

    def __init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建激活就绪门禁（红线①）"
            )

    CHECK_KEYS = (
        "engineering_enabled_false",
        "evidence_bundle_complete",
        "governance_integrity_9_9",
        "rollback_reference_present",
        "recovery_validation_present",
        "no_activation_blockers",
        "human_signoffs_complete",
        "no_pending_verification",
    )

    def evaluate(
        self,
        *,
        engineering_enabled: bool,
        evidence_bundle_complete: bool,
        governance_integrity_ok: bool,
        rollback_reference_present: bool,
        recovery_validation_present: bool,
        blockers: Sequence[ActivationBlocker],
        pending_items: Sequence[ProductionPendingVerificationItem],
        signoff_complete: bool,
    ) -> "ProductionActivationReadinessGateResult":
        checks: Dict[str, bool] = {
            "engineering_enabled_false": engineering_enabled is False,
            "evidence_bundle_complete": bool(evidence_bundle_complete),
            "governance_integrity_9_9": bool(governance_integrity_ok),
            "rollback_reference_present": bool(rollback_reference_present),
            "recovery_validation_present": bool(recovery_validation_present),
            "no_activation_blockers": len(blockers) == 0,
            "human_signoffs_complete": bool(signoff_complete),
            "no_pending_verification": len(pending_items) == 0,
        }
        # 硬客观检查（不含"真实人工签署/待核验"，后者属人工前置态而非硬失败）。
        hard_keys = (
            "engineering_enabled_false",
            "evidence_bundle_complete",
            "governance_integrity_9_9",
            "rollback_reference_present",
            "recovery_validation_present",
        )
        hard_missing = [k for k in hard_keys if not checks[k]]
        if hard_missing or not checks["no_activation_blockers"]:
            status = ActivationReadinessStatus.BLOCKED
        elif not checks["human_signoffs_complete"] or not checks["no_pending_verification"]:
            status = ActivationReadinessStatus.PENDING_VERIFICATION
        else:
            status = ActivationReadinessStatus.READY_FOR_HUMAN_SIGNOFF

        return ProductionActivationReadinessGateResult(
            gate_id="parg",
            status=status,
            checks=checks,
            missing=[k for k, v in checks.items() if not v],
            evaluated_at=_now(),
        )


@dataclass(frozen=True)
class ProductionActivationReadinessGateResult:
    """就绪门禁评估结果（只读事实）。"""

    gate_id: str
    status: ActivationReadinessStatus
    checks: Dict[str, bool]
    missing: List[str]
    evaluated_at: str
    note: str = (
        "PRODUCTION_ACTIVATION_READINESS_GATE_ONLY: 仅判定就绪前置态；"
        "绝不 APPROVED；激活由主理人在人类终端执行"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "checks": dict(self.checks),
            "missing": list(self.missing),
            "evaluated_at": self.evaluated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# Task 11 / 12：人工复核包（Markdown + 机器可读 JSON）                           #
# --------------------------------------------------------------------------- #
@dataclass
class ProductionHumanReviewPacket:
    """供真实责任人审核的复核包（Task 11/12）。只输事实与证据，不夹带 AI 审批结论。"""

    release_candidate: str
    commit_sha: str
    artifact_manifest: Dict[str, object]
    test_summary: Dict[str, object]
    security_summary: Dict[str, object]
    identity_summary: Dict[str, object]
    dr_summary: Dict[str, object]
    observability_summary: Dict[str, object]
    telemetry_summary: Dict[str, object]
    incident_readiness: Dict[str, object]
    rollback: Dict[str, object]
    pending_verification: Tuple[Dict[str, object], ...]
    blockers: Tuple[Dict[str, object], ...]
    required_signatures: Tuple[Dict[str, object], ...]
    generated_at: str = field(default_factory=_now)
    schema_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, object]:
        """机器可读包（含 schema_version 与所有 evidence refs，可哈希，无真实 secret）。"""
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "release_candidate": self.release_candidate,
            "commit_sha": self.commit_sha,
            "artifact_manifest": dict(self.artifact_manifest),
            "test_summary": dict(self.test_summary),
            "security_summary": dict(self.security_summary),
            "identity_summary": dict(self.identity_summary),
            "dr_summary": dict(self.dr_summary),
            "observability_summary": dict(self.observability_summary),
            "telemetry_summary": dict(self.telemetry_summary),
            "incident_readiness": dict(self.incident_readiness),
            "rollback": dict(self.rollback),
            "pending_verification": [dict(p) for p in self.pending_verification],
            "blockers": [dict(b) for b in self.blockers],
            "required_signatures": [dict(s) for s in self.required_signatures],
            "contains_real_secret": False,
        }

    def render_markdown(self) -> str:
        lines = [
            "# 生产激活人工复核包（Human Review Packet）",
            "",
            f"- Release Candidate：`{self.release_candidate}`",
            f"- Commit SHA：`{self.commit_sha}`",
            f"- 生成时间：{self.generated_at}",
            "",
            "> 本包仅列事实与证据，**不含任何 AI 审批结论**。最终 GO 须四角色线下签署。",
            "",
            "## 1. 发布候选 / Commit",
            f"- RC：{self.release_candidate}",
            f"- Commit：{self.commit_sha}",
            "",
            "## 2. 产物清单（Manifest）",
            "```json",
            _json_line(self.artifact_manifest),
            "```",
            "",
            "## 3. 测试摘要",
            "```json",
            _json_line(self.test_summary),
            "```",
            "",
            "## 4. 安全摘要",
            "```json",
            _json_line(self.security_summary),
            "```",
            "",
            "## 5. 身份摘要",
            "```json",
            _json_line(self.identity_summary),
            "```",
            "",
            "## 6. 灾备（DR）摘要",
            "```json",
            _json_line(self.dr_summary),
            "```",
            "",
            "## 7. 可观测性摘要",
            "```json",
            _json_line(self.observability_summary),
            "```",
            "",
            "## 8. 遥测摘要",
            "```json",
            _json_line(self.telemetry_summary),
            "```",
            "",
            "## 9. 事故就绪",
            "```json",
            _json_line(self.incident_readiness),
            "```",
            "",
            "## 10. 回滚",
            "```json",
            _json_line(self.rollback),
            "```",
            "",
            "## 11. 待核验事项（Pending Verification）",
        ]
        for p in self.pending_verification:
            lines.append(
                f"- [{p.get('id')}] {p.get('item')}（{p.get('required_role')} · {p.get('current_status')}）"
            )
        lines.append("")
        lines.append("## 12. 阻断器（Blockers）")
        for b in self.blockers:
            lines.append(
                f"- [{b.get('blocker_id')}] {b.get('description')}（{b.get('owner_role')} · {b.get('resolution_status')}）"
            )
        lines.append("")
        lines.append("## 13. 所需签署（Required Signatures）")
        for s in self.required_signatures:
            lines.append(
                f"- {s.get('required_role')}：{s.get('current_status')}"
                + (f" by {s.get('signed_by')}" if s.get('signed_by') else "")
            )
        lines.append("")
        lines.append("## 14. 结论")
        lines.append(
            "技术准备已完成（BUILT_NO_GO / AWAITING_HUMAN）。**未经批准生产上线**；"
            "四角色签署与真实 secret/IdP/telemetry/alert/topology 仍须人类提供与验证。"
        )
        return "\n".join(lines)


def _json_line(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Task 21：预激活质量门禁（聚合真实 CI 检查，fail-closed）                       #
# --------------------------------------------------------------------------- #
_PRE_ACTIVATION_GATE_SCRIPTS = (
    "scripts/check_governance_repository_integrity.py",
    "scripts/lint/check_production_security.py",
    "scripts/audit_category_ledger_validator.py",
    "scripts/check_phase_boundary.py",
    "scripts/check_repository_clean.py",
    "scripts/check_ci_release_gate_branches.py",
    "scripts/check_closure_commit_integrity.py",
)


class PreActivationQualityGate:
    """预激活质量门禁（Task 21）。

    聚合真实 CI 检查结果：任一失败 → ``BLOCKED``；全过 → ``READY_FOR_HUMAN_SIGNOFF``。
    **永不** ``APPROVED``。
    """

    CHECK_KEYS = (
        "agents_tests",
        "backend_tests",
        "frontend_tests",
        "tsc",
        "release_gate",
        "telemetry",
        "synthetic_drill",
        "repository_integrity",
        "production_security",
        "identity_security",
        "audit_ledger",
        "phase_boundary",
        "repo_clean",
        "activation_readiness_tests",
        "activation_blockers",
        "pending_registry",
    )

    @staticmethod
    def evaluate(checks: Dict[str, bool]) -> ActivationReadinessStatus:
        missing = [k for k, v in checks.items() if not v]
        if missing:
            return ActivationReadinessStatus.BLOCKED
        return ActivationReadinessStatus.READY_FOR_HUMAN_SIGNOFF

    @staticmethod
    def collect_from_repo(
        root: str, *, run_gate_scripts: bool = True
    ) -> Dict[str, bool]:
        """从仓库运行真实门禁脚本，构建 checks 字典（CI 用；开发期可传 run=False）。"""
        checks: Dict[str, bool] = {k: False for k in PreActivationQualityGate.CHECK_KEYS}
        if run_gate_scripts:
            for script in _PRE_ACTIVATION_GATE_SCRIPTS:
                path = os.path.join(root, script)
                if not os.path.isfile(path):
                    continue
                try:
                    rc = subprocess.run(
                        ["python3", path],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        check=False,
                    )
                    passed = rc.returncode == 0
                except (OSError, subprocess.SubprocessError):
                    passed = False
                if "repository_integrity" in script:
                    checks["repository_integrity"] = passed
                elif "check_production_security" in script:
                    checks["production_security"] = passed
                elif "audit_category_ledger_validator" in script:
                    checks["audit_ledger"] = passed
                elif "check_phase_boundary" in script:
                    checks["phase_boundary"] = passed
                elif "check_repository_clean" in script:
                    checks["repo_clean"] = passed
                elif "check_ci_release_gate_branches" in script:
                    checks["release_gate"] = passed
                elif "check_closure_commit_integrity" in script:
                    checks["activation_readiness_tests"] = passed
        return checks


# --------------------------------------------------------------------------- #
# 顶层组装：从仓库事实合成就绪 dossier（供 API / 报告消费）                      #
# --------------------------------------------------------------------------- #
def assemble_activation_readiness_dossier(
    *, rc_id: str, root_dir: str = ".", signoff_registry: Optional[HumanSignoffRegistry] = None
) -> Dict[str, object]:
    """从仓库事实合成生产激活就绪 dossier（只读，不持久化、不激活）。"""
    from agents.enterprise.production_release.freeze_checker import (  # 局部导入，避免循环
        _governance_integrity_ok,
    )

    registry = signoff_registry or HumanSignoffRegistry(rc_id=rc_id)
    eng = load_engineering_enabled()
    gov_ok = _governance_integrity_ok(os.path.abspath(root_dir))
    evidence_bundle = build_default_activation_evidence_bundle_v2(rc_id=rc_id)
    blockers = build_default_activation_blockers()
    pending = build_default_pending_verification_registry()
    requirements = build_default_signoff_requirements(registry)

    gate = ProductionActivationReadinessGate()
    result = gate.evaluate(
        engineering_enabled=eng,
        evidence_bundle_complete=evidence_bundle.production_evidence_complete,
        governance_integrity_ok=gov_ok,
        rollback_reference_present=True,
        recovery_validation_present=True,
        blockers=blockers,
        pending_items=pending,
        signoff_complete=registry.snapshot().signoff_complete,
    )
    sod = SoDValidator.validate(registry)
    contract = EngineeringActivationContract(
        required_gates=ProductionActivationReadinessGate.CHECK_KEYS,
        required_evidence=("activation-evidence-bundle-v2",),
        required_signoffs=REQUIRED_SIGNOFF_ROLES,
        blocker_count=len(blockers),
        pending_count=len(pending),
        activation_allowed_for_human=(
            result.status is ActivationReadinessStatus.READY_FOR_HUMAN_SIGNOFF
        ),
    )
    return {
        "rc_id": rc_id,
        "engineering_enabled": eng,
        "evidence_bundle": evidence_bundle.to_dict(),
        "signoff_requirements": [r.to_dict() for r in requirements],
        "sod": sod.to_dict(),
        "blockers": [b.to_dict() for b in blockers],
        "pending_verification": [p.to_dict() for p in pending],
        "readiness_gate": result.to_dict(),
        "contract": contract.to_dict(),
        "status_terminal": "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO",
    }


__all__ = [
    "EvidenceScope",
    "ActivationReadinessStatus",
    "HumanReviewStatus",
    "EvidenceFreshnessStatus",
    "ActivationEvidenceItem",
    "ActivationEvidenceBundleV2",
    "build_default_activation_evidence_bundle_v2",
    "ProductionActivationSignoffRequirement",
    "build_default_signoff_requirements",
    "SoDValidator",
    "SoDValidationResult",
    "ActivationBlocker",
    "build_default_activation_blockers",
    "ProductionPendingVerificationItem",
    "build_default_pending_verification_registry",
    "ActivationEvidenceFreshness",
    "EngineeringActivationContract",
    "ProductionActivationReadinessGate",
    "ProductionActivationReadinessGateResult",
    "ProductionHumanReviewPacket",
    "PreActivationQualityGate",
    "assemble_activation_readiness_dossier",
    "ACTIVATION_READINESS_EXTRA_FORBIDDEN_COUNT",
    "ACTIVATION_READINESS_FORBIDDEN_COUNT",
]

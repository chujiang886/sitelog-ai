"""Phase 3.9.6 最终激活评审包（T8）—— 供真实人工裁决的材料，永不含裁决。

本模块把 T5 接收服务的只读汇总（``EvidenceIntakeSummary``）、T7 签署登记簿快照
（``HumanSignoffRegistrySnapshot``）与 3.9.2 受控激活闸门结论（可选）聚合成一份
**只读评审材料包**，交给主理人 / 四角色责任人做最终 GO / NO-GO 判断。

材料 ≠ 裁决
-----------
这是本模块存在的唯一理由，也是它最容易被误用的地方，因此在三个层面反复加固：

1. **类型层**：``ReviewPackageReadiness`` 的取值集合中**根本不存在** ``approved`` /
   ``production_go`` / ``engineering_approved`` 这类终态；能表达的最高就绪度只有
   ``READY_FOR_HUMAN_FINAL_REVIEW``（"材料齐了，请人来判"）。
2. **数据层**：``human_final_decision`` 字段恒为 ``None`` 且由 ``__post_init__``
   强制 —— 评审包在结构上无法携带裁决结果。
3. **运行时层**：``assert_no_activation_conclusion()`` 对序列化产物做递归扫描，
   一旦在任何非注释字段里出现放行类词元（engineering_approved / production_go /
   activated_by_human / auto_approved…）立即抛 ``EnterpriseRedLineViolationError``。

红线映射（Phase 3.9.6）
-----------------------
* ①：构建期校验 ``safety_invariants_ok()`` 与 ``engineering_enabled is False``，
  启用态下拒绝生成评审包；
* ②⑤：包内不得出现 ``engineering_approved`` / ``PRODUCTION_GO``（运行时扫描强制）；
* ③④⑨：包只**读取**人工事实（签署 / 证据裁决），不构造、不改写、不补齐；
* ⑩：包不是闸门旁路 —— 它如实转述闸门结论，就绪度取"最差事实"，绝不乐观归并。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from agents.config_loader import load_engineering_enabled
from agents.enterprise.production_release.activation_intake import (
    ActivationEvidenceSubmission,
)
from agents.enterprise.production_release.human_signoff import (
    HumanSignoffRegistrySnapshot,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ActivationReviewPackageError(EnterpriseRedLineViolationError):
    """评审包契约被违反（继承红线异常，保证调用方 fail-closed 处理）。"""


# --------------------------------------------------------------------------- #
# 就绪度（**不含任何放行终态**）                                                  #
# --------------------------------------------------------------------------- #
class ReviewPackageReadiness(str, Enum):
    """评审包就绪度 —— 描述"材料准备到哪一步"，不描述"能不能上线"。

    刻意不提供 ``APPROVED`` / ``PRODUCTION_GO`` / ``ACTIVATED`` 之类的取值：
    最终裁决只能发生在评审包**之外**、由真实自然人在人类终端做出（红线⑤）。
    """

    #: 真实人工已作出阻断性裁决（NO_GO / NEED_MORE_EVIDENCE / 证据被拒）。
    BLOCKED_BY_HUMAN_DECISION = "blocked_by_human_decision"
    #: 必需证据未收齐 / 存在结构校验失败 / 尚未获得人工批准。
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    #: 证据侧齐备，但四角色人工签署未齐。
    AWAITING_HUMAN_SIGNOFF = "awaiting_human_signoff"
    #: 材料全部齐备，等待真实人工最终裁决（**这不是批准**）。
    READY_FOR_HUMAN_FINAL_REVIEW = "ready_for_human_final_review"


#: 评审包允许出现的全部就绪度（用于自检：多一个都不行）。
ALLOWED_REVIEW_READINESS = frozenset(
    {
        ReviewPackageReadiness.BLOCKED_BY_HUMAN_DECISION,
        ReviewPackageReadiness.EVIDENCE_INCOMPLETE,
        ReviewPackageReadiness.AWAITING_HUMAN_SIGNOFF,
        ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW,
    }
)

#: 一旦出现在评审包任何非注释字段中即判定越权的放行类词元（小写匹配）。
FORBIDDEN_CONCLUSION_TOKENS: Tuple[str, ...] = (
    "engineering_approved",
    "production_go",
    "activated_by_human",
    "auto_approved",
    "auto_activated",
    "approved_for_production",
    "activation_granted",
)

#: 扫描时跳过的说明性字段（这些字段的正文本身要**讲**红线，必然含关键词）。
_NOTE_KEYS = ("note", "notes", "disclaimer", "human_action_required")


def _scan_forbidden(payload: Any, path: str = "$") -> List[str]:
    """递归扫描序列化产物，返回命中放行类词元的字段路径（跳过说明性字段）。"""
    hits: List[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_s = str(key)
            if key_s in _NOTE_KEYS or key_s.endswith("_note"):
                continue
            hits.extend(_scan_forbidden(value, f"{path}.{key_s}"))
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            hits.extend(_scan_forbidden(item, f"{path}[{idx}]"))
    elif isinstance(payload, str):
        low = payload.lower()
        for token in FORBIDDEN_CONCLUSION_TOKENS:
            if token in low:
                hits.append(f"{path}:{token}")
    return hits


# --------------------------------------------------------------------------- #
# 评审包                                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FinalActivationReviewPackage:
    """最终激活评审包（T8，只读材料）。

    读者是**人**：主理人与四位责任角色。因此除了机器字段外，还提供
    ``render_markdown()`` 输出可直接进入线下评审会的清单。

    ``human_final_decision`` 恒为 ``None`` —— 结构上不承载裁决（红线⑤）。
    """

    package_id: str
    rc_id: str
    readiness: ReviewPackageReadiness
    generated_at: str
    generated_for_actor: str

    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    signoff_snapshot: Dict[str, Any] = field(default_factory=dict)
    gate_snapshot: Optional[Dict[str, Any]] = None

    evidence_index: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    signoff_scope_gaps: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    outstanding_items: Tuple[str, ...] = field(default_factory=tuple)
    redline_assertions: Dict[str, bool] = field(default_factory=dict)
    decision_log_size: int = 0

    #: 恒为 None：评审包不携带、也无法携带最终裁决。
    human_final_decision: None = None

    note: str = (
        "REVIEW_MATERIAL_ONLY: 供真实人工裁决的材料汇总；不含 engineering_approved / "
        "Production GO 结论；不翻转 engineering_enabled；不绕过 ControlledActivationGate"
    )
    human_action_required: str = (
        "请四位责任角色（production-owner / release-manager / security-owner / auditor）"
        "线下独立复核后，由主理人在人类终端作出 GO / NO-GO 裁决；AI 不参与裁决。"
    )

    def __post_init__(self) -> None:
        if self.readiness not in ALLOWED_REVIEW_READINESS:
            raise ActivationReviewPackageError(
                f"readiness {self.readiness!r} 不在允许集合内（红线⑤）"
            )
        if self.human_final_decision is not None:
            raise ActivationReviewPackageError(
                "评审包不得携带最终裁决（human_final_decision 必须为 None，红线⑤/⑨）"
            )

    # -- 派生只读事实 ---------------------------------------------------- #

    @property
    def is_blocked(self) -> bool:
        return self.readiness in (
            ReviewPackageReadiness.BLOCKED_BY_HUMAN_DECISION,
            ReviewPackageReadiness.EVIDENCE_INCOMPLETE,
        )

    @property
    def awaiting_human(self) -> bool:
        """是否仍在等待真实人工动作（签署或最终裁决）。

        注意：``READY_FOR_HUMAN_FINAL_REVIEW`` 同样为 True —— 材料齐备只意味着
        "轮到人了"，永远不意味着"已经放行"。
        """
        return self.readiness in (
            ReviewPackageReadiness.AWAITING_HUMAN_SIGNOFF,
            ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "rc_id": self.rc_id,
            "readiness": self.readiness.value,
            "generated_at": self.generated_at,
            "generated_for_actor": self.generated_for_actor,
            "evidence_summary": dict(self.evidence_summary),
            "signoff_snapshot": dict(self.signoff_snapshot),
            "gate_snapshot": dict(self.gate_snapshot) if self.gate_snapshot else None,
            "evidence_index": [dict(e) for e in self.evidence_index],
            "signoff_scope_gaps": {k: list(v) for k, v in self.signoff_scope_gaps.items()},
            "outstanding_items": list(self.outstanding_items),
            "redline_assertions": dict(self.redline_assertions),
            "decision_log_size": self.decision_log_size,
            "human_final_decision": self.human_final_decision,
            "is_blocked": self.is_blocked,
            "awaiting_human": self.awaiting_human,
            "note": self.note,
            "human_action_required": self.human_action_required,
        }

    # -- 运行时红线自检 --------------------------------------------------- #

    def assert_no_activation_conclusion(self) -> None:
        """确认评审包未携带任何放行结论（红线②⑤，构建期即调用）。"""
        if self.human_final_decision is not None:
            raise ActivationReviewPackageError(
                "评审包携带了最终裁决，违反红线⑤"
            )
        if self.redline_assertions.get("engineering_enabled_false") is not True:
            raise ActivationReviewPackageError(
                "评审包必须断言 engineering_enabled=False（红线①）"
            )
        hits = _scan_forbidden(self.to_dict())
        if hits:
            raise ActivationReviewPackageError(
                "评审包出现放行类结论词元（红线②⑤）: " + "; ".join(sorted(hits))
            )

    # -- 人类可读渲染 ------------------------------------------------------ #

    def render_markdown(self) -> str:
        """渲染供线下评审会使用的 Markdown 清单（材料，不是结论）。"""
        ev = self.evidence_summary
        so = self.signoff_snapshot
        lines: List[str] = []
        lines.append(f"# 生产激活最终评审包 · {self.rc_id}")
        lines.append("")
        lines.append(f"- 包 ID：`{self.package_id}`")
        lines.append(f"- 生成时间（UTC）：{self.generated_at}")
        lines.append(f"- 生成请求人：{self.generated_for_actor}")
        lines.append(f"- **就绪度：`{self.readiness.value}`**（材料状态，非裁决）")
        lines.append("")
        lines.append("> " + self.note)
        lines.append("")
        lines.append("## 1. 证据接收状态")
        lines.append("")
        lines.append(f"- 必需类型：{', '.join(ev.get('required_types', [])) or '（无）'}")
        lines.append(f"- 已提交类型：{', '.join(ev.get('submitted_types', [])) or '（无）'}")
        lines.append(f"- **缺失/未获人工批准类型：{', '.join(ev.get('missing_types', [])) or '无'}**")
        lines.append(f"- 提交总数：{ev.get('total_submissions', 0)}")
        lines.append(f"- 结构校验失败：{len(ev.get('validation_failed_ids', []))}")
        lines.append(f"- 已获人工批准：{len(ev.get('human_approved_ids', []))}")
        lines.append(f"- 被人工驳回：{len(ev.get('human_rejected_ids', []))}")
        lines.append(f"- 待人工复核：{len(ev.get('awaiting_human_ids', []))}")
        lines.append("")
        lines.append("## 2. 证据明细（仅引用与哈希，不含原文）")
        lines.append("")
        if self.evidence_index:
            lines.append("| 提交 ID | 类型 | 状态 | 结构 | 哈希一致 | 溯源可核验 | 裁决人 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for item in self.evidence_index:
                lines.append(
                    "| `{sid}` | {etype} | {status} | {ok} | {hm} | {pv} | {by} |".format(
                        sid=item.get("submission_id", ""),
                        etype=item.get("evidence_type", ""),
                        status=item.get("status", ""),
                        ok="✓" if item.get("structurally_valid") else "✗",
                        hm={True: "✓", False: "✗", None: "未算"}.get(
                            item.get("hash_match"), "未算"
                        ),
                        pv="✓" if item.get("provenance_verifiable") else "✗",
                        by=item.get("human_decision_by") or "—",
                    )
                )
        else:
            lines.append("（尚无任何证据提交）")
        lines.append("")
        lines.append("## 3. 四角色人工签署")
        lines.append("")
        lines.append(f"- 必需角色：{', '.join(so.get('required_roles', []))}")
        lines.append(f"- 已签署：{', '.join(so.get('signed_roles', [])) or '（无）'}")
        lines.append(f"- **缺失：{', '.join(so.get('missing_roles', [])) or '无'}**")
        lines.append(f"- 阻断角色：{', '.join(so.get('blocking_roles', [])) or '无'}")
        lines.append(f"- 签署齐备（四角色且全 GO）：{so.get('signoff_complete', False)}")
        lines.append(f"- 历史记录总数：{so.get('total_records', 0)}"
                     f"（被取代 {len(so.get('superseded_records', []))} 条）")
        if self.signoff_scope_gaps:
            lines.append("")
            lines.append("### 3.1 签署覆盖面缺口（声明未复核的必需证据）")
            lines.append("")
            for role, gaps in sorted(self.signoff_scope_gaps.items()):
                lines.append(f"- `{role}`：{', '.join(gaps)}")
        lines.append("")
        lines.append("## 4. 受控激活闸门")
        lines.append("")
        if self.gate_snapshot:
            lines.append(f"- 闸门状态：`{self.gate_snapshot.get('status', '')}`")
            miss = self.gate_snapshot.get("missing", []) or []
            lines.append(f"- 未通过检查：{', '.join(miss) or '无'}")
        else:
            lines.append("- 未提供闸门评估结果（材料不完整，人工需自行核对）")
        lines.append("")
        lines.append("## 5. 待办阻断项")
        lines.append("")
        if self.outstanding_items:
            for item in self.outstanding_items:
                lines.append(f"- [ ] {item}")
        else:
            lines.append("- （无机器可见阻断项；仍需人工独立判断）")
        lines.append("")
        lines.append("## 6. 红线断言")
        lines.append("")
        for key, value in sorted(self.redline_assertions.items()):
            lines.append(f"- `{key}`：{'✓' if value else '✗'}")
        lines.append("")
        lines.append("## 7. 需要人来做的事")
        lines.append("")
        lines.append(self.human_action_required)
        lines.append("")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 工厂                                                                          #
# --------------------------------------------------------------------------- #
def _index_submission(sub: ActivationEvidenceSubmission) -> Dict[str, Any]:
    """把一条提交压缩成评审索引项（**只保留引用与判定，不含原文**，T13）。"""
    return {
        "submission_id": sub.submission_id,
        "evidence_type": sub.evidence_type,
        "title": sub.title,
        "content_reference": sub.content_reference,
        "status": sub.status.value,
        "structurally_valid": sub.structurally_valid,
        "hash_match": sub.hash_match,
        "declared_sha256": sub.provenance.declared_sha256,
        "computed_sha256": sub.computed_sha256,
        "provenance_verifiable": sub.provenance.verifiable,
        "origin_system": sub.provenance.origin_system,
        "origin_reference": sub.provenance.origin_reference,
        "submitted_by": sub.provenance.submitted_by,
        "custody_events": len(sub.provenance.chain_of_custody),
        "validation_findings": list(sub.validation_findings),
        "human_decision_by": sub.human_decision_by,
        "human_decision_at": sub.human_decision_at,
    }


def _derive_outstanding(
    *,
    evidence_summary: Mapping[str, Any],
    signoff: HumanSignoffRegistrySnapshot,
    submissions: Sequence[ActivationEvidenceSubmission],
    gate_snapshot: Optional[Mapping[str, Any]],
    scope_gaps: Mapping[str, Tuple[str, ...]],
) -> Tuple[str, ...]:
    """把机器可见的阻断事实翻译成人话（只陈述事实，不给建议性结论）。"""
    items: List[str] = []
    missing_types = list(evidence_summary.get("missing_types", []))
    if missing_types:
        items.append(
            "以下必需证据类型尚未获得真实人工批准：" + ", ".join(missing_types)
        )
    failed = [s for s in submissions if not s.structurally_valid]
    for sub in failed:
        items.append(
            f"证据 `{sub.submission_id}`（{sub.evidence_type}）结构校验未通过："
            + "；".join(sub.validation_findings or ("未记录具体发现",))
        )
    rejected = [s for s in submissions if s.is_human_rejected]
    for sub in rejected:
        items.append(
            f"证据 `{sub.submission_id}`（{sub.evidence_type}）已被 "
            f"{sub.human_decision_by} 驳回：{sub.human_decision_reason or '未填理由'}"
        )
    if signoff.missing_roles:
        items.append("以下责任角色尚未签署：" + ", ".join(signoff.missing_roles))
    if signoff.blocking_roles:
        items.append(
            "以下责任角色作出阻断性裁决（NO_GO / 需补证据）："
            + ", ".join(signoff.blocking_roles)
        )
    for role, gaps in sorted(scope_gaps.items()):
        items.append(
            f"角色 `{role}` 未声明复核的必需证据：" + ", ".join(gaps)
        )
    if gate_snapshot:
        gate_missing = list(gate_snapshot.get("missing", []) or [])
        if gate_missing:
            items.append("受控激活闸门未通过检查：" + ", ".join(gate_missing))
    else:
        items.append("未附受控激活闸门评估结果，人工需独立核对冻结与治理完整性")
    return tuple(items)


def build_final_activation_review_package(
    *,
    package_id: str,
    rc_id: str,
    generated_for_actor: str,
    evidence_summary: Mapping[str, Any],
    signoff_snapshot: HumanSignoffRegistrySnapshot,
    submissions: Sequence[ActivationEvidenceSubmission] = (),
    gate_snapshot: Optional[Mapping[str, Any]] = None,
    decision_log_size: int = 0,
    required_submission_ids: Sequence[str] = (),
    scope_gaps: Optional[Mapping[str, Tuple[str, ...]]] = None,
) -> FinalActivationReviewPackage:
    """聚合真实事实，产出只读评审材料包。

    就绪度按"**最差事实优先**"归并，绝不乐观合并：

    ``BLOCKED_BY_HUMAN_DECISION`` > ``EVIDENCE_INCOMPLETE``
        > ``AWAITING_HUMAN_SIGNOFF`` > ``READY_FOR_HUMAN_FINAL_REVIEW``

    构建期强制三项红线前置：``safety_invariants_ok()``、
    ``load_engineering_enabled() is False``、以及输出自扫描
    ``assert_no_activation_conclusion()``。任一不满足即抛错，不产出半成品。
    """

    if not safety_invariants_ok():
        raise ActivationReviewPackageError(
            "safety_invariants_ok() 失败：禁止在启用态下生成激活评审包（红线①）"
        )
    engineering_enabled = load_engineering_enabled()
    if engineering_enabled is not False:
        raise ActivationReviewPackageError(
            f"engineering_enabled 必须为 False，实测 {engineering_enabled!r}（红线①）"
        )
    if not str(rc_id).strip():
        raise ActivationReviewPackageError("review package requires a real rc_id")
    if signoff_snapshot.rc_id != rc_id:
        raise ActivationReviewPackageError(
            f"signoff snapshot rc_id mismatch: {signoff_snapshot.rc_id!r} != {rc_id!r}"
        )
    if str(evidence_summary.get("rc_id", rc_id)) != rc_id:
        raise ActivationReviewPackageError(
            "evidence summary rc_id mismatch: "
            f"{evidence_summary.get('rc_id')!r} != {rc_id!r}"
        )

    subs = tuple(submissions)
    gaps: Dict[str, Tuple[str, ...]] = {k: tuple(v) for k, v in (scope_gaps or {}).items()}
    if not gaps and required_submission_ids:
        # 未显式传入时，从签署快照的 evidence_scope_reviewed 现算覆盖面缺口
        # （只读推导，不修改任何人工记录 —— 红线⑨）。
        required_ids = [str(s) for s in required_submission_ids]
        for record in signoff_snapshot.effective_records:
            reviewed = {str(x) for x in (record.get("evidence_scope_reviewed") or [])}
            missing_scope = tuple(s for s in required_ids if s not in reviewed)
            if missing_scope:
                gaps[str(record.get("role", "unknown"))] = missing_scope

    intake_complete = bool(evidence_summary.get("intake_complete", False))
    human_rejected = list(evidence_summary.get("human_rejected_ids", []))

    if signoff_snapshot.blocking_roles or human_rejected:
        readiness = ReviewPackageReadiness.BLOCKED_BY_HUMAN_DECISION
    elif not intake_complete:
        readiness = ReviewPackageReadiness.EVIDENCE_INCOMPLETE
    elif not signoff_snapshot.signoff_complete:
        readiness = ReviewPackageReadiness.AWAITING_HUMAN_SIGNOFF
    else:
        readiness = ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW

    outstanding = _derive_outstanding(
        evidence_summary=evidence_summary,
        signoff=signoff_snapshot,
        submissions=subs,
        gate_snapshot=gate_snapshot,
        scope_gaps=gaps,
    )

    redline_assertions = {
        "engineering_enabled_false": engineering_enabled is False,
        "safety_invariants_ok": True,
        "package_carries_no_decision": True,
        "human_approval_not_synthesized": all(
            (s.human_decision_by is None) or bool(str(s.human_decision_by).strip())
            for s in subs
        ),
        "all_signoffs_by_real_user": all(
            r.get("actor_kind") == "user"
            for r in signoff_snapshot.effective_records
        ),
        "evidence_content_not_stored": True,
    }

    package = FinalActivationReviewPackage(
        package_id=package_id,
        rc_id=rc_id,
        readiness=readiness,
        generated_at=_now(),
        generated_for_actor=generated_for_actor,
        evidence_summary=dict(evidence_summary),
        signoff_snapshot=signoff_snapshot.to_dict(),
        gate_snapshot=dict(gate_snapshot) if gate_snapshot else None,
        evidence_index=tuple(_index_submission(s) for s in subs),
        signoff_scope_gaps=gaps,
        outstanding_items=outstanding,
        redline_assertions=redline_assertions,
        decision_log_size=int(decision_log_size),
    )
    # 输出自扫描：任何放行类词元泄漏进材料包即视为红线违例。
    package.assert_no_activation_conclusion()
    return package


__all__ = [
    "ActivationReviewPackageError",
    "ReviewPackageReadiness",
    "ALLOWED_REVIEW_READINESS",
    "FORBIDDEN_CONCLUSION_TOKENS",
    "FinalActivationReviewPackage",
    "build_final_activation_review_package",
]

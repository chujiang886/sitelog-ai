"""Cost Intelligence Layer（Phase 3.7.6）。

在 3.7.5 约束优化层之上，建立「成本智能层」：
- ``CostEstimator``：对方案做成本估算（material_cost / labor_cost / auxiliary_cost /
  total_estimate），仅产出占位估算壳（CostEstimateDraft），**禁止报价**（红线④）、
  **禁止自动成交价格**（新增）、**禁止伪造市场价格**（新增⑤：单价必须有来源、不硬编码）；
- ``CostExplanation``：为方案生成成本来源解释链，关联 Solution / BOM / Rule / SourceRef
  （只读聚合，不写图、不报价）；
- ``CostReviewQueue``：成本审核队列（draft / reviewing / approved_by_human / rejected），
  **仅人工** 可进入 approved_by_human（红线②：AI 不得批准）。

====================
最高红线（fail-closed，6 条）
====================
① 禁止开启 ``engineering_enabled``（构造/估算/解释/审核全断言 ``safety_invariants_ok``）；
② 禁止输出 ``engineering_approved``（``approve`` 仅 ``by_human=True`` 可入
   ``approved_by_human``，AI 调用抛 ``SolutionRedLineViolationError``）；
③ （沿用）禁止 AI 自动选终/激活（mixin 拦截 ``approve`` / ``select`` / ``finalize`` /
   ``activate`` / ``engineering_approved``）；
④ 禁止自动报价 + 禁止自动成交价格（forbidden 方法名 ``quote`` / ``pricing`` /
   ``deal_price`` / ``final_price``）；
⑤ 禁止伪造市场价格（新增 ``market_price`` 拦截；``CostRule.unit_price`` 必须有
   ``source_ref``、禁止硬编码）；
⑥ 禁止绕过 ``UnifiedActivationGate``（所有构造/决策路径先断言 ``safety_invariants_ok``）。

本层仅承载成本占位估算壳与来源解释；真实价格/报价/成交须经专家双签 + 主理人核准（G6）
写入来源系统，属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.entities import (
    BOMEntity,
    CostRule,
    PENDING_PLACEHOLDER,
    PENDING_VERIFICATION,
    SolutionCandidateEntity,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionRedLineViolationError,
    SolutionReviewError,
    _RedLineForbiddenMixin,
)


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳（审计用）。"""
    return datetime.now(timezone.utc).isoformat()


# 成本智能层 forbidden 方法名（覆盖红线②/③/④/⑤）。
_FORBIDDEN_COST_METHODS = (
    "approve",         # 红线②：不得批准（仅 by_human 可入 approved_by_human）
    "select",          # 红线③：不得选终
    "finalize",        # 红线③：不得定稿
    "activate",        # 红线③：不得激活
    "engineering_approved",  # 红线②：不得输出 engineering_approved
    "quote",           # 红线④：禁止自动报价
    "pricing",         # 红线④：禁止自动报价
    "deal_price",      # 红线④：禁止自动成交价格
    "final_price",     # 红线④：禁止自动成交价格
    "market_price",    # 红线⑤：禁止伪造市场价格
)


# ---------------------------------------------------------------------------
# 报告载体（纯数据，含成本来源链；不含任何决策位 / 报价位）
# ---------------------------------------------------------------------------
@dataclass
class CostEstimateDraft:
    """成本估算占位壳（仅估算，禁止报价，红线④/⑤）。

    所有真实金额字段默认 ``PENDING_PLACEHOLDER``，AI 不填真实单价/总价、不报价、
    不成交价、不伪造市场价。真实价格须经来源（专家双签 + 主理人核准的价目/定额）
    由人工填充。
    """

    estimate_id: str
    solution_id: str
    material_cost: Any = PENDING_PLACEHOLDER
    labor_cost: Any = PENDING_PLACEHOLDER
    auxiliary_cost: Any = PENDING_PLACEHOLDER
    total_estimate: Any = PENDING_PLACEHOLDER
    currency: str = PENDING_PLACEHOLDER
    requires_human_review: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class CostExplanationReport:
    """成本解释报告（关联 Solution / BOM / Rule / SourceRef，含来源链）。"""

    solution_id: str
    source_chain: list[dict[str, Any]] = field(default_factory=list)
    referenced_types: dict[str, list[str]] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


# ---------------------------------------------------------------------------
# 任务3：成本估算器（仅占位估算，禁止报价/成交价/伪造市场价）
# ---------------------------------------------------------------------------
class CostEstimator(_RedLineForbiddenMixin):
    """成本估算器（Cost Estimator）。

    对方案（``SolutionCandidate``）做成本估算拆分（material / labor / auxiliary /
    total），仅产出占位估算壳（``CostEstimateDraft``）。**不报价、不成交价、不伪造市场价**。

    红线：
    - ⑥ 构造断言 ``safety_invariants_ok()``；
    - ③ 无 ``select`` / ``finalize`` / ``activate`` / ``approve``（mixin 拦截）；
    - ④ 无 ``quote`` / ``pricing`` / ``deal_price`` / ``final_price``（mixin 拦截，
      禁止报价/成交价）；
    - ⑤ 无 ``market_price``（mixin 拦截，禁止伪造市场价）；估算不填真实单价。
    """

    _FORBIDDEN = _FORBIDDEN_COST_METHODS

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造成本估算器（红线①/⑥）"
            )

    def _draft(self, candidate: SolutionCandidateEntity, *, stage: str) -> CostEstimateDraft:
        return CostEstimateDraft(
            estimate_id=f"EST-{candidate.solution_id}-{stage}",
            solution_id=candidate.solution_id,
            notes=[
                f"[{stage}] 仅占位估算，真实成本须经来源（价目/定额）由人工填价（红线④/⑤）。",
                "本层不报价、不成交价、不伪造市场价。",
            ],
        )

    def material_cost(self, candidate: SolutionCandidateEntity) -> CostEstimateDraft:
        """材料成本占位估算（不报价）。"""
        return self._draft(candidate, stage="material")

    def labor_cost(self, candidate: SolutionCandidateEntity) -> CostEstimateDraft:
        """人工成本占位估算（不报价）。"""
        return self._draft(candidate, stage="labor")

    def auxiliary_cost(self, candidate: SolutionCandidateEntity) -> CostEstimateDraft:
        """辅材/其他成本占位估算（不报价）。"""
        return self._draft(candidate, stage="auxiliary")

    def total_estimate(self, candidate: SolutionCandidateEntity) -> CostEstimateDraft:
        """总成本占位估算（不报价）。"""
        return self._draft(candidate, stage="total")


# ---------------------------------------------------------------------------
# 任务4：成本解释链（关联 Solution / BOM / Rule / SourceRef，只读聚合）
# ---------------------------------------------------------------------------
class CostExplanation:
    """成本可解释层（Cost Explainability Layer）。

    为方案聚合成本来源解释链，关联 **Solution / BOM / Rule / SourceRef** 四类载体
    （只读聚合，不写图、不报价、不伪造市场价）。``BOMEntity`` / ``CostRule`` 为独立
    数据壳（非图谱实体），直接以对象列举；``SourceRef`` 可经图谱遍历补充。

    红线：只读聚合，不写、不报价、不成交价。
    """

    def __init__(self, repository: Optional[KnowledgeGraphRepository] = None) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造成本解释器（红线①/⑥）"
            )

    def explain(
        self,
        candidate: SolutionCandidateEntity,
        *,
        bom_entries: Optional[list[BOMEntity]] = None,
        cost_rules: Optional[list[CostRule]] = None,
    ) -> CostExplanationReport:
        """构建方案成本来源链（Solution / BOM / Rule / SourceRef 四类）。"""
        chain: list[dict[str, Any]] = []
        referenced: dict[str, list[str]] = {
            "Solution": [],
            "BOM": [],
            "Rule": [],
            "SourceRef": [],
        }

        # Solution（候选本体）
        chain.append({
            "category": "Solution",
            "node_id": candidate.solution_id,
            "label": getattr(candidate, "label", candidate.solution_id),
            "relation_type": "self",
        })
        referenced["Solution"].append(candidate.solution_id)

        # BOM（物料清单数据壳）
        for b in (bom_entries or []):
            chain.append({
                "category": "BOM",
                "node_id": b.bom_id,
                "solution_id": b.solution_id,
                "item_type": b.item_type,
                "item_name": b.item_name,
                "source_ref": b.source_ref,
                "status": b.status,
                "relation_type": "solution_to_bom",
            })
            referenced["BOM"].append(b.bom_id)

        # Rule（成本规则数据壳，含 source_ref 与 unit_price 占位）
        for r in (cost_rules or []):
            chain.append({
                "category": "Rule",
                "node_id": r.rule_id,
                "source_ref": r.source_ref,
                "formula": r.formula,
                "unit_price": r.unit_price,  # 恒 None 或经来源填充，绝不硬编码
                "status": r.status,
                "relation_type": "solution_to_cost_rule",
            })
            referenced["Rule"].append(r.rule_id)

        # SourceRef（图谱遍历补充，若提供 repository）
        if self._repo is not None:
            node = self._repo.get_node(candidate.solution_id)
            if node is not None:
                try:
                    steps = self._repo.traverse(
                        candidate.solution_id, direction="out", max_depth=3
                    )
                except KeyError:
                    steps = []
                for s in steps:
                    tgt = self._repo.get_node(s["node_id"])
                    if tgt is None:
                        continue
                    if tgt.entity_type in ("SourceRef", "Rule", "BOM"):
                        chain.append({
                            "category": tgt.entity_type,
                            "node_id": s["node_id"],
                            "entity_type": tgt.entity_type,
                            "relation_type": s.get("relation_type"),
                            "via_edge_id": s.get("via_edge_id"),
                            "label": tgt.label,
                        })
                        referenced.setdefault(tgt.entity_type, []).append(s["node_id"])

        explanation = [
            f"方案 {candidate.solution_id} 成本来源链长度={len(chain)}。",
            f"引用 Solution={referenced['Solution']}",
            f"引用 BOM={referenced['BOM']}",
            f"引用 Rule={referenced['Rule']}",
            f"引用 SourceRef={referenced['SourceRef']}",
            "成本来源链供人工核验取价依据（AI 不参与权威性/价格判定）。",
        ]
        return CostExplanationReport(
            solution_id=candidate.solution_id,
            source_chain=chain,
            referenced_types=referenced,
            explanation=explanation,
            requires_human_review=True,
        )


# ---------------------------------------------------------------------------
# 任务5：成本人工审核队列（draft / reviewing / approved_by_human / rejected）
# ---------------------------------------------------------------------------
@dataclass
class CostReviewItem:
    """成本审核条目（状态机载体）。"""

    review_id: str
    solution_id: str
    state: str
    draft: CostEstimateDraft
    created_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None


class CostReviewQueue:
    """成本审核队列（状态机：draft → reviewing → approved_by_human / rejected）。

    红线：
    - ② ``approve`` 仅 ``by_human=True`` 可进入 ``approved_by_human``；AI 调用抛
      ``SolutionRedLineViolationError``（禁止输出 engineering_approved）；
    - ④ ``reject`` 同样要求 ``by_human=True``（AI 不做任何终裁）；
    - ⑤/⑥ 构造/决策路径断言 ``safety_invariants_ok()``；
    - 非法状态转移抛 ``SolutionReviewError``（正常业务校验，非红线）。
    """

    STATES = ("draft", "reviewing", "approved_by_human", "rejected")
    _REVIEWABLE = "reviewing"

    def __init__(self) -> None:
        self._items: dict[str, CostReviewItem] = {}
        self._seq: int = 0
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造成本审核队列（红线①/⑥）"
            )

    def _get(self, review_id: str) -> CostReviewItem:
        item = self._items.get(review_id)
        if item is None:
            raise SolutionReviewError(f"审核条目 {review_id!r} 不存在")
        return item

    def submit(
        self, candidate: SolutionCandidateEntity, *, draft: CostEstimateDraft
    ) -> str:
        """将成本估算提交入队（状态 draft）。"""
        self._seq += 1
        rid = f"CREV-{candidate.solution_id}-{self._seq}"
        self._items[rid] = CostReviewItem(
            review_id=rid,
            solution_id=candidate.solution_id,
            state="draft",
            draft=draft,
            created_at=_utc_now(),
        )
        return rid

    def begin_review(self, review_id: str) -> CostReviewItem:
        """draft → reviewing。"""
        item = self._get(review_id)
        if item.state != "draft":
            raise SolutionReviewError(
                f"begin_review 失败：当前态 {item.state!r} 应为 draft"
            )
        item.state = "reviewing"
        return item

    def approve(self, review_id: str, *, by_human: bool = False) -> CostReviewItem:
        """reviewing → approved_by_human（**仅人工**）。"""
        item = self._get(review_id)
        if item.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"approve 失败：当前态 {item.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得批准成本：approve 必须 by_human=True（红线②）。"
                "最终批准须经真实主理人/专家线下决策。"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下批准成本（红线①/⑥）"
            )
        item.state = "approved_by_human"
        item.decided_at = _utc_now()
        item.decided_by = "human_reviewer"
        return item

    def reject(self, review_id: str, *, by_human: bool = False) -> CostReviewItem:
        """reviewing → rejected（**仅人工**）。"""
        item = self._get(review_id)
        if item.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"reject 失败：当前态 {item.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得做出终裁：reject 必须 by_human=True（红线④）。"
                "任何终裁须由真实主理人/专家驱动。"
            )
        item.state = "rejected"
        item.decided_at = _utc_now()
        item.decided_by = "human_reviewer"
        return item


__all__ = [
    "SolutionRedLineViolationError",
    "CostEstimator",
    "CostEstimateDraft",
    "CostExplanation",
    "CostExplanationReport",
    "CostReviewQueue",
    "CostReviewItem",
]

"""Solution Constraint & Optimization Layer（Phase 3.7.5）。

在 3.7.4 方案生成层之上，建立「方案约束与优化层」：
- ``SolutionConstraintEngine``：对候选方案做约束检查（geometry / dependency /
  compatibility / conflict），**仅过滤明显冲突**，**不**自动选择最终方案；
- ``SolutionComparison``：比较候选 A/B/C，输出 difference / risk / knowledge_trace，
  **无** winner；
- ``SolutionExplanation``：为候选生成可解释说明（引用 Case / Rule / Threshold /
  KnowledgeItem 的**完整来源链**）。

====================
最高红线（fail-closed，6 条）
====================
① 禁止开启 ``engineering_enabled``（构造/检查/解释全断言 ``safety_invariants_ok``）；
② 禁止输出 ``engineering_approved``（本层不提供任何批准/选终路径）；
③ 禁止 AI 自动选择最终方案（引擎/比较器无 ``select`` / ``finalize``，由 mixin 拦截）；
④ 禁止自动报价（新增 forbidden 方法名 ``quote`` / ``pricing``）+ 禁止伪造工程参数
   （约束仅占位壳，components/confidence 恒 PENDING/pending，不填真实值）；
⑤ 禁止伪造工程参数（约束模型仅占位，不填真实约束数值）；
⑥ 禁止绕过 ``UnifiedActivationGate``（所有构造/检查路径先断言 ``safety_invariants_ok``）。

本层仅承载约束标注与对比分析；真实约束/选终/报价须经专家双签 + 主理人核准（G6），
属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.entities import (
    PENDING_PLACEHOLDER,
    PENDING_VERIFICATION,
    SolutionCandidateEntity,
    SolutionConstraint,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionRedLineViolationError,
    _RedLineForbiddenMixin,
)


# 约束/优化层 forbidden 方法名（覆盖红线②/③/④：不得批准/选终/激活/报价）。
_FORBIDDEN_CONSTRAINT_METHODS = (
    "approve",
    "select",
    "finalize",
    "activate",
    "engineering_approved",
    "quote",
    "pricing",
)


# ---------------------------------------------------------------------------
# 报告载体（纯数据，含分析链；不含任何决策位）
# ---------------------------------------------------------------------------
@dataclass
class SolutionConstraintReport:
    """约束检查结果（仅分析，含明显冲突列表，不下选终结论）。"""

    check_type: str
    candidate_ids: list[str]
    issues: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    requires_human_review: bool = True
    explanation: list[str] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


@dataclass
class SolutionComparisonReport:
    """对比报告（difference / risk / knowledge_trace，winner 恒 None）。"""

    candidate_ids: list[str]
    difference: list[dict[str, Any]] = field(default_factory=list)
    risk: list[str] = field(default_factory=list)
    knowledge_trace: list[dict[str, Any]] = field(default_factory=list)
    winner: Any = None
    requires_human_review: bool = True
    explanation: list[str] = field(default_factory=list)


@dataclass
class SolutionExplanationReport:
    """解释报告（完整来源链 + 引用分类，供人工核验）。"""

    candidate_id: str
    source_chain: list[dict[str, Any]] = field(default_factory=list)
    referenced_types: dict[str, list[str]] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


# ---------------------------------------------------------------------------
# 任务2：方案约束引擎（仅过滤明显冲突，不自动选终）
# ---------------------------------------------------------------------------
class SolutionConstraintEngine(_RedLineForbiddenMixin):
    """方案约束引擎（Solution Constraint Engine）。

    对候选方案集合施加约束检查（geometry / dependency / compatibility / conflict），
    **仅过滤明显冲突**（如候选 id 重复、引用缺失、约束与候选结构矛盾），
    **不**自动选择最终方案、不报价、不伪造工程参数。

    红线：
    - ⑥ 构造断言 ``safety_invariants_ok()``；
    - ③ 无 ``select`` / ``finalize``（mixin 拦截）；
    - ④ 新增 ``quote`` / ``pricing`` 拦截（禁止自动报价）；
    - ⑤ 约束仅占位壳，检查不填真实值。
    """

    _FORBIDDEN = _FORBIDDEN_CONSTRAINT_METHODS

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造约束引擎（红线①/⑥）"
            )

    def check_geometry(self, candidates: list[SolutionCandidateEntity]) -> SolutionConstraintReport:
        """几何约束检查：仅检测明显冲突（solution_id 重复 / 方案实质未定）。

        不输出真实几何结论；真实几何约束须经专家双签 + 主理人核准（G6）。
        """
        issues: list[tuple[str, str]] = []
        conflicts: list[tuple[str, str]] = []
        seen: set[str] = set()
        for c in candidates:
            if c.solution_id in seen:
                issues.append((c.solution_id, "duplicate_solution_id"))
                conflicts.append((c.solution_id, "duplicate_solution_id"))
            seen.add(c.solution_id)
            # 方案实质未定（pending）仅作待核验标注，非「冲突」
            if c.components == PENDING_VERIFICATION:
                issues.append((c.solution_id, "geometry_unsettled_pending_verification"))
        explanation = [
            "几何约束仅检查明显冲突（id 重复 / 方案实质未定），不做真实几何判定。",
            "真实几何约束须经专家双签 + 主理人核准（G6）。",
        ]
        return SolutionConstraintReport(
            check_type="geometry",
            candidate_ids=[c.solution_id for c in candidates],
            issues=issues,
            conflicts=conflicts,
            requires_human_review=True,
            explanation=explanation,
        )

    def check_dependency(self, candidates: list[SolutionCandidateEntity]) -> SolutionConstraintReport:
        """依赖约束检查：仅检测明显冲突（候选引用的 Case/Rule/Threshold 缺失于图谱）。"""
        repo = self._repo
        issues: list[tuple[str, str]] = []
        conflicts: list[tuple[str, str]] = []
        for c in candidates:
            for cid in c.related_cases:
                if repo.get_node(cid) is None:
                    issues.append((c.solution_id, f"missing_case:{cid}"))
                    conflicts.append((c.solution_id, f"missing_case:{cid}"))
            for rid in c.related_rules:
                if repo.get_node(rid) is None:
                    issues.append((c.solution_id, f"missing_rule:{rid}"))
                    conflicts.append((c.solution_id, f"missing_rule:{rid}"))
            for tid in c.related_thresholds:
                if repo.get_node(tid) is None:
                    issues.append((c.solution_id, f"missing_threshold:{tid}"))
                    conflicts.append((c.solution_id, f"missing_threshold:{tid}"))
        explanation = [
            "依赖约束仅检查候选引用的 Case/Rule/Threshold 是否真实存在于图谱（明显缺失冲突）。",
            "不替代人工依赖核验。",
        ]
        return SolutionConstraintReport(
            check_type="dependency",
            candidate_ids=[c.solution_id for c in candidates],
            issues=issues,
            conflicts=conflicts,
            requires_human_review=True,
            explanation=explanation,
        )

    def check_compatibility(
        self,
        candidates: list[SolutionCandidateEntity],
        constraints: Optional[list[SolutionConstraint]] = None,
    ) -> SolutionConstraintReport:
        """兼容约束检查：比对候选与约束（仅占位），检测约束标记冲突。

        仅做结构性扫描：候选/约束未转正时一律标 pending，**不**据此自动拒绝或选终。
        """
        constraints = constraints or []
        issues: list[tuple[str, str]] = []
        conflicts: list[tuple[str, str]] = []
        for c in candidates:
            if c.verification_status == PENDING_VERIFICATION:
                issues.append((c.solution_id, "candidate_unverified_incompatible_pending"))
        for con in constraints:
            if con.status != PENDING_VERIFICATION:
                # 若有人传入非 pending 状态（异常），仅记录，不据此自动拒绝
                issues.append((con.constraint_id, "constraint_status_non_pending_review_only"))
        explanation = [
            "兼容约束仅做结构性扫描：候选未转正或与约束状态不符时标 pending，不做真实兼容判定。",
            "真实兼容须专家双签 + 主理人核准。",
        ]
        return SolutionConstraintReport(
            check_type="compatibility",
            candidate_ids=[c.solution_id for c in candidates],
            issues=issues,
            conflicts=conflicts,
            requires_human_review=True,
            explanation=explanation,
        )

    def check_conflict(self, candidates: list[SolutionCandidateEntity]) -> SolutionConstraintReport:
        """冲突约束检查：仅检测候选间的明显互斥（同名 id 指向不同 input_context）。"""
        issues: list[tuple[str, str]] = []
        conflicts: list[tuple[str, str]] = []
        by_id: dict[str, SolutionCandidateEntity] = {}
        for c in candidates:
            if c.solution_id in by_id:
                prev = by_id[c.solution_id]
                if prev.input_context != c.input_context:
                    issues.append((c.solution_id, "conflicting_context_same_id"))
                    conflicts.append((c.solution_id, "conflicting_context_same_id"))
            else:
                by_id[c.solution_id] = c
        explanation = [
            "冲突约束仅检测同名 id 的上下文互斥等明显冲突，不做方案优劣评判。",
            "不自动选终（红线③）。",
        ]
        return SolutionConstraintReport(
            check_type="conflict",
            candidate_ids=[c.solution_id for c in candidates],
            issues=issues,
            conflicts=conflicts,
            requires_human_review=True,
            explanation=explanation,
        )


# ---------------------------------------------------------------------------
# 任务3：候选方案对比器（A/B/C，无 winner）
# ---------------------------------------------------------------------------
class SolutionComparison(_RedLineForbiddenMixin):
    """候选方案对比器（SolutionComparison）。

    比较多个候选方案的 difference / risk / knowledge_trace，**不**输出 winner
    （winner 恒 None，并由 mixin 拦截任何 ``select`` / ``finalize`` / ``quote`` / ``pricing``）。

    红线：
    - ③ 无 winner / 无 select（mixin 拦截）；
    - ④ 禁止报价（``quote`` / ``pricing`` 拦截）；
    - ⑤ 仅对比占位壳，不编造真实优劣。
    """

    _FORBIDDEN = _FORBIDDEN_CONSTRAINT_METHODS

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造对比器（红线①/⑥）"
            )

    def compare(self, candidates: list[SolutionCandidateEntity]) -> SolutionComparisonReport:
        """对比候选 A/B/C，输出 difference / risk / knowledge_trace，winner 恒 None。"""
        differences: list[dict[str, Any]] = []
        risks: list[str] = []
        knowledge_trace: list[dict[str, Any]] = []
        for c in candidates:
            differences.append(
                {
                    "solution_id": c.solution_id,
                    "components": c.components,
                    "confidence": c.confidence,
                    "verification_status": c.verification_status,
                    "related_cases": list(c.related_cases),
                    "related_rules": list(c.related_rules),
                    "related_thresholds": list(c.related_thresholds),
                }
            )
            # 风险：仅 pending 标记，不输出终裁
            if c.components == PENDING_VERIFICATION:
                risks.append(f"{c.solution_id}: components 未定(pending_verification)")
            if c.verification_status == PENDING_VERIFICATION:
                risks.append(f"{c.solution_id}: 未转正(PENDING_VERIFICATION)")
            # 知识溯源：沿四关系只读遍历
            node = self._repo.get_node(c.solution_id)
            if node is not None:
                try:
                    steps = self._repo.traverse(c.solution_id, direction="out", max_depth=2)
                except KeyError:
                    steps = []
                for s in steps:
                    tgt = self._repo.get_node(s["node_id"])
                    if tgt is None:
                        continue
                    knowledge_trace.append(
                        {
                            "solution_id": c.solution_id,
                            "node_id": s["node_id"],
                            "entity_type": tgt.entity_type,
                            "relation_type": s.get("relation_type"),
                        }
                    )
        explanation = [
            "对比仅呈现各候选占位壳差异与待人工核验风险/知识溯源，",
            "不输出 winner（红线③），最终选择权归人工审核队列。",
        ]
        return SolutionComparisonReport(
            candidate_ids=[c.solution_id for c in candidates],
            difference=differences,
            risk=risks,
            knowledge_trace=knowledge_trace,
            winner=None,
            requires_human_review=True,
            explanation=explanation,
        )


# ---------------------------------------------------------------------------
# 任务4：方案可解释层（Explainability Layer，完整来源链）
# ---------------------------------------------------------------------------
class SolutionExplanation:
    """方案可解释层（Explainability Layer）。

    为候选方案生成可解释说明，引用 Case / Rule / Threshold / KnowledgeItem 的
    **完整来源链**（沿图谱四关系只读遍历），使方案依据可被人工核验。

    红线：只读遍历，不写、不选终、不报价。
    """

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造解释器（红线①/⑥）"
            )

    def explain(self, candidate: SolutionCandidateEntity) -> SolutionExplanationReport:
        """构建候选来源的完整解释链（Case / Rule / Threshold / KnowledgeItem）。"""
        chain: list[dict[str, Any]] = []
        node = self._repo.get_node(candidate.solution_id)
        if node is not None:
            try:
                steps = self._repo.traverse(candidate.solution_id, direction="out", max_depth=3)
            except KeyError:
                steps = []
            for s in steps:
                tgt = self._repo.get_node(s["node_id"])
                if tgt is None:
                    continue
                chain.append(
                    {
                        "level": s.get("level"),
                        "node_id": s["node_id"],
                        "entity_type": tgt.entity_type,
                        "relation_type": s.get("relation_type"),
                        "via_edge_id": s.get("via_edge_id"),
                        "label": tgt.label,
                    }
                )
        # 按来源类型归类，确保引用 Case/Rule/Threshold/KnowledgeItem 四类
        referenced: dict[str, list[str]] = {
            "Case": [],
            "Rule": [],
            "Threshold": [],
            "KnowledgeItem": [],
        }
        for entry in chain:
            et = entry["entity_type"]
            if et in referenced:
                referenced[et].append(entry["node_id"])
        explanation = [
            f"候选 {candidate.solution_id} 来源链长度={len(chain)}。",
            f"引用 Case={referenced['Case']}",
            f"引用 Rule={referenced['Rule']}",
            f"引用 Threshold={referenced['Threshold']}",
            f"引用 KnowledgeItem={referenced['KnowledgeItem']}",
            "完整来源链供人工核验方案依据（AI 不参与权威性判定）。",
        ]
        return SolutionExplanationReport(
            candidate_id=candidate.solution_id,
            source_chain=chain,
            referenced_types=referenced,
            explanation=explanation,
            requires_human_review=True,
        )


__all__ = [
    "SolutionRedLineViolationError",
    "SolutionConstraintEngine",
    "SolutionConstraintReport",
    "SolutionComparison",
    "SolutionComparisonReport",
    "SolutionExplanation",
    "SolutionExplanationReport",
]

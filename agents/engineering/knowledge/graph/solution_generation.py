"""Engineering Solution Generation Layer（Phase 3.7.4）。

在 Knowledge Graph Foundation（3.7.1）/ Reasoning Layer（3.7.2）/ Case Layer（3.7.3）
之上，建立「工程方案生成层」：根据 ``DesignCandidate`` + 既有 ``Case`` / ``Rule`` /
``Threshold`` / ``KnowledgeItem`` 图谱，**产出多个候选方案（SolutionCandidate）**，
并提供候选评价（兼容性 / 风险 / 知识溯源）与人工审核队列（SolutionReviewQueue）。

====================
最高红线（fail-closed）
====================
① 禁止开启 ``engineering_enabled``（构造/生成/评价/审核全部断言
   ``UnifiedActivationGate.safety_invariants_ok()``，非 False 即抛错）；
② 禁止输出 ``engineering_approved``：``SolutionReviewQueue.approve`` 仅 ``by_human=True``
   可进入 ``approved_by_human``，AI 调用一律抛 ``SolutionRedLineViolationError``；
③ 禁止 AI 自动选择最终工程方案：生成器/评价器**无** ``select`` / ``finalize`` 方法
   （通过 ``_RedLineForbiddenMixin`` 拦截 forbidden 方法名），仅产出多候选；
④ 禁止伪造工程参数：``SolutionCandidate.components`` / ``confidence`` 恒
   ``PENDING_VERIFICATION`` / ``"pending"``，不填任何真实方案数值；
⑤ 禁止绕过 ``UnifiedActivationGate``：所有写/决策路径先断言 ``safety_invariants_ok()``。

本层**仅**承载候选占位壳与图谱关联；真实方案数值转正须经专家双签 + 主理人核准
（G6）写入 verified.json，属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.entities import (
    CaseEntity,
    DesignCandidate,
    KnowledgeGraphEntityType,
    PENDING_PLACEHOLDER,
    PENDING_VERIFICATION,
    SolutionCandidateEntity,
)
from agents.engineering.knowledge.graph.relationships import GraphEdge
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository


# ---------------------------------------------------------------------------
# 异常与守卫
# ---------------------------------------------------------------------------
class SolutionRedLineViolationError(Exception):
    """方案生成层红线违例（类比 Reasoning Layer 的 RedLineViolationError）。"""


class SolutionReviewError(ValueError):
    """审核队列状态机转移非法（非红线，属正常业务校验失败）。"""


# 生成器/评价器上被禁止的方法名（红线②/③/①：不得批准/选终/激活）。
_FORBIDDEN_GENERATOR_METHODS = (
    "approve",
    "select",
    "finalize",
    "activate",
    "engineering_approved",
)


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳（审计用）。"""
    return datetime.now(timezone.utc).isoformat()


class _RedLineForbiddenMixin:
    """拦截生成器/评价器上的 forbidden 方法名（红线②/③/①）。

    仅当属性名确实缺失时才进入 ``__getattr__``；已定义的方法/字段不会受影响。
    旨在让「批准/选终/激活」在结构上不可达，而非靠约定。
    """

    _FORBIDDEN = _FORBIDDEN_GENERATOR_METHODS

    def __getattr__(self, name: str) -> Any:
        if name in self._FORBIDDEN:
            raise SolutionRedLineViolationError(
                f"拦截调用 {name!r}：生成阶段禁止批准/选终/激活工程方案"
                f"（红线②/③/①）。最终决策须经 SolutionReviewQueue.by_human 驱动。"
            )
        raise AttributeError(f"{type(self).__name__!r} 对象无属性 {name!r}")


# ---------------------------------------------------------------------------
# 报告载体（纯数据，含解释链；不含任何决策位）
# ---------------------------------------------------------------------------
@dataclass
class SolutionCompatibilityReport:
    """候选方案兼容性检查报告（仅分析，不下结论）。"""

    candidate_id: str
    compatible: bool
    missing_references: list[tuple[str, str]] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


@dataclass
class SolutionRiskReport:
    """候选方案风险检查报告（仅标记 pending_review，不做终裁）。"""

    candidate_id: str
    risk_level: str = "pending_review"
    risks: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


@dataclass
class SolutionTraceReport:
    """候选方案知识溯源报告（解释链：候选→Case→Rule/Threshold→KnowledgeItem）。"""

    candidate_id: str
    chain: list[dict[str, Any]] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


@dataclass
class SolutionSubmission:
    """审核队列中的一条提交记录（状态机载体，Phase 3.7.5 扩展三阶段审查位）。"""

    submission_id: str
    solution_id: str
    state: str
    candidate: SolutionCandidateEntity
    created_at: str = ""
    decided_at: str = ""
    decided_by: str = ""
    review_stage: str = "constraint"
    constraint_review_done: bool = False
    expert_review_done: bool = False


# ---------------------------------------------------------------------------
# 任务2 + 任务3：方案生成器（产出多候选，建立图谱关联）
# ---------------------------------------------------------------------------
class SolutionGenerator(_RedLineForbiddenMixin):
    """工程方案生成器。

    输入：``DesignCandidate`` + ``KnowledgeGraphRepository`` + 可选 ``Case`` 列表。
    输出：``list[SolutionCandidateEntity]``（多个候选，**不自动选终**）。

    红线：
    - ⑤ 生成前断言 ``safety_invariants_ok()``；
    - ③ 仅产出候选，无 ``select`` / ``finalize``（由 mixin 拦截）；
    - ④ 候选 ``components`` / ``confidence`` 恒 PENDING/pending，不伪造；
    - 任务3：``persist=True`` 时将候选节点 + ``solution_case`` / ``solution_rule`` /
      ``solution_threshold`` / ``solution_knowledge_item`` 四关系写入图谱（纯结构关联，
      不填真实值），使方案可溯源至 Case/Rule/Threshold/KnowledgeItem。
    """

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造方案生成器（红线①/⑤）"
            )

    # -- 内部：从 case 经 case_item 收集关联 KnowledgeItem 节点 id（只读）--
    def _collect_knowledge_items(self, case_id: str) -> list[str]:
        try:
            steps = self._repo.traverse(
                case_id, relation_types=["case_item"], direction="out", max_depth=1
            )
        except KeyError:
            return []
        ids: list[str] = []
        for s in steps:
            node = self._repo.get_node(s["node_id"])
            if node is not None and node.entity_type == KnowledgeGraphEntityType.KNOWLEDGE_ITEM.value:
                ids.append(node.node_id)
        return ids

    # -- 内部：将一个候选落图并挂四关系（红线：仅结构关联，不填真实值）--
    def _persist_candidate(self, cand: SolutionCandidateEntity, ki_ids: list[str]) -> None:
        self._repo.add_node(cand.to_node(), actor="solution_generator")
        edge_seq = 0
        for target in cand.related_cases:
            if self._repo.get_node(target) is not None:
                edge_seq += 1
                self._repo.add_edge(
                    GraphEdge(
                        f"se-{cand.solution_id}-{edge_seq}",
                        "solution_case",
                        cand.solution_id,
                        target,
                        {},
                    ),
                    actor="solution_generator",
                )
        for target in cand.related_rules:
            if self._repo.get_node(target) is not None:
                edge_seq += 1
                self._repo.add_edge(
                    GraphEdge(
                        f"se-{cand.solution_id}-{edge_seq}",
                        "solution_rule",
                        cand.solution_id,
                        target,
                        {},
                    ),
                    actor="solution_generator",
                )
        for target in cand.related_thresholds:
            if self._repo.get_node(target) is not None:
                edge_seq += 1
                self._repo.add_edge(
                    GraphEdge(
                        f"se-{cand.solution_id}-{edge_seq}",
                        "solution_threshold",
                        cand.solution_id,
                        target,
                        {},
                    ),
                    actor="solution_generator",
                )
        for target in ki_ids:
            if self._repo.get_node(target) is not None:
                edge_seq += 1
                self._repo.add_edge(
                    GraphEdge(
                        f"se-{cand.solution_id}-{edge_seq}",
                        "solution_knowledge_item",
                        cand.solution_id,
                        target,
                        {},
                    ),
                    actor="solution_generator",
                )

    def generate(
        self,
        design: DesignCandidate,
        *,
        cases: Optional[list[CaseEntity]] = None,
        persist: bool = True,
    ) -> list[SolutionCandidateEntity]:
        """根据设计候选 + 图谱产出多个方案候选（禁止选终）。

        参数：
        - ``design``：``DesignCandidate``（构造时已断言未启用工程判定）；
        - ``cases``：可选人工导入的 ``Case`` 列表；缺省则从图谱查询全部 Case 节点；
        - ``persist``：是否将候选节点 + 四关系写入图谱（默认 True，建立任务3关联）。

        返回：候选实体列表（每个 Case 派生一个候选骨架）。无 Case 时返回空列表
        （不伪造候选，保持诚实）。
        """
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成方案（红线①/⑤）"
            )
        if cases is None:
            case_nodes = self._repo.query(entity_type=KnowledgeGraphEntityType.CASE.value)
            cases = [CaseEntity.from_node(n) for n in case_nodes]

        candidates: list[SolutionCandidateEntity] = []
        for idx, case in enumerate(cases):
            ki_ids = self._collect_knowledge_items(case.case_id)
            context = design.metadata.get("context", PENDING_PLACEHOLDER) \
                if isinstance(design.metadata, dict) else PENDING_PLACEHOLDER
            cand = SolutionCandidateEntity(
                solution_id=f"{design.design_id}__SOL-{idx + 1}",
                input_context=context,
                related_cases=[case.case_id],
                related_rules=list(case.linked_rules),
                related_thresholds=list(case.linked_thresholds),
                components=PENDING_VERIFICATION,
                confidence="pending",
                verification_status=PENDING_VERIFICATION,
                status="pending_build",
            )
            candidates.append(cand)
            if persist:
                self._persist_candidate(cand, ki_ids)
        return candidates


# ---------------------------------------------------------------------------
# 任务4：候选方案评价器（兼容性 / 风险 / 知识溯源，仅分析不下结论）
# ---------------------------------------------------------------------------
class SolutionEvaluator(_RedLineForbiddenMixin):
    """候选方案评价器（兼容性检查 / 风险检查 / 知识溯源）。

    红线：
    - ⑤ 构造断言 ``safety_invariants_ok()``；
    - ③ 仅产出分析报告（含解释链），**无** ``select`` / ``finalize``（mixin 拦截）；
    - ``requires_human_review`` 恒 True：所有评价结果必须经人工复核，AI 不做终裁。
    """

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造方案评价器（红线①/⑤）"
            )

    @property
    def requires_human_review(self) -> bool:
        return True

    def compatibility_check(self, candidate: SolutionCandidateEntity) -> SolutionCompatibilityReport:
        """检查候选引用的 Case/Rule/Threshold 是否都在图谱中存在（只读）。"""
        missing: list[tuple[str, str]] = []
        for cid in candidate.related_cases:
            if self._repo.get_node(cid) is None:
                missing.append(("case", cid))
        for rid in candidate.related_rules:
            if self._repo.get_node(rid) is None:
                missing.append(("rule", rid))
        for tid in candidate.related_thresholds:
            if self._repo.get_node(tid) is None:
                missing.append(("threshold", tid))
        compatible = len(missing) == 0
        explanation = [
            f"候选 {candidate.solution_id} 关联 Case={candidate.related_cases}",
            f"关联 Rule={candidate.related_rules}",
            f"关联 Threshold={candidate.related_thresholds}",
            f"缺失引用数={len(missing)}；兼容性={compatible}",
            "兼容性仅反映图谱引用完整性，不构成工程批准（须经人工审核队列）。",
        ]
        return SolutionCompatibilityReport(
            candidate_id=candidate.solution_id,
            compatible=compatible,
            missing_references=missing,
            explanation=explanation,
            requires_human_review=True,
        )

    def risk_check(self, candidate: SolutionCandidateEntity) -> SolutionRiskReport:
        """标记方案风险（恒 pending_review，不输出终裁）。"""
        risks: list[str] = []
        if candidate.components == PENDING_VERIFICATION:
            risks.append(
                "components 未定（pending_verification）：方案实质未定，禁止据此施工或出图"
            )
        if candidate.confidence == "pending":
            risks.append("confidence 未定：禁止据此做工程决策或选型")
        if candidate.verification_status == PENDING_VERIFICATION:
            risks.append("verification_status=PENDING_VERIFICATION：未经双签转正，不得作为权威依据")
        explanation = [
            f"候选 {candidate.solution_id} 风险扫描完成，risk_level=pending_review。",
            "风险标记仅提示待人工核验，不构成 AI 终裁（红线③）。",
        ]
        return SolutionRiskReport(
            candidate_id=candidate.solution_id,
            risk_level="pending_review",
            risks=risks,
            explanation=explanation,
            requires_human_review=True,
        )

    def knowledge_trace(self, candidate: SolutionCandidateEntity) -> SolutionTraceReport:
        """从候选节点出发，沿四关系 BFS 构建知识溯源解释链（只读）。"""
        chain: list[dict[str, Any]] = []
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
                chain.append(
                    {
                        "level": s.get("level"),
                        "node_id": s["node_id"],
                        "entity_type": tgt.entity_type,
                        "relation_type": s.get("relation_type"),
                        "via_edge_id": s.get("via_edge_id"),
                    }
                )
        explanation = [
            f"候选 {candidate.solution_id} 溯源链长度={len(chain)}。",
            "解释链展示候选→Case/Rule/Threshold/KnowledgeItem 的关联路径，",
            "供人工核验方案依据来源（AI 不参与依据权威性判定）。",
        ]
        return SolutionTraceReport(
            candidate_id=candidate.solution_id,
            chain=chain,
            explanation=explanation,
            requires_human_review=True,
        )


# ---------------------------------------------------------------------------
# 任务5：人工审核队列（仅人工驱动，AI 不能进入 approved）
# ---------------------------------------------------------------------------
class SolutionReviewQueue:
    """方案候选审核队列（状态机：candidate → reviewing → approved_by_human / rejected）。

    红线：
    - ② ``approve`` 仅 ``by_human=True`` 可进入 ``approved_by_human``；AI 调用抛
      ``SolutionRedLineViolationError``（禁止输出 engineering_approved）；
    - ③ ``reject`` 同样要求 ``by_human=True``（AI 不做任何终裁）；
    - ⑤ 构造/决策路径断言 ``safety_invariants_ok()``；
    - 非法状态转移抛 ``SolutionReviewError``（正常业务校验，非红线）。
    """

    STATES = ("candidate", "reviewing", "approved_by_human", "rejected")
    _REVIEWABLE = "reviewing"

    def __init__(self) -> None:
        self._items: dict[str, SolutionSubmission] = {}
        self._seq: int = 0
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造审核队列（红线①/⑤）"
            )

    def _get(self, submission_id: str) -> SolutionSubmission:
        sub = self._items.get(submission_id)
        if sub is None:
            raise SolutionReviewError(f"提交 {submission_id!r} 不存在")
        return sub

    def submit(self, candidate: SolutionCandidateEntity) -> str:
        """将候选提交入队（状态 candidate）。"""
        self._seq += 1
        sid = f"SUB-{candidate.solution_id}-{self._seq}"
        self._items[sid] = SolutionSubmission(
            submission_id=sid,
            solution_id=candidate.solution_id,
            state="candidate",
            candidate=candidate,
            created_at=_utc_now(),
            review_stage="constraint",
        )
        return sid

    def begin_review(self, submission_id: str) -> SolutionSubmission:
        """candidate → reviewing。"""
        sub = self._get(submission_id)
        if sub.state != "candidate":
            raise SolutionReviewError(
                f"begin_review 失败：当前态 {sub.state!r} 应为 candidate"
            )
        sub.state = "reviewing"
        return sub

    def approve(self, submission_id: str, *, by_human: bool = False) -> SolutionSubmission:
        """reviewing → approved_by_human（**仅人工**）。"""
        sub = self._get(submission_id)
        if sub.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"approve 失败：当前态 {sub.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得批准方案：approve 必须 by_human=True（红线②）。"
                "最终批准须经真实主理人/专家线下决策。"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下批准方案（红线①/⑤）"
            )
        sub.state = "approved_by_human"
        sub.decided_at = _utc_now()
        sub.decided_by = "human_reviewer"
        return sub

    def reject(self, submission_id: str, *, by_human: bool = False) -> SolutionSubmission:
        """reviewing → rejected（**仅人工**）。"""
        sub = self._get(submission_id)
        if sub.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"reject 失败：当前态 {sub.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得做出终裁：reject 必须 by_human=True（红线③）。"
                "任何终裁须由真实主理人/专家驱动。"
            )
        sub.state = "rejected"
        sub.decided_at = _utc_now()
        sub.decided_by = "human_reviewer"
        return sub

    # -- 任务5：三阶段人工审查扩展（constraint_review / expert_review / human_decision）--
    def record_constraint_review(self, submission_id: str, *, by_human: bool = False) -> SolutionSubmission:
        """标记约束审查完成（**仅人工**）。审查后进入 expert 阶段。"""
        sub = self._get(submission_id)
        if sub.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"record_constraint_review 失败：当前态 {sub.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得执行约束审查：record_constraint_review 必须 by_human=True（红线②/③）。"
                "约束审查须经真实主理人/专家线下完成。"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录约束审查（红线①/⑥）"
            )
        sub.constraint_review_done = True
        sub.review_stage = "expert"
        return sub

    def record_expert_review(self, submission_id: str, *, by_human: bool = False) -> SolutionSubmission:
        """标记专家审查完成（**仅人工**）。须先完成约束审查；审查后进入 human_decision 阶段。"""
        sub = self._get(submission_id)
        if sub.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"record_expert_review 失败：当前态 {sub.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得执行专家审查：record_expert_review 必须 by_human=True（红线②/③）。"
                "专家审查须经真实专家线下完成。"
            )
        if not sub.constraint_review_done:
            raise SolutionReviewError(
                "record_expert_review 失败：须先完成约束审查（constraint_review_done）"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录专家审查（红线①/⑥）"
            )
        sub.expert_review_done = True
        sub.review_stage = "human_decision"
        return sub

    def human_decision(self, submission_id: str, *, by_human: bool = False, approve: bool = False) -> SolutionSubmission:
        """人工终裁（**仅人工**；须 constraint_review + expert_review 均完成）。

        红线②/③：AI 不得做出终裁（by_human 默认 False 抛 ``SolutionRedLineViolationError``）；
        终裁结果进入 ``approved_by_human``（approve=True）或 ``rejected``（approve=False）。
        """
        sub = self._get(submission_id)
        if sub.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"human_decision 失败：当前态 {sub.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得做出终裁：human_decision 必须 by_human=True（红线②/③）。"
                "任何终裁须由真实主理人/专家驱动。"
            )
        if not (sub.constraint_review_done and sub.expert_review_done):
            raise SolutionReviewError(
                "human_decision 失败：须先完成 constraint_review 与 expert_review"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下做出终裁（红线①/⑥）"
            )
        sub.state = "approved_by_human" if approve else "rejected"
        sub.decided_at = _utc_now()
        sub.decided_by = "human_reviewer"
        return sub

    def get(self, submission_id: str) -> SolutionSubmission:
        return self._get(submission_id)

    def list_submissions(self) -> list[SolutionSubmission]:
        return list(self._items.values())


__all__ = [
    "SolutionRedLineViolationError",
    "SolutionReviewError",
    "SolutionCompatibilityReport",
    "SolutionRiskReport",
    "SolutionTraceReport",
    "SolutionSubmission",
    "SolutionGenerator",
    "SolutionEvaluator",
    "SolutionReviewQueue",
]

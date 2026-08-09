"""Knowledge Graph Query & Reasoning Layer（Phase 3.7.2 Task 1–5）。

在 Phase 3.7.1 Knowledge Graph Foundation 之上新增**只读推理层**
``KnowledgeGraphQueryEngine``，能力：
- ``node_query()``           ：包装 ``graph.query``；
- ``edge_query()``           ：按 relation_type/source/target 过滤边（只读）；
- ``path_query()``           ：start→end 双向 BFS 寻路（按关系/最大跳数）；
- ``impact_analysis()``      ：threshold impact（某 Threshold 变化影响哪些 Agent/Case/Rule）；
- ``trace_knowledge_path()`` ：KnowledgeItem→Threshold→Rule→CalcAgent 候选链追踪；
- ``reason_associations()``  ：relationship traversal（parent_child/references/cites/basis）；
- ``conflict_scan()``        ：复用 ``KnowledgeGraphConflictDetector``，review_required 恒 True。

设计铁律（本层全部为**只读**）：
- 本层**绝不**调用 graph.add_node / add_edge / delete；
- 构造与每次调用前断言 ``safety_invariants_ok()``（engineering_enabled 必须 False，红线①）；
- 本类**不提供** approve / merge / delete / engineering_approved 任何方法或属性（红线②④）；
- 所有"候选分析"只报告、不审批、不处置（红线②⑤）；
- CalcAgent 恒为 pending 候选，绝不编造真实计算主体（红线⑤）；
- 冲突候选 review_required 恒 True，禁止自动 merge/delete（红线④）。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from agents.engineering.knowledge.graph.conflict import (
    CONFLICT_DANGLING_EDGE,
    CONFLICT_DUPLICATE_NODE,
    CONFLICT_PENDING_BUILD_EDGE,
    CONFLICT_TYPE_MISMATCH,
    GraphConflictReport,
    KnowledgeGraphConflictDetector,
)
from agents.engineering.knowledge.graph.entities import GraphNode
from agents.engineering.knowledge.graph.relationships import GraphEdge
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository

# 知识关联推理默认支持的关系（任务4）。
DEFAULT_ASSOCIATION_RELATIONS: tuple[str, ...] = (
    "parent_child",
    "references",
    "cites",
    "basis",
)

# 本推理层明确禁止对外暴露的方法/属性名（红线②④）。
_FORBIDDEN_METHOD_NAMES: tuple[str, ...] = (
    "approve",
    "merge",
    "delete",
    "engineering_approved",
)


class RedLineViolationError(ValueError):
    """推理层红线违例（fail-closed 抛错）。"""


# ---------------------------------------------------------------------------
# 输出载体（全部只读、候选化、禁止审批）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CalcAgentCandidate:
    """受某 Rule 影响的 CalcAgent **pending 候选**。

    红线⑤：绝不编造真实计算主体；``computation_body`` 恒 ``pending_verification``，
    真实 CalcAgent 须经专家双签 + G6 授权后在激活阶段补全。
    """

    candidate_id: str
    source_rule_id: str
    is_candidate: bool = True
    pending: bool = True
    computation_body: str = "pending_verification"
    note: str = "CalcAgent 为 pending 候选，真实计算主体须人工在激活阶段补全"

    @classmethod
    def from_rule(cls, rule_id: str) -> "CalcAgentCandidate":
        return cls(
            candidate_id=f"CalcAgent(candidate:{rule_id})",
            source_rule_id=rule_id,
        )


@dataclass
class KnowledgePathTrace:
    """KnowledgeItem→Threshold→Rule→CalcAgent 候选链追踪结果（候选分析）。

    ``requires_human_review`` / ``approval_forbidden`` 恒 True（红线②）；
    CalcAgent 仅以 pending 候选形式出现（红线⑤）。
    """

    knowledge_item_id: str
    thresholds: list[str]
    rules: list[str]
    calc_agent_candidates: list[CalcAgentCandidate]
    requires_human_review: bool = True
    approval_forbidden: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_item_id": self.knowledge_item_id,
            "thresholds": list(self.thresholds),
            "rules": list(self.rules),
            "calc_agent_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "source_rule_id": c.source_rule_id,
                    "is_candidate": c.is_candidate,
                    "pending": c.pending,
                    "computation_body": c.computation_body,
                    "note": c.note,
                }
                for c in self.calc_agent_candidates
            ],
            "requires_human_review": self.requires_human_review,
            "approval_forbidden": self.approval_forbidden,
        }


@dataclass
class ThresholdImpactReport:
    """Threshold 影响分析报告（仅报告，不处置，红线③）。

    某 Threshold 变化可能波及：KnowledgeItem / Rule / Case / 受 Rule 派生的
    CalcAgent 候选。``requires_human_review`` 恒 True；本报告绝不自动改写任何值。
    """

    threshold_id: str
    affected_knowledge_items: list[str]
    affected_rules: list[str]
    affected_cases: list[str]
    affected_agent_candidates: list[CalcAgentCandidate]
    requires_human_review: bool = True
    approval_forbidden: bool = True
    note: str = "影响分析报告（只读）；不自动处置、不编造新值；须人工在激活阶段复核"

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_id": self.threshold_id,
            "affected_knowledge_items": list(self.affected_knowledge_items),
            "affected_rules": list(self.affected_rules),
            "affected_cases": list(self.affected_cases),
            "affected_agent_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "source_rule_id": c.source_rule_id,
                    "pending": c.pending,
                }
                for c in self.affected_agent_candidates
            ],
            "requires_human_review": self.requires_human_review,
            "approval_forbidden": self.approval_forbidden,
            "note": self.note,
        }


@dataclass
class ReasoningConflictCandidate:
    """推理层冲突候选（包装图谱冲突报告，红线④）。

    ``review_required`` 恒 True；``auto_resolvable`` 恒 False；
    本类无任何 merge / delete / approve 方法。
    """

    conflict_id: str
    scope: str
    conflict_type: str
    entity_a: str
    entity_b: str
    detail: str
    review_required: bool = True
    auto_resolvable: bool = False
    recommended_action: str = "manual_review"

    @classmethod
    def from_report(cls, r: GraphConflictReport) -> "ReasoningConflictCandidate":
        return cls(
            conflict_id=r.conflict_id,
            scope=r.scope,
            conflict_type=r.conflict_type,
            entity_a=r.entity_a,
            entity_b=r.entity_b,
            detail=r.detail,
            review_required=r.review_required,
            auto_resolvable=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "scope": self.scope,
            "conflict_type": self.conflict_type,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "detail": self.detail,
            "review_required": self.review_required,
            "auto_resolvable": self.auto_resolvable,
            "recommended_action": self.recommended_action,
        }


@dataclass
class CaseSimilarityReport:
    """案例相似度候选分析（仅候选，红线③⑤）。

    基于关联字段（``linked_thresholds``/``linked_rules``/``linked_experts``/
    ``project_ref``/``environment``）计算与其它案例的重叠候选；
    不编造真实案例内容，不作任何判定，仅输出候选供人工复核。
    """

    source_case_id: str
    candidate_cases: list[dict[str, Any]]
    requires_human_review: bool = True
    approval_forbidden: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_case_id": self.source_case_id,
            "candidate_cases": list(self.candidate_cases),
            "requires_human_review": self.requires_human_review,
            "approval_forbidden": self.approval_forbidden,
        }


@dataclass
class CasePathReport:
    """案例→KnowledgeItem→Threshold→Rule→Expert 链路候选追踪（仅候选，红线②⑤）。

    沿新案例链路关系（case_item / basis / threshold_rule / rule_expert）追踪；
    CalcAgent/Expert 仅以候选/资料壳形式出现，绝不审批、不编造。
    """

    case_id: str
    knowledge_items: list[str]
    thresholds: list[str]
    rules: list[str]
    experts: list[str]
    requires_human_review: bool = True
    approval_forbidden: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "knowledge_items": list(self.knowledge_items),
            "thresholds": list(self.thresholds),
            "rules": list(self.rules),
            "experts": list(self.experts),
            "requires_human_review": self.requires_human_review,
            "approval_forbidden": self.approval_forbidden,
        }


@dataclass
class CaseImpactReport:
    """案例影响分析报告（仅报告，不处置，红线③⑤）。

    某 Case 经由 ``linked_thresholds``/``linked_rules``/``linked_experts`` 关联，
    可能波及的 Threshold / Rule / KnowledgeItem / 受 Rule 派生的 CalcAgent 候选。
    ``requires_human_review`` 恒 True；本报告绝不自动改写任何值。
    """

    case_id: str
    affected_thresholds: list[str]
    affected_rules: list[str]
    affected_knowledge_items: list[str]
    affected_agent_candidates: list[CalcAgentCandidate]
    requires_human_review: bool = True
    approval_forbidden: bool = True
    note: str = "案例影响分析报告（只读）；不自动处置、不编造新值；须人工在激活阶段复核"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "affected_thresholds": list(self.affected_thresholds),
            "affected_rules": list(self.affected_rules),
            "affected_knowledge_items": list(self.affected_knowledge_items),
            "affected_agent_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "source_rule_id": c.source_rule_id,
                    "pending": c.pending,
                }
                for c in self.affected_agent_candidates
            ],
            "requires_human_review": self.requires_human_review,
            "approval_forbidden": self.approval_forbidden,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# 推理引擎（只读）
# ---------------------------------------------------------------------------
class KnowledgeGraphQueryEngine:
    """Knowledge Graph Query & Reasoning Layer（只读）。

    - 构造即断言 ``graph.safety_invariants_ok()``（红线①：engineering_enabled=False）；
    - 所有方法仅调用 graph 的 query / traverse / get_node / get_edge / history
      以及只读访问 ``_edges`` / ``_nodes``，绝不写盘或改状态（红线③）；
    - 不暴露 approve / merge / delete / engineering_approved（红线②④）。
    """

    def __init__(self, graph: KnowledgeGraphRepository) -> None:
        if graph is None:
            raise ValueError("KnowledgeGraphQueryEngine 需要 KnowledgeGraphRepository 实例")
        self._graph = graph
        # 红线①：构造即断言工程闸门关闭。
        self.assert_red_lines()

    # ------------------------------------------------------------------ #
    # 红线屏障
    # ------------------------------------------------------------------ #
    def assert_red_lines(self) -> None:
        """只读断言：engineering_enabled 必须保持 False（红线①）。

        违例即抛 ``RedLineViolationError``（fail-closed）。
        """
        if self._graph.safety_invariants_ok() is False:
            raise RedLineViolationError(
                "红线①违例：engineering_enabled 不得开启；推理层仅可在闸门关闭时运行"
            )
        # 红线②④：本引擎不得暴露审批/合并/删除入口。
        for forbidden in _FORBIDDEN_METHOD_NAMES:
            if hasattr(self, forbidden):
                raise RedLineViolationError(
                    f"红线②④违例：推理引擎不得暴露 {forbidden!r}（禁止自动审批/合并/删除）"
                )

    # ------------------------------------------------------------------ #
    # 任务1：Graph Query Engine
    # ------------------------------------------------------------------ #
    def node_query(
        self,
        *,
        entity_type: Optional[str] = None,
        attribute_contains: Optional[tuple[str, str]] = None,
        node_id_prefix: Optional[str] = None,
        pending_build_only: Optional[bool] = None,
    ) -> list[GraphNode]:
        """包装 ``graph.query``（只读）。"""
        self.assert_red_lines()
        return self._graph.query(
            entity_type=entity_type,
            attribute_contains=attribute_contains,
            node_id_prefix=node_id_prefix,
            pending_build_only=pending_build_only,
        )

    def edge_query(
        self,
        *,
        relation_type: Optional[str] = None,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> list[GraphEdge]:
        """按 relation_type / source / target 过滤边（只读，不触碰持久化）。"""
        self.assert_red_lines()
        edges: list[GraphEdge] = list(self._graph._edges.values())
        if relation_type is not None:
            edges = [e for e in edges if e.relation_type == relation_type]
        if source_id is not None:
            edges = [e for e in edges if e.source_id == source_id]
        if target_id is not None:
            edges = [e for e in edges if e.target_id == target_id]
        return edges

    def path_query(
        self,
        start_node_id: str,
        end_node_id: str,
        *,
        relation_types: Optional[Sequence[str]] = None,
        max_depth: int = 6,
    ) -> list[dict[str, Any]]:
        """start→end 双向 BFS 寻路（按关系白名单与最大跳数）。

        返回节点序列（含每段 relation_type / via_edge_id / direction），
        不可达时返回空列表。只读。
        """
        self.assert_red_lines()
        if start_node_id not in self._graph._nodes:
            raise KeyError(f"start_node_id={start_node_id!r} 未入图")
        if end_node_id not in self._graph._nodes:
            raise KeyError(f"end_node_id={end_node_id!r} 未入图")
        allowed = set(relation_types) if relation_types else None
        return self._bidirectional_bfs(start_node_id, end_node_id, allowed, max_depth)

    def impact_analysis(self, threshold_id: str) -> ThresholdImpactReport:
        """Threshold 影响分析（任务3，仅报告，红线③⑤）。

        收集：受该 Threshold 关联的 KnowledgeItem、应用其上的 Rule、
        引用该 Threshold 的 Case、以及由 Rule 派生的 CalcAgent pending 候选。
        不自动处置任何值；requires_human_review 恒 True。
        """
        self.assert_red_lines()
        node = self._graph.get_node(threshold_id)
        if node is None or node.entity_type != "Threshold":
            raise KeyError(f"threshold_id={threshold_id!r} 不是已入图的 Threshold 节点")
        # Threshold --used_by--> KnowledgeItem
        used_by_kis = {
            t["node_id"]
            for t in self._graph.traverse(threshold_id, relation_types=["used_by"], direction="out")
        }
        # KnowledgeItem --basis--> Threshold（反向抵达引用它的 KI）
        basis_kis = {
            t["node_id"]
            for t in self._graph.traverse(threshold_id, relation_types=["basis"], direction="in")
        }
        affected_kis = sorted(used_by_kis | basis_kis)
        # Rule --applies--> KnowledgeItem（in 方向从 KI 抵达 Rule）
        affected_rules: set[str] = set()
        for ki in affected_kis:
            for t in self._graph.traverse(ki, relation_types=["applies"], direction="in"):
                affected_rules.add(t["node_id"])
        # Case：via linked_thresholds 属性（兼容旧键 related_thresholds；pending_build 骨架，不编造）
        affected_cases: list[str] = []
        for c in self._graph.query(entity_type="Case"):
            related = c.attributes.get("linked_thresholds") or c.attributes.get("related_thresholds") or []
            if threshold_id in related:
                affected_cases.append(c.node_id)
        # CalcAgent：受 Rule 派生的 pending 候选（红线⑤，不编造计算主体）
        agent_candidates = [CalcAgentCandidate.from_rule(r) for r in sorted(affected_rules)]
        return ThresholdImpactReport(
            threshold_id=threshold_id,
            affected_knowledge_items=affected_kis,
            affected_rules=sorted(affected_rules),
            affected_cases=sorted(affected_cases),
            affected_agent_candidates=agent_candidates,
            requires_human_review=True,
            approval_forbidden=True,
        )

    # ------------------------------------------------------------------ #
    # 任务2：知识路径分析（KnowledgeItem→Threshold→Rule→CalcAgent 候选）
    # ------------------------------------------------------------------ #
    def trace_knowledge_path(self, knowledge_item_id: str) -> KnowledgePathTrace:
        """追踪 KnowledgeItem→Threshold→Rule→CalcAgent 候选链（红线②⑤）。

        输出 candidate analysis；CalcAgent 仅以 pending 候选形式出现，
        绝不审批（approval_forbidden 恒 True），绝不编造真实计算主体。
        """
        self.assert_red_lines()
        node = self._graph.get_node(knowledge_item_id)
        if node is None or node.entity_type != "KnowledgeItem":
            raise KeyError(
                f"knowledge_item_id={knowledge_item_id!r} 不是已入图的 KnowledgeItem 节点"
            )
        # KnowledgeItem --basis--> Threshold
        thresholds = [
            t["node_id"]
            for t in self._graph.traverse(knowledge_item_id, relation_types=["basis"], direction="out")
        ]
        # Rule --applies--> KnowledgeItem（in 方向）
        rules = [
            t["node_id"]
            for t in self._graph.traverse(knowledge_item_id, relation_types=["applies"], direction="in")
        ]
        calc_agent_candidates = [CalcAgentCandidate.from_rule(r) for r in rules]
        return KnowledgePathTrace(
            knowledge_item_id=knowledge_item_id,
            thresholds=thresholds,
            rules=rules,
            calc_agent_candidates=calc_agent_candidates,
            requires_human_review=True,
            approval_forbidden=True,
        )

    # ------------------------------------------------------------------ #
    # 任务4：知识关联推理（relationship traversal）
    # ------------------------------------------------------------------ #
    def reason_associations(
        self,
        node_id: str,
        *,
        relation_types: Sequence[str] = DEFAULT_ASSOCIATION_RELATIONS,
        max_depth: int = 4,
    ) -> list[dict[str, Any]]:
        """关系遍历推理（parent_child / references / cites / basis，双向）。

        返回 ``graph.traverse(..., direction="both")`` 的结果；只读。
        """
        self.assert_red_lines()
        if node_id not in self._graph._nodes:
            raise KeyError(f"node_id={node_id!r} 未入图")
        return self._graph.traverse(
            node_id,
            relation_types=list(relation_types),
            direction="both",
            max_depth=max_depth,
        )

    # ------------------------------------------------------------------ #
    # 任务5：冲突保持人工审核（复用检测器，review_required 恒 True）
    # ------------------------------------------------------------------ #
    def conflict_scan(self) -> list[ReasoningConflictCandidate]:
        """扫描图谱冲突；所有候选 review_required 恒 True，禁止自动处置（红线④）。

        复用 ``KnowledgeGraphConflictDetector``；本引擎不提供任何 merge/delete/approve。
        """
        self.assert_red_lines()
        reports = KnowledgeGraphConflictDetector().detect(self._graph)
        candidates = [ReasoningConflictCandidate.from_report(r) for r in reports]
        # 强制红线④：任何候选都不得自动可解 / 不得脱离人工复核。
        for c in candidates:
            assert c.review_required is True
            assert c.auto_resolvable is False
        return candidates

    # ------------------------------------------------------------------ #
    # 任务6（Phase 3.7.3）：案例知识层查询能力（仅候选分析，红线③⑤）
    # ------------------------------------------------------------------ #
    def similar_case(self, case_id: str, *, top_k: int = 5) -> CaseSimilarityReport:
        """案例相似度候选分析（仅候选，红线③⑤）。

        基于关联字段重叠计算与其它 Case 的候选相似度；仅输出候选，不判定、
        不审批、不编造。``requires_human_review`` / ``approval_forbidden`` 恒 True。
        """
        self.assert_red_lines()
        node = self._graph.get_node(case_id)
        if node is None or node.entity_type != "Case":
            raise KeyError(f"case_id={case_id!r} 不是已入图的 Case 节点")
        src = node.attributes
        src_keys = (
            set(src.get("linked_thresholds") or [])
            | set(src.get("linked_rules") or [])
            | set(src.get("linked_experts") or [])
        )
        src_proj = str(src.get("project_ref", ""))
        src_env = str(src.get("environment", ""))
        candidates: list[dict[str, Any]] = []
        for other in self._graph.query(entity_type="Case"):
            if other.node_id == case_id:
                continue
            o = other.attributes
            o_keys = (
                set(o.get("linked_thresholds") or [])
                | set(o.get("linked_rules") or [])
                | set(o.get("linked_experts") or [])
            )
            overlap = sorted(src_keys & o_keys)
            proj_match = bool(src_proj) and src_proj == str(o.get("project_ref", ""))
            env_match = bool(src_env) and src_env == str(o.get("environment", ""))
            score = len(overlap) + (1 if proj_match else 0) + (1 if env_match else 0)
            if score <= 0:
                continue
            candidates.append(
                {
                    "case_id": other.node_id,
                    "shared_linked_keys": overlap,
                    "project_ref_match": proj_match,
                    "environment_match": env_match,
                    "similarity_score": score,
                    "is_candidate": True,
                }
            )
        candidates.sort(key=lambda c: c["similarity_score"], reverse=True)
        return CaseSimilarityReport(
            source_case_id=case_id,
            candidate_cases=candidates[:top_k],
            requires_human_review=True,
            approval_forbidden=True,
        )

    def case_path(self, case_id: str) -> CasePathReport:
        """案例→KnowledgeItem→Threshold→Rule→Expert 候选链追踪（红线②⑤）。

        沿新案例链路关系（``case_item`` / ``basis`` / ``threshold_rule`` /
        ``rule_expert``）追踪；并兼容 Case 的 ``linked_*`` 属性（图谱尚未建边时）。
        输出 candidate analysis，绝不审批（approval_forbidden 恒 True）。
        """
        self.assert_red_lines()
        node = self._graph.get_node(case_id)
        if node is None or node.entity_type != "Case":
            raise KeyError(f"case_id={case_id!r} 不是已入图的 Case 节点")
        # Case --case_item--> KnowledgeItem
        kis = [
            t["node_id"]
            for t in self._graph.traverse(case_id, relation_types=["case_item"], direction="out")
        ]
        # KnowledgeItem --basis--> Threshold（out）
        thresholds: set[str] = set()
        for ki in kis:
            for t in self._graph.traverse(ki, relation_types=["basis"], direction="out"):
                thresholds.add(t["node_id"])
        # Threshold --threshold_rule--> Rule（out）
        rules: set[str] = set()
        for th in thresholds:
            for t in self._graph.traverse(th, relation_types=["threshold_rule"], direction="out"):
                rules.add(t["node_id"])
        # Rule --rule_expert--> Expert（out）
        experts: set[str] = set()
        for ru in rules:
            for t in self._graph.traverse(ru, relation_types=["rule_expert"], direction="out"):
                experts.add(t["node_id"])
        # 兼容：直接从 Case 的 linked_* 属性补充（图谱尚未建边时）
        a = node.attributes
        thresholds |= set(a.get("linked_thresholds") or [])
        rules |= set(a.get("linked_rules") or [])
        experts |= set(a.get("linked_experts") or [])
        return CasePathReport(
            case_id=case_id,
            knowledge_items=sorted(kis),
            thresholds=sorted(thresholds),
            rules=sorted(rules),
            experts=sorted(experts),
            requires_human_review=True,
            approval_forbidden=True,
        )

    def case_impact(self, case_id: str) -> CaseImpactReport:
        """案例影响分析（仅报告，红线③⑤）。

        收集：受该 Case 关联的 Threshold、应用其上的 Rule、由 Threshold 反向抵达的
        KnowledgeItem、以及由 Rule 派生的 CalcAgent pending 候选。
        不自动处置任何值；requires_human_review 恒 True。
        """
        self.assert_red_lines()
        node = self._graph.get_node(case_id)
        if node is None or node.entity_type != "Case":
            raise KeyError(f"case_id={case_id!r} 不是已入图的 Case 节点")
        a = node.attributes
        thresholds = set(a.get("linked_thresholds") or a.get("related_thresholds") or [])
        rules = set(a.get("linked_rules") or [])
        # Threshold --basis--> KnowledgeItem（in 方向从 Threshold 抵达 KI）
        kis: set[str] = set()
        for th in thresholds:
            for t in self._graph.traverse(th, relation_types=["basis"], direction="in"):
                kis.add(t["node_id"])
        # CalcAgent：受 Rule 派生的 pending 候选（红线⑤，不编造计算主体）
        agent_candidates = [CalcAgentCandidate.from_rule(r) for r in sorted(rules)]
        return CaseImpactReport(
            case_id=case_id,
            affected_thresholds=sorted(thresholds),
            affected_rules=sorted(rules),
            affected_knowledge_items=sorted(kis),
            affected_agent_candidates=agent_candidates,
            requires_human_review=True,
            approval_forbidden=True,
        )

    # ------------------------------------------------------------------ #
    # 任务7（Phase 3.7.3）：案例冲突保护（复用检测器 + Case 级重复检测，红线④）
    # ------------------------------------------------------------------ #
    def case_conflict_scan(self) -> list[ReasoningConflictCandidate]:
        """案例级冲突扫描（复用检测器 + Case 重复检测，红线④）。

        - 复用 ``conflict_scan()``（通用图谱冲突 + 红线④断言）；
        - 追加 Case 级重复检测：同 ``project_ref`` + ``environment`` 的不同 Case
          视为冲突候选（须人工区分/合并，AI 不自动合并）；
        所有候选 ``review_required`` 恒 True、``auto_resolvable`` 恒 False；
        本引擎无 merge / delete / approve。
        """
        self.assert_red_lines()
        candidates = self.conflict_scan()  # 复用基础冲突 + 红线④断言
        # Case 级重复检测（仅当 project_ref 与 environment 均非空才有意义）。
        seen: dict[tuple[str, str], str] = {}
        for case in self._graph.query(entity_type="Case"):
            a = case.attributes
            proj = str(a.get("project_ref", ""))
            env = str(a.get("environment", ""))
            if not proj and not env:
                continue
            key = (proj, env)
            if key in seen and seen[key] != case.node_id:
                r = GraphConflictReport(
                    conflict_id=f"GCFL-case-{abs(hash((proj, env, seen[key], case.node_id))) % 10**10:010d}",
                    scope="case",
                    conflict_type="case_duplicate_project_env",
                    entity_a=seen[key],
                    entity_b=case.node_id,
                    detail=(
                        f"同 project_ref={proj!r} 同 environment={env!r} 出现不同 Case"
                        f"（{seen[key]} 与 {case.node_id}），疑似重复/冲突案例，须人工复核"
                    ),
                    review_required=True,
                )
                candidates.append(ReasoningConflictCandidate.from_report(r))
            else:
                seen.setdefault(key, case.node_id)
        for c in candidates:
            assert c.review_required is True
            assert c.auto_resolvable is False
        return candidates

    # ------------------------------------------------------------------ #
    # 内部：邻接与双向 BFS
    # ------------------------------------------------------------------ #
    def _adjacent_edges(self, node: str, allowed: Optional[set[str]]) -> list[GraphEdge]:
        out: list[GraphEdge] = []
        for eid in self._graph._edge_index.get(node, []):
            edge = self._graph._edges.get(eid)
            if edge is None:
                continue
            if allowed is not None and edge.relation_type not in allowed:
                continue
            out.append(edge)
        return out

    def _bidirectional_bfs(
        self,
        start: str,
        end: str,
        allowed: Optional[set[str]],
        max_depth: int,
    ) -> list[dict[str, Any]]:
        """从 start 单向 BFS 到 end，记录父指针后重建路径。"""
        if start == end:
            return [{"node_id": start, "relation_type": None, "via_edge_id": None, "direction": None}]
        parent: dict[str, Optional[tuple[str, GraphEdge]]] = {start: None}
        depth_map: dict[str, int] = {start: 0}
        queue: deque[str] = deque([start])
        while queue:
            cur = queue.popleft()
            if cur == end:
                break
            if depth_map[cur] >= max_depth:
                continue
            for edge in self._adjacent_edges(cur, allowed):
                nxt = edge.target_id if edge.source_id == cur else edge.source_id
                if nxt in parent:
                    continue
                parent[nxt] = (cur, edge)
                depth_map[nxt] = depth_map[cur] + 1
                queue.append(nxt)
        if end not in parent:
            return []
        # 重建路径（end → start，再反转）。
        path: list[dict[str, Any]] = []
        cur = end
        while parent[cur] is not None:
            prev, edge = parent[cur]  # type: ignore[misc]
            path.append(
                {
                    "node_id": cur,
                    "relation_type": edge.relation_type,
                    "via_edge_id": edge.edge_id,
                    "direction": "out" if edge.source_id == prev else "in",
                }
            )
            cur = prev
        path.append({"node_id": start, "relation_type": None, "via_edge_id": None, "direction": None})
        path.reverse()
        return path


__all__ = [
    "KnowledgeGraphQueryEngine",
    "CalcAgentCandidate",
    "KnowledgePathTrace",
    "ThresholdImpactReport",
    "ReasoningConflictCandidate",
    "CaseSimilarityReport",
    "CasePathReport",
    "CaseImpactReport",
    "RedLineViolationError",
    "DEFAULT_ASSOCIATION_RELATIONS",
    "CONFLICT_DUPLICATE_NODE",
    "CONFLICT_DANGLING_EDGE",
    "CONFLICT_PENDING_BUILD_EDGE",
    "CONFLICT_TYPE_MISMATCH",
]

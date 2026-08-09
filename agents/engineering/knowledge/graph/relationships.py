"""Knowledge Graph 关系 Schema（Phase 3.7.1 Task 2 + Phase 3.7.3 案例链路 + Phase 3.7.4 方案关联）。

定义 BOIP Knowledge Graph Foundation 的 17 类关系 Schema，每类含：
- ``relation_type``：关系名（值即落库字符串）；
- ``from_entity`` / ``to_entity``：合法起止实体类型约束（fail-closed 校验源）；
- ``description``：语义说明；
- ``required_attrs``：关系须携带的属性键；
- ``invariant``：不变量（红线，禁止自动 merge/delete/approve）。

17 关系：
1. references     KnowledgeItem → KnowledgeItem   知识条目相互引用
2. authored_by    KnowledgeItem → Expert          知识条目由其作者（专家）署名
3. parent_child   KnowledgeItem → KnowledgeItem   知识谱系父子（禁环）
4. sourced_from   KnowledgeItem → SourceRef       知识条目引用规范来源（结构化）
5. used_by        Threshold     → KnowledgeItem   阈值被知识条目/案例使用
6. applies        Rule         → KnowledgeItem   规则适用于某知识条目
7. cites          KnowledgeItem → SourceRef       知识条目引述（轻量引用）
8. basis          KnowledgeItem → Threshold       知识条目以阈值为依据（threshold_candidate 关联）
9. witnessed_by   KnowledgeItem → Expert          知识条目经专家见证（区别于署名）
10. signs         Expert       → KnowledgeItem    专家对知识条目落签（签署位）
11. case_item     Case         → KnowledgeItem   案例关联知识条目（Case→KG 链路起点）
12. threshold_rule Threshold    → Rule            阈值被规则引用（Threshold→Rule 链路）
13. rule_expert   Rule         → Expert           规则由专家签署/见证（Rule→Expert 链路，签署位）
14. solution_case        SolutionCandidate → Case         方案候选关联案例（方案溯源链路 Phase 3.7.4）
15. solution_rule        SolutionCandidate → Rule         方案候选关联规则（方案溯源链路 Phase 3.7.4）
16. solution_threshold   SolutionCandidate → Threshold    方案候选关联阈值（方案溯源链路 Phase 3.7.4）
17. solution_knowledge_item SolutionCandidate → KnowledgeItem 方案候选关联知识条目（方案溯源链路 Phase 3.7.4）

校验（repository.add_edge 调用 ``validate_edge``）：起止实体类型须匹配 spec，
否则抛 ``ValueError``（fail-closed，绝不静默降级或自动改写）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from agents.engineering.knowledge.graph.entities import (
    GraphNode,
    KnowledgeGraphEntityType,
)


class KnowledgeGraphRelationType(str, Enum):
    """图谱关系类型枚举（值即落库字符串）。"""

    REFERENCES = "references"
    AUTHORED_BY = "authored_by"
    PARENT_CHILD = "parent_child"
    SOURCED_FROM = "sourced_from"
    USED_BY = "used_by"
    APPLIES = "applies"
    CITES = "cites"
    BASIS = "basis"
    WITNESSED_BY = "witnessed_by"
    SIGNS = "signs"
    CASE_ITEM = "case_item"
    THRESHOLD_RULE = "threshold_rule"
    RULE_EXPERT = "rule_expert"
    SOLUTION_CASE = "solution_case"
    SOLUTION_RULE = "solution_rule"
    SOLUTION_THRESHOLD = "solution_threshold"
    SOLUTION_KNOWLEDGE_ITEM = "solution_knowledge_item"

    @classmethod
    def all_values(cls) -> list[str]:
        return [m.value for m in cls]


@dataclass(frozen=True)
class RelationSpec:
    """单类关系的 Schema 规格（不可变）。"""

    relation_type: str
    from_entity: KnowledgeGraphEntityType
    to_entity: KnowledgeGraphEntityType
    description: str
    required_attrs: tuple[str, ...] = ()
    invariant: str = ""


RELATIONSHIP_SPECS: dict[str, RelationSpec] = {
    KnowledgeGraphRelationType.REFERENCES.value: RelationSpec(
        KnowledgeGraphRelationType.REFERENCES.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "知识条目相互引用（如规范条目、派生说明）",
        invariant="references 不传递签署效力；仅承载知识关联，禁止据此 auto-approve",
    ),
    KnowledgeGraphRelationType.AUTHORED_BY.value: RelationSpec(
        KnowledgeGraphRelationType.AUTHORED_BY.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.EXPERT,
        "知识条目由其 author（专家）署名",
        invariant="AI 不代签：authored_by 仅记录署名主体，绝不翻转 Expert.qualification_status",
    ),
    KnowledgeGraphRelationType.PARENT_CHILD.value: RelationSpec(
        KnowledgeGraphRelationType.PARENT_CHILD.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "知识谱系父子（parent_knowledge_id 指向）",
        ("no_cycle",),
        invariant="no_cycle：谱系禁环；派生置信不得强于最弱父",
    ),
    KnowledgeGraphRelationType.SOURCED_FROM.value: RelationSpec(
        KnowledgeGraphRelationType.SOURCED_FROM.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.SOURCE_REF,
        "知识条目引用结构化规范来源（standard+clause 必备）",
        ("standard", "clause"),
        invariant="sourced_from 须带完整结构化引用；缺引用时停留 Pending_Verification，禁止伪造",
    ),
    KnowledgeGraphRelationType.USED_BY.value: RelationSpec(
        KnowledgeGraphRelationType.USED_BY.value,
        KnowledgeGraphEntityType.THRESHOLD,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "阈值被知识条目/案例使用",
        invariant="used_by 仅承载使用关系；Threshold.value 恒 pending 直至双签转正",
    ),
    KnowledgeGraphRelationType.APPLIES.value: RelationSpec(
        KnowledgeGraphRelationType.APPLIES.value,
        KnowledgeGraphEntityType.RULE,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "规则适用于某知识条目/案例/阈值",
        invariant="Rule 为待建骨架（pending_build）；applies 不得触发任何真实计算",
    ),
    KnowledgeGraphRelationType.CITES.value: RelationSpec(
        KnowledgeGraphRelationType.CITES.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.SOURCE_REF,
        "知识条目引述来源（轻量引用，区别于 sourced_from 结构化引用）",
        invariant="cites 不替代 sourced_from 的完整性校验；引用真实性由人工核验",
    ),
    KnowledgeGraphRelationType.BASIS.value: RelationSpec(
        KnowledgeGraphRelationType.BASIS.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.THRESHOLD,
        "知识条目以阈值为依据（threshold_candidate 关联链路）",
        invariant="BASIS 仅建立关联；阈值转正须经专家双签 + G6 授权，AI 不代决",
    ),
    KnowledgeGraphRelationType.WITNESSED_BY.value: RelationSpec(
        KnowledgeGraphRelationType.WITNESSED_BY.value,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        KnowledgeGraphEntityType.EXPERT,
        "知识条目经专家见证（区别于署名 authored_by）",
        invariant="witnessed_by 仅记录见证，不赋予签署效力；AI 不代见证",
    ),
    KnowledgeGraphRelationType.SIGNS.value: RelationSpec(
        KnowledgeGraphRelationType.SIGNS.value,
        KnowledgeGraphEntityType.EXPERT,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "专家对知识条目落签（签署位，映射 expert_verified_by）",
        invariant="AI 不代签：signs 由真实专家经正式流程驱动，Expert 资格须 verified",
    ),
    KnowledgeGraphRelationType.CASE_ITEM.value: RelationSpec(
        KnowledgeGraphRelationType.CASE_ITEM.value,
        KnowledgeGraphEntityType.CASE,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "案例关联知识条目（Case→KnowledgeItem 链路起点，案例知识层 Phase 3.7.3）",
        invariant="case_item 仅承载案例→知识条目关联；案例真实内容须人工经 ESW 窗口导入，AI 不编造",
    ),
    KnowledgeGraphRelationType.THRESHOLD_RULE.value: RelationSpec(
        KnowledgeGraphRelationType.THRESHOLD_RULE.value,
        KnowledgeGraphEntityType.THRESHOLD,
        KnowledgeGraphEntityType.RULE,
        "阈值被某规则引用/适用（Threshold→Rule 链路，案例知识层 Phase 3.7.3）",
        invariant="threshold_rule 仅承载关联；Rule 为 pending 骨架，不触发真实计算",
    ),
    KnowledgeGraphRelationType.RULE_EXPERT.value: RelationSpec(
        KnowledgeGraphRelationType.RULE_EXPERT.value,
        KnowledgeGraphEntityType.RULE,
        KnowledgeGraphEntityType.EXPERT,
        "规则由某专家签署/见证（Rule→Expert 链路，签署位，案例知识层 Phase 3.7.3）",
        invariant="AI 不代签：rule_expert 由真实专家经正式流程驱动，Rule 资格须 verified",
    ),
    KnowledgeGraphRelationType.SOLUTION_CASE.value: RelationSpec(
        KnowledgeGraphRelationType.SOLUTION_CASE.value,
        KnowledgeGraphEntityType.SOLUTION_CANDIDATE,
        KnowledgeGraphEntityType.CASE,
        "方案候选关联案例（SolutionCandidate→Case 溯源链路，方案生成层 Phase 3.7.4）",
        invariant="solution_case 仅承载方案→案例关联；案例真实内容须人工经 ESW 窗口导入，AI 不编造",
    ),
    KnowledgeGraphRelationType.SOLUTION_RULE.value: RelationSpec(
        KnowledgeGraphRelationType.SOLUTION_RULE.value,
        KnowledgeGraphEntityType.SOLUTION_CANDIDATE,
        KnowledgeGraphEntityType.RULE,
        "方案候选关联规则（SolutionCandidate→Rule 溯源链路，方案生成层 Phase 3.7.4）",
        invariant="solution_rule 仅承载关联；Rule 为 pending 骨架，不触发真实计算",
    ),
    KnowledgeGraphRelationType.SOLUTION_THRESHOLD.value: RelationSpec(
        KnowledgeGraphRelationType.SOLUTION_THRESHOLD.value,
        KnowledgeGraphEntityType.SOLUTION_CANDIDATE,
        KnowledgeGraphEntityType.THRESHOLD,
        "方案候选关联阈值（SolutionCandidate→Threshold 溯源链路，方案生成层 Phase 3.7.4）",
        invariant="solution_threshold 仅承载关联；Threshold.value 恒 pending 直至双签转正",
    ),
    KnowledgeGraphRelationType.SOLUTION_KNOWLEDGE_ITEM.value: RelationSpec(
        KnowledgeGraphRelationType.SOLUTION_KNOWLEDGE_ITEM.value,
        KnowledgeGraphEntityType.SOLUTION_CANDIDATE,
        KnowledgeGraphEntityType.KNOWLEDGE_ITEM,
        "方案候选关联知识条目（SolutionCandidate→KnowledgeItem 溯源链路，方案生成层 Phase 3.7.4）",
        invariant="solution_knowledge_item 仅承载关联；知识条目真实性由人工核验",
    ),
}

# 关系合法起止实体类型速查（供 add_edge 校验）。
_RELATION_FROM_TO: dict[str, tuple[str, str]] = {
    name: (spec.from_entity.value, spec.to_entity.value)
    for name, spec in RELATIONSHIP_SPECS.items()
}


@dataclass
class GraphEdge:
    """图谱边通用结构（任务3 落库单元）。"""

    edge_id: str
    relation_type: str
    source_id: str
    target_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    content_hash: str = ""
    actor: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "relation_type": self.relation_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "attributes": dict(self.attributes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "content_hash": self.content_hash,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphEdge":
        return cls(
            edge_id=str(data.get("edge_id", "")),
            relation_type=str(data.get("relation_type", "")),
            source_id=str(data.get("source_id", "")),
            target_id=str(data.get("target_id", "")),
            attributes=dict(data.get("attributes") or {}),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            version=int(data.get("version", 1) or 1),
            content_hash=str(data.get("content_hash", "")),
            actor=str(data.get("actor", "system")),
        )


def _edge_hash(edge: GraphEdge) -> str:
    """对边核心内容求 sha256 摘要（审计）。"""
    payload = {
        "relation_type": edge.relation_type,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "attributes": edge.attributes,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def validate_edge(edge: GraphEdge, node_index: Mapping[str, GraphNode]) -> None:
    """校验边的起止实体类型约束（fail-closed）。

    违反规格（关系未注册 / 起止节点缺失 / 实体类型不匹配）一律抛 ``ValueError``，
    **绝不**静默降级、自动改写或回退。这是红线屏障的一部分。
    """
    spec = RELATIONSHIP_SPECS.get(edge.relation_type)
    if spec is None:
        raise ValueError(
            f"关系类型 {edge.relation_type!r} 未在 RELATIONSHIP_SPECS 注册（17 关系白名单）"
        )
    src = node_index.get(edge.source_id)
    tgt = node_index.get(edge.target_id)
    if src is None:
        raise ValueError(f"边起点节点缺失：source_id={edge.source_id!r} 未入图")
    if tgt is None:
        raise ValueError(f"边终点节点缺失：target_id={edge.target_id!r} 未入图")
    expected_from = spec.from_entity.value
    expected_to = spec.to_entity.value
    if src.entity_type != expected_from:
        raise ValueError(
            f"关系 {edge.relation_type!r} 起点实体类型约束违例："
            f"实际 {src.entity_type!r} 应为 {expected_from!r}"
        )
    if tgt.entity_type != expected_to:
        raise ValueError(
            f"关系 {edge.relation_type!r} 终点实体类型约束违例："
            f"实际 {tgt.entity_type!r} 应为 {expected_to!r}"
        )
    # required_attrs 校验（缺则 fail-closed）。
    for attr in spec.required_attrs:
        if attr not in edge.attributes:
            raise ValueError(
                f"关系 {edge.relation_type!r} 缺必需属性 {attr!r}（不变量：{spec.invariant!r}）"
            )


__all__ = [
    "KnowledgeGraphRelationType",
    "RelationSpec",
    "RELATIONSHIP_SPECS",
    "GraphEdge",
    "validate_edge",
]

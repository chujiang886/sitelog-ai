"""Knowledge Graph 实体 Schema（Phase 3.7.1 Task 1 + Phase 3.7.4 工程方案生成层）。

定义 BOIP Knowledge Graph Foundation 的 7 类实体 Schema：
- ``KnowledgeItem``：复用 ``connector.KnowledgeItem`` 13 字段七态契约（真实代码已建）；
- ``Threshold``    ：复用 ``thresholds.schema.ThresholdSourceRef`` + 治理态；``value`` 恒 ``pending_verification``（红线：不伪造工程参数）；
- ``Expert``       ：复用 ``experts.json`` 字段结构；``qualification_status`` 严禁 AI 翻转（AI 不代签/代授权）；
- ``SourceRef``    ：复用 ``thresholds.schema.ThresholdSourceRef`` 结构化来源引用；
- ``Case``         ：方案/成本关联载体（Phase 3.7.3 已建骨架，pending_build=True），仅承载人工经 ESW 导入的占位壳；
- ``Rule``         ：成本/校验规则载体（pending_build=True），expression 恒 pending_verification，不填真实计算式；
- ``SolutionCandidate``：工程方案候选载体（Phase 3.7.4 新增，pending_build=True），**仅承载候选占位壳**，
                        components/confidence 恒 PENDING_VERIFICATION，AI 不编造真实方案数值、不自动选终、不批准。

统一承载：``GraphNode``（图谱节点通用结构，含审计字段），各实体经 ``to_node()`` 落图，
经 ``from_node()`` 还原。Case / Rule / SolutionCandidate 明确标 ``pending_build=True``，
禁止被当作已就绪实体用于工程判定。

红线（本 Sprint 串接全系列）：
- 不录入真实工程参数：Threshold.value / Case / Rule / SolutionCandidate 真实取值保持 pending_verification；
- 不开启 engineering_enabled（复用 load_engineering_enabled 作只读断言）；
- 不输出 engineering_approved、不自动创建 ReleaseApproval；
- AI 不代签 / 不代授权：Expert 仅承载被登记专家的资料壳，绝不落 expert_verified_by / verified_by；
- AI 不自动选择最终工程方案、不批准方案（红线③/②，SolutionReviewQueue 仅人工驱动）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.thresholds.schema import ThresholdSourceRef, ThresholdStatus


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳（审计用）。"""
    return datetime.now(timezone.utc).isoformat()


def _canonical(obj: Any) -> str:
    """对任意可序列化结构做规范 JSON 序列化（审计哈希源）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


# 方案候选验证态常量（与 PENDING_PLACEHOLDER 同值，语义独立命名，便于阅读）。
PENDING_VERIFICATION: str = "pending_verification"


def compute_node_hash(node: "GraphNode") -> str:
    """对节点核心内容（entity_type + label + attributes）求 sha256 摘要。"""
    payload = {
        "entity_type": node.entity_type,
        "label": node.label,
        "attributes": node.attributes,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]


class KnowledgeGraphEntityType(str, Enum):
    """图谱实体类型枚举（值即落库字符串）。"""

    KNOWLEDGE_ITEM = "KnowledgeItem"
    CASE = "Case"
    RULE = "Rule"
    THRESHOLD = "Threshold"
    EXPERT = "Expert"
    SOURCE_REF = "SourceRef"
    SOLUTION_CANDIDATE = "SolutionCandidate"

    @classmethod
    def all_values(cls) -> list[str]:
        return [m.value for m in cls]


# ---------------------------------------------------------------------------
# 通用节点结构（含审计字段）
# ---------------------------------------------------------------------------
@dataclass
class GraphNode:
    """图谱节点通用结构（任务3 落库单元）。

    ``attributes`` 承载各实体的类型化字段；``pending_build`` 标记该节点所属实体
    是否仍为待建骨架（Case/Rule 为 True），禁止在 enabled 前参与工程判定。
    """

    node_id: str
    entity_type: str
    label: str
    attributes: dict[str, Any]
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    content_hash: str = ""
    actor: str = "system"
    pending_build: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "entity_type": self.entity_type,
            "label": self.label,
            "attributes": dict(self.attributes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "content_hash": self.content_hash,
            "actor": self.actor,
            "pending_build": self.pending_build,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphNode":
        return cls(
            node_id=str(data.get("node_id", "")),
            entity_type=str(data.get("entity_type", "")),
            label=str(data.get("label", "")),
            attributes=dict(data.get("attributes") or {}),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            version=int(data.get("version", 1) or 1),
            content_hash=str(data.get("content_hash", "")),
            actor=str(data.get("actor", "system")),
            pending_build=bool(data.get("pending_build", False)),
        )


# ---------------------------------------------------------------------------
# 实体 1：KnowledgeItem（复用真实 13 字段契约）
# ---------------------------------------------------------------------------
@dataclass
class KnowledgeItemEntity:
    """知识条目实体；直接包裹真实 ``KnowledgeItem``（connector 已建）。"""

    item: KnowledgeItem

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        node = GraphNode(
            node_id=self.item.knowledge_id,
            entity_type=KnowledgeGraphEntityType.KNOWLEDGE_ITEM.value,
            label=self.item.title or self.item.knowledge_id,
            attributes=self.item.to_dict(),
            created_at=self.item.created_at or now,
            updated_at=self.item.updated_at or now,
            version=1,
            actor=actor,
            pending_build=False,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "KnowledgeItemEntity":
        return cls(item=KnowledgeItem.from_dict(node.attributes))


# ---------------------------------------------------------------------------
# 实体 2：Threshold（复用 thresholds.schema；value 恒 pending_verification）
# ---------------------------------------------------------------------------
@dataclass
class ThresholdEntity:
    """工程阈值实体（E/D-TH-*）。

    红线：``value`` 必须为 ``pending_verification``，本 Schema 不提供任何填真实值的方法；
    真实 value 转正须经专家双签 + 主理人核准（G6）后写入 verified.json，属激活阶段。
    """

    threshold_id: str
    domain: str = PENDING_PLACEHOLDER
    value: str = PENDING_PLACEHOLDER
    status: str = ThresholdStatus.DRAFT.value
    source_ref: ThresholdSourceRef = field(default_factory=ThresholdSourceRef)

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "threshold_id": self.threshold_id,
            "domain": self.domain,
            "value": self.value,
            "status": self.status,
            "source_ref": self.source_ref.as_dict(),
        }
        node = GraphNode(
            node_id=self.threshold_id,
            entity_type=KnowledgeGraphEntityType.THRESHOLD.value,
            label=f"Threshold {self.threshold_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=False,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "ThresholdEntity":
        a = node.attributes
        return cls(
            threshold_id=str(a.get("threshold_id", node.node_id)),
            domain=str(a.get("domain", PENDING_PLACEHOLDER)),
            value=str(a.get("value", PENDING_PLACEHOLDER)),
            status=str(a.get("status", ThresholdStatus.DRAFT.value)),
            source_ref=ThresholdSourceRef.from_raw(a.get("source_ref")),
        )


# ---------------------------------------------------------------------------
# 实体 3：Expert（复用 experts.json 字段结构）
# ---------------------------------------------------------------------------
@dataclass
class ExpertEntity:
    """专家实体；承载被登记专家的资料壳。

    红线：``qualification_status`` 仅为容器位，AI 绝不翻转（不代签/不代授权）；
    绝不落 expert_verified_by / verified_by（签署由真实专家/主理人经正式流程驱动）。
    """

    expert_id: str
    domains: list[str] = field(default_factory=list)
    qualification_ref: str = PENDING_PLACEHOLDER
    sign_scope: list[str] = field(default_factory=list)
    sod_role: str = PENDING_PLACEHOLDER
    valid_until: str = PENDING_PLACEHOLDER
    qualification_status: str = "pending"

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "expert_id": self.expert_id,
            "domains": list(self.domains),
            "qualification_ref": self.qualification_ref,
            "sign_scope": list(self.sign_scope),
            "sod_role": self.sod_role,
            "valid_until": self.valid_until,
            "qualification_status": self.qualification_status,
        }
        node = GraphNode(
            node_id=self.expert_id,
            entity_type=KnowledgeGraphEntityType.EXPERT.value,
            label=f"Expert {self.expert_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=False,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "ExpertEntity":
        a = node.attributes
        return cls(
            expert_id=str(a.get("expert_id", node.node_id)),
            domains=list(a.get("domains") or []),
            qualification_ref=str(a.get("qualification_ref", PENDING_PLACEHOLDER)),
            sign_scope=list(a.get("sign_scope") or []),
            sod_role=str(a.get("sod_role", PENDING_PLACEHOLDER)),
            valid_until=str(a.get("valid_until", PENDING_PLACEHOLDER)),
            qualification_status=str(a.get("qualification_status", "pending")),
        )


# ---------------------------------------------------------------------------
# 实体 4：SourceRef（复用 thresholds.schema.ThresholdSourceRef）
# ---------------------------------------------------------------------------
@dataclass
class SourceRefEntity:
    """规范来源引用实体；包裹结构化 ``ThresholdSourceRef``。"""

    source_ref_id: str
    source_ref: ThresholdSourceRef = field(default_factory=ThresholdSourceRef)

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "source_ref_id": self.source_ref_id,
            "source_ref": self.source_ref.as_dict(),
        }
        node = GraphNode(
            node_id=self.source_ref_id,
            entity_type=KnowledgeGraphEntityType.SOURCE_REF.value,
            label=f"SourceRef {self.source_ref_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=False,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "SourceRefEntity":
        a = node.attributes
        return cls(
            source_ref_id=str(a.get("source_ref_id", node.node_id)),
            source_ref=ThresholdSourceRef.from_raw(a.get("source_ref")),
        )


# ---------------------------------------------------------------------------
# 实体 5：Case（方案/成本关联载体，schema 待建补全）
# ---------------------------------------------------------------------------
@dataclass
class CaseEntity:
    """案例实体（方案生成/成本计算关联载体，Phase 3.7.3 Case Knowledge Layer）。

    **红线③：禁止 AI 伪造真实项目案例。** 所有真实案例字段（project_ref /
    environment / design_context / solution / outcome / lessons）默认空串或
    PENDING_PLACEHOLDER，仅承载由真实主理人/专家经 ESW 窗口线下导入的占位壳；
    AI 不编造任何真实工程数值、不填真实案例内容。

    关联字段（``linked_*``）与图谱链路对齐：
    ``Case --case_item--> KnowledgeItem --> Threshold --threshold_rule--> Rule
    --rule_expert--> Expert``。

    ``lifecycle_stage`` 默认 ``"Captured"``（案例生命周期起点），真实推进须经
    Verified_Source → Expert_Reviewed → Engineering_Referenced 的人工审核
    （见 ``case_lifecycle``），**AI 不自动推进**（红线⑤）。
    """

    case_id: str
    project_ref: str = ""
    environment: str = ""
    title: str = PENDING_PLACEHOLDER
    description: str = PENDING_PLACEHOLDER
    domain: str = PENDING_PLACEHOLDER
    design_context: str = ""
    solution: str = ""
    outcome: str = ""
    lessons: str = ""
    linked_thresholds: list[str] = field(default_factory=list)
    linked_rules: list[str] = field(default_factory=list)
    linked_experts: list[str] = field(default_factory=list)
    lifecycle_stage: str = "Captured"
    status: str = "pending_build"

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "case_id": self.case_id,
            "project_ref": self.project_ref,
            "environment": self.environment,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "design_context": self.design_context,
            "solution": self.solution,
            "outcome": self.outcome,
            "lessons": self.lessons,
            "linked_thresholds": list(self.linked_thresholds),
            "linked_rules": list(self.linked_rules),
            "linked_experts": list(self.linked_experts),
            "lifecycle_stage": self.lifecycle_stage,
            "status": self.status,
        }
        node = GraphNode(
            node_id=self.case_id,
            entity_type=KnowledgeGraphEntityType.CASE.value,
            label=f"Case {self.case_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=True,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "CaseEntity":
        a = node.attributes
        # 兼容旧键 related_thresholds（红线：平滑迁移，不丢数据）。
        linked_thresholds = list(a.get("linked_thresholds") or a.get("related_thresholds") or [])
        return cls(
            case_id=str(a.get("case_id", node.node_id)),
            project_ref=str(a.get("project_ref", "")),
            environment=str(a.get("environment", "")),
            title=str(a.get("title", PENDING_PLACEHOLDER)),
            description=str(a.get("description", PENDING_PLACEHOLDER)),
            domain=str(a.get("domain", PENDING_PLACEHOLDER)),
            design_context=str(a.get("design_context", "")),
            solution=str(a.get("solution", "")),
            outcome=str(a.get("outcome", "")),
            lessons=str(a.get("lessons", "")),
            linked_thresholds=linked_thresholds,
            linked_rules=list(a.get("linked_rules") or []),
            linked_experts=list(a.get("linked_experts") or []),
            lifecycle_stage=str(a.get("lifecycle_stage", "Captured")),
            status=str(a.get("status", "pending_build")),
        )

    @classmethod
    def from_empty(cls, case_id: str, *, project_ref: str = "", environment: str = "") -> "CaseEntity":
        """构造空壳案例（无真实数据，红线③）。

        仅提供 ``case_id`` 与可选的项目/工况引用占位；不填任何真实值。
        真实字段保持空串/PENDING_PLACEHOLDER，等待人工经 ESW 窗口导入。
        """
        return cls(case_id=case_id, project_ref=project_ref, environment=environment)


# ---------------------------------------------------------------------------
# 实体 6：Rule（成本/校验规则载体，schema 待建补全）
# ---------------------------------------------------------------------------
@dataclass
class RuleEntity:
    """规则实体（成本计算/校验规则载体）。

    **待建补全（pending_build=True）**：真实规则结构（rule_type / 表达式 / 适用域）
    将在后续成本计算路线落地，本轮仅骨架，expression 恒 ``pending_verification``，
    **不填任何真实计算式/单价**（红线：不伪造工程参数）。
    """

    rule_id: str
    rule_type: str = PENDING_PLACEHOLDER
    expression: str = PENDING_PLACEHOLDER
    domain: str = PENDING_PLACEHOLDER
    applies_to: list[str] = field(default_factory=list)

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "expression": self.expression,
            "domain": self.domain,
            "applies_to": list(self.applies_to),
        }
        node = GraphNode(
            node_id=self.rule_id,
            entity_type=KnowledgeGraphEntityType.RULE.value,
            label=f"Rule {self.rule_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=True,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "RuleEntity":
        a = node.attributes
        return cls(
            rule_id=str(a.get("rule_id", node.node_id)),
            rule_type=str(a.get("rule_type", PENDING_PLACEHOLDER)),
            expression=str(a.get("expression", PENDING_PLACEHOLDER)),
            domain=str(a.get("domain", PENDING_PLACEHOLDER)),
            applies_to=list(a.get("applies_to") or []),
        )


# ---------------------------------------------------------------------------
# 实体 7：SolutionCandidate（工程方案候选载体，Phase 3.7.4 方案生成层）
# ---------------------------------------------------------------------------
@dataclass
class SolutionCandidateEntity:
    """工程方案候选实体（Engineering Solution Generation Layer，Phase 3.7.4）。

    **红线④：禁止 AI 伪造真实工程参数。** 所有方案实质字段（components /
    confidence）默认 ``PENDING_VERIFICATION`` / ``"pending"``，仅承载由真实
    主理人/专家经审核队列（SolutionReviewQueue）线下导入的占位壳；AI 不编造
    任何真实工程数值、不填真实方案内容。

    **红线③：禁止 AI 自动选择最终工程方案。** 本实体仅代表「候选」，不具备
    ``selected`` / ``final`` 状态位；最终选定须经 SolutionReviewQueue 的
    ``approved_by_human`` 状态（仅 ``by_human=True`` 可入）。

    关联字段（``related_*``）与图谱链路对齐，使方案可溯源至：
    ``SolutionCandidate --solution_case--> Case
     --solution_rule--> Rule
     --solution_threshold--> Threshold
     --solution_knowledge_item--> KnowledgeItem``。

    ``verification_status`` 默认 ``PENDING_VERIFICATION``，真实转正须在启用态
    后经专家双签 + 主理人核准（G6）写入 verified.json，属激活阶段。
    """

    solution_id: str
    input_context: str = PENDING_PLACEHOLDER
    related_cases: list[str] = field(default_factory=list)
    related_rules: list[str] = field(default_factory=list)
    related_thresholds: list[str] = field(default_factory=list)
    components: str = PENDING_VERIFICATION
    confidence: str = "pending"
    verification_status: str = PENDING_VERIFICATION
    status: str = "pending_build"

    def to_node(self, *, actor: str = "graph_import") -> GraphNode:
        now = _utc_now()
        attrs = {
            "solution_id": self.solution_id,
            "input_context": self.input_context,
            "related_cases": list(self.related_cases),
            "related_rules": list(self.related_rules),
            "related_thresholds": list(self.related_thresholds),
            "components": self.components,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "status": self.status,
        }
        node = GraphNode(
            node_id=self.solution_id,
            entity_type=KnowledgeGraphEntityType.SOLUTION_CANDIDATE.value,
            label=f"SolutionCandidate {self.solution_id}",
            attributes=attrs,
            created_at=now,
            updated_at=now,
            version=1,
            actor=actor,
            pending_build=True,
        )
        node.content_hash = compute_node_hash(node)
        return node

    @classmethod
    def from_node(cls, node: GraphNode) -> "SolutionCandidateEntity":
        a = node.attributes
        # 兼容旧键（红线：平滑迁移，不丢数据）。
        related_cases = list(a.get("related_cases") or a.get("related_case_ids") or [])
        related_rules = list(a.get("related_rules") or a.get("related_rule_ids") or [])
        related_thresholds = list(
            a.get("related_thresholds") or a.get("related_threshold_ids") or []
        )
        return cls(
            solution_id=str(a.get("solution_id", node.node_id)),
            input_context=str(a.get("input_context", PENDING_PLACEHOLDER)),
            related_cases=related_cases,
            related_rules=related_rules,
            related_thresholds=related_thresholds,
            components=str(a.get("components", PENDING_VERIFICATION)),
            confidence=str(a.get("confidence", "pending")),
            verification_status=str(a.get("verification_status", PENDING_VERIFICATION)),
            status=str(a.get("status", "pending_build")),
        )

    @classmethod
    def from_empty(cls, solution_id: str, *, input_context: str = PENDING_PLACEHOLDER) -> "SolutionCandidateEntity":
        """构造空壳方案候选（无真实数据，红线④/③）。

        仅提供 ``solution_id`` 与可选的上下文占位；不填任何真实方案数值。
        真实 components/confidence 保持 PENDING_VERIFICATION/pending，等待人工导入。
        """
        return cls(solution_id=solution_id, input_context=input_context)


# ---------------------------------------------------------------------------
# 设计候选契约（方案生成器入参，Phase 3.7.4 Task 2）
# ---------------------------------------------------------------------------
@dataclass
class DesignCandidate:
    """设计候选契约（SolutionGenerator 的入参之一）。

    承载方案生成所需的「设计侧」上下文占位。构造器断言 ``load_engineering_enabled()
    is False``（红线①：禁止在禁用态下构造可被用于工程判定的设计对象）。

    **红线③（Phase 3.7.7 新增）**：``geometry`` / ``opening_type`` 仅为占位（默认
    ``PENDING_PLACEHOLDER``），AI **不自动确认图纸尺寸**；尺寸转正须经人工核验。
    **红线④（Phase 3.7.7 新增）**：``glass_config`` / ``profile_config`` 仅为占位，
    AI **不自动生成真实工程参数**；真实参数转正须经激活流程（专家双签 + 主理人核准）。
    **红线⑤**：``confidence`` 仅占位，AI 不输出报价依据；解析必须带 ``source_ref`` +
    ``confidence`` 占位（见 ``DrawingParser``）。

    ``verification_status`` 默认 ``PENDING_VERIFICATION``：所有设计侧取值须经人工核验
    转正，AI 不进入 ``verified_by_human`` 状态（见 ``DesignReviewQueue``）。
    """

    design_id: str
    components: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    # —— Phase 3.7.7 Drawing Intelligence Layer 新增字段（全部默认占位，红线③/④/⑤） ——
    source_files: list[str] = field(default_factory=list)
    geometry: Any = PENDING_PLACEHOLDER
    opening_type: str = PENDING_PLACEHOLDER
    glass_config: Any = PENDING_PLACEHOLDER
    profile_config: Any = PENDING_PLACEHOLDER
    confidence: Any = PENDING_PLACEHOLDER
    verification_status: str = PENDING_VERIFICATION

    def __post_init__(self) -> None:
        # 红线①：构造即断言未启用工程判定，fail-closed。
        if load_engineering_enabled() is not False:
            raise RuntimeError(
                "DesignCandidate 构造失败：engineering_enabled 不为 False，"
                "禁止在启用态下由 AI 构造设计候选（红线①）"
            )


# ---------------------------------------------------------------------------
# 约束模型（Solution Constraint & Optimization Layer，Phase 3.7.5 任务1）
# ---------------------------------------------------------------------------
@dataclass
class SolutionConstraint:
    """方案约束模型（Solution Constraint & Optimization Layer，Phase 3.7.5）。

    纯数据占位壳（非图谱实体：不进 ``KnowledgeGraphEntityType``、不进
    ``_ENTITY_DISPATCH``、不新增关系白名单），承载方案候选的约束标注。
    所有真实约束字段默认 ``PENDING_PLACEHOLDER`` / ``PENDING_VERIFICATION``，
    AI 不填真实工程约束数值（红线④/⑤：不伪造工程参数、不自动报价）。

    ``status`` 默认 ``PENDING_VERIFICATION``：真实约束须经人工核验转正。
    """

    constraint_id: str
    type: str = PENDING_PLACEHOLDER
    source: str = PENDING_PLACEHOLDER
    severity: str = PENDING_PLACEHOLDER
    description: str = PENDING_PLACEHOLDER
    status: str = PENDING_VERIFICATION


# ---------------------------------------------------------------------------
# 成本智能层模型（Cost Intelligence Layer，Phase 3.7.6 任务1/任务2）
# ---------------------------------------------------------------------------
@dataclass
class BOMEntity:
    """物料清单模型（Cost Intelligence Layer，Phase 3.7.6 任务1）。

    纯数据占位壳（非图谱实体：不进 ``KnowledgeGraphEntityType``、不进
    ``_ENTITY_DISPATCH``、不新增关系白名单），承载某方案（``solution_id``）的
    物料/人工/辅材清单项。所有真实取值字段默认 ``PENDING_PLACEHOLDER`` /
    ``PENDING_VERIFICATION``，AI 不填真实工程量、不报价、不伪造市场价格。

    ``status`` 默认 ``PENDING_VERIFICATION``：真实 BOM 须经人工核验转正。
    """

    bom_id: str
    solution_id: str
    item_type: str = PENDING_PLACEHOLDER
    item_name: str = PENDING_PLACEHOLDER
    quantity: Any = PENDING_PLACEHOLDER
    unit: str = PENDING_PLACEHOLDER
    source_ref: str = PENDING_PLACEHOLDER
    status: str = PENDING_VERIFICATION


@dataclass
class CostRule:
    """成本规则模型（Cost Intelligence Layer，Phase 3.7.6 任务2）。

    纯数据占位壳（非图谱实体），承载某成本项的取价/计算规则。**价格必须有来源**：
    ``unit_price`` 默认 ``None``（禁止硬编码价格，红线⑤：不伪造市场价格），任何真实
    单价必须经 ``source_ref`` 指向可信来源（专家双签 + 主理人核准的价目/定额），
    由人工（非本层）填充。``formula`` 默认 ``PENDING_PLACEHOLDER``（不填真实计算式）。

    ``status`` 默认 ``PENDING_VERIFICATION``：真实规则须经人工核验转正。
    """

    rule_id: str
    source_ref: str = PENDING_PLACEHOLDER
    formula: str = PENDING_PLACEHOLDER
    unit_price: Optional[Any] = None  # 禁止硬编码价格：默认 None，价格必须有来源。
    status: str = PENDING_VERIFICATION


# 实体类型 → (to_node 工厂, from_node 工厂) 调度表（供 repository/集成层使用）。
_ENTITY_DISPATCH: dict[str, tuple[type, type]] = {
    KnowledgeGraphEntityType.KNOWLEDGE_ITEM.value: (KnowledgeItemEntity, KnowledgeItemEntity),
    KnowledgeGraphEntityType.THRESHOLD.value: (ThresholdEntity, ThresholdEntity),
    KnowledgeGraphEntityType.EXPERT.value: (ExpertEntity, ExpertEntity),
    KnowledgeGraphEntityType.SOURCE_REF.value: (SourceRefEntity, SourceRefEntity),
    KnowledgeGraphEntityType.CASE.value: (CaseEntity, CaseEntity),
    KnowledgeGraphEntityType.RULE.value: (RuleEntity, RuleEntity),
    KnowledgeGraphEntityType.SOLUTION_CANDIDATE.value: (SolutionCandidateEntity, SolutionCandidateEntity),
}


def entity_to_node(entity: Any, *, actor: str = "graph_import") -> GraphNode:
    """将任一实体对象转为 ``GraphNode``（调度 to_node）。"""
    if isinstance(entity, GraphNode):
        return entity
    if hasattr(entity, "to_node"):
        return entity.to_node(actor=actor)
    raise TypeError(f"未知实体类型，无法转为 GraphNode：{type(entity)!r}")


__all__ = [
    "KnowledgeGraphEntityType",
    "GraphNode",
    "KnowledgeItemEntity",
    "ThresholdEntity",
    "ExpertEntity",
    "SourceRefEntity",
    "CaseEntity",
    "RuleEntity",
    "SolutionCandidateEntity",
    "DesignCandidate",
    "SolutionConstraint",
    "BOMEntity",
    "CostRule",
    "PENDING_VERIFICATION",
    "entity_to_node",
    "compute_node_hash",
    "load_engineering_enabled",
]

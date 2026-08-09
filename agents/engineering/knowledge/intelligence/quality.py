"""Knowledge Quality Analyzer（Phase 3.3 Sprint 3.3.9, Task 1）。

KnowledgeQualityAnalyzer.analyze(item) -> KnowledgeQualityReport

五维度评分，**全部可追溯到 KnowledgeItem 字段/状态**，不虚构任何行业常数：
- completeness        : 13 核心字段已填比例（字段计数，非经验值）。
- source_strength      : 由 validation_status 映射（产品定义表，非统计估计）。
- validation_status    : 直接透传 item.validation_status（分类字段，不评分）。
- freshness            : 基于 updated_at 与当前时间的相对时长分桶（策略常量，待治理确认）。
- dependency_integrity : 上游依赖（parent_knowledge_id）可解析性；可选 repo 精确核验。

红线约束：
- 不输出 engineering_approved：source_strength 仅在 item 已为 Engineering_Approved 时映射 1.0，
  分析器**不主动产生**该状态。
- 不读 verified.json：评分仅用 KnowledgeItem 字段与（可选的）Repository 内存数据。
- overall 为四数值维度固定权重加权平均（权重在代码注释中显式声明，标注 pending_verification，
  不标榜为行业最佳实践）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.intelligence._core import (
    CORE_FIELD_NAMES,
    is_filled,
    linked_entities_filled,
)

# source_strength 映射表（产品定义，非统计估计）。
# pending_verification 标记：权重/分桶为策略常量，待治理确认。
_SOURCE_STRENGTH_MAP: dict[str, float] = {
    "Captured": 0.2,
    "Pending_Verification": 0.2,
    "Source_Verified": 0.5,
    "Expert_Verified": 0.75,
    "Engineering_Verified": 0.9,
    "Engineering_Approved": 1.0,
    "Deprecated": 0.0,
}

# freshness 分桶（策略常量，pending_verification）：距 updated_at 天数上限 -> 分数。
_FRESHNESS_WINDOWS: tuple[tuple[float, float], ...] = (
    (30.0, 1.0),    # 30 天内
    (90.0, 0.7),    # 90 天内
    (365.0, 0.4),   # 1 年内
    (float("inf"), 0.1),  # 超过 1 年
)
_UNKNOWN_FRESHNESS: float = 0.0

# overall 四数值维度权重（pending_verification：默认权重，待治理确认）。
_OVERALL_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "source_strength": 0.30,
    "freshness": 0.20,
    "dependency_integrity": 0.20,
}


@dataclass
class KnowledgeQualityReport:
    """单条 KnowledgeItem 的质量评估报告（只读产物）。"""

    knowledge_id: str
    completeness: float
    source_strength: float
    validation_status: str
    freshness: float
    dependency_integrity: float
    overall: float
    rationale: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "completeness": self.completeness,
            "source_strength": self.source_strength,
            "validation_status": self.validation_status,
            "freshness": self.freshness,
            "dependency_integrity": self.dependency_integrity,
            "overall": self.overall,
            "rationale": dict(self.rationale),
        }


class KnowledgeQualityAnalyzer:
    """Task 1：知识质量评估（只读，无副作用）。"""

    def analyze(
        self,
        item: KnowledgeItem,
        repo: Optional[Any] = None,
    ) -> KnowledgeQualityReport:
        """评估单条 item 质量；repo 可选（用于精确核验上游依赖存在性）。"""
        completeness, comp_r = self._completeness(item)
        source_strength, src_r = self._source_strength(item)
        freshness, fresh_r = self._freshness(item)
        dep_integrity, dep_r = self._dependency_integrity(item, repo)
        overall = (
            completeness * _OVERALL_WEIGHTS["completeness"]
            + source_strength * _OVERALL_WEIGHTS["source_strength"]
            + freshness * _OVERALL_WEIGHTS["freshness"]
            + dep_integrity * _OVERALL_WEIGHTS["dependency_integrity"]
        )
        rationale = {
            "completeness": comp_r,
            "source_strength": src_r,
            "validation_status": f"透传 item.validation_status={item.validation_status!r}",
            "freshness": fresh_r,
            "dependency_integrity": dep_r,
            "overall": (
                "四数值维度（completeness/source_strength/freshness/dependency_integrity）"
                "固定权重加权平均；权重为 pending_verification 默认策略"
            ),
        }
        return KnowledgeQualityReport(
            knowledge_id=item.knowledge_id,
            completeness=completeness,
            source_strength=source_strength,
            validation_status=item.validation_status,
            freshness=freshness,
            dependency_integrity=dep_integrity,
            overall=overall,
            rationale=rationale,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _completeness(item: KnowledgeItem) -> tuple[float, str]:
        filled = 0
        for name in CORE_FIELD_NAMES:
            value = getattr(item, name, None)
            if name == "linked_entities":
                if linked_entities_filled(item):
                    filled += 1
            elif is_filled(value):
                filled += 1
        total = len(CORE_FIELD_NAMES)
        return filled / total, f"{filled}/{total} 核心字段已填（非空且非 pending_verification）"

    @staticmethod
    def _source_strength(item: KnowledgeItem) -> tuple[float, str]:
        score = _SOURCE_STRENGTH_MAP.get(item.validation_status, 0.2)
        return score, (
            f"validation_status={item.validation_status!r} -> {score} "
            f"（产品定义映射，非统计估计；approved 态仅作映射输入，AI 不主动产生）"
        )

    @staticmethod
    def _freshness(item: KnowledgeItem) -> tuple[float, str]:
        raw = item.updated_at or ""
        if not raw:
            return _UNKNOWN_FRESHNESS, "updated_at 缺失，freshness=0.0"
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return _UNKNOWN_FRESHNESS, f"updated_at={raw!r} 无法解析，freshness=0.0"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max(0, (datetime.now(timezone.utc) - dt).days)
        for window, score in _FRESHNESS_WINDOWS:
            if days < window:
                return score, f"距 updated_at {days}d（<{window:g}d 桶）-> {score}（策略常量 pending_verification）"
        return 0.1, f"距 updated_at {days}d -> 0.1（策略常量 pending_verification）"

    @staticmethod
    def _dependency_integrity(
        item: KnowledgeItem, repo: Optional[Any]
    ) -> tuple[float, str]:
        has_parent = bool(item.parent_knowledge_id) and item.parent_knowledge_id != PENDING_PLACEHOLDER
        if not has_parent:
            return 1.0, "无上游 parent_knowledge_id 依赖，dependency_integrity=1.0"
        if repo is None:
            return (
                0.6,
                "声明了上游 parent_knowledge_id 但孤立分析无 repo，无法核验父节点状态（建议经 Repository 评估）",
            )
        parent = repo.get(item.parent_knowledge_id)
        if parent is None:
            return 0.0, f"父节点 {item.parent_knowledge_id!r} 在仓库中缺失，dependency_integrity=0.0"
        if parent.validation_status == "Deprecated":
            return 0.0, f"父节点 {item.parent_knowledge_id!r} 已 Deprecated，dependency_integrity=0.0"
        return 1.0, f"父节点 {item.parent_knowledge_id!r} 存在且未废弃，dependency_integrity=1.0"


__all__ = ["KnowledgeQualityAnalyzer", "KnowledgeQualityReport"]

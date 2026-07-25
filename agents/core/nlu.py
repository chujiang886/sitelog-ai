"""Core Agent 自然语言理解（NLU）模块（Phase 1 / T06a）。

设计：
- ``IntentExtractor`` 提供规则 + 关键词提取，无外部依赖；
- 提供 LLM 增强入口：当 ``agents.config.yaml::llm.enabled = true`` 且
   ``DualTrackRouter`` 可用时，调用 LLM 重写意图，缺失 LLM 时回退规则；
- 任何 LLM 失败必须降级到规则结果，不让对话 API 崩溃。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from agents.llm.types import LLMMessage, LLMRequest, LLMRole


# --------------------------------------------------------------------------- #
# Intent 枚举                                                                   #
# --------------------------------------------------------------------------- #


class Intent(str, Enum):
    """Phase 1 支持的对话意图集合。"""

    CONSULT = "consult"                # 通用咨询
    CREATE_PROJECT = "create_project"  # 创建项目
    QUERY_STATUS = "query_status"      # 查询项目/任务状态
    EXPLAIN_PLAN = "explain_plan"      # 解释方案/候选
    REVIEW_TRIGGER = "review_trigger"  # 触发人工复核
    UNKNOWN = "unknown"                # 兜底


# --------------------------------------------------------------------------- #
# IntentExtractor 结构体                                                          #
# --------------------------------------------------------------------------- #


def build_llm_messages_for_intent(
    user_text: str,
    intent_candidates: Iterable[Intent],
) -> list[LLMMessage]:
    """构造调用 LLM 提取意图的标准 system + user 双消息。

    参数：
        user_text: 用户自然语言文本
        intent_candidates: 可选意图候选列表（默认使用全部）
    返回：
        ``[system, user]`` 两个 LLMMessage 对象
    """
    candidate_labels: str = ", ".join(
        (c.value for c in intent_candidates),
    )
    system_prompt: str = (
        "你是 BOIP 的对话意图分类器，仅负责输出 JSON，禁止自然语言。\n"
        f"可用意图：{candidate_labels}\n"
        '输出格式：{"intent": "<intent>", "confidence": <0-1>, "rationale": "..."}'
    )
    return [
        LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
        LLMMessage(role=LLMRole.USER, content=user_text.strip() or "(empty)"),
    ]


@dataclass(frozen=True, slots=True)
class ExtractedIntent:
    """提取意图的标准结果；confidence + method 便于评估与审计。"""

    intent: Intent
    confidence: float
    method: str   # "rule" / "llm" / "llm_fallback_rule"
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""

    def __post_init__(self) -> None:
        """校验 confidence 范围，冻结元数据字段。"""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("ExtractedIntent.confidence must be within [0, 1]")
        object.__setattr__(self, "matched_keywords", tuple(self.matched_keywords))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "method": self.method,
            "matched_keywords": list(self.matched_keywords),
            "rationale": self.rationale,
        }


# --------------------------------------------------------------------------- #
# 规则提取引擎                                                                    #
# --------------------------------------------------------------------------- #

# 规则表：每条 ``(Intent, tuple[关键词])；命中数最多的胜出
_RULE_TABLE: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.CREATE_PROJECT,
        (
            "新建项目",
            "创建项目",
            "发起项目",
            "做个项目",
            "建一个项目",
            "create project",
            "new project",
        ),
    ),
    (
        Intent.QUERY_STATUS,
        (
            "进度",
            "状态",
            "怎么样了",
            "项目状态",
            "查询",
            "status",
            "progress",
        ),
    ),
    (
        Intent.EXPLAIN_PLAN,
        (
            "解释方案",
            "说明方案",
            "为什么",
            "依据",
            "讲解",
            "explain",
            "rationale",
        ),
    ),
    (
        Intent.REVIEW_TRIGGER,
        (
            "人工复核",
            "复核",
            "审核",
            "找工程师",
            "工程师看一下",
            "需要审核",
        ),
    ),
    (
        Intent.CONSULT,
        (
            "什么是",
            "怎么",
            "如何",
            "咨询",
            "请问",
            "what is",
            "how",
            "help",
        ),
    ),
)


def _keyword_hits(text: str, keywords: Iterable[str]) -> tuple[str, ...]:
    """返回所有命中的关键词；忽略大小写、按字面匹配。

    参数：
        text: 用户文本（将被 lower）
        keywords: 候选关键词列表
    返回：
        命中的关键词 tuple
    """
    lowered = text.lower()
    hits: list[str] = []
    for keyword in keywords:
        if not keyword:
            continue
        token = keyword.lower()
        if token in lowered:
            hits.append(keyword)
    return tuple(hits)


def _rule_extract(text: str) -> ExtractedIntent:
    """按规则表投票；空文本直接返回 UNKNOWN/0.0。

    参数：
        text: 用户原始文本
    返回：
        ExtractedIntent（method="rule"）
    """
    cleaned = text.strip()
    if not cleaned:
        return ExtractedIntent(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            method="rule",
            matched_keywords=(),
            rationale="空文本无法识别",
        )
    scored: list[tuple[int, Intent, tuple[str, ...]]] = []
    for intent, keywords in _RULE_TABLE:
        hits = _keyword_hits(cleaned, keywords)
        if hits:
            scored.append((len(hits), intent, hits))
    if not scored:
        return ExtractedIntent(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            method="rule",
            matched_keywords=(),
            rationale="无关键词命中",
        )
    scored.sort(key=lambda item: (-item[0], item[1].value))
    top_count, top_intent, top_hits = scored[0]
    confidence = min(0.95, 0.4 + 0.15 * top_count)
    return ExtractedIntent(
        intent=top_intent,
        confidence=confidence,
        method="rule",
        matched_keywords=top_hits,
        rationale=f"命中 {top_count} 个关键词 → {top_intent.value}",
    )


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    """尝试解析 LLM 返回的 JSON；宽容地剥离 markdown 代码块围栏。

    参数：
        text: LLM 原始文本输出
    返回：
        解析出的 ``dict`` 或 ``None``（解析失败）
    """
    candidate = text.strip()
    if not candidate:
        return None
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, flags=re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    try:
        import json
    except ImportError:
        return None
    try:
        parsed = json.loads(candidate)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


# --------------------------------------------------------------------------- #
# IntentExtractor 类                                                              #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class IntentExtractor:
    """意图提取器：先规则后 LLM 增强，失败时降级。

    参数：
        rule_table: 自定义规则表（可选，默认使用内置 ``_RULE_TABLE``）
        llm_enabled: ``True`` 表示允许调用 LLM
        router: DualTrackRouter 实例；无 Router 时不走 LLM
    """

    rule_table: Mapping[Intent, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType(
            {intent: keywords for intent, keywords in _RULE_TABLE}
        )
    )
    llm_enabled: bool = False
    router: Any = None   # DualTrackRouter 实例；缺省时不走 LLM

    async def extract(self, text: str) -> ExtractedIntent:
        """异步提取（规则 + LLM 增强），LLM 失败时回退到规则结果。

        参数：
            text: 用户文本
        返回：
            ``ExtractedIntent``（method="rule" / "llm" / "llm_fallback_rule"）
        """
        rule_result = _rule_extract(text)
        if not (self.llm_enabled and self.router is not None):
            return rule_result       # 无 LLM 支撑，直接返回规则结果
        try:
            llm_result = await self._llm_extract(text, rule_result)
        except Exception:    # noqa: BLE001
            return rule_result       # LLM 失败 → 降级规则
        if llm_result is None:
            return ExtractedIntent(
                intent=rule_result.intent,
                confidence=rule_result.confidence,
                method="llm_fallback_rule",
                matched_keywords=rule_result.matched_keywords,
                rationale=f"LLM 解析失败，回退规则结果：{rule_result.rationale}",
            )
        return llm_result

    async def _llm_extract(
        self,
        text: str,
        rule_result: ExtractedIntent,
    ) -> ExtractedIntent | None:
        """调用 LLM 重写意图；解析失败返回 None 触发降级。"""
        messages = build_llm_messages_for_intent(
            text, list(self.rule_table.keys()),
        )
        response, _ = await self.router.route(
            LLMRequest(messages=tuple(messages)),
        )
        parsed = _safe_json_loads(response.content)
        if not parsed:
            return None
        intent_raw = str(parsed.get("intent", "")).strip().lower()
        try:
            intent = Intent(intent_raw)
        except ValueError:
            return None     # LLM 返回的意图不在已知枚举中，视为无效
        try:
            confidence = float(parsed.get("confidence", rule_result.confidence))
        except (TypeError, ValueError):
            confidence = rule_result.confidence
        confidence = max(0.0, min(1.0, confidence))
        rationale = (
            str(parsed.get("rationale", "")).strip()
            or f"LLM 改写：{intent.value}"
        )
        return ExtractedIntent(
            intent=intent,
            confidence=confidence,
            method="llm",
            matched_keywords=rule_result.matched_keywords,
            rationale=rationale,
        )

    def extract_sync(self, text: str) -> ExtractedIntent:
        """同步提取（仅规则引擎）。Phase 1 LLM 增强默认不阻塞主线程。

        参数：
            text: 用户原始文本
        返回：
            ``ExtractedIntent``（method="rule"）
        """
        return _rule_extract(text)


__all__ = [
    "ExtractedIntent",
    "Intent",
    "IntentExtractor",
    "build_llm_messages_for_intent",
]

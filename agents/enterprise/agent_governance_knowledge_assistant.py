"""Enterprise Agent Governance Knowledge Assistant Layer（Phase 3.8.24）。

链路：**用户问题 → 治理知识检索 → 案例匹配 → 上下文构建 → 事实摘要 → 人工使用**。

本层建立在 3.8.23 治理知识检索与辅助学习层之上，是面向「真实人工提出治理问题」的
**问答型辅助**入口：把人的自然语言问题结构化，复用 3.8.23 的只读相似检索引擎
（``GovernanceSimilarityMatcher``）做案例 / 模式 / 知识 / 事件匹配，组装**只辅助分析**
的上下文与**纯事实型**答案草稿，最终只能由**真实人工**确认怎么用。

新增（任务1–7）：
- ``GovernanceAssistantQuery``：助手层检索请求（query_id / user_id / org_id /
  question / filters / created_at）。**权限隔离**：``user_id`` / ``org_id`` 缺失即拒绝；
  发起人必须是真实人类标识；``filters`` 不得夹带越权键；``question`` 命中「自动改知识 /
  自动应用经验 / 自动生成策略」语义即拒绝（任务1，红线③/④/⑤/⑥）。
- ``GovernanceAssistantContext``：助手层辅助上下文（cases / patterns /
  knowledge_candidates / related_events / source_chain）。**只辅助分析**：
  ``is_advisory_only`` 恒为 True；无来源链即拒绝；上下文不含任何处置结论（任务2）。
- ``GovernanceAssistantAgent``：助手编排服务（任务3）。``understand_query()`` 把问题
  结构化为 3.8.23 检索请求；``retrieve_context()`` 复用检索引擎攒上下文；
  ``build_summary()`` 产出**纯事实**答案草稿。**禁止生成治理建议**：所有 AI 产出文本
  经语义拦截，``GovernanceAnswerDraft.contains_recommendation`` 恒为 False（红线⑥）。
- ``GovernanceAnswerDraft``：助手答案草稿（answer_id / query_id / facts /
  references / confidence / requires_human_review）。**引用来源**：每条事实都对应可溯源
  引用；``requires_human_review`` 恒为 True；结构上不存在 recommendation / action /
  policy 字段（任务4，红线④/⑤/⑥）。
- ``GovernanceAssistantReview``：人工确认节点（任务5）。**禁止 AI 确认答案**：
  构造即强制 ``reviewer_kind == USER`` 且 ``confirm_answer`` 强制
  ``require_human_actor(USER)``，``record_human_approval`` / ``auto_approve`` 被结构性
  拦截（红线②/⑥）。

红线（fail-closed，复用 3.8.0~3.8.23 基座 + Phase 3.8.24 主理人六条）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved（forbidden 方法名结构性拦截）。
③ 不 AI 自动修改知识（``auto_update_knowledge`` / ``auto_merge_knowledge`` 及同族
   方法名被 mixin 拦截；问题 / 上下文 / 答案文本命中自动改知识语义即拒绝）。
④ 不 AI 自动应用治理经验（``auto_apply_knowledge`` / ``auto_execute_knowledge``
   及同族被拦截；助手产出**永远只是草稿**，``requires_human_review`` 恒为 True，
   不存在任何"应用/执行/落地"路径；文本命中应用经验语义即拒绝）。
⑤ 不 AI 自动生成治理策略（``generate_policy`` / ``recommend_policy`` 及同族被拦截；
   本层输出物中**不存在** policy 类型枚举，``GovernanceAnswerDraft`` 结构上无法承载
   策略；文本命中生成策略语义即拒绝）。
⑥ 不 AI 代替治理责任人（审计禁止 ``record_human_approval``；答案草稿禁止出现任何
   建议 / 责任判定语义；``confirm_answer`` 强制 ``require_human_actor(USER)``；
   AI 产出只陈述事实与来源，不含处置指令）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.agent_governance_knowledge_retrieval import (
    GovernanceKnowledgeQuery,
    GovernanceMatchCandidate,
    GovernanceMatchKind,
    GovernanceSimilarityMatcher,
    _ADVICE_MARKERS,
    _KNOWLEDGE_APPLY_MARKERS,
    _KNOWLEDGE_MUTATION_MARKERS,
    _NON_HUMAN_ACTORS,
    _POLICY_GENERATION_MARKERS,
    _RETRIEVAL_FORBIDDEN,
    _looks_non_human,
    _reject_advice_markers,
    _reject_markers,
    _reject_non_human,
    _reject_retrieval_markers,
    _similarity,
    _tokenize,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_security_risk import SourceTrace
from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# forbidden 方法名（红线②/③/④/⑤/⑥，结构上不可达）
# ---------------------------------------------------------------------------

# 复用 3.8.23 检索层 forbidden 全集（已覆盖基座 + knowledge/experience/policy/责任人族），
# 再叠加助手层专属：禁止 AI 自动确认 / 自动作答 / 代替责任人下结论。
_ASSISTANT_FORBIDDEN = _RETRIEVAL_FORBIDDEN + (
    # 助手层专属：禁止 AI 自动确认答案 / 自动作答 / 自动代替责任人下结论
    "auto_confirm",
    "auto_answer",
    "auto_generate_answer",
    "auto_review_answer",
    "auto_approve_answer",
    "confirm_answer_automatically",
    "answer_automatically",
    "auto_conclude_answer",
    "auto_decide_answer",
    "assistant_approve",
    # 红线⑤：禁止 AI 自动生成治理策略（generate_policy / recommend_policy 同族）
    "recommend_policy",
    "auto_recommend",
)


# ``filters`` 中禁止出现的越权键（红线⑥：不得靠 filter 绕过组织/权限隔离）。
_FORBIDDEN_FILTER_KEYS = (
    "org_id",
    "organization_id",
    "tenant_id",
    "all_orgs",
    "cross_org",
    "bypass_permission",
    "ignore_permission",
    "skip_permission",
    "as_user",
    "impersonate",
    "override_scope",
)

# ``filters`` 允许的键（白名单，默认拒绝未知键）。
_ALLOWED_FILTER_KEYS = (
    "agent_id",
    "knowledge_type",
    "pattern_kind",
    "case_id",
    "time_from",
    "time_to",
    "top_k",
    "min_similarity",
)


# ---------------------------------------------------------------------------
# 任务1：助手层检索请求（权限隔离）
# ---------------------------------------------------------------------------


@dataclass
class GovernanceAssistantQuery:
    """助手层治理知识检索请求（任务1，**权限隔离**）。

    字段严格对应主理人要求：``query_id`` / ``user_id`` / ``org_id`` / ``question`` /
    ``filters`` / ``created_at``。

    权限隔离（红线⑥）：
    - ``user_id`` 为空即拒绝：检索必须能追溯到真实发起人；
    - ``user_id`` 命中 ai / system / bot / agent / auto 等非人类标识即拒绝：
      治理知识助手是**人在问**，AI 不得以自己的名义发起问题；
    - ``org_id`` 为空即拒绝：无组织归属的检索无法做隔离，一律拒绝；
    - ``filters`` 不得夹带 ``org_id`` / ``cross_org`` / ``bypass_permission`` 等
      越权键（结构上堵死"用 filter 绕隔离"）；未知键一律拒绝（白名单）。

    只读语义（红线③/④/⑤）：
    - ``question`` 命中「自动改知识 / 自动应用经验 / 自动生成策略」语义即拒绝 ——
      提问本身不得要求 AI 去改、去用、去生成；
    - 本类**不提供**任何 apply / execute / update / generate / answer 方法，
      问题只是一个只读的自然语言描述，不是一条指令。
    """

    query_id: str
    user_id: str
    org_id: str
    question: str
    filters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAssistantQuery（红线①）"
            )
        self.query_id = str(self.query_id).strip()
        self.user_id = str(self.user_id).strip()
        self.org_id = str(self.org_id).strip()
        self.question = str(self.question).strip()
        self.created_at = str(self.created_at).strip()

        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceAssistantQuery 缺少 query_id：禁止匿名问题（红线⑥）"
            )
        if not self.user_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantQuery {self.query_id!r} 缺少 user_id："
                f"治理知识助手问题必须可追溯到真实发起人（红线⑥）"
            )
        _reject_non_human(
            self.user_id,
            ctx=f"GovernanceAssistantQuery {self.query_id!r} 的 user_id",
        )
        if not self.org_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantQuery {self.query_id!r} 缺少 org_id："
                f"无组织归属的治理知识问题无法隔离，默认拒绝（红线⑥）"
            )
        if not self.question:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantQuery {self.query_id!r} 缺少 question："
                f"禁止空问题（会退化成全量拉取，破坏最小必要原则，红线⑥）"
            )

        if not isinstance(self.filters, dict):
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantQuery {self.query_id!r} 的 filters 必须是 dict"
            )
        normalized: Dict[str, Any] = {}
        for key, value in self.filters.items():
            name = str(key).strip().lower()
            if name in _FORBIDDEN_FILTER_KEYS:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceAssistantQuery {self.query_id!r} 的 filters 含越权键 "
                    f"{key!r}：禁止通过过滤条件绕过组织 / 权限隔离（红线⑥）"
                )
            if name not in _ALLOWED_FILTER_KEYS:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceAssistantQuery {self.query_id!r} 的 filters 含未知键 "
                    f"{key!r}：过滤条件采用白名单，未知键默认拒绝"
                    f"（允许键：{','.join(_ALLOWED_FILTER_KEYS)}）"
                )
            normalized[name] = value
            _reject_retrieval_markers(
                f"{name}={value}",
                ctx=f"GovernanceAssistantQuery {self.query_id!r} 的 filters[{key!r}]",
            )
        self.filters = normalized

        _reject_retrieval_markers(
            self.question,
            ctx=f"GovernanceAssistantQuery {self.query_id!r} 的 question",
        )

    @property
    def is_human_initiated(self) -> bool:
        """是否由真实人工发起（构造期已强制为 True，此处只读复述事实）。"""
        return bool(self.user_id) and not _looks_non_human(self.user_id)

    @property
    def scope_key(self) -> str:
        """只读隔离键（org + user），供上层做租户隔离审计。"""
        return f"{self.org_id}:{self.user_id}"

    def top_k(self, default: int = 5) -> int:
        """只读取出 top_k（非法值回落默认，绝不放大到全量）。"""
        raw = self.filters.get("top_k", default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if value <= 0:
            return default
        return min(value, 50)

    def min_similarity(self, default: float = 0.0) -> float:
        """只读取出最小相似度阈值（非法值回落默认）。"""
        raw = self.filters.get("min_similarity", default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        if value < 0.0 or value > 1.0:
            return default
        return value

    def summary(self) -> str:
        """只读摘要（只陈述"谁在什么范围里问了什么"，不含任何结论）。"""
        return (
            f"query={self.query_id} org={self.org_id} user={self.user_id} "
            f"filters={len(self.filters)} advisory_only=true"
        )


# ---------------------------------------------------------------------------
# 任务2：助手层辅助上下文（只辅助分析）
# ---------------------------------------------------------------------------


@dataclass
class GovernanceAssistantContext:
    """助手层辅助上下文（任务2，**只辅助分析**）。

    字段：cases / patterns / knowledge_candidates / related_events / source_chain。

    只辅助分析（红线④/⑥）：
    - ``is_advisory_only`` 恒为 True，置 False 即拒绝 —— 这份上下文只是
      "摆给人看的材料"，不是可执行输入；
    - ``source_chain`` 缺失或不可溯源即拒绝：无源材料不得进入人工判断视野；
    - 上下文内所有条目都是 ``GovernanceMatchCandidate``（已强校验
      ``requires_human_use=True`` + ``source_ref``），结构上不可能夹带
      "已生效结论"；
    - 本类**不提供**任何 apply / execute / adopt / to_policy 方法。
    """

    context_id: str
    query_id: str
    org_id: str = ""
    cases: List[GovernanceMatchCandidate] = field(default_factory=list)
    patterns: List[GovernanceMatchCandidate] = field(default_factory=list)
    knowledge_candidates: List[GovernanceMatchCandidate] = field(default_factory=list)
    related_events: List[GovernanceMatchCandidate] = field(default_factory=list)
    source_chain: "SourceTrace | None" = None
    built_at: str = ""
    is_advisory_only: bool = True

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAssistantContext（红线①）"
            )
        self.context_id = str(self.context_id).strip()
        self.query_id = str(self.query_id).strip()
        self.org_id = str(self.org_id).strip()
        self.built_at = str(self.built_at).strip()

        if not self.context_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceAssistantContext 缺少 context_id"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantContext {self.context_id!r} 缺少 query_id："
                f"辅助上下文必须挂在一条真实问题之上（红线⑥）"
            )
        if self.is_advisory_only is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantContext {self.context_id!r} 拒绝 "
                f"is_advisory_only=False：本层产出只能辅助人工分析，"
                f"不得转为可执行治理输入（红线④/⑥）"
            )
        if self.source_chain is None or not self.source_chain.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantContext {self.context_id!r} 无来源链："
                f"辅助材料必须强可溯源（红线⑥）"
            )
        for label, bucket in (
            ("cases", self.cases),
            ("patterns", self.patterns),
            ("knowledge_candidates", self.knowledge_candidates),
            ("related_events", self.related_events),
        ):
            for item in bucket:
                if not isinstance(item, GovernanceMatchCandidate):
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceAssistantContext {self.context_id!r} 的 {label} "
                        f"含非法条目：只接受 GovernanceMatchCandidate"
                        f"（禁止塞入未经红线校验的对象）"
                    )
                if item.requires_human_use is not True:
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceAssistantContext {self.context_id!r} 的 {label} "
                        f"含非候选条目 {item.candidate_id!r}（红线④）"
                    )

    @property
    def total_items(self) -> int:
        """只读条目总数。"""
        return (
            len(self.cases)
            + len(self.patterns)
            + len(self.knowledge_candidates)
            + len(self.related_events)
        )

    @property
    def is_empty(self) -> bool:
        """只读：是否检索不到任何材料（空也如实呈现，绝不编造凑数）。"""
        return self.total_items == 0

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.source_chain is not None and self.source_chain.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链。"""
        return self.source_chain.render() if self.source_chain else "no_source"

    def all_candidates(self) -> List[GovernanceMatchCandidate]:
        """只读汇总全部候选（新列表，不暴露内部可变引用）。"""
        return [
            *self.cases,
            *self.patterns,
            *self.knowledge_candidates,
            *self.related_events,
        ]

    def summary(self) -> str:
        """只读摘要（**只统计事实，不含任何结论或倾向**）。"""
        return (
            f"context={self.context_id} query={self.query_id} "
            f"cases={len(self.cases)} patterns={len(self.patterns)} "
            f"knowledge={len(self.knowledge_candidates)} "
            f"events={len(self.related_events)} "
            f"advisory_only=true traceable={self.is_traceable}"
        )


# ---------------------------------------------------------------------------
# 任务4：助手层答案草稿（引用来源，禁止建议）
# ---------------------------------------------------------------------------


@dataclass
class GovernanceAnswerDraft:
    """助手层答案草稿（任务4，**引用来源，禁止治理建议**）。

    字段严格对应主理人要求：answer_id / query_id / facts / references /
    confidence / requires_human_review。

    引用来源（红线⑥）：``references`` 全部来自 3.8.23 检索候选 ``source_ref``，
    每条事实都可被追溯；无命中时如实回落到 ``query:<id>``，绝不编造引用。

    禁止治理建议（红线⑥，本任务核心）：
    - ``facts`` / ``summary`` 全部经 ``_reject_advice_markers`` 与
      ``_reject_retrieval_markers``：命中 recommend / suggest / 建议 / 应当整改 /
      应立即 / 判定责任 或自动改知识 / 应用经验 / 生成策略语义即拒绝生成；
    - ``contains_recommendation`` 恒为 False，且是**计算属性**，无法被外部赋值伪造；
    - 草稿结构里**不存在** ``recommendation`` / ``action`` / ``policy`` 字段，
      即便有人想塞建议也无处可放（结构级堵死）；
    - ``requires_human_review`` 恒为 True：草稿永远是待人工审阅的材料，不是结论。

    置信度（确定性，非模型判断）：``confidence`` 是匹配相似度与来源覆盖度的**确定性
    函数**，可复现、可解释，绝不冒充"模型判断"（红线⑥：AI 不替人下结论）。
    """

    answer_id: str
    query_id: str
    facts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    confidence: float = 0.0
    requires_human_review: bool = True
    summary: str = ""
    org_id: str = ""
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAnswerDraft（红线①）"
            )
        self.answer_id = str(self.answer_id).strip()
        self.query_id = str(self.query_id).strip()
        self.org_id = str(self.org_id).strip()
        self.summary = str(self.summary).strip()
        self.generated_at = str(self.generated_at).strip()
        self.facts = [str(f).strip() for f in self.facts if str(f).strip()]
        self.references = [str(r).strip() for r in self.references if str(r).strip()]

        if not self.answer_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceAnswerDraft 缺少 answer_id"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAnswerDraft {self.answer_id!r} 缺少 query_id："
                f"答案草稿必须挂在一条真实问题之上（红线⑥）"
            )
        if self.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAnswerDraft {self.answer_id!r} 拒绝 "
                f"requires_human_review=False：助手答案永远是待人工审阅的材料，"
                f"不得转为已采纳结论（红线④/⑥）"
            )
        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAnswerDraft {self.answer_id!r} 的 confidence 非法"
            ) from exc
        if not (0.0 <= self.confidence <= 1.0):
            raise EnterpriseRedLineViolationError(
                f"GovernanceAnswerDraft {self.answer_id!r} 的 confidence "
                f"{self.confidence} 越界：置信度必须是 [0,1] 的确定性事实值"
            )

        # 任务4 核心：AI 产出文本三层语义拦截（③/④/⑤ + ⑥ 建议）。
        for idx, fact in enumerate(self.facts):
            fact_ctx = (
                f"GovernanceAnswerDraft {self.answer_id!r} 的 facts[{idx}]"
            )
            _reject_retrieval_markers(fact, ctx=fact_ctx)
            _reject_advice_markers(fact, ctx=fact_ctx)
        ctx = f"GovernanceAnswerDraft {self.answer_id!r} 的 summary"
        _reject_retrieval_markers(self.summary, ctx=ctx)
        _reject_advice_markers(self.summary, ctx=ctx)

    @property
    def contains_recommendation(self) -> bool:
        """恒为 False：本草稿结构上与语义上都不承载治理建议（红线⑥）。

        写成计算属性而非字段，是为了让"草稿里有没有建议"这件事**不可被赋值伪造**。
        """
        return False

    @property
    def is_advisory_only(self) -> bool:
        """恒为 True：草稿只辅助人工分析（红线④）。"""
        return True

    @property
    def is_traceable(self) -> bool:
        """只读：草稿是否带有可溯源引用（无命中时回落 query 引用仍为真）。"""
        return bool(self.references)

    def render_references(self) -> str:
        """只读渲染来源引用（逗号分隔）。"""
        return ",".join(self.references) if self.references else "no_source"

    def render(self) -> str:
        """只读渲染草稿全文（**纯事实 + 来源，无任何处置指向**）。"""
        lines = [
            f"# 治理知识助手答案草稿 {self.answer_id}",
            f"query={self.query_id} org={self.org_id or 'n/a'}",
            f"confidence={self.confidence} requires_human_review=true",
            f"references={self.render_references()}",
            "",
            "## 事实摘要",
            self.summary or "(无)",
        ]
        if self.facts:
            lines.append("")
            lines.append("## 事实条目")
            lines.extend(f"- {fact}" for fact in self.facts)
        lines.append("")
        lines.append(
            "## 使用说明\n"
            "本草稿仅为辅助分析材料：只呈现相似历史事实与来源，"
            "不含治理建议、不含处置指令、不含责任判定、不含治理策略。"
            "如何使用由真实治理责任人自行判断并留痕。"
        )
        return "\n".join(lines)

    def summary(self) -> str:
        """只读摘要（只陈述事实规模与可溯源性）。"""
        return (
            f"answer={self.answer_id} query={self.query_id} "
            f"facts={len(self.facts)} references={len(self.references)} "
            f"confidence={self.confidence} requires_human_review=true "
            f"contains_recommendation=false advisory_only=true"
        )


# ---------------------------------------------------------------------------
# 任务5：人工确认节点（禁止 AI 确认答案）
# ---------------------------------------------------------------------------


class AssistantReviewDecision(str, Enum):
    """人工确认结论（**刻意不含 approve / applied / adopted** 这类"已生效"语义）。

    助手答案草稿经真实人工确认后，只是"人看了、人自己去处理了"这一事实留痕；
    三种结论都不会让草稿变成治理动作（红线④/⑥）。
    """

    ACKNOWLEDGED = "acknowledged"   # 真实人工已阅知并自行处理
    REJECTED = "rejected"           # 人工判断本答案不适用 / 需另行处理
    NEEDS_MORE = "needs_more"       # 人工要求补充材料 / 重新检索


@dataclass
class GovernanceAssistantReview:
    """治理知识助手答案人工确认节点（任务5，**禁止 AI 确认**）。

    字段：review_id / answer_id / query_id / reviewer_id / reviewer_kind /
    decision / reviewed_at / note。

    禁止 AI 确认答案（红线②/⑥）：
    - 构造即强制 ``reviewer_kind == USER``，否则拒绝（即便直接 new 也无法伪造
      非人类确认）；
    - ``reviewer_id`` 命中非人类标识即拒绝；
    - ``decision`` 只接受 ``AssistantReviewDecision``（不含 approve / applied）；
    - ``note`` 命中自动改知识 / 应用经验 / 生成策略 / 建议语义即拒绝；
    - 本类**不提供** approve / auto_approve / record_human_approval / apply 方法。
    """

    review_id: str
    answer_id: str
    query_id: str
    reviewer_id: str
    reviewer_kind: str
    decision: AssistantReviewDecision
    reviewed_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAssistantReview（红线①）"
            )
        self.review_id = str(self.review_id).strip()
        self.answer_id = str(self.answer_id).strip()
        self.query_id = str(self.query_id).strip()
        self.reviewer_id = str(self.reviewer_id).strip()
        self.reviewer_kind = str(self.reviewer_kind).strip()
        self.reviewed_at = str(self.reviewed_at).strip()
        self.note = str(self.note).strip()

        if not self.review_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceAssistantReview 缺少 review_id"
            )
        if not self.answer_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantReview {self.review_id!r} 缺少 answer_id："
                f"人工确认必须挂在一条真实答案草稿之上（红线⑥）"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantReview {self.review_id!r} 缺少 query_id"
            )
        if self.reviewer_kind != AuditActorKind.USER.value:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistantReview {self.review_id!r} 拒绝非人工确认："
                f"reviewer_kind 必须是 {AuditActorKind.USER.value!r}，"
                f"禁止 AI 代替治理责任人确认答案（红线⑥）"
            )
        _reject_non_human(
            self.reviewer_id,
            ctx=f"GovernanceAssistantReview {self.review_id!r} 的 reviewer_id",
        )
        if not isinstance(self.decision, AssistantReviewDecision):
            try:
                self.decision = AssistantReviewDecision(str(self.decision))
            except (TypeError, ValueError) as exc:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceAssistantReview {self.review_id!r} 的 decision "
                    f"非法：只接受 AssistantReviewDecision"
                ) from exc
        note_ctx = f"GovernanceAssistantReview {self.review_id!r} 的 note"
        _reject_retrieval_markers(self.note, ctx=note_ctx)
        _reject_advice_markers(self.note, ctx=note_ctx)

    @property
    def is_human_confirmed(self) -> bool:
        """是否由真实人工确认（构造期已强制为 True）。"""
        return self.reviewer_kind == AuditActorKind.USER.value and (
            not _looks_non_human(self.reviewer_id)
        )

    def summary(self) -> str:
        """只读摘要（只陈述"谁在何时确认了哪份草稿"，不含任何动作语义）。"""
        return (
            f"review={self.review_id} answer={self.answer_id} "
            f"reviewer={self.reviewer_id} decision={self.decision.value} "
            f"human_confirmed=true"
        )


# ---------------------------------------------------------------------------
# 助手流程阶段机（只前进不回退，唯一终态 HUMAN_USED）
# ---------------------------------------------------------------------------


class GovernanceAssistantStage(str, Enum):
    """助手辅助流程阶段（**不存在任何"已应用/已生效"终态**，红线④）。"""

    QUERY_UNDERSTOOD = "query_understood"
    CONTEXT_RETRIEVED = "context_retrieved"
    SUMMARY_BUILT = "summary_built"
    REVIEWED = "reviewed"
    HUMAN_USED = "human_used"


_ALLOWED_ASSISTANT_TRANSITIONS: Dict[
    GovernanceAssistantStage, "tuple[GovernanceAssistantStage, ...]"
] = {
    GovernanceAssistantStage.QUERY_UNDERSTOOD: (GovernanceAssistantStage.CONTEXT_RETRIEVED,),
    GovernanceAssistantStage.CONTEXT_RETRIEVED: (GovernanceAssistantStage.SUMMARY_BUILT,),
    GovernanceAssistantStage.SUMMARY_BUILT: (GovernanceAssistantStage.REVIEWED,),
    GovernanceAssistantStage.REVIEWED: (GovernanceAssistantStage.HUMAN_USED,),
    GovernanceAssistantStage.HUMAN_USED: (),
}


# ---------------------------------------------------------------------------
# 任务3：助手编排服务（understand_query / retrieve_context / build_summary）
# ---------------------------------------------------------------------------


class GovernanceAssistantAgent(_RedLineForbiddenMixin):
    """治理知识助手编排服务（任务3，**只生成事实摘要，禁止治理建议**）。

    承载链路：**用户问题 → 治理知识检索 → 案例匹配 → 上下文构建 → 事实摘要 → 人工使用**。

    方法边界：
    - ``understand_query``：**AI 可代做**，把助手层问题结构化为 3.8.23 检索请求
      （``user_id`` 必须是真实人类且经权限校验，红线⑥）；
    - ``retrieve_context``：复用 3.8.23 ``GovernanceSimilarityMatcher`` 做只读相似检索，
      攒成**只辅助分析**的 ``GovernanceAssistantContext``；
    - ``build_summary``：从上下文产出**纯事实** ``GovernanceAnswerDraft``
      （``requires_human_review`` 恒 True，``contains_recommendation`` 恒 False），
      文本经三层语义拦截（红线③/④/⑤/⑥）；
    - ``confirm_answer``：**强制 ``require_human_actor(USER)``** —— 只有真实人工
      能确认草稿，AI 无论如何无法自称"已确认答案"（红线④/⑥）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - **不改知识**：对 3.8.22 知识层 / 3.8.23 检索层**纯只读**（红线③）。
    - **不用经验**：草稿 ``requires_human_review`` 恒 True，无任何 apply /
      execute 路径；阶段机里不存在"已应用"终态（红线④）。
    - **不生策略**：本层无 policy 类型、无 policy 字段、无 policy 方法（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_update_knowledge / auto_merge_knowledge /
      auto_apply_knowledge / auto_execute_knowledge / generate_policy /
      auto_recommend / auto_confirm / auto_answer 等方法。
    """

    _FORBIDDEN = _ASSISTANT_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
        knowledge_service: "Any | None" = None,
        governance_workflow: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAssistantAgent（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        # 只读使用：仅用于访问校验，绝不写任何权限或策略（红线③/⑤）。
        self._permission_policy = permission_policy
        # 只读消费 3.8.22 治理知识事实 / 3.8.21 治理流程事实（红线③）。
        self._knowledge_service = knowledge_service
        self._governance_workflow = governance_workflow
        # 复用 3.8.23 只读相似检索引擎（不重复造轮子，保证匹配语义一致）。
        self._matcher = GovernanceSimilarityMatcher(
            knowledge_service=knowledge_service,
            governance_workflow=governance_workflow,
        )
        self._queries: Dict[str, GovernanceAssistantQuery] = {}
        self._contexts: Dict[str, GovernanceAssistantContext] = {}
        self._drafts: Dict[str, GovernanceAnswerDraft] = {}
        self._reviews: Dict[str, GovernanceAssistantReview] = {}
        self._stages: Dict[str, GovernanceAssistantStage] = {}
        self._human_usages: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(
        self, *, user: object, resource_category: str = "knowledge"
    ) -> None:
        """治理知识助手访问权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误
        （红线⑥：治理知识受控访问、跨组织隔离）。**

        本方法**只读校验**，绝不修改任何权限或策略（红线③/⑤）。
        """
        from agents.enterprise.organization import EnterpriseIsolationError

        if self._permission_policy is not None:
            allowed = self._permission_policy.check_agent_access(
                user=user,
                resource_category=resource_category,
                required_permission=Permission.READ_RESOURCE,
            )
            if not allowed:
                raise EnterpriseIsolationError(
                    f"用户角色无权限访问 Agent 治理知识助手数据"
                    f"（resource={resource_category}），默认拒绝"
                )
        elif self._identity is not None:
            if not (
                hasattr(user, "role")
                and self._identity.check(user, Permission.READ_RESOURCE)
            ):
                raise EnterpriseIsolationError(
                    "无 AgentPermissionPolicy 时，需经身份层 READ_RESOURCE 校验，默认拒绝"
                )

    def _ensure_org_scope(self, org_id: str, *, op: str) -> None:
        """组织隔离：请求 org 必须与服务实例 org 一致（红线⑥）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        target = str(org_id).strip()
        if self._org_id and target and target != self._org_id:
            raise EnterpriseIsolationError(
                f"{op} 拒绝跨组织访问：请求 org_id={target!r} 与服务 org_id="
                f"{self._org_id!r} 不一致，治理知识默认按组织隔离"
            )

    def _ensure_knowledge_visible(self, *, user: object, op: str) -> None:
        """知识可见性校验（``KnowledgeVisibilityPolicy`` 存在时生效，默认拒绝）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        policy = self._visibility
        if policy is None:
            return
        checker = getattr(policy, "can_read", None)
        if not callable(checker):
            return
        if not checker(user):
            raise EnterpriseIsolationError(
                f"{op} 拒绝访问：知识可见性策略未授予该用户治理知识读权限，默认拒绝"
            )

    # ------------------------------------------------------------------
    # 阶段机（只前进不回退）
    # ------------------------------------------------------------------

    def _advance_stage(
        self, query_id: str, target: GovernanceAssistantStage, *, op: str
    ) -> None:
        """推进助手辅助流程阶段（非法迁移直接拒绝）。"""
        current = self._stages.get(query_id)
        if current is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 问题 {query_id!r} 尚无流程阶段："
                f"禁止跳过 query_understood（红线⑥）"
            )
        if target not in _ALLOWED_ASSISTANT_TRANSITIONS.get(current, ()):
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把助手流程 {query_id!r} 从 {current.value} 迁移到 "
                f"{target.value}：非法阶段迁移（只能逐步推进，且最后两步必须由真实人工"
                f"执行，红线④/⑥）"
            )
        self._stages[query_id] = target

    def stage_of(self, query_id: str) -> "GovernanceAssistantStage | None":
        """只读查询某次问题当前阶段（不改动任何状态）。"""
        return self._stages.get(query_id)

    def _get_query_or_raise(
        self, query_id: str, *, op: str
    ) -> GovernanceAssistantQuery:
        """只读取出问题，不存在即拒绝（禁止凭空推进流程）。"""
        query = self._queries.get(query_id)
        if query is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到问题 {query_id!r}：禁止凭空推进助手流程（红线⑥）"
            )
        return query

    def _get_draft_or_raise(
        self, answer_id: str, *, op: str
    ) -> GovernanceAnswerDraft:
        """只读取出答案草稿，不存在即拒绝（禁止凭空确认）。"""
        draft = self._drafts.get(answer_id)
        if draft is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到答案草稿 {answer_id!r}：禁止对不存在的草稿确认（红线⑥）"
            )
        return draft

    # ------------------------------------------------------------------
    # 任务1 入口：提交问题
    # ------------------------------------------------------------------

    def submit_query(
        self,
        *,
        query_id: str,
        user_id: str,
        question: str,
        org_id: str = "",
        filters: "Dict[str, Any] | None" = None,
        created_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceAssistantQuery:
        """登记一次助手层治理知识问题（**权限隔离**，任务1/7）。

        AI 可以代为提交（只是把人的问题结构化），但：
        - ``user_id`` 必须是真实人类标识，AI 不得以自己的名义提问（红线⑥）；
        - ``org_id`` 必须与服务实例组织一致，跨组织一律拒绝（红线⑥）；
        - ``filters`` 走白名单 + 越权键黑名单，禁止靠过滤条件绕隔离（红线⑥）；
        - ``question`` 命中自动改知识 / 自动应用经验 / 自动生成策略语义即拒绝
          （红线③/④/⑤）。
        """
        op = "submit_query"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        target_org = str(org_id).strip() or self._org_id
        self._ensure_org_scope(target_org, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        query = GovernanceAssistantQuery(
            query_id=query_id,
            user_id=user_id,
            org_id=target_org,
            question=question,
            filters=dict(filters or {}),
            created_at=created_at,
        )
        if query.query_id in self._queries:
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝重复登记问题 {query.query_id!r}"
            )
        self._queries[query.query_id] = query
        self._stages[query.query_id] = GovernanceAssistantStage.QUERY_UNDERSTOOD

        if self._audit is not None:
            self._audit.record_agent_governance_assistant_query_action(
                record_id=f"gaq-{query.query_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="submit_assistant_query",
                target=query.query_id,
                detail=query.summary(),
            )
        return query

    # ------------------------------------------------------------------
    # 任务3-①：understand_query（问题 → 3.8.23 检索请求，只读结构化）
    # ------------------------------------------------------------------

    def understand_query(
        self,
        query: GovernanceAssistantQuery,
        *,
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceKnowledgeQuery:
        """把助手层问题**只读**结构化为 3.8.23 检索请求（任务3-①）。

        不做任何语义理解 / 不做 LLM 调用：仅把 ``question`` 映射为检索 ``query_text``，
        把 ``filters`` 原样透传，并复用 3.8.23 ``GovernanceKnowledgeQuery`` 的强校验
        （权限隔离 / 红线③/④/⑤）。返回的对象即后续检索引擎的输入。
        """
        op = "understand_query"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        if not isinstance(query, GovernanceAssistantQuery):
            raise EnterpriseRedLineViolationError(
                "understand_query 只接受 GovernanceAssistantQuery"
                "（禁止绕过权限隔离校验）"
            )
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        # 复用 3.8.23 检索请求的强校验（权限隔离 + 红线语义拦截）。
        retrieval_query = GovernanceKnowledgeQuery(
            query_id=query.query_id,
            user_id=query.user_id,
            org_id=query.org_id,
            query_text=query.question,
            filters=dict(query.filters),
            created_at=query.created_at,
        )
        return retrieval_query

    # ------------------------------------------------------------------
    # 任务3-②：retrieve_context（复用 3.8.23 检索引擎攒上下文）
    # ------------------------------------------------------------------

    def retrieve_context(
        self,
        query: GovernanceAssistantQuery,
        *,
        context_id: str = "",
        built_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceAssistantContext:
        """复用 3.8.23 只读相似检索引擎，攒成**只辅助分析**的上下文（任务3-②/任务2）。

        检索范围 = 3.8.22 治理案例 + 事实模式 + **已人工采纳**的知识候选
        + 3.8.21 **已人工闭环**的治理事件。全部只读，绝不写回。
        """
        op = "retrieve_context"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        if not isinstance(query, GovernanceAssistantQuery):
            raise EnterpriseRedLineViolationError(
                "retrieve_context 只接受 GovernanceAssistantQuery"
                "（禁止绕过权限隔离校验）"
            )
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        retrieval_query = self.understand_query(query, user=user)
        cases = self._matcher.match_cases(retrieval_query)
        patterns = self._matcher.match_patterns(retrieval_query)
        knowledge = self._matcher.match_knowledge(retrieval_query)
        events = self._matcher.find_related_events(retrieval_query)
        candidates = [*cases, *patterns, *knowledge, *events]

        # 惰性登记：若问题此前未经过 submit_query，则 understand_query 已校验通过，
        # 等价于"问题已被理解"，补置 QUERY_UNDERSTOOD 阶段（不跳过红线⑥：
        # 必须先 understood 才可 retrieved）。
        if query.query_id not in self._stages:
            self._stages[query.query_id] = GovernanceAssistantStage.QUERY_UNDERSTOOD
        if query.query_id not in self._queries:
            self._queries[query.query_id] = query

        sources = sorted({c.source_ref for c in candidates})
        trace = SourceTrace(trace_id=f"a-ctx-trace-{query.query_id}")
        trace.add_entry(f"query:{query.query_id}")
        for ref in sources:
            trace.add_entry(ref)
        if not sources:
            sources = [f"query:{query.query_id}"]

        context = GovernanceAssistantContext(
            context_id=str(context_id).strip() or f"actx-{query.query_id}",
            query_id=query.query_id,
            org_id=query.org_id,
            cases=cases,
            patterns=patterns,
            knowledge_candidates=knowledge,
            related_events=events,
            source_chain=trace,
            built_at=built_at,
            is_advisory_only=True,
        )
        self._contexts[context.context_id] = context
        self._advance_stage(
            query.query_id, GovernanceAssistantStage.CONTEXT_RETRIEVED, op=op
        )

        if self._audit is not None:
            self._audit.record_agent_governance_assistant_context_action(
                record_id=f"gac-{context.context_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="retrieve_assistant_context",
                target=context.context_id,
                detail=context.summary(),
            )
        return context

    # ------------------------------------------------------------------
    # 任务3-③：build_summary（上下文 → 纯事实答案草稿）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(context: GovernanceAssistantContext) -> float:
        """确定性置信度（**非模型判断**，可复现可解释，红线⑥）。

        只由候选相似度的均值与来源覆盖度决定，绝不冒充"模型判断"，
        也不随输入以外的任何随机因素影响。
        """
        cands = context.all_candidates()
        if not cands:
            return 0.0
        avg = sum(c.similarity for c in cands) / len(cands)
        kinds = {c.match_kind for c in cands}
        coverage = min(len(kinds), 4) / 4.0
        return round(min(avg * (0.6 + 0.4 * coverage), 1.0), 6)

    def build_summary(
        self,
        context: GovernanceAssistantContext,
        *,
        answer_id: str = "",
        generated_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceAnswerDraft:
        """从上下文产出**纯事实**答案草稿（任务3-③/任务4）。

        摘要由**模板化事实句**生成（数量 / 相似度区间 / 来源），不引用任何案例的
        人工处置结论原文 —— 一旦把"别人当时怎么处理的"搬进摘要，草稿实质就变成处置
        建议（红线⑥）。
        """
        op = "build_summary"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        if not isinstance(context, GovernanceAssistantContext):
            raise EnterpriseRedLineViolationError(
                "build_summary 只接受 GovernanceAssistantContext"
                "（禁止绕过红线校验）"
            )
        self._ensure_org_scope(context.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        query = self._get_query_or_raise(context.query_id, op=op)

        cases = list(context.cases)
        patterns = list(context.patterns)
        knowledge = list(context.knowledge_candidates)
        events = list(context.related_events)

        top_case = cases[0].similarity if cases else 0.0
        top_pattern = patterns[0].similarity if patterns else 0.0
        top_knowledge = knowledge[0].similarity if knowledge else 0.0
        top_event = events[0].similarity if events else 0.0

        # 模板化事实句（无建议、无处置指向）。
        facts: List[str] = []
        facts.append(
            f"检索到相似历史治理案例 {len(cases)} 条"
            f"（最高重合度 {top_case}）"
        )
        facts.append(
            f"检索到相关事实模式 {len(patterns)} 条"
            f"（最高重合度 {top_pattern}）"
        )
        facts.append(
            f"检索到已人工采纳治理知识 {len(knowledge)} 条"
            f"（最高重合度 {top_knowledge}）"
        )
        facts.append(
            f"检索到已闭环相关治理事件 {len(events)} 条"
            f"（最高重合度 {top_event}）"
        )
        if context.is_empty:
            facts = [
                "未检索到可关联的治理知识、案例或事件："
                "当前问题暂无既有事实材料支撑，请真实治理责任人自行补充或调整问法"
            ]

        references = sorted({c.source_ref for c in context.all_candidates()})
        if not references:
            references = [f"query:{context.query_id}"]

        confidence = self._compute_confidence(context)
        summary_text = (
            f"针对该治理问题，检索到相似历史案例 {len(cases)} 条、"
            f"相关事实模式 {len(patterns)} 条、已人工采纳知识 {len(knowledge)} 条、"
            f"已闭环相关事件 {len(events)} 条。"
            f"以上均为只读事实材料，不含处置结论与责任判定。"
        )

        draft = GovernanceAnswerDraft(
            answer_id=str(answer_id).strip() or f"ans-{context.query_id}",
            query_id=context.query_id,
            facts=facts,
            references=references,
            confidence=confidence,
            requires_human_review=True,
            summary=summary_text,
            org_id=context.org_id,
            generated_at=generated_at,
        )
        self._drafts[draft.answer_id] = draft
        self._advance_stage(
            query.query_id, GovernanceAssistantStage.SUMMARY_BUILT, op=op
        )

        if self._audit is not None:
            self._audit.record_agent_governance_assistant_draft_action(
                record_id=f"gad-{draft.answer_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="build_assistant_answer_draft",
                target=draft.answer_id,
                detail=draft.summary,
            )
        return draft

    # ------------------------------------------------------------------
    # 任务5：人工确认节点（红线④/⑥：强制真实人工）
    # ------------------------------------------------------------------

    def confirm_answer(
        self,
        *,
        answer_id: str,
        reviewer_id: str,
        reviewer_kind: Any,
        decision: Any,
        query_id: str = "",
        reviewed_at: str = "",
        note: str = "",
        user: object = None,
        resource_category: str = "knowledge",
    ) -> GovernanceAssistantReview:
        """登记「**真实人工**已确认该助手答案草稿」这一事实（任务5，红线④/⑥）。

        这是本层唯一的人工节点：
        - 强制 ``require_human_actor(USER)``，AI 调用直接抛错；
        - ``reviewer_id`` 命中非人类标识即拒绝；
        - 只登记"人看了、人自己去处理了"这一事实，**不承载任何治理动作**：
          本方法不会、也无法触发禁用 Agent、修改策略、关闭任务等任何操作。
        """
        op = "confirm_answer"
        require_human_actor(reviewer_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        _reject_non_human(reviewer_id, ctx=f"{op} 的 reviewer_id")
        draft = self._get_draft_or_raise(answer_id, op=op)
        self._ensure_org_scope(draft.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)

        qid = str(query_id).strip() or draft.query_id
        if qid != draft.query_id:
            raise EnterpriseRedLineViolationError(
                f"{op} 的 query_id {qid!r} 与草稿 {draft.answer_id!r} 归属的 "
                f"query_id {draft.query_id!r} 不一致：禁止张冠李戴确认（红线⑥）"
            )

        review = GovernanceAssistantReview(
            review_id=f"rev-{answer_id}",
            answer_id=answer_id,
            query_id=qid,
            reviewer_id=reviewer_id,
            reviewer_kind=AuditActorKind.USER.value,
            decision=decision,
            reviewed_at=reviewed_at,
            note=note,
        )
        self._reviews[review.review_id] = review
        self._advance_stage(qid, GovernanceAssistantStage.REVIEWED, op=op)

        if self._audit is not None:
            self._audit.record_agent_governance_assistant_draft_action(
                record_id=f"gad-rev-{answer_id}",
                actor_id=reviewer_id,
                actor_kind=AuditActorKind.USER,
                action="human_confirm_assistant_answer",
                target=answer_id,
                detail=review.summary(),
            )
        return review

    def review_of(self, answer_id: str) -> "GovernanceAssistantReview | None":
        """只读查询某份草稿的人工确认（不改动任何状态）。"""
        for review in self._reviews.values():
            if review.answer_id == answer_id:
                return review
        return None

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def get_query(
        self, query_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceAssistantQuery | None":
        """只读获取某条问题（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._queries.get(query_id)

    def get_context(
        self, context_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceAssistantContext | None":
        """只读获取某份辅助上下文（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._contexts.get(context_id)

    def get_draft(
        self, answer_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceAnswerDraft | None":
        """只读获取某份答案草稿（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._drafts.get(answer_id)

    def list_queries(
        self, *, user: object, resource_category: str = "knowledge"
    ) -> List[GovernanceAssistantQuery]:
        """只读列出本组织内的问题（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return [
            q for q in self._queries.values()
            if not self._org_id or q.org_id == self._org_id
        ]


__all__ = [
    "GovernanceAssistantQuery",
    "GovernanceAssistantContext",
    "GovernanceAnswerDraft",
    "AssistantReviewDecision",
    "GovernanceAssistantReview",
    "GovernanceAssistantStage",
    "GovernanceAssistantAgent",
    "_ASSISTANT_FORBIDDEN",
]

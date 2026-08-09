"""Enterprise Agent Governance Knowledge Retrieval & Learning Assistance Layer（Phase 3.8.23）。

链路：**治理事件 → 历史案例检索 → 知识匹配 → 辅助分析 → 人工使用**。

本层建立在 3.8.13~3.8.22 各治理层之上（能力注册 / 可观测性 / 质量 / 成本 /
运行时策略 / 安全风险 / 合规审计 / 治理中枢 / 治理流程与责任闭环 / 治理知识与
持续改进）：把 3.8.22 已由**真实人工审核沉淀**的治理知识、治理案例与事实模式，
按治理事件语境做**只读相似检索**，产出**辅助分析上下文**与**事实型辅助报告**，
最终只能由**真实人工**决定怎么用。AI 在本层只能「检索事实 → 摆候选 → 摆来源」，
绝不能改知识、绝不能应用经验、绝不能生成治理策略、绝不能代替治理责任人。

新增（任务1–5）：
- ``GovernanceKnowledgeQuery``：治理知识检索请求（query_id / user_id / org_id /
  query_text / filters / created_at）。**权限隔离**：``user_id`` / ``org_id``
  缺失即拒绝；发起人必须是真实人类标识（命中 ai / system / bot / agent / auto
  即拒绝）；``filters`` 中不得夹带跨组织 org 覆盖；``query_text`` 命中
  「自动改知识 / 自动应用经验 / 自动生成策略」语义即拒绝（任务1，红线③/④/⑤/⑥）。
- ``GovernanceKnowledgeRetrieval``：治理知识检索结果（retrieval_id / query_id /
  knowledge_candidates / sources / trace）。**来源可追溯**：``sources`` 为空即拒绝；
  ``trace`` 不可溯源即拒绝；每条候选必须自带来源引用，无源候选一律拒绝落库
  （任务2，红线⑥）。
- ``GovernanceSimilarityMatcher``：治理相似度匹配器（``match_cases()`` /
  ``match_patterns()`` / ``find_related_events()``）。**只提供相似候选**：
  匹配为**确定性词元重合度**计算（无 LLM、无编造），输出恒为
  ``GovernanceMatchCandidate`` 候选态（``requires_human_use`` 恒为 True）；
  匹配器**不提供**任何 apply / execute / adopt / promote 能力（任务3，红线③/④/⑤）。
- ``GovernanceLearningContext``：治理辅助学习上下文（历史案例 / 治理模式 /
  知识候选 / 来源链）。**只辅助分析**：``is_advisory_only`` 恒为 True；
  无来源链即拒绝构造；上下文不含任何处置结论（任务4，红线④/⑥）。
- ``GovernanceAssistanceReport``：治理辅助报告（匹配案例 / 相关模式 / 来源 /
  事实摘要）。**禁止治理建议**：``factual_summary`` 与所有 AI 产出文本经
  ``_ADVICE_MARKERS`` 拦截，命中「建议 / 应当 / 应立即 / recommend / suggest /
  判定责任」等指令性语义即拒绝；``contains_recommendation`` 恒为 False
  （任务5，红线⑥）。
- ``GovernanceKnowledgeRetrievalService``：检索与辅助学习服务（任务1–7 统一入口）。
  ``submit_query`` / ``retrieve`` / ``build_learning_context`` /
  ``build_assistance_report`` 均为 AI 可发起的**只读**动作；
  ``mark_human_used`` 强制 ``require_human_actor(USER)`` —— 知识到底怎么用，
  只能由真实人工落地并留痕。

红线（fail-closed，复用 3.8.0~3.8.22 基座 + Phase 3.8.23 主理人六条）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved（forbidden 方法名结构性拦截）。
③ 不 AI 自动修改知识（``auto_update_knowledge`` / ``auto_merge_knowledge`` 及同族
   方法名被 mixin 拦截；检索请求 / 匹配理由 / 上下文 / 报告文本命中自动改知识语义
   即拒绝；本层对 3.8.22 知识层**纯只读**，不持有任何知识写能力）。
④ 不 AI 自动应用治理经验（``auto_apply_knowledge`` / ``auto_execute_knowledge``
   及同族被拦截；检索结果**永远只是候选**，``requires_human_use`` 恒为 True，
   不存在任何"应用/执行/落地"路径；文本命中应用经验语义即拒绝）。
⑤ 不 AI 自动生成治理策略（``auto_generate_policy`` / ``generate_policy`` 及同族
   被拦截；本层输出物中**不存在** policy 类型枚举，``GovernanceAssistanceReport``
   结构上无法承载策略；文本命中生成策略语义即拒绝）。
⑥ 不 AI 代替治理责任人（审计禁止 ``record_human_approval``；辅助报告禁止出现
   任何建议 / 责任判定语义；``mark_human_used`` 强制 ``require_human_actor(USER)``；
   AI 产出只陈述事实与来源，不含处置指令）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

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

_RETRIEVAL_FORBIDDEN = (
    # 基座（红线②/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动修改知识（主理人明列两项 + 同族收敛）
    "auto_update_knowledge",
    "auto_merge_knowledge",
    "update_knowledge",
    "merge_knowledge",
    "auto_modify_knowledge",
    "modify_knowledge",
    "auto_edit_knowledge",
    "edit_knowledge",
    "auto_rewrite_knowledge",
    "rewrite_knowledge",
    "auto_delete_knowledge",
    "delete_knowledge",
    "auto_patch_knowledge",
    "patch_knowledge",
    "auto_overwrite_knowledge",
    "overwrite_knowledge",
    "auto_upsert_knowledge",
    "upsert_knowledge",
    "auto_sync_knowledge",
    "sync_knowledge",
    "auto_write_knowledge",
    "write_knowledge",
    "auto_publish_knowledge",
    "publish_knowledge",
    "auto_index_knowledge",
    "reindex_knowledge",
    # 红线④：禁止 AI 自动应用治理经验（主理人明列两项 + 同族收敛）
    "auto_apply_knowledge",
    "auto_execute_knowledge",
    "apply_knowledge",
    "execute_knowledge",
    "auto_apply_experience",
    "apply_experience",
    "auto_execute_experience",
    "execute_experience",
    "auto_adopt_knowledge",
    "adopt_knowledge",
    "auto_enforce_knowledge",
    "enforce_knowledge",
    "auto_deploy_knowledge",
    "deploy_knowledge",
    "auto_act_on_knowledge",
    "act_on_knowledge",
    "auto_trigger_action",
    "trigger_governance_action",
    "auto_execute_governance",
    "execute_governance",
    "auto_remediate",
    "auto_fix",
    "auto_resolve",
    # 红线⑤：禁止 AI 自动生成治理策略
    "auto_generate_policy",
    "generate_policy",
    "auto_create_policy",
    "create_policy",
    "auto_draft_policy",
    "draft_policy",
    "auto_derive_policy",
    "derive_policy",
    "auto_synthesize_policy",
    "synthesize_policy",
    "auto_update_policy",
    "update_policy",
    "auto_apply_policy",
    "apply_policy",
    "auto_publish_policy",
    "publish_policy",
    "auto_enforce_policy",
    "enforce_policy",
    "auto_promote_knowledge",
    "promote_knowledge_to_policy",
    "knowledge_to_policy",
    "auto_change_permission",
    "change_permission",
    "auto_grant_permission",
    "grant_permission",
    # 红线⑥：禁止 AI 代替治理责任人
    "act_as_governance_owner",
    "take_governance_ownership",
    "assume_governance_responsibility",
    "auto_review",
    "auto_review_knowledge",
    "review_knowledge_automatically",
    "auto_confirm_knowledge",
    "confirm_knowledge_automatically",
    "auto_decide_governance",
    "decide_governance",
    "auto_judge",
    "judge_governance",
    "auto_assign_responsibility",
    "assign_responsibility",
    "auto_conclude",
    "conclude_automatically",
    "auto_close_task",
    "close_task",
    "auto_recommend",
    "recommend_action",
    "auto_advise",
    "advise_governance",
    "auto_suggest",
    "suggest_governance_action",
)


# 文本中禁止出现的「自动修改知识」语义（红线③）。
_KNOWLEDGE_MUTATION_MARKERS = (
    "auto_update_knowledge",
    "auto update knowledge",
    "auto_merge_knowledge",
    "auto merge knowledge",
    "auto_overwrite_knowledge",
    "auto_delete_knowledge",
    "automatically updated knowledge",
    "automatically merged knowledge",
    "自动修改知识",
    "自动更新知识",
    "自动合并知识",
    "自动覆盖知识",
    "自动删除知识",
    "自动写入知识库",
    "由ai自动改写知识",
)

# 文本中禁止出现的「自动应用治理经验」语义（红线④）。
_KNOWLEDGE_APPLY_MARKERS = (
    "auto_apply_knowledge",
    "auto apply knowledge",
    "auto_execute_knowledge",
    "auto execute knowledge",
    "auto_apply_experience",
    "auto_execute_experience",
    "automatically applied experience",
    "automatically executed knowledge",
    "自动应用知识",
    "自动执行知识",
    "自动应用经验",
    "自动执行经验",
    "自动套用经验",
    "自动落地经验",
)

# 文本中禁止出现的「自动生成治理策略」语义（红线⑤）。
_POLICY_GENERATION_MARKERS = (
    "auto_generate_policy",
    "auto generate policy",
    "auto_create_policy",
    "auto_draft_policy",
    "auto_derive_policy",
    "automatically generated policy",
    "自动生成策略",
    "自动生成治理策略",
    "自动制定策略",
    "自动产出策略",
    "自动形成策略",
    "自动升级为策略",
    "自动下发策略",
)

# 文本中禁止出现的「治理建议 / 代替责任人下判断」语义（红线⑥，任务5 核心）。
_ADVICE_MARKERS = (
    "recommend",
    "recommendation",
    "suggest",
    "should be disabled",
    "must be disabled",
    "建议",
    "应当整改",
    "应立即",
    "需处罚",
    "责任在于",
    "判定责任",
)

_NON_HUMAN_ACTORS = (
    "ai",
    "system",
    "bot",
    "robot",
    "agent",
    "auto",
    "automation",
    "llm",
    "model",
    "机器人",
    "系统",
    "自动",
)


def _reject_markers(text: str, markers: "tuple[str, ...]", *, ctx: str, rule: str) -> None:
    """命中语义标记即抛红线违例（只读校验，不改写任何文本）。"""
    lowered = str(text).lower()
    for marker in markers:
        if marker.lower() in lowered:
            raise EnterpriseRedLineViolationError(
                f"{ctx} 命中禁止语义 {marker!r}：{rule}"
            )


def _looks_non_human(value: str) -> bool:
    """只读判断某个标识是否为非人类（AI / system / bot ...）。"""
    raw = str(value).strip().lower()
    if not raw:
        return True
    for marker in _NON_HUMAN_ACTORS:
        if raw == marker or any(
            raw.startswith(f"{marker}{sep}") for sep in ("-", "_", ".", "@", ":")
        ):
            return True
    return False


def _reject_non_human(value: str, *, ctx: str) -> None:
    """拒绝非人类标识（红线⑥：人工节点只能来自真实人工）。

    只做**整体等值 / 前缀分段**判断（``<marker>-`` / ``_`` / ``.`` / ``@`` / ``:``），
    避免误伤 ``aileen`` 之类的正常人名。
    """
    raw = str(value).strip().lower()
    for marker in _NON_HUMAN_ACTORS:
        if raw == marker or any(
            raw.startswith(f"{marker}{sep}") for sep in ("-", "_", ".", "@", ":")
        ):
            raise EnterpriseRedLineViolationError(
                f"{ctx} 拒绝非人类标识 {value!r}："
                f"治理知识检索发起 / 人工使用留痕必须由真实人工 USER 给出（红线⑥）"
            )


def _reject_retrieval_markers(text: str, *, ctx: str) -> None:
    """统一施加红线③/④/⑤ 三组语义拦截（本层所有自由文本字段共用）。"""
    _reject_markers(
        text, _KNOWLEDGE_MUTATION_MARKERS,
        ctx=ctx, rule="本层对治理知识纯只读，禁止 AI 自动修改知识（红线③）",
    )
    _reject_markers(
        text, _KNOWLEDGE_APPLY_MARKERS,
        ctx=ctx, rule="检索结果永远只是候选，禁止 AI 自动应用治理经验（红线④）",
    )
    _reject_markers(
        text, _POLICY_GENERATION_MARKERS,
        ctx=ctx, rule="本层不产出策略，禁止 AI 自动生成治理策略（红线⑤）",
    )


def _reject_advice_markers(text: str, *, ctx: str) -> None:
    """拦截建议 / 责任判定语义（红线⑥，任务5：辅助报告禁止治理建议）。"""
    _reject_markers(
        text, _ADVICE_MARKERS,
        ctx=ctx,
        rule=(
            "辅助分析只陈述事实与来源，禁止输出治理建议、处置指令或责任判定，"
            "怎么用只能由真实治理责任人决定（红线⑥）"
        ),
    )


def _tokenize(text: str) -> "set[str]":
    """确定性分词（英文按非字母数字切分 + 中文按字切分）。

    **不调用任何模型、不做任何语义推断**：相似度必须是可复现、可解释的事实计算，
    否则 AI 就是在"编造相关性"（红线⑥）。
    """
    raw = str(text).lower()
    tokens: "set[str]" = set()
    buf: List[str] = []
    for ch in raw:
        if ch.isalnum() and ch.isascii():
            buf.append(ch)
            continue
        if buf:
            tokens.add("".join(buf))
            buf = []
        if "\u4e00" <= ch <= "\u9fff":
            tokens.add(ch)
    if buf:
        tokens.add("".join(buf))
    return {t for t in tokens if t}


def _similarity(left: str, right: str) -> float:
    """Jaccard 词元重合度（0.0~1.0，确定性、可复现）。"""
    a = _tokenize(left)
    b = _tokenize(right)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(inter / union, 6) if union else 0.0


# ---------------------------------------------------------------------------
# 任务1：治理知识检索请求（权限隔离）
# ---------------------------------------------------------------------------

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


@dataclass
class GovernanceKnowledgeQuery:
    """治理知识检索请求（任务1，**权限隔离**）。

    字段严格对应主理人要求：``query_id`` / ``user_id`` / ``org_id`` /
    ``query_text`` / ``filters`` / ``created_at``。

    权限隔离（红线⑥）：
    - ``user_id`` 为空即拒绝：检索必须能追溯到真实发起人；
    - ``user_id`` 命中 ai / system / bot / agent / auto 等非人类标识即拒绝：
      治理知识检索是**人在用**，AI 不得以自己的名义发起治理知识检索；
    - ``org_id`` 为空即拒绝：无组织归属的检索无法做隔离，一律拒绝；
    - ``filters`` 不得夹带 ``org_id`` / ``cross_org`` / ``bypass_permission`` 等
      越权键（结构上堵死"用 filter 绕隔离"）；未知键一律拒绝（白名单）。

    只读语义（红线③/④/⑤）：
    - ``query_text`` 命中「自动改知识 / 自动应用经验 / 自动生成策略」语义即拒绝
      —— 检索请求本身不得要求 AI 去改、去用、去生成；
    - 本类**不提供**任何 apply / execute / update / generate 方法，
      检索请求就是一个只读的问题描述，不是一条指令。

    注：``query_text`` **不施加** ``_ADVICE_MARKERS``——人当然可以问"有没有类似案例、
    大家一般怎么处理"；红线⑥ 约束的是**AI 的输出**不得给建议，而不是禁止人提问。
    AI 侧产出（匹配理由 / 事实摘要 / 辅助报告）才强制 ``_reject_advice_markers``。
    """

    query_id: str
    user_id: str
    org_id: str
    query_text: str
    filters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceKnowledgeQuery（红线①）"
            )
        self.query_id = str(self.query_id).strip()
        self.user_id = str(self.user_id).strip()
        self.org_id = str(self.org_id).strip()
        self.query_text = str(self.query_text).strip()
        self.created_at = str(self.created_at).strip()

        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceKnowledgeQuery 缺少 query_id：禁止匿名检索请求（红线⑥）"
            )
        if not self.user_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeQuery {self.query_id!r} 缺少 user_id："
                f"治理知识检索必须可追溯到真实发起人（红线⑥）"
            )
        _reject_non_human(
            self.user_id,
            ctx=f"GovernanceKnowledgeQuery {self.query_id!r} 的 user_id",
        )
        if not self.org_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeQuery {self.query_id!r} 缺少 org_id："
                f"无组织归属的治理知识检索无法隔离，默认拒绝（红线⑥）"
            )
        if not self.query_text:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeQuery {self.query_id!r} 缺少 query_text："
                f"禁止空检索（会退化成全量拉取，破坏最小必要原则，红线⑥）"
            )

        if not isinstance(self.filters, dict):
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeQuery {self.query_id!r} 的 filters 必须是 dict"
            )
        normalized: Dict[str, Any] = {}
        for key, value in self.filters.items():
            name = str(key).strip().lower()
            if name in _FORBIDDEN_FILTER_KEYS:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceKnowledgeQuery {self.query_id!r} 的 filters 含越权键 "
                    f"{key!r}：禁止通过过滤条件绕过组织 / 权限隔离（红线⑥）"
                )
            if name not in _ALLOWED_FILTER_KEYS:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceKnowledgeQuery {self.query_id!r} 的 filters 含未知键 "
                    f"{key!r}：过滤条件采用白名单，未知键默认拒绝"
                    f"（允许键：{','.join(_ALLOWED_FILTER_KEYS)}）"
                )
            normalized[name] = value
            _reject_retrieval_markers(
                f"{name}={value}",
                ctx=f"GovernanceKnowledgeQuery {self.query_id!r} 的 filters[{key!r}]",
            )
        self.filters = normalized

        _reject_retrieval_markers(
            self.query_text,
            ctx=f"GovernanceKnowledgeQuery {self.query_id!r} 的 query_text",
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
        """只读摘要（只陈述"谁在什么范围里查了什么"，不含任何结论）。"""
        return (
            f"query={self.query_id} org={self.org_id} user={self.user_id} "
            f"filters={len(self.filters)} advisory_only=true"
        )


# ---------------------------------------------------------------------------
# 任务2：治理知识检索结果（来源可追溯）
# ---------------------------------------------------------------------------

class GovernanceMatchKind(str, Enum):
    """匹配对象类型（**刻意不含任何 policy 类型**，红线⑤）。"""

    CASE = "case"
    PATTERN = "pattern"
    KNOWLEDGE = "knowledge"
    EVENT = "event"


@dataclass
class GovernanceMatchCandidate:
    """相似匹配候选（任务2/3 共用，**恒为候选，永不生效**）。

    只提供相似候选（红线④）：
    - ``requires_human_use`` 恒为 ``True``，置 False 即拒绝 —— 结构上不存在
      "自动采用"这条路；
    - ``similarity`` 必须落在 [0,1]，由确定性词元重合度算出，不接受外部塞入
      的"模型置信度"式虚构分值；
    - ``source_ref`` 为空即拒绝：无源候选不得进入检索结果（红线⑥）；
    - ``rationale`` 只写**事实层面的重合点**，命中建议 / 应用 / 生成策略语义即拒绝。

    本类**不提供** apply / adopt / execute / promote 任何方法。
    """

    candidate_id: str
    match_kind: GovernanceMatchKind
    ref_id: str
    similarity: float = 0.0
    rationale: str = ""
    source_ref: str = ""
    requires_human_use: bool = True

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceMatchCandidate（红线①）"
            )
        self.candidate_id = str(self.candidate_id).strip()
        self.ref_id = str(self.ref_id).strip()
        self.rationale = str(self.rationale).strip()
        self.source_ref = str(self.source_ref).strip()

        if not self.candidate_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceMatchCandidate 缺少 candidate_id"
            )
        if not self.ref_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceMatchCandidate {self.candidate_id!r} 缺少 ref_id："
                f"候选必须指向真实存在的治理事实（红线⑥）"
            )
        if not isinstance(self.match_kind, GovernanceMatchKind):
            self.match_kind = GovernanceMatchKind(str(self.match_kind))
        if self.requires_human_use is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceMatchCandidate {self.candidate_id!r} 拒绝 "
                f"requires_human_use=False：检索结果永远只是候选，"
                f"是否采用只能由真实人工决定（红线④/⑥）"
            )
        try:
            self.similarity = float(self.similarity)
        except (TypeError, ValueError) as exc:
            raise EnterpriseRedLineViolationError(
                f"GovernanceMatchCandidate {self.candidate_id!r} 的 similarity 非法"
            ) from exc
        if not (0.0 <= self.similarity <= 1.0):
            raise EnterpriseRedLineViolationError(
                f"GovernanceMatchCandidate {self.candidate_id!r} 的 similarity "
                f"{self.similarity} 越界：相似度必须是 [0,1] 的确定性事实值"
            )
        if not self.source_ref:
            raise EnterpriseRedLineViolationError(
                f"GovernanceMatchCandidate {self.candidate_id!r} 缺少 source_ref："
                f"禁止输出无来源的匹配候选（红线⑥）"
            )
        ctx = f"GovernanceMatchCandidate {self.candidate_id!r} 的 rationale"
        _reject_retrieval_markers(self.rationale, ctx=ctx)
        _reject_advice_markers(self.rationale, ctx=ctx)

    @property
    def is_advisory_only(self) -> bool:
        """恒为 True：候选只能辅助人工判断（红线④）。"""
        return True

    def render(self) -> str:
        """只读渲染（事实：类型 / 引用 / 相似度 / 来源）。"""
        return (
            f"{self.match_kind.value}:{self.ref_id}"
            f"@{self.similarity}[{self.source_ref}]"
        )


@dataclass
class GovernanceKnowledgeRetrieval:
    """治理知识检索结果（任务2，**来源可追溯**）。

    字段严格对应主理人要求：``retrieval_id`` / ``query_id`` /
    ``knowledge_candidates`` / ``sources`` / ``trace``。

    来源可追溯（红线⑥）：
    - ``sources`` 为空即拒绝：检索结果必须能说明"从哪些库 / 哪些集合里查出来的"；
    - ``trace``（``SourceTrace``）缺失或不可溯源即拒绝；
    - 每条 ``knowledge_candidates`` 自身已强校验 ``source_ref``，
      本类再做一次"候选来源必须被 ``sources`` 或 ``trace`` 覆盖"的交叉校验，
      杜绝"候选来源指向一个检索结果根本没声明过的地方"。

    只读语义（红线③/④）：本类不提供任何 apply / merge / update 方法；
    检索结果是**只读事实快照**，不是可执行对象。
    """

    retrieval_id: str
    query_id: str
    knowledge_candidates: List[GovernanceMatchCandidate] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    trace: "SourceTrace | None" = None
    retrieved_at: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceKnowledgeRetrieval（红线①）"
            )
        self.retrieval_id = str(self.retrieval_id).strip()
        self.query_id = str(self.query_id).strip()
        self.retrieved_at = str(self.retrieved_at).strip()
        self.sources = [str(s).strip() for s in self.sources if str(s).strip()]

        if not self.retrieval_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceKnowledgeRetrieval 缺少 retrieval_id"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeRetrieval {self.retrieval_id!r} 缺少 query_id："
                f"检索结果必须挂在一条真实检索请求上（红线⑥）"
            )
        if not self.sources:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeRetrieval {self.retrieval_id!r} 缺少 sources："
                f"禁止输出来源不明的治理知识检索结果（红线⑥）"
            )
        if self.trace is None or not self.trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeRetrieval {self.retrieval_id!r} 无来源链 trace："
                f"检索结果必须强可溯源（红线⑥）"
            )

        declared = set(self.sources) | set(self.trace.entries)
        for cand in self.knowledge_candidates:
            if not isinstance(cand, GovernanceMatchCandidate):
                raise EnterpriseRedLineViolationError(
                    f"GovernanceKnowledgeRetrieval {self.retrieval_id!r} 的候选类型非法："
                    f"只接受 GovernanceMatchCandidate（禁止塞入未经红线校验的对象）"
                )
            if cand.source_ref not in declared:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceKnowledgeRetrieval {self.retrieval_id!r} 的候选 "
                    f"{cand.candidate_id!r} 来源 {cand.source_ref!r} 未在 sources / trace "
                    f"中声明：禁止凭空来源（红线⑥）"
                )

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.trace is not None and self.trace.is_traceable

    @property
    def candidate_count(self) -> int:
        """只读候选数量。"""
        return len(self.knowledge_candidates)

    @property
    def all_candidates_require_human(self) -> bool:
        """恒为 True：所有候选都必须由人工决定是否使用（红线④）。"""
        return all(c.requires_human_use for c in self.knowledge_candidates)

    def render_source(self) -> str:
        """只读渲染来源链（不改动任何状态）。"""
        return self.trace.render() if self.trace else "no_source"

    def top(self, limit: int = 5) -> List[GovernanceMatchCandidate]:
        """只读取相似度最高的若干候选（不改动内部顺序）。"""
        if limit <= 0:
            return []
        return sorted(
            self.knowledge_candidates,
            key=lambda c: (-c.similarity, c.candidate_id),
        )[:limit]

    def summary(self) -> str:
        """只读摘要（只陈述事实：候选数 / 来源数 / 可溯源）。"""
        return (
            f"retrieval={self.retrieval_id} query={self.query_id} "
            f"candidates={self.candidate_count} sources={len(self.sources)} "
            f"traceable={self.is_traceable} advisory_only=true"
        )


# ---------------------------------------------------------------------------
# 任务3：治理相似度匹配器（只提供相似候选）
# ---------------------------------------------------------------------------

class GovernanceSimilarityMatcher(_RedLineForbiddenMixin):
    """治理相似度匹配器（任务3，**只提供相似候选**）。

    三个入口严格对应主理人要求：
    - ``match_cases()``：在 3.8.22 已沉淀的**治理案例**中找相似历史案例；
    - ``match_patterns()``：在 3.8.22 已归纳的**事实模式**中找相关模式；
    - ``find_related_events()``：在 3.8.21 **已由人工闭环**的治理任务中找相关事件。

    只提供相似候选（红线④）：
    - 三个方法的返回值统一是 ``List[GovernanceMatchCandidate]``，
      每条候选 ``requires_human_use`` 恒为 True；
    - 匹配是**确定性词元重合度**（``_similarity``），可复现、可解释、可复核，
      不调用任何模型、不做语义推断、不编造相关性；
    - 匹配器对 3.8.21 / 3.8.22 数据**纯只读**（只读 ``_cases`` / ``_patterns`` /
      ``_candidates`` / ``_tasks`` 快照，绝不写回、绝不推进、绝不关闭）。

    结构性禁止（红线③/④/⑤/⑥）：
    ``_FORBIDDEN = _RETRIEVAL_FORBIDDEN``，因此
    ``auto_update_knowledge`` / ``auto_merge_knowledge`` /
    ``auto_apply_knowledge`` / ``auto_execute_knowledge`` /
    ``auto_generate_policy`` / ``auto_recommend`` 等方法名在结构上不可达。
    """

    _FORBIDDEN = _RETRIEVAL_FORBIDDEN

    def __init__(
        self,
        knowledge_service: "Any | None" = None,
        governance_workflow: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceSimilarityMatcher（红线①）"
            )
        # 只读消费 3.8.22 治理知识层事实；本层绝不修改、绝不合并任何知识（红线③）。
        self._knowledge_service = knowledge_service
        # 只读消费 3.8.21 治理流程事实；本层绝不推进、绝不关闭任何治理任务。
        self._governance_workflow = governance_workflow

    # ------------------------------------------------------------------
    # 内部只读快照
    # ------------------------------------------------------------------

    def _snapshot(self, attr: str) -> Dict[str, Any]:
        """只读取出 3.8.22 知识层内部映射的**浅拷贝快照**（绝不写回）。"""
        svc = self._knowledge_service
        if svc is None:
            return {}
        data = getattr(svc, attr, None)
        if not isinstance(data, dict):
            return {}
        return dict(data)

    def _task_snapshot(self) -> Dict[str, Any]:
        """只读取出 3.8.21 治理任务的**浅拷贝快照**（绝不写回，红线⑤）。"""
        wf = self._governance_workflow
        if wf is None:
            return {}
        data = getattr(wf, "_tasks", None)
        if not isinstance(data, dict):
            return {}
        return dict(data)

    @staticmethod
    def _match_scope(org_id: str, item: Any) -> bool:
        """只读组织隔离：目标对象声明了 org_id 时必须与请求一致（红线⑥）。"""
        target = str(getattr(item, "org_id", "") or "").strip()
        if not target:
            return True
        return target == org_id

    @staticmethod
    def _agent_scope(filters: Dict[str, Any], item: Any) -> bool:
        """只读 agent 过滤（filters 未声明 agent_id 时不过滤）。"""
        wanted = str(filters.get("agent_id", "") or "").strip()
        if not wanted:
            return True
        return str(getattr(item, "agent_id", "") or "").strip() == wanted

    def _build_candidate(
        self,
        *,
        prefix: str,
        index: int,
        kind: GovernanceMatchKind,
        ref_id: str,
        similarity: float,
        source_ref: str,
        overlap: "set[str]",
    ) -> GovernanceMatchCandidate:
        """构造一条候选（``rationale`` 只写事实层面的重合词元，绝不写建议）。"""
        shared = ",".join(sorted(overlap)[:8])
        return GovernanceMatchCandidate(
            candidate_id=f"{prefix}-{index}",
            match_kind=kind,
            ref_id=ref_id,
            similarity=similarity,
            rationale=f"token_overlap={shared}" if shared else "token_overlap=none",
            source_ref=source_ref,
            requires_human_use=True,
        )

    # ------------------------------------------------------------------
    # 任务3-①：match_cases（相似历史案例）
    # ------------------------------------------------------------------

    def match_cases(
        self, query: GovernanceKnowledgeQuery
    ) -> List[GovernanceMatchCandidate]:
        """在已沉淀治理案例中检索相似候选（**只读、只候选**）。

        匹配文本 = 案例的 ``problem_pattern``（问题事实）。
        **刻意不把 ``human_resolution`` 纳入相似度计算**：人工处理结论是"怎么办"，
        一旦拿它做匹配，检索就滑向"给你找一个照抄的处置方案"，那等于变相给建议
        （红线⑥）。本层只按"问题长得像不像"检索，怎么处理由人自己看。
        """
        if not isinstance(query, GovernanceKnowledgeQuery):
            raise EnterpriseRedLineViolationError(
                "match_cases 只接受 GovernanceKnowledgeQuery（禁止绕过权限隔离校验）"
            )
        threshold = query.min_similarity()
        results: List[GovernanceMatchCandidate] = []
        index = 0
        for case_id, case in sorted(self._snapshot("_cases").items()):
            if not self._match_scope(query.org_id, case):
                continue
            if not self._agent_scope(query.filters, case):
                continue
            text = str(getattr(case, "problem_pattern", "") or "")
            score = _similarity(query.query_text, text)
            if score <= 0.0 or score < threshold:
                continue
            index += 1
            results.append(
                self._build_candidate(
                    prefix=f"{query.query_id}-case",
                    index=index,
                    kind=GovernanceMatchKind.CASE,
                    ref_id=str(case_id),
                    similarity=score,
                    source_ref=f"case:{case_id}",
                    overlap=_tokenize(query.query_text) & _tokenize(text),
                )
            )
        results.sort(key=lambda c: (-c.similarity, c.ref_id))
        return results[: query.top_k()]

    # ------------------------------------------------------------------
    # 任务3-②：match_patterns（相关治理模式）
    # ------------------------------------------------------------------

    def match_patterns(
        self, query: GovernanceKnowledgeQuery
    ) -> List[GovernanceMatchCandidate]:
        """在已归纳事实模式中检索相关候选（**只读、只候选**）。

        模式本身在 3.8.22 就已经 ``is_policy`` 恒为 False；本层原样只读引用，
        不做任何"模式 → 策略"的提升（红线⑤）。
        """
        if not isinstance(query, GovernanceKnowledgeQuery):
            raise EnterpriseRedLineViolationError(
                "match_patterns 只接受 GovernanceKnowledgeQuery（禁止绕过权限隔离校验）"
            )
        wanted_kind = str(query.filters.get("pattern_kind", "") or "").strip().lower()
        threshold = query.min_similarity()
        results: List[GovernanceMatchCandidate] = []
        index = 0
        for pattern_id, pattern in sorted(self._snapshot("_patterns").items()):
            if not self._match_scope(query.org_id, pattern):
                continue
            if not self._agent_scope(query.filters, pattern):
                continue
            if wanted_kind:
                kind_value = str(
                    getattr(getattr(pattern, "pattern_kind", None), "value", "")
                ).lower()
                if kind_value != wanted_kind:
                    continue
            text = str(getattr(pattern, "description", "") or "")
            score = _similarity(query.query_text, text)
            if score <= 0.0 or score < threshold:
                continue
            index += 1
            results.append(
                self._build_candidate(
                    prefix=f"{query.query_id}-pattern",
                    index=index,
                    kind=GovernanceMatchKind.PATTERN,
                    ref_id=str(pattern_id),
                    similarity=score,
                    source_ref=f"pattern:{pattern_id}",
                    overlap=_tokenize(query.query_text) & _tokenize(text),
                )
            )
        results.sort(key=lambda c: (-c.similarity, c.ref_id))
        return results[: query.top_k()]

    # ------------------------------------------------------------------
    # 任务3-③：find_related_events（相关治理事件）
    # ------------------------------------------------------------------

    def find_related_events(
        self, query: GovernanceKnowledgeQuery
    ) -> List[GovernanceMatchCandidate]:
        """在 3.8.21 治理任务中检索相关事件候选（**纯只读，绝不推进/关闭**）。

        只纳入**已由真实人工闭环**（``status == completed`` 且 ``closed_by`` 为
        真实人类）的治理任务：未闭环的事件还在流程里，把它拿来当"经验"检索，
        等于让 AI 拿半成品去影响在办案子（红线⑤/⑥）。
        """
        if not isinstance(query, GovernanceKnowledgeQuery):
            raise EnterpriseRedLineViolationError(
                "find_related_events 只接受 GovernanceKnowledgeQuery"
                "（禁止绕过权限隔离校验）"
            )
        threshold = query.min_similarity()
        results: List[GovernanceMatchCandidate] = []
        index = 0
        for task_id, task in sorted(self._task_snapshot().items()):
            if not self._match_scope(query.org_id, task):
                continue
            if not self._agent_scope(query.filters, task):
                continue
            status_value = str(getattr(getattr(task, "status", None), "value", ""))
            if status_value != "completed":
                continue
            closed_by = str(getattr(task, "closed_by", "") or "").strip()
            if not closed_by or _looks_non_human(closed_by):
                continue
            text = " ".join(
                str(getattr(task, attr, "") or "")
                for attr in ("title", "description", "problem_summary")
            ).strip()
            score = _similarity(query.query_text, text)
            if score <= 0.0 or score < threshold:
                continue
            index += 1
            results.append(
                self._build_candidate(
                    prefix=f"{query.query_id}-event",
                    index=index,
                    kind=GovernanceMatchKind.EVENT,
                    ref_id=str(task_id),
                    similarity=score,
                    source_ref=f"event:{task_id}",
                    overlap=_tokenize(query.query_text) & _tokenize(text),
                )
            )
        results.sort(key=lambda c: (-c.similarity, c.ref_id))
        return results[: query.top_k()]

    # ------------------------------------------------------------------
    # 任务3-④：match_knowledge（已人工采纳知识的只读候选）
    # ------------------------------------------------------------------

    def match_knowledge(
        self, query: GovernanceKnowledgeQuery
    ) -> List[GovernanceMatchCandidate]:
        """在 3.8.22 知识候选中检索相关候选（**只纳入已人工采纳的**）。

        未经人工审核（``status != accepted``）的候选属于"AI 的草稿"，
        把它检索出来当经验用，等价于让 AI 的产出绕过人工审核生效（红线④/⑥），
        因此结构上直接排除。
        """
        if not isinstance(query, GovernanceKnowledgeQuery):
            raise EnterpriseRedLineViolationError(
                "match_knowledge 只接受 GovernanceKnowledgeQuery（禁止绕过权限隔离校验）"
            )
        wanted_type = str(query.filters.get("knowledge_type", "") or "").strip().lower()
        threshold = query.min_similarity()
        results: List[GovernanceMatchCandidate] = []
        index = 0
        for cand_id, cand in sorted(self._snapshot("_candidates").items()):
            if not self._match_scope(query.org_id, cand):
                continue
            if not self._agent_scope(query.filters, cand):
                continue
            status_value = str(getattr(getattr(cand, "status", None), "value", ""))
            if status_value != "accepted":
                continue
            reviewed_by = str(getattr(cand, "reviewed_by", "") or "").strip()
            if not reviewed_by or _looks_non_human(reviewed_by):
                continue
            if wanted_type:
                type_value = str(
                    getattr(getattr(cand, "knowledge_type", None), "value", "")
                ).lower()
                if type_value != wanted_type:
                    continue
            text = str(getattr(cand, "content", "") or "")
            score = _similarity(query.query_text, text)
            if score <= 0.0 or score < threshold:
                continue
            index += 1
            results.append(
                self._build_candidate(
                    prefix=f"{query.query_id}-knowledge",
                    index=index,
                    kind=GovernanceMatchKind.KNOWLEDGE,
                    ref_id=str(cand_id),
                    similarity=score,
                    source_ref=f"knowledge:{cand_id}",
                    overlap=_tokenize(query.query_text) & _tokenize(text),
                )
            )
        results.sort(key=lambda c: (-c.similarity, c.ref_id))
        return results[: query.top_k()]


# ---------------------------------------------------------------------------
# 任务4：治理辅助学习上下文（只辅助分析）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceLearningContext:
    """治理辅助学习上下文（任务4，**只辅助分析**）。

    字段严格对应主理人要求：历史案例 / 治理模式 / 知识候选 / 来源链。

    只辅助分析（红线④/⑥）：
    - ``is_advisory_only`` 恒为 True，置 False 即拒绝 —— 这份上下文只是
      "摆给人看的材料"，不是可执行输入；
    - ``source_trace`` 缺失或不可溯源即拒绝：无源材料不得进入人工判断视野；
    - 上下文内所有条目都是 ``GovernanceMatchCandidate``（已强校验
      ``requires_human_use=True`` + ``source_ref``），结构上不可能夹带
      "已生效结论"；
    - 本类**不提供**任何 apply / execute / adopt / to_policy 方法。
    """

    context_id: str
    query_id: str
    org_id: str = ""
    historical_cases: List[GovernanceMatchCandidate] = field(default_factory=list)
    governance_patterns: List[GovernanceMatchCandidate] = field(default_factory=list)
    knowledge_candidates: List[GovernanceMatchCandidate] = field(default_factory=list)
    related_events: List[GovernanceMatchCandidate] = field(default_factory=list)
    source_trace: "SourceTrace | None" = None
    built_at: str = ""
    is_advisory_only: bool = True

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceLearningContext（红线①）"
            )
        self.context_id = str(self.context_id).strip()
        self.query_id = str(self.query_id).strip()
        self.org_id = str(self.org_id).strip()
        self.built_at = str(self.built_at).strip()

        if not self.context_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceLearningContext 缺少 context_id"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceLearningContext {self.context_id!r} 缺少 query_id："
                f"辅助上下文必须挂在一条真实检索请求上（红线⑥）"
            )
        if self.is_advisory_only is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceLearningContext {self.context_id!r} 拒绝 "
                f"is_advisory_only=False：本层产出只能辅助人工分析，"
                f"不得转为可执行治理输入（红线④/⑥）"
            )
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceLearningContext {self.context_id!r} 无来源链："
                f"辅助材料必须强可溯源（红线⑥）"
            )
        for label, bucket in (
            ("historical_cases", self.historical_cases),
            ("governance_patterns", self.governance_patterns),
            ("knowledge_candidates", self.knowledge_candidates),
            ("related_events", self.related_events),
        ):
            for item in bucket:
                if not isinstance(item, GovernanceMatchCandidate):
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceLearningContext {self.context_id!r} 的 {label} "
                        f"含非法条目：只接受 GovernanceMatchCandidate"
                        f"（禁止塞入未经红线校验的对象）"
                    )
                if item.requires_human_use is not True:
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceLearningContext {self.context_id!r} 的 {label} "
                        f"含非候选条目 {item.candidate_id!r}（红线④）"
                    )

    @property
    def total_items(self) -> int:
        """只读条目总数。"""
        return (
            len(self.historical_cases)
            + len(self.governance_patterns)
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
        return self.source_trace is not None and self.source_trace.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链。"""
        return self.source_trace.render() if self.source_trace else "no_source"

    def all_candidates(self) -> List[GovernanceMatchCandidate]:
        """只读汇总全部候选（新列表，不暴露内部可变引用）。"""
        return [
            *self.historical_cases,
            *self.governance_patterns,
            *self.knowledge_candidates,
            *self.related_events,
        ]

    def summary(self) -> str:
        """只读摘要（**只统计事实，不含任何结论或倾向**）。"""
        return (
            f"context={self.context_id} query={self.query_id} "
            f"cases={len(self.historical_cases)} "
            f"patterns={len(self.governance_patterns)} "
            f"knowledge={len(self.knowledge_candidates)} "
            f"events={len(self.related_events)} "
            f"advisory_only=true traceable={self.is_traceable}"
        )


# ---------------------------------------------------------------------------
# 任务5：治理辅助报告（禁止治理建议）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceAssistanceReport:
    """治理辅助报告（任务5，**禁止治理建议**）。

    字段严格对应主理人要求：匹配案例 / 相关模式 / 来源 / 事实摘要。

    禁止治理建议（红线⑥，本任务核心）：
    - ``factual_summary`` 与 ``fact_lines`` 全部经 ``_reject_advice_markers``：
      命中 recommend / suggest / 建议 / 应当整改 / 应立即 / 判定责任 等语义
      **直接拒绝生成报告**（fail-closed，宁可不出报告也不越界）；
    - ``contains_recommendation`` 恒为 False，且是**计算属性**，
      无法被外部赋值伪造；
    - 报告结构里**不存在** ``recommendation`` / ``action`` / ``policy`` 字段，
      即便有人想塞建议也无处可放（结构级堵死）；
    - 本类**不提供**任何 apply / execute / to_policy / approve 方法。

    可溯源（红线⑥）：``sources`` 为空或 ``source_trace`` 不可溯源即拒绝。
    """

    report_id: str
    query_id: str
    org_id: str = ""
    matched_cases: List[GovernanceMatchCandidate] = field(default_factory=list)
    related_patterns: List[GovernanceMatchCandidate] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    factual_summary: str = ""
    fact_lines: List[str] = field(default_factory=list)
    source_trace: "SourceTrace | None" = None
    generated_by: str = ""
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceAssistanceReport（红线①）"
            )
        self.report_id = str(self.report_id).strip()
        self.query_id = str(self.query_id).strip()
        self.org_id = str(self.org_id).strip()
        self.factual_summary = str(self.factual_summary).strip()
        self.generated_by = str(self.generated_by).strip()
        self.generated_at = str(self.generated_at).strip()
        self.sources = [str(s).strip() for s in self.sources if str(s).strip()]
        self.fact_lines = [str(x).strip() for x in self.fact_lines if str(x).strip()]

        if not self.report_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceAssistanceReport 缺少 report_id"
            )
        if not self.query_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistanceReport {self.report_id!r} 缺少 query_id："
                f"辅助报告必须挂在一条真实检索请求上（红线⑥）"
            )
        if not self.sources:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistanceReport {self.report_id!r} 缺少 sources："
                f"禁止输出来源不明的辅助报告（红线⑥）"
            )
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssistanceReport {self.report_id!r} 无来源链："
                f"辅助报告必须强可溯源（红线⑥）"
            )

        for label, bucket in (
            ("matched_cases", self.matched_cases),
            ("related_patterns", self.related_patterns),
        ):
            for item in bucket:
                if not isinstance(item, GovernanceMatchCandidate):
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceAssistanceReport {self.report_id!r} 的 {label} "
                        f"含非法条目：只接受 GovernanceMatchCandidate"
                    )
                if item.requires_human_use is not True:
                    raise EnterpriseRedLineViolationError(
                        f"GovernanceAssistanceReport {self.report_id!r} 的 {label} "
                        f"含非候选条目 {item.candidate_id!r}（红线④）"
                    )

        # 任务5 核心：AI 产出文本三层语义拦截（③/④/⑤ + ⑥ 建议）。
        ctx = f"GovernanceAssistanceReport {self.report_id!r} 的 factual_summary"
        _reject_retrieval_markers(self.factual_summary, ctx=ctx)
        _reject_advice_markers(self.factual_summary, ctx=ctx)
        for idx, line in enumerate(self.fact_lines):
            line_ctx = (
                f"GovernanceAssistanceReport {self.report_id!r} 的 fact_lines[{idx}]"
            )
            _reject_retrieval_markers(line, ctx=line_ctx)
            _reject_advice_markers(line, ctx=line_ctx)

    @property
    def contains_recommendation(self) -> bool:
        """恒为 False：本报告结构上与语义上都不承载治理建议（红线⑥）。

        写成计算属性而非字段，是为了让"报告里有没有建议"这件事**不可被赋值伪造**。
        """
        return False

    @property
    def is_advisory_only(self) -> bool:
        """恒为 True：报告只辅助人工分析（红线④）。"""
        return True

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链。"""
        return self.source_trace.render() if self.source_trace else "no_source"

    def render(self) -> str:
        """只读渲染报告全文（**纯事实 + 来源，无任何处置指向**）。"""
        lines = [
            f"# 治理辅助报告 {self.report_id}",
            f"query={self.query_id} org={self.org_id or 'n/a'}",
            f"matched_cases={len(self.matched_cases)} "
            f"related_patterns={len(self.related_patterns)}",
            f"sources={','.join(self.sources)}",
            f"trace={self.render_source()}",
            "",
            "## 事实摘要",
            self.factual_summary or "(无)",
        ]
        if self.fact_lines:
            lines.append("")
            lines.append("## 事实条目")
            lines.extend(f"- {line}" for line in self.fact_lines)
        lines.append("")
        lines.append(
            "## 使用说明\n"
            "本报告仅为辅助分析材料：只呈现相似历史事实与来源，"
            "不含治理建议、不含处置指令、不含责任判定。"
            "如何使用由真实治理责任人自行判断并留痕。"
        )
        return "\n".join(lines)

    def summary(self) -> str:
        """只读摘要（只陈述事实规模与可溯源性）。"""
        return (
            f"report={self.report_id} query={self.query_id} "
            f"cases={len(self.matched_cases)} patterns={len(self.related_patterns)} "
            f"traceable={self.is_traceable} contains_recommendation=false "
            f"advisory_only=true"
        )


# ---------------------------------------------------------------------------
# 检索与辅助学习服务（任务1–7 统一入口）
# ---------------------------------------------------------------------------

class GovernanceRetrievalStage(str, Enum):
    """检索辅助流程阶段（**不存在任何"已应用/已生效"终态**，红线④）。"""

    QUERY_SUBMITTED = "query_submitted"
    RETRIEVED = "retrieved"
    CONTEXT_BUILT = "context_built"
    REPORT_READY = "report_ready"
    HUMAN_USED = "human_used"


_ALLOWED_RETRIEVAL_TRANSITIONS: Dict[
    GovernanceRetrievalStage, "tuple[GovernanceRetrievalStage, ...]"
] = {
    GovernanceRetrievalStage.QUERY_SUBMITTED: (GovernanceRetrievalStage.RETRIEVED,),
    GovernanceRetrievalStage.RETRIEVED: (GovernanceRetrievalStage.CONTEXT_BUILT,),
    GovernanceRetrievalStage.CONTEXT_BUILT: (GovernanceRetrievalStage.REPORT_READY,),
    GovernanceRetrievalStage.REPORT_READY: (GovernanceRetrievalStage.HUMAN_USED,),
    GovernanceRetrievalStage.HUMAN_USED: (),
}


class GovernanceKnowledgeRetrievalService(_RedLineForbiddenMixin):
    """Agent 治理知识检索与辅助学习服务（任务1–7 统一入口）。

    承载链路：**治理事件 → 历史案例检索 → 知识匹配 → 辅助分析 → 人工使用**。

    方法边界：
    - ``submit_query``：**AI 可代提**，但 ``user_id`` 必须是真实人类且经权限校验
      （红线⑥）；
    - ``retrieve`` / ``build_learning_context`` / ``build_assistance_report``：
      **AI 可发起**，全部为只读检索与只读汇编，产出恒为候选 / 辅助材料；
    - ``mark_human_used``：**强制 ``require_human_actor(USER)``** —— 只有真实人工
      能声明"我看了这份材料并据此处理"，AI 无论如何无法自称使用者、
      无法把检索结果变成治理动作（红线④/⑥）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - **不改知识**：不持有任何 update / merge / delete knowledge 能力，
      对 3.8.22 ``GovernanceImprovementWorkflowService`` **纯只读**（红线③）。
    - **不用经验**：检索结果 ``requires_human_use`` 恒 True，无任何 apply /
      execute 路径；阶段机里不存在"已应用"终态（红线④）。
    - **不生策略**：本层无 policy 类型、无 policy 字段、无 policy 方法（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_update_knowledge / auto_merge_knowledge /
      auto_apply_knowledge / auto_execute_knowledge / auto_generate_policy /
      auto_recommend 等方法。
    """

    _FORBIDDEN = _RETRIEVAL_FORBIDDEN

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
                "GovernanceKnowledgeRetrievalService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        # 只读使用：仅用于访问校验，绝不写任何权限或策略（红线③/⑤）。
        self._permission_policy = permission_policy
        # 只读消费 3.8.22 治理知识事实；本层绝不修改、绝不合并任何知识（红线③）。
        self._knowledge_service = knowledge_service
        # 只读消费 3.8.21 治理流程事实；本层绝不推进、绝不关闭任何治理任务。
        self._governance_workflow = governance_workflow
        self._matcher = GovernanceSimilarityMatcher(
            knowledge_service=knowledge_service,
            governance_workflow=governance_workflow,
        )
        self._queries: Dict[str, GovernanceKnowledgeQuery] = {}
        self._retrievals: Dict[str, GovernanceKnowledgeRetrieval] = {}
        self._contexts: Dict[str, GovernanceLearningContext] = {}
        self._reports: Dict[str, GovernanceAssistanceReport] = {}
        self._stages: Dict[str, GovernanceRetrievalStage] = {}
        self._human_usages: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(
        self, *, user: object, resource_category: str = "knowledge"
    ) -> None:
        """治理知识检索访问权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误
        （红线⑥：治理知识受控访问、跨组织隔离）。

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
                    f"用户角色无权限访问 Agent 治理知识检索数据"
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
        self, query_id: str, target: GovernanceRetrievalStage, *, op: str
    ) -> None:
        """推进检索辅助流程阶段（非法迁移直接拒绝）。"""
        current = self._stages.get(query_id)
        if current is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 检索请求 {query_id!r} 尚无流程阶段："
                f"禁止跳过 query_submitted（红线⑥）"
            )
        if target not in _ALLOWED_RETRIEVAL_TRANSITIONS.get(current, ()):
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把检索 {query_id!r} 从 {current.value} 迁移到 {target.value}："
                f"非法阶段迁移（只能 query_submitted → retrieved → context_built → "
                f"report_ready → human_used 逐步推进，且最后一步必须由真实人工执行，"
                f"红线④/⑥）"
            )
        self._stages[query_id] = target

    def stage_of(self, query_id: str) -> "GovernanceRetrievalStage | None":
        """只读查询某次检索当前阶段（不改动任何状态）。"""
        return self._stages.get(query_id)

    def _get_query_or_raise(self, query_id: str, *, op: str) -> GovernanceKnowledgeQuery:
        """只读取出检索请求，不存在即拒绝（禁止凭空推进流程）。"""
        query = self._queries.get(query_id)
        if query is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到检索请求 {query_id!r}：禁止凭空推进检索流程（红线⑥）"
            )
        return query

    # ------------------------------------------------------------------
    # 任务1 服务入口：submit_query
    # ------------------------------------------------------------------

    def submit_query(
        self,
        *,
        query_id: str,
        user_id: str,
        query_text: str,
        org_id: str = "",
        filters: "Dict[str, Any] | None" = None,
        created_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceKnowledgeQuery:
        """登记一次治理知识检索请求（**权限隔离**，任务1/7）。

        AI 可以代为提交（只是把人的问题结构化），但：
        - ``user_id`` 必须是真实人类标识，AI 不得以自己的名义检索治理知识（红线⑥）；
        - ``org_id`` 必须与服务实例组织一致，跨组织一律拒绝（红线⑥）；
        - ``filters`` 走白名单 + 越权键黑名单，禁止靠过滤条件绕隔离（红线⑥）；
        - ``query_text`` 命中自动改知识 / 自动应用经验 / 自动生成策略语义即拒绝
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

        query = GovernanceKnowledgeQuery(
            query_id=query_id,
            user_id=user_id,
            org_id=target_org,
            query_text=query_text,
            filters=dict(filters or {}),
            created_at=created_at,
        )
        if query.query_id in self._queries:
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝重复登记检索请求 {query.query_id!r}"
            )
        self._queries[query.query_id] = query
        self._stages[query.query_id] = GovernanceRetrievalStage.QUERY_SUBMITTED

        if self._audit is not None:
            self._audit.record_agent_governance_knowledge_query_action(
                record_id=f"gkq-{query.query_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="submit_governance_knowledge_query",
                target=query.query_id,
                detail=query.summary(),
            )
        return query

    # ------------------------------------------------------------------
    # 任务2/3 服务入口：retrieve
    # ------------------------------------------------------------------

    def retrieve(
        self,
        *,
        query_id: str,
        retrieval_id: str = "",
        retrieved_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceKnowledgeRetrieval:
        """执行一次**只读**治理知识检索（来源可追溯，任务2/3）。

        检索范围 = 3.8.22 治理案例 + 事实模式 + **已人工采纳**的知识候选
        + 3.8.21 **已人工闭环**的治理事件。全部只读，绝不写回。
        """
        op = "retrieve"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        query = self._get_query_or_raise(query_id, op=op)
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        cases = self._matcher.match_cases(query)
        patterns = self._matcher.match_patterns(query)
        knowledge = self._matcher.match_knowledge(query)
        events = self._matcher.find_related_events(query)
        candidates = [*cases, *patterns, *knowledge, *events]

        sources = sorted({c.source_ref for c in candidates})
        trace = SourceTrace(trace_id=f"trace-{query.query_id}")
        trace.add_entry(f"query:{query.query_id}")
        for ref in sources:
            trace.add_entry(ref)
        # 无命中时也如实出具"空结果"，来源链只记检索行为本身，绝不编造候选凑数。
        if not sources:
            sources = [f"query:{query.query_id}"]

        retrieval = GovernanceKnowledgeRetrieval(
            retrieval_id=str(retrieval_id).strip() or f"ret-{query.query_id}",
            query_id=query.query_id,
            knowledge_candidates=candidates,
            sources=sources,
            trace=trace,
            retrieved_at=retrieved_at,
        )
        self._retrievals[retrieval.retrieval_id] = retrieval
        self._advance_stage(query.query_id, GovernanceRetrievalStage.RETRIEVED, op=op)

        if self._audit is not None:
            self._audit.record_agent_governance_knowledge_retrieval_action(
                record_id=f"gkr-{retrieval.retrieval_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="retrieve_governance_knowledge",
                target=retrieval.retrieval_id,
                detail=retrieval.summary(),
            )
        return retrieval

    # ------------------------------------------------------------------
    # 任务4 服务入口：build_learning_context
    # ------------------------------------------------------------------

    def build_learning_context(
        self,
        *,
        query_id: str,
        retrieval_id: str = "",
        context_id: str = "",
        built_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceLearningContext:
        """把检索结果汇编成**只辅助分析**的学习上下文（任务4）。"""
        op = "build_learning_context"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        query = self._get_query_or_raise(query_id, op=op)
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        rid = str(retrieval_id).strip() or f"ret-{query.query_id}"
        retrieval = self._retrievals.get(rid)
        if retrieval is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到检索结果 {rid!r}：辅助上下文必须建立在真实检索事实上"
                f"（禁止凭空拼材料，红线⑥）"
            )

        buckets: Dict[GovernanceMatchKind, List[GovernanceMatchCandidate]] = {
            GovernanceMatchKind.CASE: [],
            GovernanceMatchKind.PATTERN: [],
            GovernanceMatchKind.KNOWLEDGE: [],
            GovernanceMatchKind.EVENT: [],
        }
        for cand in retrieval.knowledge_candidates:
            buckets[cand.match_kind].append(cand)

        trace = SourceTrace(trace_id=f"ctx-trace-{query.query_id}")
        trace.add_entry(f"retrieval:{retrieval.retrieval_id}")
        for entry in retrieval.trace.entries if retrieval.trace else []:
            trace.add_entry(entry)

        context = GovernanceLearningContext(
            context_id=str(context_id).strip() or f"ctx-{query.query_id}",
            query_id=query.query_id,
            org_id=query.org_id,
            historical_cases=buckets[GovernanceMatchKind.CASE],
            governance_patterns=buckets[GovernanceMatchKind.PATTERN],
            knowledge_candidates=buckets[GovernanceMatchKind.KNOWLEDGE],
            related_events=buckets[GovernanceMatchKind.EVENT],
            source_trace=trace,
            built_at=built_at,
            is_advisory_only=True,
        )
        self._contexts[context.context_id] = context
        self._advance_stage(
            query.query_id, GovernanceRetrievalStage.CONTEXT_BUILT, op=op
        )

        if self._audit is not None:
            self._audit.record_agent_governance_assistance_action(
                record_id=f"gka-ctx-{context.context_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="build_governance_learning_context",
                target=context.context_id,
                detail=context.summary(),
            )
        return context

    # ------------------------------------------------------------------
    # 任务5 服务入口：build_assistance_report
    # ------------------------------------------------------------------

    def build_assistance_report(
        self,
        *,
        query_id: str,
        context_id: str = "",
        report_id: str = "",
        generated_at: str = "",
        generated_by: str = "ai",
        user: object = None,
        resource_category: str = "knowledge",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceAssistanceReport:
        """汇编**禁止建议**的治理辅助报告（任务5）。

        摘要由本方法用**模板化事实句**生成（数量 / 相似度区间 / 来源），
        不引用任何案例的人工处置结论原文 —— 一旦把"别人当时怎么处理的"
        搬进摘要，报告实质就变成了处置建议（红线⑥）。
        """
        op = "build_assistance_report"
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        query = self._get_query_or_raise(query_id, op=op)
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)
            self._ensure_knowledge_visible(user=user, op=op)

        cid = str(context_id).strip() or f"ctx-{query.query_id}"
        context = self._contexts.get(cid)
        if context is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到辅助上下文 {cid!r}：报告必须建立在真实上下文之上（红线⑥）"
            )

        cases = list(context.historical_cases)
        patterns = list(context.governance_patterns)
        sources = sorted({c.source_ref for c in context.all_candidates()})
        if not sources:
            sources = [f"query:{query.query_id}"]

        trace = SourceTrace(trace_id=f"rpt-trace-{query.query_id}")
        trace.add_entry(f"context:{context.context_id}")
        for entry in context.source_trace.entries if context.source_trace else []:
            trace.add_entry(entry)

        top_case = cases[0].similarity if cases else 0.0
        top_pattern = patterns[0].similarity if patterns else 0.0
        factual_summary = (
            f"检索到相似历史案例 {len(cases)} 条（最高重合度 {top_case}），"
            f"相关事实模式 {len(patterns)} 条（最高重合度 {top_pattern}），"
            f"已人工采纳知识 {len(context.knowledge_candidates)} 条，"
            f"已闭环相关事件 {len(context.related_events)} 条。"
            f"以上均为只读事实材料，不含处置结论。"
        )
        fact_lines = [c.render() for c in context.all_candidates()]

        report = GovernanceAssistanceReport(
            report_id=str(report_id).strip() or f"rpt-{query.query_id}",
            query_id=query.query_id,
            org_id=query.org_id,
            matched_cases=cases,
            related_patterns=patterns,
            sources=sources,
            factual_summary=factual_summary,
            fact_lines=fact_lines,
            source_trace=trace,
            generated_by=generated_by,
            generated_at=generated_at,
        )
        self._reports[report.report_id] = report
        self._advance_stage(
            query.query_id, GovernanceRetrievalStage.REPORT_READY, op=op
        )

        if self._audit is not None:
            self._audit.record_agent_governance_assistance_action(
                record_id=f"gka-rpt-{report.report_id}",
                actor_id=actor_id,
                actor_kind=actor_kind or AuditActorKind.AI,
                action="build_governance_assistance_report",
                target=report.report_id,
                detail=report.summary(),
            )
        return report

    # ------------------------------------------------------------------
    # 人工使用节点（红线④/⑥：强制真实人工）
    # ------------------------------------------------------------------

    def mark_human_used(
        self,
        *,
        query_id: str,
        actor_id: str,
        actor_kind: Any,
        report_id: str = "",
        note: str = "",
        used_at: str = "",
        user: object = None,
        resource_category: str = "knowledge",
    ) -> Dict[str, str]:
        """登记「**真实人工**已查阅并自行使用该辅助材料」这一事实（红线④/⑥）。

        这是本层唯一的人工节点，也是唯一的终态：
        - 强制 ``require_human_actor(USER)``，AI 调用直接抛错；
        - ``actor_id`` 命中非人类标识即拒绝；
        - 只登记"人看过、人自己去处理了"，**不承载任何治理动作**：
          本方法不会、也无法触发禁用 Agent、修改策略、关闭任务等任何操作。
        """
        op = "mark_human_used"
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}（红线①）"
            )
        _reject_non_human(actor_id, ctx=f"{op} 的 actor_id")
        query = self._get_query_or_raise(query_id, op=op)
        self._ensure_org_scope(query.org_id, op=op)
        if user is not None:
            self._ensure_access(user=user, resource_category=resource_category)

        rid = str(report_id).strip() or f"rpt-{query.query_id}"
        if rid not in self._reports:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到辅助报告 {rid!r}：禁止对不存在的材料登记人工使用（红线⑥）"
            )
        note_text = str(note).strip()
        _reject_retrieval_markers(note_text, ctx=f"{op} 的 note")

        self._advance_stage(query.query_id, GovernanceRetrievalStage.HUMAN_USED, op=op)
        usage = {
            "query_id": query.query_id,
            "report_id": rid,
            "used_by": str(actor_id).strip(),
            "used_at": str(used_at).strip(),
            "note": note_text,
        }
        self._human_usages[query.query_id] = usage

        if self._audit is not None:
            self._audit.record_agent_governance_assistance_action(
                record_id=f"gka-use-{query.query_id}",
                actor_id=actor_id,
                actor_kind=actor_kind,
                action="human_use_governance_assistance",
                target=rid,
                detail=f"used_by={actor_id} report={rid} advisory_only=true",
            )
        return dict(usage)

    def usage_of(self, query_id: str) -> "Dict[str, str] | None":
        """只读查询某次检索的人工使用登记（不改动任何状态）。"""
        usage = self._human_usages.get(query_id)
        return dict(usage) if usage else None

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def get_query(
        self, query_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceKnowledgeQuery | None":
        """只读获取某条检索请求（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._queries.get(query_id)

    def get_retrieval(
        self, retrieval_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceKnowledgeRetrieval | None":
        """只读获取某次检索结果（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._retrievals.get(retrieval_id)

    def get_learning_context(
        self, context_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceLearningContext | None":
        """只读获取某份辅助学习上下文（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._contexts.get(context_id)

    def get_assistance_report(
        self, report_id: str, *, user: object, resource_category: str = "knowledge"
    ) -> "GovernanceAssistanceReport | None":
        """只读获取某份治理辅助报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._reports.get(report_id)

    def list_queries(
        self, *, user: object, resource_category: str = "knowledge"
    ) -> List[GovernanceKnowledgeQuery]:
        """只读列出本组织内的检索请求（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return [
            q for q in self._queries.values()
            if not self._org_id or q.org_id == self._org_id
        ]


__all__ = [
    "GovernanceKnowledgeQuery",
    "GovernanceMatchKind",
    "GovernanceMatchCandidate",
    "GovernanceKnowledgeRetrieval",
    "GovernanceSimilarityMatcher",
    "GovernanceLearningContext",
    "GovernanceAssistanceReport",
    "GovernanceRetrievalStage",
    "GovernanceKnowledgeRetrievalService",
    "_RETRIEVAL_FORBIDDEN",
]

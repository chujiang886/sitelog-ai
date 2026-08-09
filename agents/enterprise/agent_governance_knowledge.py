"""Enterprise Agent Governance Knowledge & Continuous Improvement Layer（Phase 3.8.22）。

链路：**治理事件 → 人工处理 → 治理经验 → 知识候选 → 人工审核 → 知识沉淀**。

本层建立在 3.8.13~3.8.21 各治理层之上（能力注册 / 可观测性 / 质量 / 成本 /
运行时策略 / 安全风险 / 合规审计 / 治理中枢 / 治理流程与责任闭环）：把 3.8.21
已由**真实人工闭环**的治理任务，沉淀为可复用的**治理案例**与**事实模式**，
再产出**知识候选**，最终只能由**真实人工审核**决定是否沉淀为治理知识。
AI 在本层只能「归纳事实 → 建候选」，绝不能改 Agent、绝不能改治理策略、
绝不能关闭治理任务、绝不能代替治理责任人。

新增（任务1–5）：
- ``GovernanceCase``：治理案例（case_id / source_task_id / agent_id /
  problem_pattern / human_resolution / source_trace / created_at）。
  **要求人工结果来源**：``human_resolution`` 必须非空且由真实人工给出，
  ``resolved_by`` 命中 ai / system / bot / agent / auto 等非人类标识即拒绝；
  ``source_task_id`` / ``source_trace`` 缺失即拒绝（任务1，红线⑥）。
- ``GovernanceKnowledgeCandidate``：治理知识候选（candidate_id / source_case /
  knowledge_type / content / evidence / requires_human_review）。
  **只能候选**：``requires_human_review`` 恒为 True（置 False 即拒绝）；
  构造期状态只能是 ``candidate``；``evidence`` 为空即拒绝（任务2，红线③/④/⑥）。
- ``GovernancePattern``：治理模式（记录风险 / 异常 / 处理模式）。
  **事实归纳，禁止自动策略**：必须有 ≥1 条案例证据支撑；描述命中
  自动改 Agent / 自动改策略 / 自动关闭 / 建议处置语义即拒绝；模型层
  **不提供**任何 ``to_policy`` / ``apply`` / ``enforce`` 能力（任务3，红线③/④/⑤）。
- ``GovernanceImprovementWorkflowService``：治理持续改进工作流服务。
  流程 ``case_created`` → ``candidate_generated`` → ``human_review`` →
  ``accepted`` / ``rejected``。AI 只能走前两步；``start_human_review`` /
  ``accept_candidate`` / ``reject_candidate`` 全部强制
  ``require_human_actor(USER)``（任务4，红线③/④/⑤/⑥）。
- ``GovernanceKnowledgeReport``：治理知识报告（案例 + 模式 + 经验 + 来源链
  ``SourceTrace``）。无来源链即拒绝生成；经验只收录**已人工采纳**的候选
  （任务5，红线⑥）。

红线（fail-closed，复用 3.8.0~3.8.21 基座 + Phase 3.8.22 主理人六条）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved（forbidden 方法名结构性拦截）。
③ 不 AI 自动修改 Agent（``auto_modify_agent`` / ``auto_update_agent`` 及同族方法名
   被 mixin 拦截；案例 / 候选 / 模式文本命中自动改 Agent 语义即拒绝；
   本层不持有任何 Agent 写能力，对注册表 / 权限策略**纯只读**）。
④ 不 AI 自动修改治理策略（``auto_update_policy`` / ``auto_apply_policy`` 及同族
   被拦截；知识候选**永远只是候选**，不会自动变成策略；文本命中改策略语义即拒绝）。
⑤ 不 AI 自动关闭治理任务（``auto_close_task`` / ``close_governance_task`` 等被拦截；
   本层对 3.8.21 ``GovernanceWorkflowService`` **纯只读**，只读取已由人工闭环的事实，
   绝不推进、绝不关闭任何治理任务）。
⑥ 不 AI 代替治理责任人（审计禁止 ``record_human_approval``；案例的人工结论、
   候选的审核结论均强制 ``require_human_actor(USER)``；AI 产出只陈述事实，
   不含处置建议、不含责任判定）。
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

_KNOWLEDGE_FORBIDDEN = (
    # 基座（红线②/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动修改 Agent（主理人明列两项 + 同族收敛）
    "auto_modify_agent",
    "auto_update_agent",
    "modify_agent",
    "update_agent",
    "auto_change_agent",
    "change_agent",
    "auto_patch_agent",
    "patch_agent",
    "auto_upgrade_agent",
    "upgrade_agent",
    "auto_tune_agent",
    "tune_agent",
    "auto_optimize_agent",
    "optimize_agent",
    "auto_retrain_agent",
    "retrain_agent",
    "auto_disable_agent",
    "disable_agent",
    "auto_deprecate_agent",
    "deprecate_agent",
    "auto_configure_agent",
    "configure_agent",
    "auto_rewrite_prompt",
    "rewrite_prompt",
    # 红线④：禁止 AI 自动修改治理策略（主理人明列两项 + 同族收敛）
    "auto_update_policy",
    "auto_apply_policy",
    "update_policy",
    "apply_policy",
    "auto_modify_policy",
    "modify_policy",
    "auto_change_policy",
    "change_policy",
    "auto_create_policy",
    "create_policy",
    "auto_publish_policy",
    "publish_policy",
    "auto_enforce_policy",
    "enforce_policy",
    "auto_promote_knowledge",
    "promote_knowledge_to_policy",
    "auto_adopt_knowledge",
    "adopt_knowledge_automatically",
    "auto_accept_candidate",
    "accept_candidate_automatically",
    "auto_reject_candidate",
    "reject_candidate_automatically",
    "auto_publish_knowledge",
    "publish_knowledge_automatically",
    "auto_change_permission",
    "change_permission",
    "auto_grant_permission",
    "grant_permission",
    # 红线⑤：禁止 AI 自动关闭治理任务
    "auto_close",
    "auto_close_task",
    "close_task",
    "close_governance_task",
    "auto_close_governance_task",
    "auto_complete_task",
    "complete_task",
    "auto_finish_task",
    "finish_task",
    "auto_resolve_task",
    "resolve_task",
    "auto_dismiss_task",
    "dismiss_task",
    "auto_cancel_task",
    "cancel_task",
    "auto_signoff",
    "signoff_task",
    "auto_remediate",
    "auto_fix",
    "auto_resolve",
    # 红线⑥：禁止 AI 代替治理责任人
    "act_as_governance_owner",
    "take_governance_ownership",
    "assume_governance_responsibility",
    "auto_review",
    "auto_review_candidate",
    "review_candidate_automatically",
    "auto_confirm_knowledge",
    "confirm_knowledge_automatically",
    "auto_decide_governance",
    "decide_governance",
    "auto_conclude_case",
    "conclude_case_automatically",
    "auto_recommend",
    "recommend_action",
    "auto_advise",
    "advise_governance",
    "auto_suggest",
    "suggest_governance_action",
)


# 文本中禁止出现的「自动修改 Agent」语义（红线③）。
_AGENT_MODIFY_MARKERS = (
    "auto_modify_agent",
    "auto modify agent",
    "auto_update_agent",
    "auto update agent",
    "auto_upgrade_agent",
    "auto_retrain_agent",
    "auto_disable_agent",
    "automatically modified agent",
    "automatically updated agent",
    "自动修改agent",
    "自动更新agent",
    "自动升级agent",
    "自动禁用agent",
    "自动调整智能体",
    "自动修改智能体",
    "由ai自动修改",
)

# 文本中禁止出现的「自动修改治理策略」语义（红线④）。
_POLICY_MARKERS = (
    "auto_update_policy",
    "auto update policy",
    "auto_apply_policy",
    "auto apply policy",
    "auto_modify_policy",
    "auto_enforce_policy",
    "automatically applied policy",
    "automatically updated policy",
    "自动修改策略",
    "自动更新策略",
    "自动应用策略",
    "自动下发策略",
    "自动生效策略",
    "自动变更权限",
    "自动修改权限",
)

# 文本中禁止出现的「自动关闭治理任务」语义（红线⑤）。
_CLOSURE_MARKERS = (
    "auto_close",
    "auto close",
    "auto_complete_task",
    "auto_resolve_task",
    "automatically closed",
    "自动关闭",
    "自动结案",
    "自动完成任务",
    "自动销项",
)

# 文本中禁止出现的「处置建议 / 代替责任人下判断」语义（红线⑥）。
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

# 非人类标识（红线⑥：人工结论 / 审核人必须真实 USER）。
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
    """拒绝非人类标识（红线⑥：人工结论只能来自真实人工）。

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
                f"治理结论 / 知识审核必须由真实人工 USER 给出（红线⑥）"
            )


def _reject_governance_markers(text: str, *, ctx: str) -> None:
    """统一施加红线③/④/⑤ 三组语义拦截（本层所有自由文本字段共用）。"""
    _reject_markers(
        text, _AGENT_MODIFY_MARKERS,
        ctx=ctx, rule="治理知识只陈述事实，禁止 AI 自动修改 Agent（红线③）",
    )
    _reject_markers(
        text, _POLICY_MARKERS,
        ctx=ctx, rule="治理知识永远只是候选，禁止 AI 自动修改治理策略（红线④）",
    )
    _reject_markers(
        text, _CLOSURE_MARKERS,
        ctx=ctx, rule="本层对治理任务纯只读，禁止 AI 自动关闭治理任务（红线⑤）",
    )


# ---------------------------------------------------------------------------
# 任务1：治理案例（要求人工结果来源）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceCase:
    """治理案例（任务1，**要求人工结果来源**）。

    字段严格对应主理人指令：case_id / source_task_id / agent_id /
    problem_pattern / human_resolution / source_trace / created_at；额外增加
    org_id / resolved_by / recorded_by / source_type 便于隔离与溯源。

    红线约束：
    - ``source_task_id`` 为空即拒绝（案例只能源自 3.8.21 一条**真实治理任务**，
      禁止凭空造案例，红线⑤/⑥）；
    - ``problem_pattern`` 为空即拒绝（案例必须陈述问题事实）；
    - ``human_resolution`` 为空即拒绝（**结论只能来自真实人工处理**，
      AI 不得代填，红线⑥）；
    - ``resolved_by`` 为空或命中 ai / system / bot / agent / auto 等非人类标识
      即拒绝（红线⑥）；
    - ``source_trace`` 不可溯源即拒绝（红线⑥）；
    - ``problem_pattern`` / ``human_resolution`` 命中自动改 Agent / 自动改策略 /
      自动关闭语义即拒绝（红线③/④/⑤）；
    - 模型层**不提供**任何 modify_agent / update_policy / close_task 方法。
    """

    case_id: str
    source_task_id: str = ""
    agent_id: str = ""
    problem_pattern: str = ""
    human_resolution: str = ""
    source_trace: "SourceTrace | None" = None
    created_at: str = ""
    org_id: str = ""
    source_type: str = ""     # 上游治理任务来源类型（只读复制的事实）
    resolved_by: str = ""     # 真实人工处理人（红线⑥）
    recorded_by: str = ""     # 案例登记者（AI 登记时如实记为 ai，不伪装为人工）

    def __post_init__(self) -> None:
        if not str(self.case_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceCase 缺少 case_id：禁止落库无标识的治理案例（红线⑥）"
            )
        if not str(self.source_task_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceCase {self.case_id!r} 缺少 source_task_id："
                f"治理案例必须源自一条真实治理任务，禁止凭空造案例（红线⑤/⑥）"
            )
        if not str(self.problem_pattern).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceCase {self.case_id!r} 缺少 problem_pattern："
                f"案例必须陈述真实问题事实（红线⑥）"
            )
        if not str(self.human_resolution).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceCase {self.case_id!r} 缺少 human_resolution："
                f"案例结论只能来自真实人工处理结果，AI 不得代填（红线⑥）"
            )
        if not str(self.resolved_by).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceCase {self.case_id!r} 缺少 resolved_by："
                f"人工处理结果必须可追溯到真实责任人（红线⑥）"
            )
        _reject_non_human(
            self.resolved_by,
            ctx=f"GovernanceCase {self.case_id!r} 的 resolved_by",
        )
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceCase {self.case_id!r} 无来源链："
                f"禁止落库不可溯源的治理案例（红线⑥）"
            )
        for label, text in (
            ("problem_pattern", self.problem_pattern),
            ("human_resolution", self.human_resolution),
        ):
            _reject_governance_markers(
                text, ctx=f"GovernanceCase {self.case_id!r} 的 {label}"
            )

    @property
    def is_human_resolved(self) -> bool:
        """是否有真实人工处理结论（只读事实，构造期已强制为 True）。"""
        return bool(str(self.human_resolution).strip()) and bool(
            str(self.resolved_by).strip()
        )

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链（不改动任何状态）。"""
        return self.source_trace.render() if self.source_trace else "no_source"

    def summary(self) -> str:
        """只读摘要（**只陈述问题事实与人工结论来源，不含建议**）。"""
        return (
            f"case={self.case_id} task={self.source_task_id} "
            f"agent={self.agent_id or 'n/a'} resolved_by={self.resolved_by} "
            f"trace={self.render_source()}"
        )


# ---------------------------------------------------------------------------
# 任务3：治理模式（事实归纳，禁止自动策略）
# ---------------------------------------------------------------------------

class GovernancePatternKind(str, Enum):
    """治理模式类型（主理人明列三类：风险 / 异常 / 处理）。

    刻意**不提供** ``policy`` / ``rule`` / ``enforcement`` 之类的类型：
    模式只是**事实归纳**，永远不会成为可执行策略（红线④）。
    """

    RISK = "risk"          # 风险模式（同类风险反复出现的事实）
    ANOMALY = "anomaly"    # 异常模式（同类运行异常反复出现的事实）
    HANDLING = "handling"  # 处理模式（人工反复采用的同类处理方式的事实）


@dataclass
class GovernancePattern:
    """治理模式（任务3，**事实归纳，禁止自动策略**）。

    只记录「某类风险 / 异常 / 处理方式在若干真实案例中反复出现」这一事实，
    并给出支撑它的案例证据。

    红线约束：
    - ``description`` 为空即拒绝（模式必须有事实描述）；
    - ``case_ids`` 为空即拒绝（**事实归纳必须有真实案例支撑**，禁止凭空造模式）；
    - ``description`` 命中自动改 Agent / 自动改策略 / 自动关闭语义即拒绝
      （红线③/④/⑤）；
    - ``description`` 命中「建议 / recommend / 应当整改 / 判定责任」等处置建议语义
      即拒绝（红线⑥：AI 只陈述事实，不代替治理责任人下判断）；
    - 模型层**不提供** ``to_policy`` / ``apply`` / ``enforce`` / ``activate``
      等任何把模式变成策略的能力（红线④），``is_policy`` 恒为 False。
    """

    pattern_id: str
    pattern_kind: GovernancePatternKind = GovernancePatternKind.RISK
    description: str = ""
    case_ids: List[str] = field(default_factory=list)
    org_id: str = ""
    agent_id: str = ""
    observed_at: str = ""
    observed_by: str = ""   # 归纳者（AI 归纳时如实记为 ai）
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_kind, GovernancePatternKind):
            self.pattern_kind = GovernancePatternKind(self.pattern_kind)
        if not str(self.pattern_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernancePattern 缺少 pattern_id：禁止落库无标识的治理模式（红线⑥）"
            )
        if not str(self.description).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernancePattern {self.pattern_id!r} 缺少 description："
                f"模式必须给出事实描述（红线⑥）"
            )
        cleaned = [str(c).strip() for c in self.case_ids if str(c).strip()]
        if not cleaned:
            raise EnterpriseRedLineViolationError(
                f"GovernancePattern {self.pattern_id!r} 缺少 case_ids："
                f"治理模式只能由真实案例归纳而来，禁止凭空造模式（红线⑥）"
            )
        self.case_ids = cleaned
        ctx = f"GovernancePattern {self.pattern_id!r} 的 description"
        _reject_governance_markers(self.description, ctx=ctx)
        _reject_markers(
            self.description, _ADVICE_MARKERS,
            ctx=ctx,
            rule="治理模式只做事实归纳，禁止给出处置建议或责任判定（红线⑥）",
        )

    @property
    def is_policy(self) -> bool:
        """恒为 False：模式**永远不是**可执行策略（红线④，只读常量事实）。"""
        return False

    @property
    def occurrence_count(self) -> int:
        """只读支撑案例条数（事实计数，不做任何评级）。"""
        return len(self.case_ids)

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（有来源链或有案例证据即可溯源）。"""
        if self.source_trace is not None and self.source_trace.is_traceable:
            return True
        return bool(self.case_ids)

    def summary(self) -> str:
        """只读摘要（**只陈述模式事实与证据数量，不含策略、不含建议**）。"""
        return (
            f"pattern={self.pattern_id} kind={self.pattern_kind.value} "
            f"cases={self.occurrence_count} agent={self.agent_id or 'n/a'} "
            f"is_policy=False"
        )


# ---------------------------------------------------------------------------
# 任务2：治理知识候选（只能候选）
# ---------------------------------------------------------------------------

class GovernanceKnowledgeType(str, Enum):
    """治理知识类型（**只描述知识是什么事实**，无任何生效语义）。

    刻意**不提供** ``policy`` / ``rule`` / ``mandatory_standard`` 之类的类型：
    本层产出永远只是**候选知识**，不会成为可执行策略（红线④）。
    """

    PROBLEM_PATTERN = "problem_pattern"          # 问题模式事实
    HANDLING_EXPERIENCE = "handling_experience"  # 人工处理经验事实
    PREVENTION_FACT = "prevention_fact"          # 预防性事实（已发生的有效做法）
    GOVERNANCE_LESSON = "governance_lesson"      # 治理教训事实


class GovernanceKnowledgeStatus(str, Enum):
    """治理知识候选状态（**无 AI 终态**）。

    ``candidate`` → ``in_human_review`` → ``accepted`` / ``rejected``。

    枚举中**不存在** ``auto_accepted`` / ``published_by_ai`` 之类的 AI 终态：
    唯一能推进到 ``accepted`` / ``rejected`` 的入口是
    ``GovernanceImprovementWorkflowService.accept_candidate`` /
    ``reject_candidate``，其上均有 ``require_human_actor(USER)`` 守卫（红线⑥）。
    """

    CANDIDATE = "candidate"
    IN_HUMAN_REVIEW = "in_human_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class GovernanceKnowledgeCandidate:
    """治理知识候选（任务2，**只能候选**）。

    字段严格对应主理人指令：candidate_id / source_case / knowledge_type /
    content / evidence / requires_human_review；额外增加 org_id / agent_id /
    status / generated_by / created_at / reviewed_by / reviewed_at /
    review_comment 便于隔离与人工审核事实登记。

    红线约束：
    - ``source_case`` 为空即拒绝（知识必须源自一条真实治理案例，红线⑥）；
    - ``content`` 为空即拒绝；``evidence`` 为空即拒绝（**无证据不成知识**，红线⑥）；
    - ``requires_human_review`` 恒为 True，置 False 即拒绝
      （**候选永远需要人工审核**，红线④/⑥）；
    - 构造期状态只能是 ``candidate``（禁止直接落 accepted / rejected，红线⑥）；
    - 构造期 ``reviewed_by`` / ``reviewed_at`` 必须为空（禁止伪造人工审核事实，红线⑥）；
    - ``content`` 命中自动改 Agent / 自动改策略 / 自动关闭语义即拒绝（红线③/④/⑤）；
    - AI 生成的候选（``generated_by`` 为非人类标识）其 ``content`` 命中处置建议 /
      责任判定语义即拒绝（红线⑥）；
    - 模型层**不提供**任何 accept / reject / publish / promote 方法。
    """

    candidate_id: str
    source_case: str = ""
    knowledge_type: GovernanceKnowledgeType = GovernanceKnowledgeType.PROBLEM_PATTERN
    content: str = ""
    evidence: List[str] = field(default_factory=list)
    requires_human_review: bool = True
    org_id: str = ""
    agent_id: str = ""
    status: GovernanceKnowledgeStatus = GovernanceKnowledgeStatus.CANDIDATE
    generated_by: str = ""    # 生成者（AI 生成时如实记为 ai，不伪装为人工）
    created_at: str = ""
    reviewed_by: str = ""     # 人工审核人（仅由服务层在 USER 守卫下写入）
    reviewed_at: str = ""
    review_comment: str = ""  # 人工审核意见（仅由服务层在 USER 守卫下写入）

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge_type, GovernanceKnowledgeType):
            self.knowledge_type = GovernanceKnowledgeType(self.knowledge_type)
        if not isinstance(self.status, GovernanceKnowledgeStatus):
            self.status = GovernanceKnowledgeStatus(self.status)
        if not str(self.candidate_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceKnowledgeCandidate 缺少 candidate_id："
                "禁止落库无标识的知识候选（红线⑥）"
            )
        if not str(self.source_case).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 缺少 source_case："
                f"治理知识必须源自一条真实治理案例（红线⑥）"
            )
        if not str(self.content).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 缺少 content："
                f"禁止落库空知识候选（红线⑥）"
            )
        cleaned = [str(e).strip() for e in self.evidence if str(e).strip()]
        if not cleaned:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 缺少 evidence："
                f"无证据不成知识，禁止落库不可溯源的知识候选（红线⑥）"
            )
        self.evidence = cleaned
        if self.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 禁止置 "
                f"requires_human_review=False：治理知识候选**永远只是候选**，"
                f"是否沉淀必须由真实人工审核决定（红线④/⑥）"
            )
        if self.status is not GovernanceKnowledgeStatus.CANDIDATE:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 禁止在构造期落 "
                f"{self.status.value}：只能以 candidate 候选态生成，后续状态须由真实人工经 "
                f"start_human_review / accept_candidate / reject_candidate"
                f"(actor_kind=USER) 推进（红线④/⑥）"
            )
        if str(self.reviewed_by).strip() or str(self.reviewed_at).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeCandidate {self.candidate_id!r} 禁止在构造期预填 "
                f"reviewed_by / reviewed_at：人工审核事实只能由真实人工产生（红线⑥）"
            )
        ctx = f"GovernanceKnowledgeCandidate {self.candidate_id!r} 的 content"
        _reject_governance_markers(self.content, ctx=ctx)
        if _looks_non_human(self.generated_by):
            _reject_markers(
                self.content, _ADVICE_MARKERS,
                ctx=ctx,
                rule=(
                    "AI 生成的知识候选只能陈述事实，禁止给出处置建议或责任判定"
                    "（红线⑥）"
                ),
            )

    @property
    def is_candidate_only(self) -> bool:
        """是否仍处于「只是候选」状态（只读事实）。"""
        return self.status is GovernanceKnowledgeStatus.CANDIDATE

    @property
    def is_accepted(self) -> bool:
        """是否已由真实人工采纳（只读事实）。"""
        return self.status is GovernanceKnowledgeStatus.ACCEPTED

    @property
    def evidence_count(self) -> int:
        """只读证据条数。"""
        return len(self.evidence)

    def summary(self) -> str:
        """只读摘要（**只陈述候选事实与证据数量，不含策略语义**）。"""
        return (
            f"candidate={self.candidate_id} case={self.source_case} "
            f"type={self.knowledge_type.value} status={self.status.value} "
            f"evidence={self.evidence_count} requires_human_review=True"
        )


# ---------------------------------------------------------------------------
# 任务5：治理知识报告（案例 + 模式 + 经验 + 来源链）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceKnowledgeReport:
    """治理知识报告（任务5，**强可溯源**）。

    内容严格对应主理人指令四段：
    - **案例**：``cases``（``GovernanceCase`` 列表，均带人工结论）；
    - **模式**：``patterns``（``GovernancePattern`` 列表，事实归纳，非策略）；
    - **经验**：``experiences``（**只收录已由真实人工采纳**的
      ``GovernanceKnowledgeCandidate``）；
    - **来源链**：``source_trace``（``SourceTrace``，空链即拒绝生成）。

    红线约束：
    - ``source_trace`` 不可溯源即拒绝构造（红线⑥）；
    - 三段内容全空即拒绝（禁止输出无事实依据的空报告，红线⑥）；
    - ``experiences`` 中混入未被人工采纳的候选即拒绝
      （**未经人工审核的知识不得进入沉淀报告**，红线④/⑥）；
    - 报告**不含**批准语义、不含策略生效语义、不含处置建议。
    """

    report_id: str
    org_id: str = ""
    agent_id: str = ""
    cases: List[GovernanceCase] = field(default_factory=list)
    patterns: List[GovernancePattern] = field(default_factory=list)
    experiences: List[GovernanceKnowledgeCandidate] = field(default_factory=list)
    generated_at: str = ""
    generated_by: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        if not str(self.report_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceKnowledgeReport 缺少 report_id："
                "禁止落库无标识的治理知识报告（红线⑥）"
            )
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeReport {self.report_id!r} 无来源链："
                f"禁止输出不可溯源的治理知识报告（红线⑥）"
            )
        if not (self.cases or self.patterns or self.experiences):
            raise EnterpriseRedLineViolationError(
                f"GovernanceKnowledgeReport {self.report_id!r} 无任何事实内容："
                f"禁止输出无案例、无模式、无经验的空报告（红线⑥）"
            )
        for exp in self.experiences:
            if not exp.is_accepted:
                raise EnterpriseRedLineViolationError(
                    f"GovernanceKnowledgeReport {self.report_id!r} 拒绝收录候选 "
                    f"{exp.candidate_id!r}（status={exp.status.value}）："
                    f"只有经真实人工审核采纳的知识才能进入沉淀报告（红线④/⑥）"
                )

    @property
    def case_count(self) -> int:
        """只读案例条数。"""
        return len(self.cases)

    @property
    def pattern_count(self) -> int:
        """只读模式条数。"""
        return len(self.patterns)

    @property
    def experience_count(self) -> int:
        """只读已沉淀经验条数（全部已人工采纳）。"""
        return len(self.experiences)

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链（不改动任何状态）。"""
        return self.source_trace.render() if self.source_trace else "no_source"

    def summary(self) -> str:
        """只读摘要（**只陈述事实数量与来源，不含策略、不含建议**）。"""
        return (
            f"knowledge_report={self.report_id} cases={self.case_count} "
            f"patterns={self.pattern_count} experiences={self.experience_count} "
            f"trace={self.render_source()}"
        )


# ---------------------------------------------------------------------------
# 任务4：治理持续改进工作流（人工审核）
# ---------------------------------------------------------------------------

class GovernanceImprovementStage(str, Enum):
    """治理持续改进流程阶段（主理人明列五态）。

    ``case_created`` → ``candidate_generated`` → ``human_review`` →
    ``accepted`` / ``rejected``。

    - ``case_created``：治理案例已从**已人工闭环**的治理任务沉淀（AI 可发起）。
    - ``candidate_generated``：知识候选已生成（AI 可发起，**只能是候选**）。
    - ``human_review``：真实人工开始审核（强制 USER）。
    - ``accepted`` / ``rejected``：真实人工审核结论（强制 USER）。

    枚举中**不存在** ``auto_accepted`` / ``auto_published`` 之类的 AI 终态（红线⑥）。
    """

    CASE_CREATED = "case_created"
    CANDIDATE_GENERATED = "candidate_generated"
    HUMAN_REVIEW = "human_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# 合法阶段迁移（**只前进，不回退**；任何非法迁移直接拒绝）。
_ALLOWED_STAGE_TRANSITIONS: Dict[
    GovernanceImprovementStage, "tuple[GovernanceImprovementStage, ...]"
] = {
    GovernanceImprovementStage.CASE_CREATED: (
        GovernanceImprovementStage.CANDIDATE_GENERATED,
    ),
    GovernanceImprovementStage.CANDIDATE_GENERATED: (
        GovernanceImprovementStage.HUMAN_REVIEW,
    ),
    GovernanceImprovementStage.HUMAN_REVIEW: (
        GovernanceImprovementStage.ACCEPTED,
        GovernanceImprovementStage.REJECTED,
    ),
    GovernanceImprovementStage.ACCEPTED: (),
    GovernanceImprovementStage.REJECTED: (),
}


class GovernanceImprovementWorkflowService(_RedLineForbiddenMixin):
    """Agent 治理知识与持续改进服务（任务1–8 统一入口）。

    承载链路：**治理事件 → 人工处理 → 治理经验 → 知识候选 → 人工审核 → 知识沉淀**。

    方法边界：
    - ``create_case``：**AI 可发起**，但案例必须挂在一条**已由真实人工闭环**的
      3.8.21 治理任务上，且 ``human_resolution`` / ``resolved_by`` 必须来自真实人工
      （红线⑤/⑥）。
    - ``record_pattern``：**AI 可发起**，只做事实归纳，必须有真实案例证据；
      产出物 ``is_policy`` 恒为 False（红线④）。
    - ``generate_candidate``：**AI 可发起**，但只产出 ``candidate`` 候选态，
      ``requires_human_review`` 恒为 True（红线④/⑥）。
    - ``start_human_review`` / ``accept_candidate`` / ``reject_candidate``：
      **强制 ``require_human_actor(USER)``**，AI 无论如何无法自我审核、
      无法采纳知识、无法把知识变成策略（红线④/⑥）。
    - ``build_knowledge_report``：只读汇编，经验段只收录**已人工采纳**的候选。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - **不改 Agent**：不持有任何 modify / update / disable / retrain agent 能力，
      对 ``AgentPermissionPolicy`` 纯只读（红线③）。
    - **不改策略**：不持有任何 policy 写能力，知识候选永不自动生效（红线④）。
    - **不关任务**：对 3.8.21 ``GovernanceWorkflowService`` **纯只读**，
      只读取已闭环事实，绝不推进、绝不关闭（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_modify_agent / auto_update_policy /
      auto_close_task / auto_review 等方法。
    """

    _FORBIDDEN = _KNOWLEDGE_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
        governance_workflow: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceImprovementWorkflowService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        # 只读使用：仅用于访问校验，绝不写任何权限或策略（红线③/④）。
        self._permission_policy = permission_policy
        # 只读消费 3.8.21 治理流程事实；本层绝不推进、绝不关闭任何治理任务（红线⑤）。
        self._governance_workflow = governance_workflow
        self._cases: Dict[str, GovernanceCase] = {}
        self._patterns: Dict[str, GovernancePattern] = {}
        self._candidates: Dict[str, GovernanceKnowledgeCandidate] = {}
        self._reports: Dict[str, GovernanceKnowledgeReport] = {}
        self._stages: Dict[str, GovernanceImprovementStage] = {}

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "knowledge") -> None:
        """治理知识数据访问权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误
        （红线⑥：治理知识受控访问、跨组织隔离）。

        本方法**只读校验**，绝不修改任何权限或策略（红线③/④）。
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
                    f"用户角色无权限访问 Agent 治理知识数据"
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

    # ------------------------------------------------------------------
    # 内部只读工具
    # ------------------------------------------------------------------

    def _lookup_source_task(self, task_id: str) -> "Any | None":
        """**只读**查看 3.8.21 治理任务事实（绝不修改任何状态，红线⑤）。"""
        wf = self._governance_workflow
        if wf is None:
            return None
        tasks = getattr(wf, "_tasks", None)
        if not isinstance(tasks, dict):
            return None
        return tasks.get(task_id)

    def _assert_human_closed_task(self, task_id: str, *, op: str) -> "Any | None":
        """断言来源治理任务已由**真实人工闭环**（只读校验，红线⑤/⑥）。

        未接入 3.8.21 服务时跳过（此时由 ``GovernanceCase`` 自身的
        ``human_resolution`` / ``resolved_by`` 强校验兜底）。
        """
        task = self._lookup_source_task(task_id)
        if task is None:
            return None
        status_value = getattr(getattr(task, "status", None), "value", "")
        if status_value != "completed":
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把未闭环治理任务 {task_id!r}（status={status_value or 'unknown'}）"
                f"沉淀为案例：只有真实人工闭环后的治理事实才能进入知识层，"
                f"且本层绝不推进或关闭任何治理任务（红线⑤/⑥）"
            )
        closed_by = str(getattr(task, "closed_by", "") or "").strip()
        if not closed_by:
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝治理任务 {task_id!r}：缺少真实人工闭环人 closed_by（红线⑥）"
            )
        _reject_non_human(closed_by, ctx=f"{op} 来源治理任务 {task_id!r} 的 closed_by")
        return task

    def _get_case_or_raise(self, case_id: str, *, op: str) -> GovernanceCase:
        """只读取出治理案例，不存在即拒绝（禁止凭空推进流程）。"""
        case = self._cases.get(case_id)
        if case is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到治理案例 {case_id!r}：禁止凭空推进改进流程（红线⑥）"
            )
        return case

    def _get_candidate_or_raise(
        self, candidate_id: str, *, op: str
    ) -> GovernanceKnowledgeCandidate:
        """只读取出知识候选，不存在即拒绝。"""
        cand = self._candidates.get(candidate_id)
        if cand is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到知识候选 {candidate_id!r}：禁止凭空推进人工审核（红线⑥）"
            )
        return cand

    def _advance_stage(
        self, case_id: str, target: GovernanceImprovementStage, *, op: str
    ) -> None:
        """推进改进流程阶段（只前进不回退，非法迁移直接拒绝）。"""
        current = self._stages.get(case_id)
        if current is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 案例 {case_id!r} 尚无改进流程阶段：禁止跳过 case_created（红线⑥）"
            )
        if target not in _ALLOWED_STAGE_TRANSITIONS.get(current, ()):
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把案例 {case_id!r} 从 {current.value} 迁移到 {target.value}："
                f"非法阶段迁移（改进流程只能按 case_created → candidate_generated → "
                f"human_review → accepted/rejected 逐步推进，且审核节点必须由真实人工"
                f"执行，红线④/⑥）"
            )
        self._stages[case_id] = target

    def stage_of(self, case_id: str) -> "GovernanceImprovementStage | None":
        """只读查询某案例当前的改进流程阶段（不改动任何状态）。"""
        return self._stages.get(case_id)

    # ------------------------------------------------------------------
    # 任务4-①：create_case（AI 可登记，但结论必须来自真实人工）
    # ------------------------------------------------------------------

    def create_case(
        self,
        *,
        case_id: str,
        source_task_id: str,
        problem_pattern: str,
        human_resolution: str,
        resolved_by: str,
        agent_id: str = "",
        source_type: str = "",
        created_at: str = "",
        source_refs: "List[str] | None" = None,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceCase:
        """把一条**已由真实人工闭环**的治理任务沉淀为治理案例（红线⑤/⑥）。

        AI 可以发起本方法（只是登记事实），但：
        - 来源任务必须已 ``completed`` 且有真实人工 ``closed_by``（接入 3.8.21 时强校验）；
        - ``human_resolution`` / ``resolved_by`` 必须由真实人工给出，AI 不得代填；
        - 案例必须带可溯源的 ``SourceTrace``。

        本方法**只读**消费 3.8.21 治理任务，绝不推进、绝不关闭任何任务（红线⑤）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下沉淀治理案例（红线①）"
            )
        if case_id in self._cases:
            raise EnterpriseRedLineViolationError(
                f"create_case 拒绝重复创建治理案例 {case_id!r}：禁止覆盖既有治理事实（红线⑥）"
            )
        task = self._assert_human_closed_task(source_task_id, op="create_case")
        trace = SourceTrace(trace_id=f"trace-case-{case_id}")
        trace.add_entry(f"governance_task:{source_task_id}")
        if task is not None:
            trace.add_entry(
                f"task_source:{getattr(getattr(task, 'source_type', None), 'value', '')}"
                f":{getattr(task, 'source_id', '')}"
            )
            trace.add_entry(f"human_closure:{getattr(task, 'closed_by', '')}")
        for ref in source_refs or []:
            trace.add_entry(str(ref))
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"create_case 拒绝创建案例 {case_id!r}：无任何事实来源（红线⑥）"
            )
        resolved_type = source_type or (
            getattr(getattr(task, "source_type", None), "value", "") if task else ""
        )
        case = GovernanceCase(
            case_id=case_id,
            source_task_id=source_task_id,
            agent_id=agent_id or (getattr(task, "agent_id", "") if task else ""),
            problem_pattern=problem_pattern,
            human_resolution=human_resolution,
            source_trace=trace,
            created_at=created_at,
            org_id=self._org_id,
            source_type=resolved_type,
            resolved_by=resolved_by,
            recorded_by=actor_id,
        )
        self._cases[case_id] = case
        self._stages[case_id] = GovernanceImprovementStage.CASE_CREATED
        if self._audit is not None:
            self._audit.record_agent_governance_case_action(
                record_id=f"agent-governance-case-{case_id}",
                actor_id=actor_id,
                action="record_governance_case_from_human_closure",
                target=case_id,
                detail=case.summary(),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return case

    # ------------------------------------------------------------------
    # 任务4-②：record_pattern（事实归纳，永不成为策略）
    # ------------------------------------------------------------------

    def record_pattern(
        self,
        *,
        pattern_id: str,
        pattern_kind: "GovernancePatternKind | str",
        description: str,
        case_ids: List[str],
        agent_id: str = "",
        observed_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernancePattern:
        """归纳一条治理模式（**事实归纳，禁止自动策略**，红线④）。

        AI 可以发起本方法，但产出物只是**事实归纳**：必须有真实案例证据，
        ``is_policy`` 恒为 False，且模型层不提供任何把模式变成策略的能力。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下归纳治理模式（红线①）"
            )
        if pattern_id in self._patterns:
            raise EnterpriseRedLineViolationError(
                f"record_pattern 拒绝重复创建治理模式 {pattern_id!r}："
                f"禁止覆盖既有治理事实（红线⑥）"
            )
        missing = [c for c in (case_ids or []) if c not in self._cases]
        if missing:
            raise EnterpriseRedLineViolationError(
                f"record_pattern 拒绝归纳模式 {pattern_id!r}：案例证据 {missing!r} 不存在，"
                f"治理模式只能由真实案例归纳而来（红线⑥）"
            )
        trace = SourceTrace(trace_id=f"trace-pattern-{pattern_id}")
        for cid in case_ids or []:
            trace.add_entry(f"case:{cid}")
        pattern = GovernancePattern(
            pattern_id=pattern_id,
            pattern_kind=pattern_kind,
            description=description,
            case_ids=list(case_ids or []),
            org_id=self._org_id,
            agent_id=agent_id,
            observed_at=observed_at,
            observed_by=actor_id,
            source_trace=trace,
        )
        self._patterns[pattern_id] = pattern
        if self._audit is not None:
            self._audit.record_agent_governance_knowledge_action(
                record_id=f"agent-governance-pattern-{pattern_id}",
                actor_id=actor_id,
                action="record_governance_pattern_fact",
                target=pattern_id,
                detail=pattern.summary(),
                ts=observed_at,
                actor_kind=actor_kind,
            )
        return pattern

    # ------------------------------------------------------------------
    # 任务4-③：generate_candidate（AI 只能产候选）
    # ------------------------------------------------------------------

    def generate_candidate(
        self,
        *,
        candidate_id: str,
        source_case: str,
        knowledge_type: "GovernanceKnowledgeType | str",
        content: str,
        evidence: "List[str] | None" = None,
        agent_id: str = "",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceKnowledgeCandidate:
        """从治理案例生成**知识候选**（**只能候选**，红线④/⑥）。

        AI 可以发起本方法，但产出物在结构上只能是 ``candidate`` 候选态：
        ``requires_human_review`` 恒为 True，``reviewed_by`` / ``reviewed_at``
        构造期必须为空。是否沉淀为治理知识只能由真实人工审核决定。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成知识候选（红线①）"
            )
        if candidate_id in self._candidates:
            raise EnterpriseRedLineViolationError(
                f"generate_candidate 拒绝重复创建知识候选 {candidate_id!r}："
                f"禁止覆盖既有治理事实（红线⑥）"
            )
        case = self._get_case_or_raise(source_case, op="generate_candidate")
        refs = [str(e).strip() for e in (evidence or []) if str(e).strip()]
        if not refs:
            refs = [f"case:{case.case_id}", f"governance_task:{case.source_task_id}"]
        candidate = GovernanceKnowledgeCandidate(
            candidate_id=candidate_id,
            source_case=source_case,
            knowledge_type=knowledge_type,
            content=content,
            evidence=refs,
            org_id=self._org_id,
            agent_id=agent_id or case.agent_id,
            generated_by=actor_id,
            created_at=created_at,
        )
        self._candidates[candidate_id] = candidate
        self._advance_stage(
            source_case,
            GovernanceImprovementStage.CANDIDATE_GENERATED,
            op="generate_candidate",
        )
        if self._audit is not None:
            self._audit.record_agent_governance_knowledge_action(
                record_id=f"agent-governance-knowledge-{candidate_id}",
                actor_id=actor_id,
                action="generate_governance_knowledge_candidate",
                target=candidate_id,
                detail=candidate.summary(),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return candidate

    # ------------------------------------------------------------------
    # 任务4-④：start_human_review（必须真实 USER）
    # ------------------------------------------------------------------

    def start_human_review(
        self,
        *,
        candidate_id: str,
        actor_kind: Any,
        actor_id: str,
        timestamp: str = "",
    ) -> GovernanceKnowledgeCandidate:
        """由**真实人工**开始审核知识候选（红线⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError`` —— AI 永远无法自我审核。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推进知识审核（红线①）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "start_human_review 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        _reject_non_human(actor_id, ctx="start_human_review 的 actor_id")
        cand = self._get_candidate_or_raise(candidate_id, op="start_human_review")
        if cand.status is not GovernanceKnowledgeStatus.CANDIDATE:
            raise EnterpriseRedLineViolationError(
                f"start_human_review 拒绝重复审核 {candidate_id!r}"
                f"（status={cand.status.value}）：审核流程只前进不回退（红线⑥）"
            )
        self._advance_stage(
            cand.source_case,
            GovernanceImprovementStage.HUMAN_REVIEW,
            op="start_human_review",
        )
        cand.status = GovernanceKnowledgeStatus.IN_HUMAN_REVIEW
        if self._audit is not None:
            self._audit.record_agent_governance_improvement_action(
                record_id=f"agent-governance-improvement-review-{candidate_id}",
                actor_id=actor_id,
                action="human_start_knowledge_review",
                target=candidate_id,
                detail=cand.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return cand

    # ------------------------------------------------------------------
    # 任务4-⑤：accept_candidate / reject_candidate（唯一终态入口，必须真实 USER）
    # ------------------------------------------------------------------

    def _conclude_review(
        self,
        *,
        candidate_id: str,
        actor_kind: Any,
        actor_id: str,
        review_comment: str,
        timestamp: str,
        target_status: GovernanceKnowledgeStatus,
        target_stage: GovernanceImprovementStage,
        op: str,
        audit_action: str,
    ) -> GovernanceKnowledgeCandidate:
        """内部：人工审核结论统一守卫（USER 强制 + 人工意见必填，红线⑥）。"""
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                f"safety_invariants_ok() 失败：禁止在启用态下{op}知识候选（红线①）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                f"{op} 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        _reject_non_human(actor_id, ctx=f"{op} 的 actor_id")
        if not str(review_comment).strip():
            raise EnterpriseRedLineViolationError(
                f"{op} 必须由人工填写 review_comment："
                f"AI 不得代替治理责任人下审核结论（红线⑥）"
            )
        _reject_governance_markers(
            review_comment, ctx=f"{op} 的 review_comment"
        )
        cand = self._get_candidate_or_raise(candidate_id, op=op)
        if cand.status is not GovernanceKnowledgeStatus.IN_HUMAN_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝对 {candidate_id!r}（status={cand.status.value}）下结论："
                f"必须先由真实人工 start_human_review(actor_kind=USER)（红线⑥）"
            )
        self._advance_stage(cand.source_case, target_stage, op=op)
        cand.status = target_status
        cand.reviewed_by = actor_id
        cand.reviewed_at = timestamp
        cand.review_comment = review_comment
        if self._audit is not None:
            self._audit.record_agent_governance_improvement_action(
                record_id=f"agent-governance-improvement-{target_status.value}-{candidate_id}",
                actor_id=actor_id,
                action=audit_action,
                target=candidate_id,
                detail=cand.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return cand

    def accept_candidate(
        self,
        *,
        candidate_id: str,
        actor_kind: Any,
        actor_id: str,
        review_comment: str,
        timestamp: str = "",
    ) -> GovernanceKnowledgeCandidate:
        """由**真实人工**采纳知识候选（红线④/⑥）。

        这是**唯一**能把候选推进到 ``accepted`` 的入口，
        ``require_human_actor(actor_kind)`` 强制。采纳只表示「该事实经验被人工确认」，
        **不产生任何策略效力**：本层不持有任何 policy 写能力（红线④）。
        """
        return self._conclude_review(
            candidate_id=candidate_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            review_comment=review_comment,
            timestamp=timestamp,
            target_status=GovernanceKnowledgeStatus.ACCEPTED,
            target_stage=GovernanceImprovementStage.ACCEPTED,
            op="accept_candidate",
            audit_action="human_accept_governance_knowledge",
        )

    def reject_candidate(
        self,
        *,
        candidate_id: str,
        actor_kind: Any,
        actor_id: str,
        review_comment: str,
        timestamp: str = "",
    ) -> GovernanceKnowledgeCandidate:
        """由**真实人工**驳回知识候选（红线⑥）。

        与 ``accept_candidate`` 对称，``require_human_actor(actor_kind)`` 强制。
        """
        return self._conclude_review(
            candidate_id=candidate_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            review_comment=review_comment,
            timestamp=timestamp,
            target_status=GovernanceKnowledgeStatus.REJECTED,
            target_stage=GovernanceImprovementStage.REJECTED,
            op="reject_candidate",
            audit_action="human_reject_governance_knowledge",
        )

    # ------------------------------------------------------------------
    # 任务5：治理知识报告（只读汇编，强可溯源）
    # ------------------------------------------------------------------

    def build_knowledge_report(
        self,
        *,
        user: object,
        report_id: str,
        agent_id: str = "",
        generated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
        resource_category: str = "knowledge",
    ) -> GovernanceKnowledgeReport:
        """汇编治理知识报告（案例 + 模式 + 经验 + 来源链，红线⑥）。

        **只读汇编**：经验段只收录已由真实人工采纳（``accepted``）的候选；
        无来源链即拒绝生成；报告不含任何策略生效语义与处置建议。
        """
        self._ensure_access(user=user, resource_category=resource_category)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成治理知识报告（红线①）"
            )
        cases = [
            c for c in self._cases.values()
            if not agent_id or c.agent_id == agent_id
        ]
        patterns = [
            p for p in self._patterns.values()
            if not agent_id or p.agent_id == agent_id
        ]
        experiences = [
            k for k in self._candidates.values()
            if k.is_accepted and (not agent_id or k.agent_id == agent_id)
        ]
        trace = SourceTrace(trace_id=f"trace-knowledge-report-{report_id}")
        for c in cases:
            trace.add_entry(f"case:{c.case_id}")
        for p in patterns:
            trace.add_entry(f"pattern:{p.pattern_id}")
        for k in experiences:
            trace.add_entry(f"accepted_knowledge:{k.candidate_id}")
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"build_knowledge_report 拒绝生成 {report_id!r}：无任何事实来源，"
                f"禁止输出不可溯源的治理知识报告（红线⑥）"
            )
        report = GovernanceKnowledgeReport(
            report_id=report_id,
            org_id=self._org_id,
            agent_id=agent_id,
            cases=cases,
            patterns=patterns,
            experiences=experiences,
            generated_at=generated_at,
            generated_by=actor_id,
            source_trace=trace,
        )
        self._reports[report_id] = report
        if self._audit is not None:
            self._audit.record_agent_governance_knowledge_action(
                record_id=f"agent-governance-knowledge-report-{report_id}",
                actor_id=actor_id,
                action="build_governance_knowledge_report",
                target=report_id,
                detail=report.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return report

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def list_cases(
        self,
        *,
        user: object,
        agent_id: str = "",
        source_task_id: str = "",
        resource_category: str = "knowledge",
    ) -> List[GovernanceCase]:
        """只读列出治理案例（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._cases.values())
        if agent_id:
            items = [c for c in items if c.agent_id == agent_id]
        if source_task_id:
            items = [c for c in items if c.source_task_id == source_task_id]
        return items

    def list_patterns(
        self,
        *,
        user: object,
        pattern_kind: "GovernancePatternKind | str | None" = None,
        resource_category: str = "knowledge",
    ) -> List[GovernancePattern]:
        """只读列出治理模式（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._patterns.values())
        if pattern_kind is not None:
            kind = (
                pattern_kind
                if isinstance(pattern_kind, GovernancePatternKind)
                else GovernancePatternKind(pattern_kind)
            )
            items = [p for p in items if p.pattern_kind is kind]
        return items

    def list_candidates(
        self,
        *,
        user: object,
        status: "GovernanceKnowledgeStatus | str | None" = None,
        source_case: str = "",
        resource_category: str = "knowledge",
    ) -> List[GovernanceKnowledgeCandidate]:
        """只读列出知识候选（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._candidates.values())
        if status is not None:
            st = (
                status
                if isinstance(status, GovernanceKnowledgeStatus)
                else GovernanceKnowledgeStatus(status)
            )
            items = [k for k in items if k.status is st]
        if source_case:
            items = [k for k in items if k.source_case == source_case]
        return items

    def get_knowledge_report(
        self,
        *,
        user: object,
        report_id: str,
        resource_category: str = "knowledge",
    ) -> "GovernanceKnowledgeReport | None":
        """只读获取某份治理知识报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._reports.get(report_id)


__all__ = [
    "GovernanceCase",
    "GovernancePatternKind",
    "GovernancePattern",
    "GovernanceKnowledgeType",
    "GovernanceKnowledgeStatus",
    "GovernanceKnowledgeCandidate",
    "GovernanceKnowledgeReport",
    "GovernanceImprovementStage",
    "GovernanceImprovementWorkflowService",
    "_KNOWLEDGE_FORBIDDEN",
]

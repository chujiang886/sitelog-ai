"""Enterprise Agent Governance Intelligence & Control Center Layer（Phase 3.8.20）。

链路：**治理数据 → 统一汇聚 → 治理洞察 → 人工管理**。

本层是 3.8.13~3.8.19 各治理层（能力注册 / 可观测性 / 质量 / 成本 / 运行时策略 /
安全风险 / 合规审计）之上的**只读汇聚中枢**：它把散落在各层的治理事实统一汇总、
统一呈现、统一给出**事实型**洞察，最终把一切处置权交还给真实的人工治理责任人。

新增（任务1–5）：
- ``GovernanceWidgetKind`` / ``GovernanceVisibility`` / ``GovernanceWidget`` /
  ``AgentGovernanceDashboard``：治理看板（dashboard_id / org_id / widgets /
  visibility / created_at）。**只展示事实**：widget 必须有 source，且任何带
  控制/处置/批准语义的标题或事实文本直接拒绝落库（任务1）。
- ``AgentHealthOverview``：健康总览（运行 / 质量 / 成本 / 安全四类事实）。
  **禁止自动评级**：模型层无 rating / grade / score_level 字段，且事实键名命中
  评级语义（rating / grade / rank / verdict / judgement ...）即拒绝（任务2，红线③）。
- ``RiskOverviewStatus`` / ``AgentRiskOverview``：风险总览（安全风险候选 +
  合规风险候选 + 状态）。**禁止自动处理**：构造期只能是
  ``pending_human_review``，``requires_human_handling`` 恒为 True，
  推进状态强制 ``require_human_actor(USER)``（任务3，红线④）。
- ``AgentGovernanceReport``：治理报告（observability / quality / cost /
  security / compliance 五段事实 + ``SourceTrace``）。无来源链即拒绝生成
  （任务4，红线⑥）。
- ``GovernanceInsightKind`` / ``GovernanceTrendDirection`` /
  ``AgentGovernanceInsight``：治理洞察。**只输出事实趋势 / 异常候选 / 来源**，
  枚举与字段刻意**不含**任何 recommendation / advice / suggestion 态，
  且文本命中建议语义即拒绝（任务5，红线⑤/⑥）。
- ``AgentGovernanceAggregator``：统一汇聚器。**纯只读**消费上游五层的
  ``list_*`` 查询（权限隔离由上游各层自身把关），绝不写、绝不改上游任何状态。
- ``AgentGovernanceCenterService``：治理中枢聚合服务，承载看板创建 / 健康总览 /
  风险总览 / 治理报告 / 治理洞察 / 人工处置 / 只读查询；接入身份层 +
  ``AgentPermissionPolicy``（治理数据隔离，默认拒绝）+ ``AgentRuntimeGovernanceService``
  （只读）；联动审计（AGENT_GOVERNANCE_DASHBOARD / AGENT_GOVERNANCE_REPORT /
  AGENT_GOVERNANCE_INSIGHT，任务6）。

红线（fail-closed，复用 3.8.0~3.8.19 基座 + 3.8.20 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved。
③ 不 AI 自动控制 Agent（``auto_disable`` / ``auto_modify`` / ``auto_upgrade`` /
   ``auto_policy_change`` 及同族方法名被 mixin 拦截；中枢层不持有任何写上游能力）。
④ 不 AI 自动处理风险（``auto_handle_risk`` / ``auto_resolve_risk`` /
   ``auto_mitigate`` 等被拦截；风险总览恒为「待人工处理」，处置强制 USER）。
⑤ 不 AI 自动判定合规（``auto_judge_compliance`` / ``auto_certify_compliance``
   等被拦截；洞察层无合规结论态，只有事实趋势与异常候选）。
⑥ 不 AI 代替治理责任人（审计禁止 ``record_human_approval``；处置节点强制
   ``require_human_actor(USER)``；看板/总览/报告/洞察只陈述事实，不含治理建议）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_runtime_policy import AgentRuntimeGovernanceService
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

_GOVERNANCE_FORBIDDEN = (
    # 基座（红线②/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动控制 Agent（主理人明列四项 + 同族收敛）
    "auto_disable",
    "auto_modify",
    "auto_upgrade",
    "auto_policy_change",
    "auto_disable_agent",
    "disable_agent",
    "auto_enable_agent",
    "enable_agent",
    "auto_modify_agent",
    "modify_agent",
    "auto_upgrade_agent",
    "upgrade_agent",
    "auto_downgrade_agent",
    "downgrade_agent",
    "auto_restart_agent",
    "restart_agent",
    "auto_stop_agent",
    "stop_agent",
    "auto_control_agent",
    "control_agent",
    "auto_deploy_agent",
    "deploy_agent",
    "auto_rollback_agent",
    "rollback_agent",
    "auto_change_policy",
    "change_policy",
    "auto_modify_policy",
    "modify_policy",
    "auto_update_policy",
    "update_policy",
    "auto_apply_policy",
    "apply_policy",
    # 红线④：禁止 AI 自动处理风险
    "auto_handle_risk",
    "handle_risk",
    "auto_resolve_risk",
    "resolve_risk",
    "auto_close_risk",
    "close_risk",
    "auto_dismiss_risk",
    "dismiss_risk",
    "auto_mitigate",
    "mitigate_risk",
    "auto_remediate",
    "remediate_risk",
    "auto_triage_risk",
    "triage_risk",
    "auto_accept_risk",
    "accept_risk",
    "auto_waive_risk",
    "waive_risk",
    # 红线⑤：禁止 AI 自动判定合规
    "auto_judge_compliance",
    "judge_compliance",
    "auto_determine_compliance",
    "determine_compliance",
    "auto_certify_compliance",
    "certify_compliance",
    "auto_attest",
    "attest_compliance",
    "auto_clear_compliance",
    "clear_compliance",
    "auto_declare_compliant",
    "declare_compliant",
    "auto_violate",
    "auto_penalty",
    # 红线⑥：禁止 AI 代替治理责任人
    "act_as_governance_owner",
    "take_governance_ownership",
    "assume_governance_responsibility",
    "auto_govern",
    "auto_govern_agent",
    "auto_decide_governance",
    "decide_governance",
    "auto_recommend",
    "recommend_action",
    "auto_advise",
    "advise_governance",
    "auto_suggest",
    "suggest_governance_action",
)


# 事实键名中禁止出现的「评级」语义（红线③：禁止 AI 自动评级）。
# 说明：原始度量事实（latency_ms / token_cost / error_count 等）不受影响，
# 只拦截把 Agent「定性分级」的键名。
_RATING_MARKERS = (
    "rating",
    "grade",
    "rank",
    "verdict",
    "judgement",
    "judgment",
    "评级",
    "评分等级",
    "定级",
)

# 文本中禁止出现的「治理建议」语义（红线⑤/⑥：洞察只陈述事实，不给建议）。
_ADVICE_MARKERS = (
    "recommend",
    "recommendation",
    "advice",
    "advise",
    "suggest",
    "suggestion",
    "should be",
    "must be disabled",
    "建议",
    "应当",
    "应该",
    "推荐",
    "宜采取",
)

# 文本中禁止出现的「控制/处置」语义（红线③/④：看板只展示事实）。
_CONTROL_MARKERS = (
    "disable agent",
    "shutdown agent",
    "terminate agent",
    "auto disable",
    "auto upgrade",
    "auto modify",
    "approve",
    "禁用该agent",
    "自动禁用",
    "自动升级",
    "自动处置",
    "自动批准",
)


def _reject_markers(text: str, markers: "tuple[str, ...]", *, ctx: str, rule: str) -> None:
    """命中语义标记即抛红线违例（只读校验，不改写任何文本）。"""
    lowered = str(text).lower()
    for marker in markers:
        if marker.lower() in lowered:
            raise EnterpriseRedLineViolationError(
                f"{ctx} 命中禁止语义 {marker!r}：{rule}"
            )


# ---------------------------------------------------------------------------
# 任务1：治理看板（只展示事实）
# ---------------------------------------------------------------------------

class GovernanceWidgetKind(str, Enum):
    """看板组件类型（**只描述展示的是哪一类事实**，无任何控制类型）。

    刻意**不提供** ``action`` / ``control`` / ``approval`` 等可操作组件类型：
    看板在结构上只能「展示」，不能「操作」（红线③）。
    """

    OBSERVABILITY_FACT = "observability_fact"   # 运行事实
    QUALITY_FACT = "quality_fact"               # 质量事实
    COST_FACT = "cost_fact"                     # 成本事实
    SECURITY_FACT = "security_fact"             # 安全事实
    COMPLIANCE_FACT = "compliance_fact"         # 合规事实
    RISK_CANDIDATE_FACT = "risk_candidate_fact" # 风险候选事实（仅陈列，不处置）


class GovernanceVisibility(str, Enum):
    """治理看板可见性（与权限隔离配合，默认最小范围）。"""

    PRIVATE = "private"   # 仅创建者可见
    ROLE = "role"         # 指定角色可见
    ORG = "org"           # 组织内可见


@dataclass
class GovernanceWidget:
    """看板组件（**只展示事实**，任务1）。

    红线（③/⑥）：
    - ``source`` 为空即拒绝落库（禁止无源的看板事实）；
    - ``title`` / ``facts`` 命中控制语义（自动禁用 / 自动升级 / 批准 ...）即拒绝；
    - 模型层不提供任何 execute / control / apply 方法。
    """

    widget_id: str
    kind: GovernanceWidgetKind = GovernanceWidgetKind.OBSERVABILITY_FACT
    title: str = ""
    source: str = ""
    facts: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GovernanceWidgetKind):
            self.kind = GovernanceWidgetKind(self.kind)
        if not str(self.title).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceWidget {self.widget_id!r} 缺少 title："
                f"禁止落库无标题的看板组件（红线⑥）"
            )
        if not str(self.source).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceWidget {self.widget_id!r} 缺少 source："
                f"看板只展示可溯源事实，禁止 AI 编造展示内容（红线⑥）"
            )
        _reject_markers(
            self.title,
            _CONTROL_MARKERS,
            ctx=f"GovernanceWidget {self.widget_id!r} 的 title",
            rule="看板只展示事实，禁止承载任何控制/处置/批准语义（红线③）",
        )
        for key, value in self.facts.items():
            _reject_markers(
                f"{key}={value}",
                _CONTROL_MARKERS,
                ctx=f"GovernanceWidget {self.widget_id!r} 的 facts[{key!r}]",
                rule="看板只展示事实，禁止承载任何控制/处置/批准语义（红线③）",
            )

    def summary(self) -> str:
        """只读摘要（不改动任何状态）。"""
        return (
            f"widget_id={self.widget_id};kind={self.kind.value};"
            f"title={self.title};source={self.source};facts={len(self.facts)}"
        )


@dataclass
class AgentGovernanceDashboard:
    """Agent 治理看板（任务1，**只展示事实**）。

    字段严格对应：dashboard_id / org_id / widgets / visibility / created_at；
    额外增加 name / created_by 便于识别与留痕。

    红线（③/⑥）：
    - 看板**没有任何执行能力**：不提供 execute / control / disable / upgrade 方法；
    - 组件必须有源（``GovernanceWidget.__post_init__`` 强制）；
    - 空看板拒绝落库（禁止输出没有任何事实依据的看板）。
    """

    dashboard_id: str
    org_id: str = ""
    widgets: List[GovernanceWidget] = field(default_factory=list)
    visibility: GovernanceVisibility = GovernanceVisibility.PRIVATE
    created_at: str = ""
    name: str = ""
    created_by: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.visibility, GovernanceVisibility):
            self.visibility = GovernanceVisibility(self.visibility)
        if not self.widgets:
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceDashboard {self.dashboard_id!r} 无任何 widget："
                f"禁止落库没有事实依据的空看板（红线⑥）"
            )
        for w in self.widgets:
            if not isinstance(w, GovernanceWidget):
                raise EnterpriseRedLineViolationError(
                    f"AgentGovernanceDashboard {self.dashboard_id!r} 含非法组件："
                    f"widgets 只接受 GovernanceWidget（红线③）"
                )

    @property
    def widget_count(self) -> int:
        """只读组件数量。"""
        return len(self.widgets)

    def summary(self) -> str:
        """只读摘要（只陈述事实，不含任何治理结论）。"""
        return (
            f"dashboard_id={self.dashboard_id};org_id={self.org_id};"
            f"widgets={self.widget_count};visibility={self.visibility.value};"
            f"created_at={self.created_at}"
        )


# ---------------------------------------------------------------------------
# 任务2：健康总览（禁止自动评级）
# ---------------------------------------------------------------------------

@dataclass
class AgentHealthOverview:
    """Agent 健康总览（任务2，**只汇总事实，禁止自动评级**）。

    汇总四类上游事实：运行（observability）/ 质量（quality）/ 成本（cost）/
    安全（security）。

    红线③（禁止 AI 自动评级）：
    - 模型层**没有** rating / grade / health_level / overall_score 等定级字段；
    - 任一事实键名命中评级语义（rating / grade / rank / verdict / 评级 ...）
      直接抛 ``EnterpriseRedLineViolationError``；
    - 不提供任何 evaluate / rate / grade / rank 方法。

    「这个 Agent 健不健康」的定性只能由真实治理责任人依职权作出（红线⑥）。
    """

    overview_id: str
    agent_id: str = ""
    org_id: str = ""
    runtime_facts: Dict[str, Any] = field(default_factory=dict)
    quality_facts: Dict[str, Any] = field(default_factory=dict)
    cost_facts: Dict[str, Any] = field(default_factory=dict)
    security_facts: Dict[str, Any] = field(default_factory=dict)
    source_trace: "SourceTrace | None" = None
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not str(self.agent_id).strip():
            raise EnterpriseRedLineViolationError(
                f"AgentHealthOverview {self.overview_id!r} 缺少 agent_id："
                f"禁止落库无主体的健康事实（红线⑥）"
            )
        groups = (
            ("runtime_facts", self.runtime_facts),
            ("quality_facts", self.quality_facts),
            ("cost_facts", self.cost_facts),
            ("security_facts", self.security_facts),
        )
        for group_name, facts in groups:
            for key in facts:
                _reject_markers(
                    str(key),
                    _RATING_MARKERS,
                    ctx=(
                        f"AgentHealthOverview {self.overview_id!r} 的 "
                        f"{group_name}[{key!r}]"
                    ),
                    rule="禁止 AI 自动评级 Agent，健康总览只汇总原始事实（红线③）",
                )
        if self.source_trace is not None and not isinstance(self.source_trace, SourceTrace):
            raise EnterpriseRedLineViolationError(
                f"AgentHealthOverview {self.overview_id!r} 的 source_trace 非法："
                f"只接受 SourceTrace（红线⑥）"
            )

    @property
    def is_traceable(self) -> bool:
        """是否具备可溯源来源（无来源链视为不可溯源）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def fact_count(self) -> int:
        """只读事实总数（四类之和）。"""
        return (
            len(self.runtime_facts)
            + len(self.quality_facts)
            + len(self.cost_facts)
            + len(self.security_facts)
        )

    def summary(self) -> str:
        """只读摘要（**不含任何评级、结论或建议**）。"""
        return (
            f"overview_id={self.overview_id};agent_id={self.agent_id};"
            f"runtime={len(self.runtime_facts)};quality={len(self.quality_facts)};"
            f"cost={len(self.cost_facts)};security={len(self.security_facts)};"
            f"source={self.source_trace.render() if self.source_trace else 'no_source'}"
        )


# ---------------------------------------------------------------------------
# 任务3：风险总览（禁止自动处理）
# ---------------------------------------------------------------------------

class RiskOverviewStatus(str, Enum):
    """风险总览状态（任务3，**刻意无 AI 可达终态**）。

    ``pending_human_review → under_human_review → handled_by_human``。

    红线④：AI 不得自动处理风险 —— 构造期只允许 ``pending_human_review``，
    后两态只能由真实人工经 ``AgentGovernanceCenterService.human_handle_risk_overview``
    在 ``require_human_actor(USER)`` 守卫下推进。枚举中**不存在**
    ``auto_resolved`` / ``dismissed_by_ai`` 之类的 AI 处置态。
    """

    PENDING_HUMAN_REVIEW = "pending_human_review"
    UNDER_HUMAN_REVIEW = "under_human_review"
    HANDLED_BY_HUMAN = "handled_by_human"


@dataclass
class AgentRiskOverview:
    """Agent 风险总览（任务3，**只汇总候选，禁止自动处理**）。

    汇总两类上游风险候选：安全风险候选（3.8.18）+ 合规风险候选（3.8.19）。

    红线④（禁止 AI 自动处理风险）：
    - ``requires_human_handling`` 恒为 True，模型层禁止置 False；
    - 构造期状态只能是 ``PENDING_HUMAN_REVIEW``；
    - 模型层不提供任何 resolve / close / dismiss / mitigate 方法。
    """

    overview_id: str
    agent_id: str = ""
    org_id: str = ""
    security_risk_ids: List[str] = field(default_factory=list)
    compliance_risk_ids: List[str] = field(default_factory=list)
    status: RiskOverviewStatus = RiskOverviewStatus.PENDING_HUMAN_REVIEW
    requires_human_handling: bool = True
    source_trace: "SourceTrace | None" = None
    generated_at: str = ""
    handled_by: str = ""    # 人工处置者（仅事实记录，由服务层写入）
    handled_at: str = ""    # 人工处置时间（仅事实记录）
    decision: str = ""      # 人工处置结论（必须人工填写，AI 不代填）

    def __post_init__(self) -> None:
        if not isinstance(self.status, RiskOverviewStatus):
            self.status = RiskOverviewStatus(self.status)
        if self.requires_human_handling is not True:
            raise EnterpriseRedLineViolationError(
                f"AgentRiskOverview {self.overview_id!r} 禁止置 "
                f"requires_human_handling=False："
                f"风险处理必须由真实人工负责（红线④/⑥）"
            )
        if self.status is not RiskOverviewStatus.PENDING_HUMAN_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"AgentRiskOverview {self.overview_id!r} 禁止在构造期落 "
                f"{self.status.value}：风险处理状态只能由真实人工推进（红线④），"
                f"请以 pending_human_review 生成后经 "
                f"human_handle_risk_overview(actor_kind=USER) 推进"
            )
        self.security_risk_ids = [
            str(r).strip() for r in self.security_risk_ids if str(r).strip()
        ]
        self.compliance_risk_ids = [
            str(r).strip() for r in self.compliance_risk_ids if str(r).strip()
        ]

    @property
    def risk_count(self) -> int:
        """只读风险候选总数（安全 + 合规）。"""
        return len(self.security_risk_ids) + len(self.compliance_risk_ids)

    @property
    def is_handled(self) -> bool:
        """是否已由真实人工处置完毕（只读事实）。"""
        return self.status is RiskOverviewStatus.HANDLED_BY_HUMAN

    def summary(self) -> str:
        """只读摘要（**不含处置建议、不含风险定性**）。"""
        return (
            f"overview_id={self.overview_id};agent_id={self.agent_id};"
            f"security_risks={len(self.security_risk_ids)};"
            f"compliance_risks={len(self.compliance_risk_ids)};"
            f"status={self.status.value};"
            f"requires_human_handling={self.requires_human_handling}"
        )


# ---------------------------------------------------------------------------
# 任务4：治理报告（五段事实 + 强可溯源）
# ---------------------------------------------------------------------------

@dataclass
class AgentGovernanceReport:
    """Agent 治理报告（任务4，**五段事实汇总 + 强可溯源**）。

    五段严格对应主理人要求：observability / quality / cost / security / compliance。

    红线（③/④/⑤/⑥）：
    - 报告只汇总事实，**不含**评级、处置建议、合规结论、批准语义；
    - ``source_trace`` 为空即拒绝构造（禁止输出无来源链的治理报告）；
    - 任一段内文本命中建议语义即拒绝（不得夹带治理建议）。
    """

    report_id: str
    org_id: str = ""
    agent_id: str = ""
    observability: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    cost: Dict[str, Any] = field(default_factory=dict)
    security: Dict[str, Any] = field(default_factory=dict)
    compliance: Dict[str, Any] = field(default_factory=dict)
    source_trace: "SourceTrace | None" = None
    generated_at: str = ""
    generated_by: str = ""

    def __post_init__(self) -> None:
        if self.source_trace is None or not isinstance(self.source_trace, SourceTrace):
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceReport {self.report_id!r} 缺少 SourceTrace："
                f"禁止输出不可溯源的治理报告（红线⑥）"
            )
        if not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceReport {self.report_id!r} 来源链为空："
                f"禁止输出无来源事实的治理报告（红线⑥）"
            )
        sections = (
            ("observability", self.observability),
            ("quality", self.quality),
            ("cost", self.cost),
            ("security", self.security),
            ("compliance", self.compliance),
        )
        for name, section in sections:
            for key, value in section.items():
                _reject_markers(
                    f"{key}={value}",
                    _ADVICE_MARKERS,
                    ctx=f"AgentGovernanceReport {self.report_id!r} 的 {name}[{key!r}]",
                    rule="治理报告只汇总事实，禁止夹带任何治理建议（红线⑤/⑥）",
                )

    @property
    def is_traceable(self) -> bool:
        """是否可溯源（构造期已强制，此处仅只读复核）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def section_counts(self) -> Dict[str, int]:
        """只读返回五段事实条目数。"""
        return {
            "observability": len(self.observability),
            "quality": len(self.quality),
            "cost": len(self.cost),
            "security": len(self.security),
            "compliance": len(self.compliance),
        }

    def summary(self) -> str:
        """只读摘要（**无结论、无建议、无批准语义**）。"""
        counts = self.section_counts()
        return (
            f"report_id={self.report_id};org_id={self.org_id};"
            f"agent_id={self.agent_id or 'all'};"
            f"observability={counts['observability']};quality={counts['quality']};"
            f"cost={counts['cost']};security={counts['security']};"
            f"compliance={counts['compliance']};"
            f"source={self.source_trace.render() if self.source_trace else 'no_source'}"
        )


# ---------------------------------------------------------------------------
# 任务5：治理洞察（只输出事实趋势 / 异常候选 / 来源）
# ---------------------------------------------------------------------------

class GovernanceInsightKind(str, Enum):
    """治理洞察类型（任务5，**刻意只有两种事实型**）。

    红线⑤/⑥：AI 不得给出治理建议。因此本枚举**不提供**
    ``recommendation`` / ``advice`` / ``action_plan`` / ``compliance_verdict``
    等任何带建议或判定语义的类型，只有：

    - ``fact_trend``：事实趋势（某项事实随时间的中性变化方向）；
    - ``anomaly_candidate``：异常候选（**待人工确认**的疑点，非结论）。
    """

    FACT_TREND = "fact_trend"
    ANOMALY_CANDIDATE = "anomaly_candidate"


class GovernanceTrendDirection(str, Enum):
    """事实趋势方向（**中性描述，不含好坏judgement**）。

    只描述数值方向本身，绝不隐含「变好 / 变坏 / 需处理」等价值判断（红线③/⑥）。
    """

    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


@dataclass
class AgentGovernanceInsight:
    """Agent 治理洞察（任务5，**只输出事实趋势 / 异常候选 / 来源**）。

    红线（⑤/⑥）：
    - ``kind`` 只有 ``fact_trend`` / ``anomaly_candidate`` 两种事实型；
    - 模型层**没有** recommendation / advice / action 字段；
    - ``subject`` / ``detail`` / ``anomaly_candidates`` 命中建议语义
      （建议 / 应当 / recommend / suggest ...）直接抛红线违例；
    - ``source_trace`` 为空即拒绝构造（洞察必须有来源）；
    - 异常候选恒为「待人工确认」（``requires_human_confirmation`` 恒为 True）。
    """

    insight_id: str
    org_id: str = ""
    agent_id: str = ""
    kind: GovernanceInsightKind = GovernanceInsightKind.FACT_TREND
    subject: str = ""
    trend: GovernanceTrendDirection = GovernanceTrendDirection.UNKNOWN
    anomaly_candidates: List[str] = field(default_factory=list)
    detail: str = ""
    requires_human_confirmation: bool = True
    source_trace: "SourceTrace | None" = None
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GovernanceInsightKind):
            self.kind = GovernanceInsightKind(self.kind)
        if not isinstance(self.trend, GovernanceTrendDirection):
            self.trend = GovernanceTrendDirection(self.trend)
        if self.requires_human_confirmation is not True:
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceInsight {self.insight_id!r} 禁止置 "
                f"requires_human_confirmation=False："
                f"洞察只是事实与疑点，必须由真实人工确认（红线⑥）"
            )
        if not str(self.subject).strip():
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceInsight {self.insight_id!r} 缺少 subject："
                f"禁止落库无主题的洞察（红线⑥）"
            )
        if self.source_trace is None or not isinstance(self.source_trace, SourceTrace):
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceInsight {self.insight_id!r} 缺少 SourceTrace："
                f"洞察必须标明来源，禁止 AI 凭空产出洞察（红线⑥）"
            )
        if not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentGovernanceInsight {self.insight_id!r} 来源链为空："
                f"禁止输出无来源的洞察（红线⑥）"
            )
        self.anomaly_candidates = [
            str(a).strip() for a in self.anomaly_candidates if str(a).strip()
        ]
        for text, label in (
            (self.subject, "subject"),
            (self.detail, "detail"),
            *[(a, f"anomaly_candidates[{i}]") for i, a in enumerate(self.anomaly_candidates)],
        ):
            _reject_markers(
                text,
                _ADVICE_MARKERS,
                ctx=f"AgentGovernanceInsight {self.insight_id!r} 的 {label}",
                rule="治理洞察只陈述事实趋势与异常候选，禁止输出治理建议（红线⑤/⑥）",
            )

    @property
    def is_traceable(self) -> bool:
        """是否可溯源（构造期已强制，此处仅只读复核）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def summary(self) -> str:
        """只读摘要（**只有事实趋势 / 异常候选 / 来源三要素**）。"""
        return (
            f"insight_id={self.insight_id};kind={self.kind.value};"
            f"subject={self.subject};trend={self.trend.value};"
            f"anomaly_candidates={len(self.anomaly_candidates)};"
            f"requires_human_confirmation={self.requires_human_confirmation};"
            f"source={self.source_trace.render() if self.source_trace else 'no_source'}"
        )


# ---------------------------------------------------------------------------
# 统一汇聚器（**纯只读**消费上游五层）
# ---------------------------------------------------------------------------

class AgentGovernanceAggregator(_RedLineForbiddenMixin):
    """治理数据统一汇聚器（**只读**，任务2/4）。

    从 3.8.14（可观测性）/ 3.8.15（质量）/ 3.8.16（成本）/ 3.8.18（安全）/
    3.8.19（合规）五层**只读**采集事实，产出可被总览与报告直接消费的事实字典。

    红线（fail-closed）：
    - 只调用上游的 ``list_*`` 只读查询，**绝不**写入、修改、删除上游任何状态（红线③）；
    - 权限隔离由上游各层自身的 ``_ensure_access`` 把关（默认拒绝），本层不绕过；
    - 不做任何评级、不做任何处置、不做任何合规判定（红线③/④/⑤）；
    - 上游服务缺失（None）时返回空事实，**绝不编造数据**（红线⑥）。
    """

    _FORBIDDEN = _GOVERNANCE_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        observability: "Any | None" = None,
        quality: "Any | None" = None,
        cost: "Any | None" = None,
        security: "Any | None" = None,
        compliance: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentGovernanceAggregator（红线①）"
            )
        self._org_id = org_id
        self._observability = observability
        self._quality = quality
        self._cost = cost
        self._security = security
        self._compliance = compliance

    # ------------------------------------------------------------------
    # 内部只读工具
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_list(service: "Any | None", method: str, **kwargs: Any) -> "List[Any]":
        """只读调用上游查询方法；不可用即返回空列表（**绝不编造数据**）。

        注意：权限不足时上游会抛 ``EnterpriseIsolationError``，此处**不吞掉**该
        异常语义 —— 由调用方 ``collect_*`` 显式决定是否向上抛（默认向上抛，
        保持默认拒绝的隔离语义）。
        """
        if service is None:
            return []
        fn = getattr(service, method, None)
        if fn is None:
            return []
        return list(fn(**kwargs))

    # ------------------------------------------------------------------
    # 五类事实采集（只读）
    # ------------------------------------------------------------------

    def collect_observability_facts(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> Dict[str, Any]:
        """采集运行事实（执行日志 / 指标 / 调用链条数，只读）。"""
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        executions = self._safe_list(self._observability, "list_executions", **kw)
        metrics = self._safe_list(self._observability, "list_metrics", **kw)
        traces = self._safe_list(self._observability, "list_traces", **kw)
        return {
            "execution_count": len(executions),
            "metric_count": len(metrics),
            "trace_count": len(traces),
            "execution_ids": [getattr(e, "log_id", getattr(e, "execution_id", "")) for e in executions],
            "metric_ids": [getattr(m, "metric_id", "") for m in metrics],
        }

    def collect_quality_facts(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> Dict[str, Any]:
        """采集质量事实（质量指标 / 人工评价 / 用户反馈条数，只读）。

        注意：**不聚合成任何等级或总分**（红线③禁止自动评级），只给条目数与 id。
        """
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        metrics = self._safe_list(self._quality, "list_quality_metrics", **kw)
        evaluations = self._safe_list(self._quality, "list_evaluations", **kw)
        feedbacks = self._safe_list(self._quality, "list_feedbacks", **kw)
        return {
            "quality_metric_count": len(metrics),
            "evaluation_count": len(evaluations),
            "feedback_count": len(feedbacks),
            "quality_metric_ids": [getattr(m, "metric_id", "") for m in metrics],
        }

    def collect_cost_facts(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> Dict[str, Any]:
        """采集成本事实（资源用量 / 成本指标条数，只读）。"""
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        usages = self._safe_list(self._cost, "list_resource_usages", **kw)
        cost_metrics = self._safe_list(self._cost, "list_cost_metrics", **kw)
        return {
            "resource_usage_count": len(usages),
            "cost_metric_count": len(cost_metrics),
            "cost_metric_ids": [getattr(m, "metric_id", "") for m in cost_metrics],
        }

    def collect_security_facts(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> Dict[str, Any]:
        """采集安全事实（安全事件 / 风险候选条数与候选 id，只读）。

        注意：只陈列候选 id，**不做任何处置**（红线④）。
        """
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        events = self._safe_list(self._security, "list_security_events", **kw)
        risks = self._safe_list(self._security, "list_risk_candidates", **kw)
        return {
            "security_event_count": len(events),
            "security_risk_count": len(risks),
            "security_risk_ids": [getattr(r, "risk_id", "") for r in risks],
        }

    def collect_compliance_facts(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> Dict[str, Any]:
        """采集合规事实（检查事实 / 合规风险候选条数与候选 id，只读）。

        注意：只陈列中性检查事实与候选 id，**不做任何合规判定**（红线⑤）。
        """
        checks = self._safe_list(
            self._compliance,
            "list_compliance_checks",
            user=user,
            agent_id=agent_id,
            resource_category=resource_category,
        )
        risks = self._safe_list(
            self._compliance,
            "list_risk_candidates",
            user=user,
            agent_id=agent_id,
            resource_category=resource_category,
        )
        return {
            "compliance_check_count": len(checks),
            "compliance_risk_count": len(risks),
            "compliance_risk_ids": [getattr(r, "risk_id", "") for r in risks],
        }


# ---------------------------------------------------------------------------
# 治理中枢聚合服务
# ---------------------------------------------------------------------------

class AgentGovernanceCenterService(_RedLineForbiddenMixin):
    """Agent 治理智能中枢聚合服务（任务1–8 统一入口）。

    承载：看板创建 / 健康总览生成 / 风险总览生成 / 治理报告生成 / 治理洞察生成 /
    人工处置（风险总览状态推进）/ 只读查询（权限隔离，默认拒绝）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - **只汇聚、只呈现、只陈述事实**，不控制 Agent（红线③）。
    - **不处理风险**：风险总览恒为待人工处理，推进强制
      ``require_human_actor(USER)``（红线④）。
    - **不判定合规**：洞察层无合规结论态（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_disable / auto_modify / auto_upgrade /
      auto_policy_change / auto_handle_risk / auto_judge_compliance 等方法。
    """

    _FORBIDDEN = _GOVERNANCE_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
        runtime_policy: "AgentRuntimeGovernanceService | None" = None,
        observability: "Any | None" = None,
        quality: "Any | None" = None,
        cost: "Any | None" = None,
        security: "Any | None" = None,
        compliance: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentGovernanceCenterService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        # 只读消费 Phase 3.8.17 运行时治理事实；本层绝不修改任何运行策略（红线③）。
        self._runtime_policy = runtime_policy
        self._aggregator = AgentGovernanceAggregator(
            org_id=org_id,
            observability=observability,
            quality=quality,
            cost=cost,
            security=security,
            compliance=compliance,
        )
        self._dashboards: Dict[str, AgentGovernanceDashboard] = {}
        self._health_overviews: Dict[str, AgentHealthOverview] = {}
        self._risk_overviews: Dict[str, AgentRiskOverview] = {}
        self._reports: Dict[str, AgentGovernanceReport] = {}
        self._insights: Dict[str, AgentGovernanceInsight] = {}

    @property
    def aggregator(self) -> AgentGovernanceAggregator:
        """只读暴露统一汇聚器（纯只读消费上游）。"""
        return self._aggregator

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """治理数据读取权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误（红线⑥：治理数据受控访问）。

        本方法**只读校验**，绝不修改任何权限或策略（红线③）。
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
                    f"用户角色无权限访问 Agent 治理中枢数据"
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
    # 任务1：治理看板（只展示事实）
    # ------------------------------------------------------------------

    def create_dashboard(
        self,
        *,
        dashboard: AgentGovernanceDashboard,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentGovernanceDashboard:
        """创建一个治理看板（**只展示事实**，红线③/⑥）。

        看板不具备任何执行能力：组件必须有源，且不得含控制/处置/批准语义
        （由 ``GovernanceWidget.__post_init__`` 与
        ``AgentGovernanceDashboard.__post_init__`` 强制）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建治理看板（红线①）"
            )
        dashboard.org_id = self._org_id
        dashboard.created_by = dashboard.created_by or actor_id
        self._dashboards[dashboard.dashboard_id] = dashboard
        if self._audit is not None:
            self._audit.record_agent_governance_dashboard_action(
                record_id=f"agent-governance-dashboard-{dashboard.dashboard_id}",
                actor_id=actor_id,
                action="create_governance_dashboard",
                target=dashboard.dashboard_id,
                detail=dashboard.summary(),
                ts=dashboard.created_at,
                actor_kind=actor_kind,
            )
        return dashboard

    # ------------------------------------------------------------------
    # 任务2：健康总览（禁止自动评级）
    # ------------------------------------------------------------------

    def build_health_overview(
        self,
        *,
        overview_id: str,
        agent_id: str,
        user: object,
        generated_at: str = "",
        resource_category: str = "data",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentHealthOverview:
        """汇聚生成 Agent 健康总览（**只汇总事实，绝不评级**，红线③/⑥）。

        四类事实全部来自上游只读查询；来源链逐条登记；
        **不产出任何等级、评分档位或健康结论**。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成健康总览（红线①）"
            )
        if not str(agent_id).strip():
            raise EnterpriseRedLineViolationError(
                "build_health_overview 必须指定 agent_id（红线⑥：事实必须有主体）"
            )
        self._ensure_access(user=user, resource_category=resource_category)
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        runtime_facts = self._aggregator.collect_observability_facts(**kw)
        quality_facts = self._aggregator.collect_quality_facts(**kw)
        cost_facts = self._aggregator.collect_cost_facts(**kw)
        security_facts = self._aggregator.collect_security_facts(**kw)
        trace = SourceTrace(trace_id=f"trace-{overview_id}")
        for label, facts in (
            ("observability", runtime_facts),
            ("quality", quality_facts),
            ("cost", cost_facts),
            ("security", security_facts),
        ):
            if facts:
                trace.add_entry(f"{label}:{agent_id}")
        overview = AgentHealthOverview(
            overview_id=overview_id,
            agent_id=agent_id,
            org_id=self._org_id,
            runtime_facts=runtime_facts,
            quality_facts=quality_facts,
            cost_facts=cost_facts,
            security_facts=security_facts,
            source_trace=trace,
            generated_at=generated_at,
        )
        self._health_overviews[overview_id] = overview
        if self._audit is not None:
            self._audit.record_agent_governance_report_action(
                record_id=f"agent-governance-health-{overview_id}",
                actor_id=actor_id,
                action="build_agent_health_overview",
                target=agent_id,
                detail=overview.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return overview

    # ------------------------------------------------------------------
    # 任务3：风险总览（禁止自动处理）
    # ------------------------------------------------------------------

    def build_risk_overview(
        self,
        *,
        overview_id: str,
        agent_id: str,
        user: object,
        generated_at: str = "",
        resource_category: str = "data",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentRiskOverview:
        """汇聚生成 Agent 风险总览（**只陈列候选，绝不处置**，红线④/⑥）。

        安全风险候选（3.8.18）+ 合规风险候选（3.8.19）只做只读汇总；
        状态恒为 ``pending_human_review``，``requires_human_handling`` 恒为 True。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成风险总览（红线①）"
            )
        if not str(agent_id).strip():
            raise EnterpriseRedLineViolationError(
                "build_risk_overview 必须指定 agent_id（红线⑥：事实必须有主体）"
            )
        self._ensure_access(user=user, resource_category=resource_category)
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        security_facts = self._aggregator.collect_security_facts(**kw)
        compliance_facts = self._aggregator.collect_compliance_facts(**kw)
        security_ids = list(security_facts.get("security_risk_ids", []))
        compliance_ids = list(compliance_facts.get("compliance_risk_ids", []))
        trace = SourceTrace(trace_id=f"trace-{overview_id}")
        for rid in security_ids:
            trace.add_entry(f"srisk:{rid}")
        for rid in compliance_ids:
            trace.add_entry(f"crisk:{rid}")
        overview = AgentRiskOverview(
            overview_id=overview_id,
            agent_id=agent_id,
            org_id=self._org_id,
            security_risk_ids=security_ids,
            compliance_risk_ids=compliance_ids,
            status=RiskOverviewStatus.PENDING_HUMAN_REVIEW,
            requires_human_handling=True,
            source_trace=trace,
            generated_at=generated_at,
        )
        self._risk_overviews[overview_id] = overview
        if self._audit is not None:
            self._audit.record_agent_governance_report_action(
                record_id=f"agent-governance-risk-{overview_id}",
                actor_id=actor_id,
                action="build_agent_risk_overview",
                target=agent_id,
                detail=overview.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return overview

    # ------------------------------------------------------------------
    # 任务4：治理报告（五段事实 + 强可溯源）
    # ------------------------------------------------------------------

    def generate_governance_report(
        self,
        *,
        report_id: str,
        user: object,
        agent_id: str = "",
        generated_at: str = "",
        resource_category: str = "data",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentGovernanceReport:
        """生成治理报告（**五段事实汇总 + 强可溯源**，红线③/④/⑤/⑥）。

        报告只包含 observability / quality / cost / security / compliance 五段
        只读事实与来源链；**不含**评级、处置建议、合规结论、批准语义。
        来源链为空即拒绝生成。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成治理报告（红线①）"
            )
        self._ensure_access(user=user, resource_category=resource_category)
        kw = {"user": user, "agent_id": agent_id, "resource_category": resource_category}
        observability = self._aggregator.collect_observability_facts(**kw)
        quality = self._aggregator.collect_quality_facts(**kw)
        cost = self._aggregator.collect_cost_facts(**kw)
        security = self._aggregator.collect_security_facts(**kw)
        compliance = self._aggregator.collect_compliance_facts(**kw)
        trace = SourceTrace(trace_id=f"trace-{report_id}")
        for label, section in (
            ("observability", observability),
            ("quality", quality),
            ("cost", cost),
            ("security", security),
            ("compliance", compliance),
        ):
            if any(
                isinstance(v, int) and v > 0
                for k, v in section.items()
                if k.endswith("_count")
            ):
                trace.add_entry(f"{label}:{agent_id or self._org_id}")
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"generate_governance_report 拒绝生成 {report_id!r}：无任何事实来源，"
                f"禁止输出无来源链的治理报告（红线⑥）"
            )
        report = AgentGovernanceReport(
            report_id=report_id,
            org_id=self._org_id,
            agent_id=agent_id,
            observability=observability,
            quality=quality,
            cost=cost,
            security=security,
            compliance=compliance,
            source_trace=trace,
            generated_at=generated_at,
            generated_by=actor_id,
        )
        self._reports[report_id] = report
        if self._audit is not None:
            self._audit.record_agent_governance_report_action(
                record_id=f"agent-governance-report-{report_id}",
                actor_id=actor_id,
                action="generate_agent_governance_report",
                target=agent_id or self._org_id,
                detail=report.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return report

    # ------------------------------------------------------------------
    # 任务5：治理洞察（只输出事实趋势 / 异常候选 / 来源）
    # ------------------------------------------------------------------

    def generate_fact_trend_insight(
        self,
        *,
        insight_id: str,
        subject: str,
        series: "List[float] | None" = None,
        agent_id: str = "",
        source_entries: "List[str] | None" = None,
        generated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentGovernanceInsight:
        """产出一条「事实趋势」洞察（**只描述方向，不给建议**，红线⑤/⑥）。

        趋势方向仅由首末两个真实数值比较得出（不足两点即 ``unknown``）：
        绝不外推、绝不预测、绝不评价好坏、绝不给出治理建议。
        来源为空即拒绝产出。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下产出治理洞察（红线①）"
            )
        values = [float(v) for v in (series or [])]
        if len(values) < 2:
            trend = GovernanceTrendDirection.UNKNOWN
        elif values[-1] > values[0]:
            trend = GovernanceTrendDirection.UP
        elif values[-1] < values[0]:
            trend = GovernanceTrendDirection.DOWN
        else:
            trend = GovernanceTrendDirection.FLAT
        trace = SourceTrace(trace_id=f"trace-{insight_id}")
        for entry in source_entries or []:
            trace.add_entry(entry)
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"generate_fact_trend_insight 拒绝产出 {insight_id!r}：无来源条目，"
                f"禁止输出无来源的洞察（红线⑥）"
            )
        insight = AgentGovernanceInsight(
            insight_id=insight_id,
            org_id=self._org_id,
            agent_id=agent_id,
            kind=GovernanceInsightKind.FACT_TREND,
            subject=subject,
            trend=trend,
            detail=f"first={values[0] if values else 'na'};last={values[-1] if values else 'na'}",
            source_trace=trace,
            generated_at=generated_at,
        )
        self._insights[insight_id] = insight
        if self._audit is not None:
            self._audit.record_agent_governance_insight_action(
                record_id=f"agent-governance-insight-{insight_id}",
                actor_id=actor_id,
                action="generate_fact_trend_insight",
                target=agent_id or self._org_id,
                detail=insight.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return insight

    def generate_anomaly_candidate_insight(
        self,
        *,
        insight_id: str,
        subject: str,
        anomaly_candidates: "List[str] | None" = None,
        agent_id: str = "",
        source_entries: "List[str] | None" = None,
        generated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentGovernanceInsight:
        """产出一条「异常候选」洞察（**只是疑点，待人工确认**，红线④/⑤/⑥）。

        异常候选**不是**异常结论，更不是风险处置依据：
        ``requires_human_confirmation`` 恒为 True；本方法不处置任何风险、
        不判定任何合规性、不控制任何 Agent。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下产出治理洞察（红线①）"
            )
        candidates = [str(c).strip() for c in (anomaly_candidates or []) if str(c).strip()]
        if not candidates:
            raise EnterpriseRedLineViolationError(
                f"generate_anomaly_candidate_insight 拒绝产出 {insight_id!r}："
                f"无任何异常候选事实，禁止编造异常（红线⑥）"
            )
        trace = SourceTrace(trace_id=f"trace-{insight_id}")
        for entry in source_entries or []:
            trace.add_entry(entry)
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"generate_anomaly_candidate_insight 拒绝产出 {insight_id!r}："
                f"无来源条目，禁止输出无来源的洞察（红线⑥）"
            )
        insight = AgentGovernanceInsight(
            insight_id=insight_id,
            org_id=self._org_id,
            agent_id=agent_id,
            kind=GovernanceInsightKind.ANOMALY_CANDIDATE,
            subject=subject,
            trend=GovernanceTrendDirection.UNKNOWN,
            anomaly_candidates=candidates,
            source_trace=trace,
            generated_at=generated_at,
        )
        self._insights[insight_id] = insight
        if self._audit is not None:
            self._audit.record_agent_governance_insight_action(
                record_id=f"agent-governance-insight-{insight_id}",
                actor_id=actor_id,
                action="generate_anomaly_candidate_insight",
                target=agent_id or self._org_id,
                detail=insight.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return insight

    # ------------------------------------------------------------------
    # 人工管理（必须真实 USER）
    # ------------------------------------------------------------------

    def human_handle_risk_overview(
        self,
        *,
        overview_id: str,
        actor_kind: Any,
        actor_id: str,
        decision: str,
        status: "RiskOverviewStatus | None" = None,
        handled_at: str = "",
        note: str = "",
    ) -> AgentRiskOverview:
        """真实人工处理风险总览（**必须真实 USER**，红线④/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError``。``decision`` 由治理责任人填写，
        AI 不得代填空值；已处置的总览不可重复处置（终态）。

        本方法**只登记人工处置事实**：不自动禁用/修改/升级 Agent、
        不自动修改任何策略、不自动判定合规。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下处置风险总览（红线①）"
            )
        overview = self._risk_overviews.get(overview_id)
        if overview is None:
            raise EnterpriseRedLineViolationError(
                f"human_handle_risk_overview 找不到风险总览 {overview_id!r}："
                f"禁止凭空处置风险（红线④）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "human_handle_risk_overview 必须提供真实 actor_id"
                "（红线⑥：人工责任可追溯）"
            )
        if not str(decision).strip():
            raise EnterpriseRedLineViolationError(
                "human_handle_risk_overview 必须由人工填写 decision，"
                "AI 不得代替治理责任人作结论（红线⑥）"
            )
        if overview.status is RiskOverviewStatus.HANDLED_BY_HUMAN:
            raise EnterpriseRedLineViolationError(
                f"风险总览 {overview_id!r} 已由人工处置完毕，不可重复处置（红线④）"
            )
        target_status = status or RiskOverviewStatus.HANDLED_BY_HUMAN
        if not isinstance(target_status, RiskOverviewStatus):
            target_status = RiskOverviewStatus(target_status)
        if target_status is RiskOverviewStatus.PENDING_HUMAN_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"human_handle_risk_overview 拒绝把 {overview_id!r} 退回 "
                f"pending_human_review：人工处置只能前进，不可回退（红线⑥）"
            )
        overview.status = target_status
        overview.handled_by = actor_id
        overview.handled_at = handled_at
        overview.decision = decision
        if self._audit is not None:
            self._audit.record_agent_governance_report_action(
                record_id=f"agent-governance-risk-handled-{overview_id}",
                actor_id=actor_id,
                action="human_handle_risk_overview",
                target=overview.agent_id or overview_id,
                detail=(
                    f"overview_id={overview_id};status={overview.status.value};"
                    f"handled_by={actor_id};decision={decision};note={note}"
                ),
                ts=handled_at,
                actor_kind=AuditActorKind.USER,
            )
        return overview

    def human_confirm_insight(
        self,
        *,
        insight_id: str,
        actor_kind: Any,
        actor_id: str,
        conclusion: str,
        confirmed_at: str = "",
    ) -> AgentGovernanceInsight:
        """真实人工确认一条治理洞察（**必须真实 USER**，红线⑤/⑥）。

        只登记「某真实人工看过并给出结论」这一事实；洞察对象本身保持
        ``requires_human_confirmation=True``（它永远只是事实与疑点，
        不因被看过而升格为结论）。AI 不得代替治理责任人作任何判定。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下确认治理洞察（红线①）"
            )
        insight = self._insights.get(insight_id)
        if insight is None:
            raise EnterpriseRedLineViolationError(
                f"human_confirm_insight 找不到洞察 {insight_id!r}："
                f"禁止凭空确认（红线⑥）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "human_confirm_insight 必须提供真实 actor_id（红线⑥）"
            )
        if not str(conclusion).strip():
            raise EnterpriseRedLineViolationError(
                "human_confirm_insight 必须由人工填写 conclusion，"
                "AI 不得代替治理责任人作结论（红线⑥）"
            )
        if self._audit is not None:
            self._audit.record_agent_governance_insight_action(
                record_id=f"agent-governance-insight-confirmed-{insight_id}",
                actor_id=actor_id,
                action="human_confirm_governance_insight",
                target=insight.agent_id or insight_id,
                detail=(
                    f"insight_id={insight_id};confirmed_by={actor_id};"
                    f"conclusion={conclusion}"
                ),
                ts=confirmed_at,
                actor_kind=AuditActorKind.USER,
            )
        return insight

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def list_dashboards(
        self,
        *,
        user: object,
        visibility: "GovernanceVisibility | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentGovernanceDashboard]":
        """列出当前组织下治理看板（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [d for d in self._dashboards.values() if d.org_id == self._org_id]
        if visibility is not None:
            out = [d for d in out if d.visibility is visibility]
        return out

    def list_health_overviews(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[AgentHealthOverview]":
        """列出当前组织下健康总览（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [o for o in self._health_overviews.values() if o.org_id == self._org_id]
        if agent_id:
            out = [o for o in out if o.agent_id == agent_id]
        return out

    def list_risk_overviews(
        self,
        *,
        user: object,
        agent_id: str = "",
        status: "RiskOverviewStatus | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentRiskOverview]":
        """列出当前组织下风险总览（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [o for o in self._risk_overviews.values() if o.org_id == self._org_id]
        if agent_id:
            out = [o for o in out if o.agent_id == agent_id]
        if status is not None:
            out = [o for o in out if o.status is status]
        return out

    def list_governance_reports(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[AgentGovernanceReport]":
        """列出当前组织下治理报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._reports.values() if r.org_id == self._org_id]
        if agent_id:
            out = [r for r in out if r.agent_id == agent_id]
        return out

    def list_governance_insights(
        self,
        *,
        user: object,
        kind: "GovernanceInsightKind | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentGovernanceInsight]":
        """列出当前组织下治理洞察（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [i for i in self._insights.values() if i.org_id == self._org_id]
        if kind is not None:
            out = [i for i in out if i.kind is kind]
        return out


__all__ = [
    "GovernanceWidgetKind",
    "GovernanceVisibility",
    "GovernanceWidget",
    "AgentGovernanceDashboard",
    "AgentHealthOverview",
    "RiskOverviewStatus",
    "AgentRiskOverview",
    "AgentGovernanceReport",
    "GovernanceInsightKind",
    "GovernanceTrendDirection",
    "AgentGovernanceInsight",
    "AgentGovernanceAggregator",
    "AgentGovernanceCenterService",
    "_GOVERNANCE_FORBIDDEN",
]

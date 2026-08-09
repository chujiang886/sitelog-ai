"""Enterprise Agent Cost & Resource Intelligence Layer（Phase 3.8.16）。

新增（任务1–5）：
- ``AgentResourceType``：资源类型枚举（token / compute / storage / external_api）。
- ``AgentResourceUsage``：Agent 资源使用事实（usage_id / agent_id / execution_id /
  resource_type / amount / unit / timestamp / org_id），**只记录事实**，不含任何
  预算 / 配额 / 上限 / 优化 / 评价字段。
- ``AgentCostType``：成本类型枚举（token / compute / storage / external_api）。
- ``AgentCostMetric``：Agent 成本指标（metric_id / agent_id / cost_type / value /
  period / source / org_id），**只记录事实**，不含批准/报价语义。
- ``AgentCostAttribution``：成本归属（attribution_id / agent_id / project_id /
  task_id / cost / source / org_id），**可追踪归属**：无归属对象或无来源即拒绝。
- ``AgentResourceAnalyzer``：资源分析器（aggregate_usage / calculate_cost /
  compare_period），**只分析事实，禁止自动优化资源策略**。
- ``AgentCostReport``：事实型成本报告（资源事实 / 成本趋势 / 来源链），
  **来源可追溯**（source_trace.is_traceable 强制）。
- ``AgentCostResourceService``：聚合运营层，承载资源使用登记 / 成本指标登记 /
  成本归属登记 / 资源分析 / 成本报告汇编；接入身份层 + AgentPermissionPolicy
  做成本数据权限隔离；联动审计（AGENT_RESOURCE / AGENT_COST / AGENT_COST_REPORT，任务6）。

红线（fail-closed，复用 3.8.0~3.8.15 基座 + 3.8.16 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved。
③ 不 AI 自动关闭/停止 Agent（auto_disable_agent / auto_stop_agent / stop_agent /
   disable_agent / kill_agent / terminate_agent 等被 mixin 拦截）。
④ 不 AI 自动修改 Agent 配置（auto_modify_agent / modify_agent_config /
   configure_agent / set_agent_config 等被拦截）。
⑤ 不 AI 自动优化资源策略（auto_optimize / optimize_resource / optimize_cost /
   auto_scale / auto_throttle / set_budget / enforce_budget 等被拦截）。
⑥ 不 AI 代替管理责任（审计禁止 record_human_approval；成本报告只汇编事实，
   不作任何削减/优化/处置建议；单价必须由外部事实台账提供，禁止 AI 编造）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import AuditService
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class AgentResourceType(str, Enum):
    """Agent 资源类型（任务1）。

    仅描述**资源事实的类别**，不含任何贵/贱、超支/节约的评价语义（红线⑤/⑥）。
    """

    TOKEN = "token"                  # 模型 token 消耗（事实计数）
    COMPUTE = "compute"              # 计算耗时/算力占用（事实数值）
    STORAGE = "storage"              # 存储占用（事实数值）
    EXTERNAL_API = "external_api"    # 外部 API 调用（事实计数）


class AgentCostType(str, Enum):
    """Agent 成本类型（任务2）。

    与 ``AgentResourceType`` 一一对应，支持 token / compute / storage / external_api。
    仅描述**成本事实的归类**，不构成报价、不构成预算结论（红线②/⑥）。
    """

    TOKEN = "token"
    COMPUTE = "compute"
    STORAGE = "storage"
    EXTERNAL_API = "external_api"


# 资源类型 → 默认计量单位（仅补全单位标签，不改变任何事实数值）。
_DEFAULT_UNITS: Dict[AgentResourceType, str] = {
    AgentResourceType.TOKEN: "tokens",
    AgentResourceType.COMPUTE: "seconds",
    AgentResourceType.STORAGE: "mb",
    AgentResourceType.EXTERNAL_API: "calls",
}


@dataclass
class AgentResourceUsage:
    """Agent 资源使用事实（任务1）。

    字段严格对应：usage_id / agent_id / execution_id / resource_type / amount /
    unit / timestamp；额外增加 org_id 做组织隔离。

    **只记录事实**：本模型仅为资源消耗事实载体，不含 budget / quota / limit /
    threshold / verdict / optimization 等字段，也不提供任何优化/处置方法
    （红线⑤/⑥：结构上禁优化、禁处置）。
    """

    usage_id: str
    agent_id: str
    resource_type: AgentResourceType
    amount: float
    execution_id: str = ""      # 关联的 Agent 执行 id（溯源用）
    unit: str = ""              # 计量单位（留空则按资源类型补默认单位）
    timestamp: str = ""         # 事实发生时间（如 2026-08-06T10:00:00）
    org_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, AgentResourceType):
            self.resource_type = AgentResourceType(self.resource_type)
        # 防编造：资源用量不得为负（仅范围约束，不评价）。
        amount = float(self.amount)
        if amount < 0:
            amount = 0.0
        self.amount = amount
        if not self.unit:
            self.unit = _DEFAULT_UNITS[self.resource_type]


@dataclass
class AgentCostMetric:
    """Agent 成本指标（任务2）。

    字段严格对应：metric_id / agent_id / cost_type / value / period / source；
    额外增加 org_id 与 currency（成本必须带币种才是完整事实）。

    **只记录事实**：不含 budget / approved / quoted / verdict 等字段，
    也不提供任何报价/审批入口（红线②/③/⑥）。``source`` 记录该成本数字的来源
    （如 derived_from_resource_usage:<usage_ids> / finance_ledger），供溯源。
    """

    metric_id: str
    agent_id: str
    cost_type: AgentCostType
    value: float
    org_id: str = ""
    period: str = ""            # 成本周期（如 2026-08 / 2026-W32）
    source: str = ""            # 成本来源（事实链，禁空口数字）
    currency: str = "CNY"

    def __post_init__(self) -> None:
        if not isinstance(self.cost_type, AgentCostType):
            self.cost_type = AgentCostType(self.cost_type)
        # 防编造：成本值不得为负（仅范围约束，不评价）。
        value = float(self.value)
        if value < 0:
            value = 0.0
        self.value = value


@dataclass
class AgentCostAttribution:
    """成本归属（任务3）。

    字段严格对应：attribution_id / agent_id / project_id / task_id / cost / source；
    额外增加 org_id / created_at / source_trace。

    **可追踪归属**：归属必须同时满足 ① 至少指向一个归属对象（project_id 或 task_id）；
    ② 具备来源（``source`` 非空，或 ``source_trace.is_traceable``）。二者缺一即抛
    ``EnterpriseRedLineViolationError`` —— 禁止 AI 生成无源、无对象的成本分摊（红线⑥）。

    本模型不含任何 chargeback 审批 / 预算扣减 / 处置语义（红线②/⑤/⑥）。
    """

    attribution_id: str
    agent_id: str
    project_id: str = ""
    task_id: str = ""
    cost: float = 0.0
    source: str = ""
    org_id: str = ""
    created_at: str = ""
    currency: str = "CNY"
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        cost = float(self.cost)
        if cost < 0:
            cost = 0.0
        self.cost = cost
        # 任务3：归属必须有对象，否则不是可追踪归属。
        if not (self.project_id or self.task_id):
            raise EnterpriseRedLineViolationError(
                f"AgentCostAttribution {self.attribution_id!r} 缺少归属对象"
                f"（project_id / task_id 至少其一）：禁止生成不可追踪的成本归属（任务3）"
            )
        # 任务3：归属必须有来源，否则视为 AI 编造。
        traceable = bool(self.source) or (
            self.source_trace is not None and self.source_trace.is_traceable
        )
        if not traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentCostAttribution {self.attribution_id!r} 来源不可追溯"
                f"（source 为空且 source_trace 缺失/不可追溯）："
                f"禁止生成 AI 创造的无源成本归属（任务3）"
            )

    @property
    def is_traceable(self) -> bool:
        """归属是否可追踪（只读，供报告汇编前置校验）。"""
        return bool(self.project_id or self.task_id) and (
            bool(self.source)
            or (self.source_trace is not None and self.source_trace.is_traceable)
        )


# 3.8.16 新增 forbidden 方法名：禁自动关停 Agent / 禁自动改配置 / 禁自动优化资源策略。
_COST_RESOURCE_FORBIDDEN = (
    # 基座（红线②/③/④/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动关闭/停止 Agent（成本高 ≠ AI 可以关它）
    "auto_disable_agent",
    "auto_stop_agent",
    "disable_agent",
    "stop_agent",
    "auto_shutdown_agent",
    "shutdown_agent",
    "kill_agent",
    "terminate_agent",
    "auto_suspend_agent",
    "suspend_agent",
    "auto_deactivate",
    "deactivate_agent",
    # 红线④：禁止 AI 自动修改 Agent 配置
    "auto_modify_agent",
    "modify_agent",
    "modify_agent_config",
    "auto_configure_agent",
    "configure_agent",
    "set_agent_config",
    "update_agent_config",
    "auto_update_agent",
    "update_agent",
    "change_agent",
    # 红线⑤：禁止 AI 自动优化资源策略
    "auto_optimize",
    "auto_optimize_resource",
    "optimize_resource",
    "optimize_cost",
    "optimize_agent",
    "auto_tune",
    "tune_resource",
    "auto_scale",
    "scale_agent",
    "auto_throttle",
    "throttle_agent",
    "reduce_cost",
    "cut_cost",
    "set_budget",
    "enforce_budget",
    "allocate_budget",
    "auto_allocate",
    "apply_resource_policy",
    "set_resource_policy",
    # 红线⑥：禁止 AI 代替管理责任
    "make_management_decision",
    "recommend",
    "decide",
)


class AgentResourceAnalyzer(_RedLineForbiddenMixin):
    """资源分析器（任务4）。

    提供三种**纯事实**分析：
    - ``aggregate_usage()``：按维度聚合资源使用事实（求和/计数，不作判断）。
    - ``calculate_cost()``：依据**外部提供的单价台账**换算成本事实；单价缺失即拒绝
      （禁止 AI 编造单价，红线⑥）。
    - ``compare_period()``：比较两个周期的成本事实差值（只算 delta，不作结论）。

    **只分析事实，禁止自动优化**：本类不含任何优化/关停/调参/预算方法，
    ``_FORBIDDEN`` 在结构上使其不可达（红线③/④/⑤/⑥）。
    """

    _FORBIDDEN = _COST_RESOURCE_FORBIDDEN

    def __init__(self, org_id: str = "") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentResourceAnalyzer（红线①/⑤）"
            )
        self._org_id = org_id

    # ---- 聚合（只求和/计数，不作判断）----

    def aggregate_usage(
        self,
        *,
        usages: "List[AgentResourceUsage]",
        group_by: str = "agent_id",
        period: str = "",
    ) -> Dict[str, dict]:
        """按维度聚合资源使用事实（红线⑤/⑥：只聚合，不优化、不建议）。

        ``group_by`` 取 ``agent_id`` / ``resource_type`` / ``execution_id``。
        ``period`` 非空时按 ``timestamp`` 前缀过滤（事实过滤，不改数据）。
        返回 ``{key: {"total_amount", "count", "units", "usage_ids", "resource_types"}}``。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下聚合资源使用（红线①/⑤）"
            )
        allowed = ("agent_id", "resource_type", "execution_id")
        if group_by not in allowed:
            raise EnterpriseRedLineViolationError(
                f"aggregate_usage 不支持的聚合维度 {group_by!r}（仅允许 {allowed}）"
            )
        out: Dict[str, dict] = {}
        for u in usages:
            if period and not (u.timestamp or "").startswith(period):
                continue
            if group_by == "resource_type":
                key = u.resource_type.value
            else:
                key = getattr(u, group_by) or ""
            bucket = out.setdefault(
                key,
                {
                    "total_amount": 0.0,
                    "count": 0,
                    "units": [],
                    "usage_ids": [],
                    "resource_types": [],
                },
            )
            bucket["total_amount"] = round(bucket["total_amount"] + u.amount, 6)
            bucket["count"] += 1
            if u.unit and u.unit not in bucket["units"]:
                bucket["units"].append(u.unit)
            if u.resource_type.value not in bucket["resource_types"]:
                bucket["resource_types"].append(u.resource_type.value)
            bucket["usage_ids"].append(u.usage_id)
        return out

    # ---- 成本换算（单价必须外部提供，禁编造）----

    def calculate_cost(
        self,
        *,
        usages: "List[AgentResourceUsage]",
        rate_card: "Dict[object, float]",
        period: str = "",
        metric_id_prefix: str = "cost",
        currency: str = "CNY",
    ) -> "List[AgentCostMetric]":
        """依据外部单价台账把资源使用事实换算为成本事实（红线⑥：禁编造单价）。

        ``rate_card`` 形如 ``{AgentResourceType.TOKEN: 0.000012, "compute": 0.02}``，
        必须由**真实计费台账/财务系统**提供。任一资源类型在台账中缺失 → 抛
        ``EnterpriseRedLineViolationError``（AI 不得臆造单价，红线⑥）。

        产出的 ``AgentCostMetric.source`` 携带原始 usage_id 链，保证可溯源。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下换算成本（红线①/⑤）"
            )
        if not usages:
            raise EnterpriseRedLineViolationError(
                "calculate_cost 至少需要一条资源使用事实，禁止生成无源成本（任务4）"
            )
        if not rate_card:
            raise EnterpriseRedLineViolationError(
                "calculate_cost 缺少单价台账（rate_card）："
                "单价必须由真实计费台账提供，禁止 AI 编造单价（红线⑥）"
            )
        # 单价台账归一化：键接受枚举或字符串。
        rates: Dict[AgentResourceType, float] = {}
        for k, v in rate_card.items():
            rk = k if isinstance(k, AgentResourceType) else AgentResourceType(str(k))
            rate = float(v)
            if rate < 0:
                raise EnterpriseRedLineViolationError(
                    f"calculate_cost 单价不得为负（{rk.value}={rate}）：台账数据无效"
                )
            rates[rk] = rate

        grouped: Dict[tuple, list] = {}
        for u in usages:
            if period and not (u.timestamp or "").startswith(period):
                continue
            grouped.setdefault((u.agent_id, u.resource_type), []).append(u)
        if not grouped:
            raise EnterpriseRedLineViolationError(
                f"calculate_cost 在周期 {period!r} 内无任何资源使用事实，"
                f"禁止生成无源成本（任务4）"
            )

        metrics: "List[AgentCostMetric]" = []
        for (agent_id, rtype), items in grouped.items():
            if rtype not in rates:
                raise EnterpriseRedLineViolationError(
                    f"calculate_cost 缺少资源类型 {rtype.value!r} 的单价："
                    f"禁止 AI 编造单价或以 0 充数（红线⑥）"
                )
            total_amount = round(sum(i.amount for i in items), 6)
            value = round(total_amount * rates[rtype], 6)
            usage_ids = [i.usage_id for i in items]
            metrics.append(
                AgentCostMetric(
                    metric_id=f"{metric_id_prefix}-{agent_id}-{rtype.value}",
                    agent_id=agent_id,
                    cost_type=AgentCostType(rtype.value),
                    value=value,
                    org_id=self._org_id,
                    period=period,
                    source=(
                        f"derived_from_resource_usage:{','.join(usage_ids)};"
                        f"rate={rates[rtype]};amount={total_amount}"
                    ),
                    currency=currency,
                )
            )
        return metrics

    # ---- 周期比较（只算 delta，不作结论）----

    def compare_period(
        self,
        *,
        period_a: str,
        period_b: str,
        metrics_a: "List[AgentCostMetric]",
        metrics_b: "List[AgentCostMetric]",
    ) -> Dict[str, object]:
        """比较两个周期的成本事实差值（红线⑤/⑥：只算差值，不作优化/削减结论）。

        返回结构含 ``totals`` / ``by_cost_type`` / ``facts``，其中 ``facts`` 为中性
        事实串（``cost_type:a=..;b=..;delta=..``）。**不含**任何 recommendation /
        verdict / action 字段。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下比较周期成本（红线①/⑤）"
            )
        if not metrics_a and not metrics_b:
            raise EnterpriseRedLineViolationError(
                "compare_period 两个周期均无成本事实，禁止生成空的无源比较（任务4）"
            )

        def _sum_by_type(metrics: "List[AgentCostMetric]") -> Dict[str, float]:
            acc: Dict[str, float] = {}
            for m in metrics:
                acc[m.cost_type.value] = round(
                    acc.get(m.cost_type.value, 0.0) + m.value, 6
                )
            return acc

        sum_a = _sum_by_type(metrics_a)
        sum_b = _sum_by_type(metrics_b)
        keys = sorted(set(sum_a) | set(sum_b))
        by_cost_type: Dict[str, dict] = {}
        facts: List[str] = []
        for k in keys:
            a_val = sum_a.get(k, 0.0)
            b_val = sum_b.get(k, 0.0)
            delta = round(b_val - a_val, 6)
            by_cost_type[k] = {
                "period_a": a_val,
                "period_b": b_val,
                "delta": delta,
            }
            facts.append(f"{k}:a={a_val};b={b_val};delta={delta}")
        total_a = round(sum(sum_a.values()), 6)
        total_b = round(sum(sum_b.values()), 6)
        return {
            "period_a": period_a,
            "period_b": period_b,
            "totals": {
                "period_a": total_a,
                "period_b": total_b,
                "delta": round(total_b - total_a, 6),
            },
            "by_cost_type": by_cost_type,
            "facts": facts,
            "source_metric_ids": (
                [m.metric_id for m in metrics_a] + [m.metric_id for m in metrics_b]
            ),
        }


@dataclass
class AgentCostReport:
    """事实型 Agent 成本报告（任务5）。

    字段：report_id / org_id / period / resource_facts / cost_metrics / cost_trends /
    attributions / sources / created_at / source_trace。

    只汇编事实（资源事实 / 成本趋势 / 归属 / 来源链），**不**含任何成本优化建议 /
    削减建议 / 关停 Agent / 修改配置语义（红线③/④/⑤/⑥：AI 只汇编，不替管理做决策）。
    ``source_trace.is_traceable`` 强制，否则拒绝生成（禁 AI 创造无源报告）。
    """

    report_id: str
    org_id: str
    period: str = ""
    resource_facts: List[str] = field(default_factory=list)   # 资源事实（聚合后的中性描述）
    cost_metrics: List[str] = field(default_factory=list)     # 成本指标 id
    cost_trends: List[str] = field(default_factory=list)      # 成本趋势（事实型 delta 描述）
    attributions: List[str] = field(default_factory=list)     # 成本归属 id
    resource_usages: List[str] = field(default_factory=list)  # 资源使用事实 id
    sources: List[str] = field(default_factory=list)          # 数据源 tag
    created_at: str = ""
    currency: str = "CNY"
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 任务5：来源不可追溯 → 禁止生成报告（AI 不得创造无源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentCostReport {self.report_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）："
                f"禁止生成 AI 创造的无源成本报告（任务5）"
            )


class AgentCostResourceService(_RedLineForbiddenMixin):
    """Agent 成本与资源聚合服务（任务1–7 统一入口）。

    承载资源使用登记 / 成本指标登记 / 成本归属登记 / 资源分析 / 成本报告汇编；
    接入身份层 + AgentPermissionPolicy 做**成本数据权限隔离**（默认拒绝）；
    联动审计（AGENT_RESOURCE / AGENT_COST / AGENT_COST_REPORT，任务6）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - 成本数据读取经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有任何 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_disable_agent / auto_stop_agent / modify_agent_config /
      auto_optimize / optimize_resource / set_budget 等方法（红线②/③/④/⑤/⑥）。
    """

    _FORBIDDEN = _COST_RESOURCE_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentCostResourceService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._analyzer = AgentResourceAnalyzer(org_id=org_id)
        self._usages: dict[str, AgentResourceUsage] = {}
        self._cost_metrics: dict[str, AgentCostMetric] = {}
        self._attributions: dict[str, AgentCostAttribution] = {}

    @property
    def analyzer(self) -> AgentResourceAnalyzer:
        """只读暴露资源分析器（只分析事实，禁自动优化）。"""
        return self._analyzer

    # ---- 登记（写路径，断言红线 + 审计）----

    def record_resource_usage(
        self,
        *,
        usage: AgentResourceUsage,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentResourceUsage:
        """登记一条资源使用事实（只记事实，红线⑤/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记资源使用（红线①/⑤）"
            )
        usage.org_id = self._org_id
        self._usages[usage.usage_id] = usage
        if self._audit is not None:
            self._audit.record_agent_resource_action(
                record_id=f"agent-resource-{usage.usage_id}",
                actor_id=actor_id,
                action="record_agent_resource_usage",
                target=usage.agent_id,
                detail=(
                    f"resource_type={usage.resource_type.value};amount={usage.amount};"
                    f"unit={usage.unit};execution_id={usage.execution_id};"
                    f"timestamp={usage.timestamp}"
                ),
                ts=usage.timestamp,
                actor_kind=actor_kind,
            )
        return usage

    def record_cost_metric(
        self,
        *,
        metric: AgentCostMetric,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentCostMetric:
        """登记一条成本指标事实（只记事实，不报价、不审批，红线②/③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记成本指标（红线①/⑤）"
            )
        metric.org_id = self._org_id
        self._cost_metrics[metric.metric_id] = metric
        if self._audit is not None:
            self._audit.record_agent_cost_action(
                record_id=f"agent-cost-{metric.metric_id}",
                actor_id=actor_id,
                action="record_agent_cost_metric",
                target=metric.agent_id,
                detail=(
                    f"cost_type={metric.cost_type.value};value={metric.value};"
                    f"currency={metric.currency};period={metric.period};"
                    f"source={metric.source}"
                ),
                ts="",
                actor_kind=actor_kind,
            )
        return metric

    def record_cost_attribution(
        self,
        *,
        attribution: AgentCostAttribution,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentCostAttribution:
        """登记一条成本归属事实（**可追踪归属**，无源即在模型层被拒，红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记成本归属（红线①/⑤）"
            )
        attribution.org_id = self._org_id
        self._attributions[attribution.attribution_id] = attribution
        if self._audit is not None:
            self._audit.record_agent_cost_action(
                record_id=f"agent-cost-attr-{attribution.attribution_id}",
                actor_id=actor_id,
                action="record_agent_cost_attribution",
                target=attribution.agent_id,
                detail=(
                    f"project_id={attribution.project_id};task_id={attribution.task_id};"
                    f"cost={attribution.cost};currency={attribution.currency};"
                    f"source={attribution.source}"
                ),
                ts=attribution.created_at,
                actor_kind=actor_kind,
            )
        return attribution

    # ---- 分析（只分析事实，禁自动优化）----

    def aggregate_usage(
        self,
        *,
        user: object,
        group_by: str = "agent_id",
        period: str = "",
        resource_category: str = "data",
    ) -> Dict[str, dict]:
        """聚合当前组织下资源使用事实（权限隔离 + 只聚合，红线⑤/⑥）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        scoped = [u for u in self._usages.values() if u.org_id == self._org_id]
        return self._analyzer.aggregate_usage(
            usages=scoped, group_by=group_by, period=period
        )

    def calculate_cost(
        self,
        *,
        rate_card: "Dict[object, float]",
        period: str = "",
        currency: str = "CNY",
        persist: bool = True,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> "List[AgentCostMetric]":
        """按外部单价台账换算成本事实（单价缺失即拒绝，红线⑥：禁编造单价）。

        ``persist=True`` 时把换算出的成本指标登记入库并写审计（AGENT_COST）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下换算成本（红线①/⑤）"
            )
        scoped = [u for u in self._usages.values() if u.org_id == self._org_id]
        metrics = self._analyzer.calculate_cost(
            usages=scoped, rate_card=rate_card, period=period, currency=currency
        )
        if persist:
            for m in metrics:
                self.record_cost_metric(
                    metric=m, actor_id=actor_id, actor_kind=actor_kind
                )
        return metrics

    def compare_period(
        self,
        *,
        user: object,
        period_a: str,
        period_b: str,
        resource_category: str = "data",
    ) -> Dict[str, object]:
        """比较两个周期的成本事实差值（权限隔离 + 只算 delta，红线⑤/⑥）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        metrics_a = [
            m
            for m in self._cost_metrics.values()
            if m.org_id == self._org_id and m.period == period_a
        ]
        metrics_b = [
            m
            for m in self._cost_metrics.values()
            if m.org_id == self._org_id and m.period == period_b
        ]
        return self._analyzer.compare_period(
            period_a=period_a,
            period_b=period_b,
            metrics_a=metrics_a,
            metrics_b=metrics_b,
        )

    # ---- 报告汇编（事实型，来源可追溯）----

    def generate_cost_report(
        self,
        *,
        report_id: str,
        user: object,
        period: str = "",
        compare_with: str = "",
        currency: str = "CNY",
        resource_category: str = "data",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentCostReport:
        """汇编事实型成本报告（权限隔离 + 仅汇编事实，红线③/④/⑤/⑥）。

        报告只含「资源事实 / 成本趋势 / 归属 / 来源链」，**绝不**含优化建议、
        削减建议、关停 Agent 或修改配置语义。
        """
        self._ensure_access(user=user, resource_category=resource_category)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成成本报告（红线①/⑤）"
            )
        scoped_usages = [u for u in self._usages.values() if u.org_id == self._org_id]
        scoped_metrics = [
            m for m in self._cost_metrics.values() if m.org_id == self._org_id
        ]
        scoped_attrs = [
            a for a in self._attributions.values() if a.org_id == self._org_id
        ]
        if not (scoped_usages or scoped_metrics or scoped_attrs):
            raise EnterpriseRedLineViolationError(
                "generate_cost_report 至少需要一条事实型输入（资源使用/成本指标/成本归属），"
                "禁止生成空的无源报告（任务5）"
            )
        trace = SourceTrace(
            raw_refs=(
                [u.usage_id for u in scoped_usages]
                + [m.metric_id for m in scoped_metrics]
                + [a.attribution_id for a in scoped_attrs]
            ),
        )
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "generate_cost_report 聚合后的溯源链不可追溯："
                "禁止生成 AI 创造的无源成本报告（任务5）"
            )

        # 资源事实：按 agent 聚合后的中性描述（不带任何评价词）。
        agg = self._analyzer.aggregate_usage(
            usages=scoped_usages, group_by="agent_id", period=period
        )
        resource_facts = [
            f"{k}:total_amount={v['total_amount']};count={v['count']};"
            f"types={'/'.join(v['resource_types'])}"
            for k, v in sorted(agg.items())
        ]

        # 成本趋势：本周期成本事实 + （可选）与对照周期的 delta 事实。
        cost_trends = [
            f"{m.agent_id}:{m.cost_type.value}={round(m.value, 6)}{m.currency}"
            f";period={m.period}"
            for m in scoped_metrics
            if (not period or m.period == period)
        ]
        if compare_with:
            cmp_result = self._analyzer.compare_period(
                period_a=compare_with,
                period_b=period,
                metrics_a=[m for m in scoped_metrics if m.period == compare_with],
                metrics_b=[m for m in scoped_metrics if m.period == period],
            )
            cost_trends.extend(
                f"delta[{compare_with}->{period}] {f}" for f in cmp_result["facts"]
            )

        source_tags = list(
            dict.fromkeys(
                [m.source for m in scoped_metrics if m.source]
                + [a.source for a in scoped_attrs if a.source]
            )
        )
        report = AgentCostReport(
            report_id=report_id,
            org_id=self._org_id,
            period=period,
            resource_facts=resource_facts,
            cost_metrics=[m.metric_id for m in scoped_metrics],
            cost_trends=cost_trends,
            attributions=[a.attribution_id for a in scoped_attrs],
            resource_usages=[u.usage_id for u in scoped_usages],
            sources=source_tags,
            created_at=created_at,
            currency=currency,
            source_trace=trace,
        )
        if self._audit is not None:
            self._audit.record_agent_cost_report_action(
                record_id=f"agent-cost-report-{report_id}",
                actor_id=actor_id,
                action="generate_agent_cost_report",
                target=report_id,
                detail=(
                    f"period={period};usages={len(scoped_usages)};"
                    f"metrics={len(scoped_metrics)};attributions={len(scoped_attrs)};"
                    f"trace={trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return report

    # ---- 读取（权限隔离，默认拒绝）----

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """成本数据读取权限校验（**默认拒绝**，任务7）。

        结合 AgentPermissionPolicy：角色须在该资源类别作用域内，且若声明了读权限须经
        IdentityService 校验。任一不过即抛隔离错误（红线⑥：成本数据受控访问）。
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
                    f"用户角色无权限访问 Agent 成本与资源数据"
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

    def list_resource_usages(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> "List[AgentResourceUsage]":
        """列出当前组织下资源使用事实（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [u for u in self._usages.values() if u.org_id == self._org_id]
        if agent_id:
            out = [u for u in out if u.agent_id == agent_id]
        return out

    def list_cost_metrics(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> "List[AgentCostMetric]":
        """列出当前组织下成本指标（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [m for m in self._cost_metrics.values() if m.org_id == self._org_id]
        if agent_id:
            out = [m for m in out if m.agent_id == agent_id]
        return out

    def list_cost_attributions(
        self,
        *,
        user: object,
        agent_id: str = "",
        project_id: str = "",
        resource_category: str = "data",
    ) -> "List[AgentCostAttribution]":
        """列出当前组织下成本归属（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [a for a in self._attributions.values() if a.org_id == self._org_id]
        if agent_id:
            out = [a for a in out if a.agent_id == agent_id]
        if project_id:
            out = [a for a in out if a.project_id == project_id]
        return out


__all__ = [
    "AgentResourceType",
    "AgentCostType",
    "AgentResourceUsage",
    "AgentCostMetric",
    "AgentCostAttribution",
    "AgentResourceAnalyzer",
    "AgentCostReport",
    "AgentCostResourceService",
]

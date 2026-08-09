"""Enterprise Agent Observability & Performance Intelligence Layer（Phase 3.8.14）。

新增（任务1–5）：
- ``AgentExecutionStatus``：执行状态枚举（事实型，仅记录结果，不评价）。
- ``AgentExecutionLog``：Agent 运行日志（execution_id / agent_id / task_id /
  input_type / output_type / status / duration / timestamp / org_id），**只记录事实**。
- ``AgentMetricType``：指标类型枚举（调用次数 / 成功率 / 耗时）。
- ``AgentMetric``：Agent 指标（metric_id / agent_id / metric_type / value /
  period / source / org_id），**禁止自动评价 Agent 好坏**（不含 verdict/score 语义）。
- ``AgentTrace``：Agent 调用链（trace_id / agent_id / parent_agent / child_agent /
  action / timestamp / org_id），可追踪。
- ``AgentHealthCandidate``：事实型健康候选（health_id / agent_id / pattern /
  evidence / requires_human_review），**禁止自动禁用 Agent**（不含 enable/disable/heal）。
- ``AgentHealthDetector``：输出健康候选，**要求人工复核**；结构上禁用自动处置/禁用入口。
- ``AgentPerformanceReport``：事实型性能报告（report_id / org_id / period / facts /
  trends / anomaly_candidates / sources / source_trace），**禁止自动优化 Agent**。
- ``AgentPerformanceReportService``：汇编报告；结构上禁用 auto_optimize / tune / reconfigure。
- ``AgentObservabilityService``：聚合运营层，承载日志/指标/追踪的登记与读取；
  接入身份层 + AgentPermissionPolicy + 知识可见性策略做监控数据权限隔离；
  联动审计（AGENT_METRIC / AGENT_TRACE / AGENT_HEALTH，任务6）。

红线（fail-closed，复用 3.8.0~3.8.13 基座）：
① 构造/写路径断言 ``safety_invariants_ok()``。
② 不输出 engineering_approved。
③ 不自动报价。
④ 不自动审批。
⑤ 不绕过 UnifiedActivationGate（以 safety_invariants_ok 统一前置）。
⑥ 不 AI 代责（审计禁止 record_human_approval；健康候选 requires_human_review 恒 True，
   报告 anomalies 仅候选、不经人确认不得处置）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

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


class AgentExecutionStatus(str, Enum):
    """Agent 执行状态（事实型，仅记录结果，不评价好坏）。

    取值：success / failure / timeout / error / cancelled / running。
    """

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"
    RUNNING = "running"


class AgentMetricType(str, Enum):
    """Agent 指标类型（任务2）。

    支持调用次数 / 成功率 / 耗时三类事实型指标；**不含任何好/坏评价语义**。
    """

    CALL_COUNT = "call_count"          # 调用次数（整数事实）
    SUCCESS_RATE = "success_rate"      # 成功率（0~1 事实比例）
    DURATION = "duration"              # 耗时（秒，平均/事实）


@dataclass
class AgentExecutionLog:
    """Agent 运行日志（任务1）。

    严格对应任务1 字段：execution_id / agent_id / task_id / input_type /
    output_type / status / duration / timestamp；额外增加 org_id 做组织隔离。

    **只记录事实**：status 为实际执行结果（不评价 Agent 优劣），duration 为实测耗时；
    所有字段均为事实型，不承载任何评价/决策/建议语义（红线③/⑥）。
    """

    execution_id: str
    agent_id: str
    task_id: str
    org_id: str = ""
    input_type: str = ""           # 输入类型事实（如 text / image / json）
    output_type: str = ""          # 输出类型事实（如 text / json / tool_call）
    status: AgentExecutionStatus = AgentExecutionStatus.SUCCESS  # 事实结果
    duration: float = 0.0          # 耗时（秒），事实
    timestamp: str = ""            # 执行时间戳（事实）

    def __post_init__(self) -> None:
        # status 统一以枚举存储，避免字符串漂移。
        if not isinstance(self.status, AgentExecutionStatus):
            self.status = AgentExecutionStatus(self.status)

    @property
    def is_successful(self) -> bool:
        """事实派生：是否成功（仅读，不评价 Agent 本身）。"""
        return self.status == AgentExecutionStatus.SUCCESS


@dataclass
class AgentMetric:
    """Agent 指标（任务2）。

    字段严格对应：agent_id / metric_type / value / period / source；额外增加 org_id。
    支持调用次数 / 成功率 / 耗时三类指标。

    **禁止自动评价 Agent 好坏**：本模型仅为事实数字载体，不含 verdict / score /
    rating / grade 等评价字段，也不提供任何评价/打分方法（红线③/⑥：结构上禁评）。
    """

    metric_id: str
    agent_id: str
    metric_type: AgentMetricType
    value: float
    org_id: str = ""
    period: str = ""               # 指标周期（如 2026-08 / 2026-W32）
    source: str = ""               # 数据来源（如 derived_from_execution_log / agent_trace）

    def __post_init__(self) -> None:
        if not isinstance(self.metric_type, AgentMetricType):
            self.metric_type = AgentMetricType(self.metric_type)
        # 防编造：成功率 / 次数 / 耗时均不得为负；成功率裁剪至 [0,1]（仅范围约束，不评价）。
        v = float(self.value)
        if self.metric_type == AgentMetricType.SUCCESS_RATE:
            v = max(0.0, min(1.0, v))
        elif v < 0:
            v = 0.0
        self.value = v


@dataclass
class AgentTrace:
    """Agent 调用链（任务3）。

    记录 agent 调用链：trace_id / agent_id / parent_agent / child_agent / action /
    timestamp / org_id，要求可追踪。

    parent_agent 为空表示根调用；child_agent 为空表示叶子调用（不再下钻）。
    所有字段均为事实型，不承载评价/决策语义（红线③/⑥）。
    """

    trace_id: str
    agent_id: str
    org_id: str = ""
    parent_agent: str = ""         # 父 Agent id（根调用为空）
    child_agent: str = ""          # 子 Agent id（叶子调用为空）
    action: str = ""               # 调用动作事实（如 invoke / delegate / handoff）
    timestamp: str = ""            # 调用时间戳（事实）

    @property
    def is_root(self) -> bool:
        """是否根调用（无父）。"""
        return not self.parent_agent

    @property
    def is_leaf(self) -> bool:
        """是否叶子调用（无子）。"""
        return not self.child_agent


@dataclass
class AgentHealthCandidate:
    """事实型健康候选（任务4）。

    字段严格对应：agent_id / pattern / evidence / requires_human_review。
    另含 health_id / org_id / created_at 作为登记主键与时间戳。

    ``requires_human_review`` 恒为 True（必须人工复核，AI 不代责，红线③/⑥）。
    **禁止自动禁用 Agent**：本模型不含 disable / deactivate / heal 等处置状态，
    也不提供任何处置入口（由 ``AgentHealthDetector`` 在结构上保证，红线③/⑥）。
    """

    health_id: str
    agent_id: str
    org_id: str = ""
    pattern: str = ""              # 健康模式（仅描述，如 error_rate_spike / latency_drift）
    evidence: str = ""             # 触发证据（事实数据）
    requires_human_review: bool = True   # 恒为 True：必须人工复核
    created_at: str = ""

    def __post_init__(self) -> None:
        # 红线③/⑥：任何健康候选都强制要求人工复核，AI 不代管理做禁用/处置决策。
        self.requires_human_review = True


class AgentHealthDetector(_RedLineForbiddenMixin):
    """Agent 健康检测器（任务4）。

    基于事实型执行日志 / 指标，输出健康候选，**要求人工复核**；
    结构上**禁用任何自动禁用/处置入口**（disable_agent / auto_disable / deactivate_agent /
    kill_agent / suspend_agent / restart_agent / auto_fix / auto_heal / mitigate / resolve /
    fix / close），AI 只发现、不处置、不代管理责任（红线③/⑥）。
    跨域访问抛 ``EnterpriseIsolationError``；构造断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 任务4：禁止自动禁用 Agent / 自动处置（AI 只发现，不代管理责任）
        "disable_agent",
        "auto_disable",
        "deactivate_agent",
        "kill_agent",
        "suspend_agent",
        "restart_agent",
        "auto_fix",
        "auto_heal",
        "mitigate",
        "resolve",
        "fix",
        "close",
        "evaluate_agent",
        "rate_agent",
        "score_agent",
        "judge_agent",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentHealthDetector（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def detect_from_execution_logs(
        self,
        *,
        health_id: str,
        agent_id: str,
        logs: List[AgentExecutionLog],
        failure_rate_threshold: float = 0.2,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentHealthCandidate:
        """基于执行日志检测健康候选（**仅发现**，红线③/⑥）。

        当失败率（failure/timeout/error 占比）超过阈值时输出健康候选；候选要求人工复核。
        执行日志须归属当前组织。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测健康（红线①/⑤）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        scoped = [log for log in logs if log.agent_id == agent_id]
        if not scoped:
            raise EnterpriseRedLineViolationError(
                "detect_from_execution_logs 需要至少一条该 Agent 的执行日志"
                "（禁 AI 创造无源健康候选）"
            )
        for log in scoped:
            if log.org_id != self._org_id:
                raise EnterpriseIsolationError(
                    f"执行日志 {log.execution_id!r} 归属组织 {log.org_id!r} "
                    f"与当前组织 {self._org_id!r} 不一致，禁止跨域检测"
                )
        failed = sum(
            1 for l in scoped
            if l.status in (
                AgentExecutionStatus.FAILURE,
                AgentExecutionStatus.TIMEOUT,
                AgentExecutionStatus.ERROR,
            )
        )
        fail_rate = failed / len(scoped)
        pattern = (
            f"failure_rate={round(fail_rate, 4)};"
            f"threshold={failure_rate_threshold};total={len(scoped)};failed={failed}"
        )
        evidence = f"executions={len(scoped)};failed={failed};fail_rate={round(fail_rate, 4)}"
        cand = AgentHealthCandidate(
            health_id=health_id,
            agent_id=agent_id,
            org_id=self._org_id,
            pattern=pattern,
            evidence=evidence,
            created_at=created_at,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def detect_from_metrics(
        self,
        *,
        health_id: str,
        agent_id: str,
        metrics: List[AgentMetric],
        success_rate_floor: float = 0.8,
        duration_ceiling: float = 10.0,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentHealthCandidate:
        """基于指标检测健康候选（**仅发现**，红线③/⑥）。

        当成功率低于下限或平均耗时高于上限时输出健康候选；候选要求人工复核。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测健康（红线①/⑤）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        scoped = [m for m in metrics if m.agent_id == agent_id]
        if not scoped:
            raise EnterpriseRedLineViolationError(
                "detect_from_metrics 需要至少一条该 Agent 的指标"
                "（禁 AI 创造无源健康候选）"
            )
        for m in scoped:
            if m.org_id != self._org_id:
                raise EnterpriseIsolationError(
                    f"指标 {m.metric_id!r} 归属组织 {m.org_id!r} "
                    f"与当前组织 {self._org_id!r} 不一致，禁止跨域检测"
                )
        success_rate = next(
            (m.value for m in scoped if m.metric_type == AgentMetricType.SUCCESS_RATE),
            None,
        )
        avg_duration = next(
            (m.value for m in scoped if m.metric_type == AgentMetricType.DURATION),
            None,
        )
        signals = []
        if success_rate is not None and success_rate < success_rate_floor:
            signals.append(f"success_rate={success_rate}<{success_rate_floor}")
        if avg_duration is not None and avg_duration > duration_ceiling:
            signals.append(f"avg_duration={avg_duration}>{duration_ceiling}")
        pattern = "metric_health;" + ";".join(signals) if signals else "metric_health;nominal"
        evidence = (
            f"success_rate={success_rate};avg_duration={avg_duration};"
            f"floor={success_rate_floor};ceiling={duration_ceiling}"
        )
        cand = AgentHealthCandidate(
            health_id=health_id,
            agent_id=agent_id,
            org_id=self._org_id,
            pattern=pattern,
            evidence=evidence,
            created_at=created_at,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def _record(
        self,
        cand: AgentHealthCandidate,
        actor_id: str,
        actor_kind: "str | None",
        created_at: str,
    ) -> None:
        if self._audit is not None:
            self._audit.record_agent_health_action(
                record_id=f"agent-health-{cand.health_id}",
                actor_id=actor_id,
                action="detect_agent_health",
                target=cand.agent_id,
                detail=(
                    f"pattern={cand.pattern};evidence={cand.evidence};"
                    f"requires_human_review={cand.requires_human_review}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )


@dataclass
class AgentPerformanceReport:
    """事实型 Agent 性能报告（任务5）。

    字段：report_id / org_id / period / facts / trends / anomaly_candidates / sources /
    created_at / source_trace。

    只汇编事实（执行摘要 / 指标趋势 / 健康候选）/ 来源，**不**含任何自动优化建议 /
    调参 / 重配置语义（红线③/⑥：AI 只汇编，不替工程/管理做优化决策）。
    """

    report_id: str
    org_id: str
    period: str = ""                          # 报告周期
    facts: List[str] = field(default_factory=list)         # 事实 id（execution_id / metric_id）
    trends: List[str] = field(default_factory=list)        # 指标趋势描述（事实型）
    anomaly_candidates: List[AgentHealthCandidate] = field(default_factory=list)  # 健康候选（仅候选）
    sources: List[str] = field(default_factory=list)       # 数据源 tag
    created_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 任务5：来源不可追溯 → 禁止生成报告（AI 不得创造无源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentPerformanceReport {self.report_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止生成 AI 创造的无源报告（任务5）"
            )


class AgentPerformanceReportService(_RedLineForbiddenMixin):
    """Agent 性能报告服务（任务5）。

    仅把已有的事实型执行日志 / 指标 / 健康候选**汇编**为性能报告；跨域访问抛隔离错误；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_optimize / tune_agent / reconfigure_agent
    等方法（红线②/③/④/⑥：禁止 AI 自动优化 Agent）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 任务5：禁止自动优化 Agent（AI 只汇编事实，不替工程/管理做调优决策）
        "auto_optimize",
        "optimize_agent",
        "tune_agent",
        "auto_tune",
        "retrain_agent",
        "reconfigure_agent",
        "auto_fix",
        "auto_heal",
        "make_management_decision",
        "recommend",
        "decide",
        "evaluate_agent",
        "rate_agent",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentPerformanceReportService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def generate_report(
        self,
        *,
        report_id: str,
        period: str = "",
        executions: "List[AgentExecutionLog] | None" = None,
        metrics: "List[AgentMetric] | None" = None,
        health_candidates: "List[AgentHealthCandidate] | None" = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentPerformanceReport:
        """汇编事实型性能报告（**仅汇总事实**，红线③/⑥）。

        所有输入须归属当前组织；其来源被聚合为报告统一溯源链，若不可溯源则抛红线违例
        （任务5：禁 AI 创造无源报告）。健康候选仅作候选列出，不得触发任何处置。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成性能报告（红线①/⑤）"
            )
        executions = executions or []
        metrics = metrics or []
        health_candidates = health_candidates or []

        from agents.enterprise.organization import EnterpriseIsolationError

        all_inputs: list = list(executions) + list(metrics) + list(health_candidates)
        if not all_inputs:
            raise EnterpriseRedLineViolationError(
                "generate_report 至少需要一条事实型输入（执行日志/指标/健康候选），"
                "禁止生成空的无源报告（任务5）"
            )
        for obj in all_inputs:
            if getattr(obj, "org_id", self._org_id) != self._org_id:
                raise EnterpriseIsolationError(
                    "报告输入归属组织不一致，禁止跨域汇编"
                )

        trace = SourceTrace(
            raw_refs=(
                [e.execution_id for e in executions]
                + [m.metric_id for m in metrics]
                + [c.health_id for c in health_candidates]
            ),
        )
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "generate_report 聚合后的溯源链不可追溯：禁止生成 AI 创造的无源报告（任务5）"
            )

        fact_ids = [e.execution_id for e in executions] + [m.metric_id for m in metrics]
        trend_parts: List[str] = []
        for m in metrics:
            trend_parts.append(f"{m.agent_id}:{m.metric_type.value}={round(m.value, 4)}")
        source_tags = list(dict.fromkeys([m.source for m in metrics if m.source]))

        report = AgentPerformanceReport(
            report_id=report_id,
            org_id=self._org_id,
            period=period,
            facts=fact_ids,
            trends=trend_parts,
            anomaly_candidates=list(health_candidates),
            sources=source_tags,
            created_at=created_at,
            source_trace=trace,
        )
        if self._audit is not None:
            self._audit.record_agent_metric_action(
                record_id=f"agent-report-{report_id}",
                actor_id=actor_id,
                action="generate_agent_performance_report",
                target=report_id,
                detail=(
                    f"period={period};facts={len(fact_ids)};"
                    f"candidates={len(health_candidates)};trace={trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return report


class AgentObservabilityService(_RedLineForbiddenMixin):
    """Agent 可观测性聚合服务（任务1–7 统一入口）。

    承载 Agent 执行日志 / 指标 / 调用链追踪的登记与读取；接入身份层 + AgentPermissionPolicy
    + 知识可见性策略做监控数据权限隔离（默认拒绝：未授权角色不可读取监控数据）；
    联动审计（AGENT_METRIC / AGENT_TRACE / AGENT_HEALTH）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    - 监控数据读取经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线③/⑥）。
    - 不持有任何 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / disable_agent / auto_optimize / evaluate_agent 等方法
      （红线②/③/④/⑥：禁止 AI 评价/禁用/优化 Agent）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 任务4/5/6：禁止 AI 评价 / 禁用 / 优化 Agent（只观测，不干预）
        "disable_agent",
        "auto_disable",
        "deactivate_agent",
        "kill_agent",
        "restart_agent",
        "auto_fix",
        "auto_heal",
        "auto_optimize",
        "optimize_agent",
        "tune_agent",
        "reconfigure_agent",
        "evaluate_agent",
        "rate_agent",
        "score_agent",
        "judge_agent",
        "make_management_decision",
        "recommend",
        "decide",
    )

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
                "AgentObservabilityService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._executions: dict[str, AgentExecutionLog] = {}
        self._metrics: dict[str, AgentMetric] = {}
        self._traces: dict[str, AgentTrace] = {}
        # 复用 3.8.14 健康检测 / 报告子服务（共享审计与可见性）。
        self.health_detector = AgentHealthDetector(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )
        self.report_service = AgentPerformanceReportService(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )

    # ---- 登记（写路径，断言红线 + 审计）----

    def record_execution(
        self,
        *,
        execution: AgentExecutionLog,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentExecutionLog:
        """登记一条 Agent 执行日志（事实型，仅记录）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记执行日志（红线①/⑤）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        # 登记即归属当前组织（监控数据统一作用域）。
        execution.org_id = self._org_id
        self._executions[execution.execution_id] = execution
        if self._audit is not None:
            self._audit.record_agent_execution_action(
                record_id=f"agent-exec-{execution.execution_id}",
                actor_id=actor_id,
                action="record_agent_execution_log",
                target=execution.agent_id,
                detail=(
                    f"execution_id={execution.execution_id};task_id={execution.task_id};"
                    f"status={execution.status.value};duration={execution.duration}"
                ),
                ts=execution.timestamp,
                actor_kind=actor_kind,
            )
        return execution

    def record_metric(
        self,
        *,
        metric: AgentMetric,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentMetric:
        """登记一条 Agent 指标（事实型，不评价）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记指标（红线①/⑤）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        metric.org_id = self._org_id
        self._metrics[metric.metric_id] = metric
        if self._audit is not None:
            self._audit.record_agent_metric_action(
                record_id=f"agent-metric-{metric.metric_id}",
                actor_id=actor_id,
                action="record_agent_metric",
                target=metric.agent_id,
                detail=(
                    f"metric_type={metric.metric_type.value};value={metric.value};"
                    f"period={metric.period};source={metric.source}"
                ),
                ts="",
                actor_kind=actor_kind,
            )
        return metric

    def record_trace(
        self,
        *,
        trace: AgentTrace,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentTrace:
        """登记一条 Agent 调用链追踪（事实型，可追踪）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记调用链（红线①/⑤）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        trace.org_id = self._org_id
        self._traces[trace.trace_id] = trace
        if self._audit is not None:
            self._audit.record_agent_trace_action(
                record_id=f"agent-trace-{trace.trace_id}",
                actor_id=actor_id,
                action="record_agent_trace",
                target=trace.agent_id,
                detail=(
                    f"parent={trace.parent_agent or 'root'};"
                    f"child={trace.child_agent or 'leaf'};action={trace.action}"
                ),
                ts=trace.timestamp,
                actor_kind=actor_kind,
            )
        return trace

    # ---- 派生指标（基于执行日志，事实计算，不评价）----

    def derive_metrics(
        self,
        *,
        agent_id: str,
        period: str = "",
        execution_ids: "List[str] | None" = None,
    ) -> List[AgentMetric]:
        """基于执行日志派生三类事实指标：调用次数 / 成功率 / 平均耗时。

        **只计算事实数字，不评价 Agent 优劣**（红线③/⑥：禁评）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下派生指标（红线①/⑤）"
            )
        logs = [
            e for e in self._executions.values()
            if e.agent_id == agent_id
            and (execution_ids is None or e.execution_id in execution_ids)
        ]
        if not logs:
            raise EnterpriseRedLineViolationError(
                "derive_metrics 需要至少一条该 Agent 的执行日志（禁 AI 创造无源指标）"
            )
        total = len(logs)
        success = sum(1 for e in logs if e.is_successful)
        success_rate = success / total if total else 0.0
        avg_duration = sum(e.duration for e in logs) / total if total else 0.0

        out = [
            AgentMetric(
                metric_id=f"{agent_id}:call_count:{period or 'all'}",
                agent_id=agent_id,
                metric_type=AgentMetricType.CALL_COUNT,
                value=float(total),
                org_id=self._org_id,
                period=period,
                source="derived_from_execution_log",
            ),
            AgentMetric(
                metric_id=f"{agent_id}:success_rate:{period or 'all'}",
                agent_id=agent_id,
                metric_type=AgentMetricType.SUCCESS_RATE,
                value=success_rate,
                org_id=self._org_id,
                period=period,
                source="derived_from_execution_log",
            ),
            AgentMetric(
                metric_id=f"{agent_id}:duration:{period or 'all'}",
                agent_id=agent_id,
                metric_type=AgentMetricType.DURATION,
                value=avg_duration,
                org_id=self._org_id,
                period=period,
                source="derived_from_execution_log",
            ),
        ]
        for m in out:
            self._metrics[m.metric_id] = m
        return out

    # ---- 读取（权限隔离，默认拒绝）----

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """监控数据读取权限校验（默认拒绝）。

        结合 AgentPermissionPolicy：角色须在该资源类别作用域内，且若声明了读权限
        须经 IdentityService 校验。任一不过即抛隔离错误（红线③/⑥：监控数据受控访问）。
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
                    f"用户角色无权限访问 Agent 监控数据（resource={resource_category}），默认拒绝"
                )
        elif self._identity is not None:
            # 无独立策略时回退到身份层只读校验（默认拒绝无身份/无权限者）。
            if not (hasattr(user, "role") and self._identity.check(user, Permission.READ_RESOURCE)):
                raise EnterpriseIsolationError(
                    "无 AgentPermissionPolicy 时，需经身份层 READ_RESOURCE 校验，默认拒绝"
                )

    def list_executions(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentExecutionLog]:
        """列出当前组织下执行日志（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [e for e in self._executions.values() if e.org_id == self._org_id]
        if agent_id:
            out = [e for e in out if e.agent_id == agent_id]
        return out

    def list_metrics(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentMetric]:
        """列出当前组织下指标（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [m for m in self._metrics.values() if m.org_id == self._org_id]
        if agent_id:
            out = [m for m in out if m.agent_id == agent_id]
        return out

    def list_traces(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentTrace]:
        """列出当前组织下调用链追踪（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [t for t in self._traces.values() if t.org_id == self._org_id]
        if agent_id:
            out = [t for t in out if t.agent_id == agent_id]
        return out

    def detect_health(
        self,
        *,
        health_id: str,
        agent_id: str,
        user: object,
        resource_category: str = "data",
        source: str = "executions",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
        **kwargs,
    ) -> AgentHealthCandidate:
        """检测 Agent 健康候选（权限隔离 + 仅发现 + 要求人工复核，红线③/⑥）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        if source == "metrics":
            return self.health_detector.detect_from_metrics(
                health_id=health_id,
                agent_id=agent_id,
                metrics=self.list_metrics(user=user, agent_id=agent_id),
                created_at=created_at,
                actor_id=actor_id,
                actor_kind=actor_kind,
                **kwargs,
            )
        return self.health_detector.detect_from_execution_logs(
            health_id=health_id,
            agent_id=agent_id,
            logs=self.list_executions(user=user, agent_id=agent_id),
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=actor_kind,
            **kwargs,
        )

    def generate_report(
        self,
        *,
        report_id: str,
        user: object,
        period: str = "",
        resource_category: str = "data",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentPerformanceReport:
        """生成 Agent 性能报告（权限隔离 + 仅汇编事实，红线③/⑥）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self.report_service.generate_report(
            report_id=report_id,
            period=period,
            executions=self.list_executions(user=user),
            metrics=self.list_metrics(user=user),
            health_candidates=[],
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )


__all__ = [
    "AgentExecutionStatus",
    "AgentMetricType",
    "AgentExecutionLog",
    "AgentMetric",
    "AgentTrace",
    "AgentHealthCandidate",
    "AgentHealthDetector",
    "AgentPerformanceReport",
    "AgentPerformanceReportService",
    "AgentObservabilityService",
]

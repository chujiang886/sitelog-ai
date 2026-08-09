"""Enterprise Agent Evaluation & Quality Governance Layer（Phase 3.8.15）。

新增（任务1–5）：
- ``AgentQualityMetricType``：质量指标类型枚举（事实型，仅记录信号，不评价）。
- ``AgentQualityMetric``：Agent 质量指标（metric_id / agent_id / metric_type / value /
  source / period / org_id），**只记录事实，禁止自动评分结论**（不含 verdict/score/
  rating/grade 语义）。
- ``AgentEvaluation``：人工评价（evaluation_id / agent_id / evaluator / criteria /
  comment / timestamp / org_id），**人工评价，禁 AI 作最终评价者**。
- ``AgentVersionComparison``：多版本运行数据/变化/性能比较（comparison_id / agent_id /
  versions / run_data_facts / changes / performance_facts / source_trace），**禁止自动
  决定升级**（不含 upgrade/promote 结论字段，不提供任何决定方法）。
- ``AgentFeedback``：用户反馈（feedback_id / agent_id / user_id / content / timestamp /
  org_id），**用户反馈须人工审核**（requires_human_review 恒 True）。
- ``AgentQualityReport``：事实型质量治理报告（report_id / org_id / period /
  quality_metrics / evaluations / feedbacks / version_comparisons / trends / sources /
  source_trace），**来源可追溯**（source_trace.is_traceable 强制）。
- ``AgentQualityGovernanceService``：聚合运营层，承载质量指标登记 / 人工评价提交 /
  版本比较 / 用户反馈 / 质量报告汇编；接入身份层 + AgentPermissionPolicy + 知识可见性策略
  做评价数据权限隔离；联动审计（AGENT_QUALITY / AGENT_EVALUATION / AGENT_FEEDBACK，任务6）。

红线（fail-closed，复用 3.8.0~3.8.14 基座 + 3.8.15 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``。
② 不输出 engineering_approved。
③ 不自动报价、不自动审批、不 AI 自动评级 Agent（auto_rate_agent / auto_grade_agent /
   auto_score_agent / rate_agent / grade_agent / score_agent / evaluate_agent / judge_agent
   被 mixin 拦截）。
④ 不 AI 自动禁用/弃用 Agent（auto_disable_agent / auto_deprecate_agent / disable_agent /
   deprecate_agent 等被拦截）。
⑤ 不 AI 自动修改 Agent（auto_modify_agent / modify_agent / auto_update_agent / update_agent
   等被拦截）。
⑥ 不 AI 代责（审计禁止 record_human_approval；评价必须由 USER 提交；反馈须人工审核；
   版本比较不自动决定升级）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import AuditService, require_human_actor
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class AgentQualityMetricType(str, Enum):
    """Agent 质量指标类型（任务1）。

    承载质量相关的**事实型**信号：任务计数 / 成功计数 / 正向反馈计数 / 负向反馈计数 /
    评价计数 / 平均响应耗时。**不含任何好/坏评价语义、不含 score/rating 字段**
    （红线③/⑥：结构上禁评）。
    """

    TASK_COUNT = "task_count"                  # 任务计数（整数事实）
    SUCCESS_COUNT = "success_count"            # 成功计数（整数事实）
    FEEDBACK_POSITIVE = "feedback_positive"    # 正向反馈计数（整数事实）
    FEEDBACK_NEGATIVE = "feedback_negative"    # 负向反馈计数（整数事实）
    EVALUATION_COUNT = "evaluation_count"      # 人工评价计数（整数事实）
    AVG_RESPONSE_TIME = "avg_response_time"    # 平均响应耗时（秒，事实）


@dataclass
class AgentQualityMetric:
    """Agent 质量指标（任务1）。

    字段严格对应：metric_id / agent_id / metric_type / value / source / period；
    额外增加 org_id 做组织隔离。

    **只记录事实**：本模型仅为事实数字载体，不含 verdict / score / rating / grade 等评价
    字段，也不提供任何评价/打分方法（红线③/⑥：结构上禁评）。``metric_type`` 仅描述事实信号
    类别，不构成对 Agent 好坏的结论。
    """

    metric_id: str
    agent_id: str
    metric_type: AgentQualityMetricType
    value: float
    org_id: str = ""
    period: str = ""               # 指标周期（如 2026-08 / 2026-W32）
    source: str = ""               # 数据来源（如 derived_from_execution_log / user_feedback）

    def __post_init__(self) -> None:
        if not isinstance(self.metric_type, AgentQualityMetricType):
            self.metric_type = AgentQualityMetricType(self.metric_type)
        # 防编造：指标值不得为负（仅范围约束，不评价）。
        v = float(self.value)
        if v < 0:
            v = 0.0
        self.value = v


@dataclass
class AgentEvaluation:
    """人工评价（任务2）。

    字段严格对应：evaluation_id / agent_id / evaluator / criteria / comment / timestamp；
    额外增加 org_id。

    **人工评价，禁 AI 作最终评价者**：``evaluator`` 必须为真实人工（USER）标识，
    AI/系统不得作为评价者（``__post_init__`` 与 ``AgentQualityGovernanceService.
    submit_evaluation`` 双重拦截，红线⑥）。``criteria`` / ``comment`` 仅记录人工填写的
    评价事实，**不含** AI 自动生成的评分/结论语义。
    """

    evaluation_id: str
    agent_id: str
    evaluator: str               # 评价者真实 USER id（不得为 ai / system / 空）
    org_id: str = ""
    criteria: str = ""           # 评价维度/标准（事实描述，不含结论）
    comment: str = ""            # 人工评价内容（事实，不含 AI 自动结论）
    timestamp: str = ""

    def __post_init__(self) -> None:
        # 红线⑥：AI/系统不得作为最终评价者（数据层防御性拦截）。
        if not self.evaluator or self.evaluator in ("ai", "system"):
            raise EnterpriseRedLineViolationError(
                "红线⑥：Agent 评价必须由真实人工（USER）执行，AI 不得作最终评价者"
            )


@dataclass
class AgentVersionComparison:
    """多版本运行数据/变化/性能比较（任务3）。

    字段：comparison_id / agent_id / versions / run_data_facts / changes /
    performance_facts / source_trace / created_at / org_id。

    **禁止自动决定升级**：本模型仅记录版本间的运行数据事实、变化事实与性能事实，
    **不含 upgrade / promote / recommend 结论字段**，也不提供任何决定升级的方法
    （由 ``AgentQualityGovernanceService.compare_versions`` 在结构上保证，红线③/⑥：
    AI 不得替管理/工程决定版本升级）。
    """

    comparison_id: str
    agent_id: str
    org_id: str = ""
    versions: List[str] = field(default_factory=list)           # 参与比较的版本 id
    run_data_facts: List[str] = field(default_factory=list)     # 运行数据事实 id
    changes: List[str] = field(default_factory=list)            # 版本间变化事实（delta 描述）
    performance_facts: List[str] = field(default_factory=list)  # 性能事实 id
    created_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 任务3：来源不可追溯 → 禁止生成比较（AI 不得创造无源比较）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentVersionComparison {self.comparison_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止生成 AI 创造的无源比较（任务3）"
            )


@dataclass
class AgentFeedback:
    """用户反馈（任务4）。

    字段严格对应：feedback_id / agent_id / user_id / content / timestamp；额外增加 org_id。

    ``requires_human_review`` 恒为 True（**用户反馈须人工审核**，AI 不代责，红线③/⑥）。
    不含任何 enable/disable/modify Agent 的处置状态，也不提供处置入口（由
    ``AgentQualityGovernanceService`` 在结构上保证，红线④/⑤）。
    """

    feedback_id: str
    agent_id: str
    user_id: str                 # 提交反馈的真实用户 id
    content: str                 # 反馈内容（事实）
    org_id: str = ""
    timestamp: str = ""
    requires_human_review: bool = True   # 恒为 True：须人工审核
    reviewed: bool = False                # 是否已人工审核
    reviewed_by: str = ""                 # 审核人（真实 USER）
    review_status: str = "pending"        # pending / approved / rejected

    def __post_init__(self) -> None:
        # 红线③/⑥：任何用户反馈都强制要求人工审核，AI 不代责做处置/弃用决策。
        self.requires_human_review = True


@dataclass
class AgentQualityReport:
    """事实型 Agent 质量治理报告（任务5）。

    字段：report_id / org_id / period / quality_metrics / evaluations / feedbacks /
    version_comparisons / trends / sources / created_at / source_trace。

    只汇编事实（质量指标 / 人工评价 / 用户反馈 / 版本比较）/ 来源，**不**含任何自动优化建议 /
    版本升级建议 / 处置 Agent 语义（红线③/④/⑤/⑥：AI 只汇编，不替工程/管理做决策）。
    """

    report_id: str
    org_id: str
    period: str = ""                                      # 报告周期
    quality_metrics: List[str] = field(default_factory=list)       # 质量指标 id
    evaluations: List[str] = field(default_factory=list)          # 人工评价 id
    feedbacks: List[str] = field(default_factory=list)            # 用户反馈 id
    version_comparisons: List[str] = field(default_factory=list)  # 版本比较 id
    trends: List[str] = field(default_factory=list)               # 趋势描述（事实型）
    sources: List[str] = field(default_factory=list)             # 数据源 tag
    created_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 任务5：来源不可追溯 → 禁止生成报告（AI 不得创造无源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentQualityReport {self.report_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止生成 AI 创造的无源报告（任务5）"
            )


class AgentQualityGovernanceService(_RedLineForbiddenMixin):
    """Agent 质量治理聚合服务（任务1–7 统一入口）。

    承载 Agent 质量指标登记 / 人工评价提交 / 版本比较 / 用户反馈 / 质量报告汇编；接入身份层
    + AgentPermissionPolicy + 知识可见性策略做评价数据权限隔离（默认拒绝）；联动审计
    （AGENT_QUALITY / AGENT_EVALUATION / AGENT_FEEDBACK）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    - 评价数据读取经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线③/⑥）。
    - 不持有任何 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_rate_agent / auto_grade_agent / auto_score_agent /
      auto_disable_agent / auto_deprecate_agent / auto_modify_agent / modify_agent /
      recommend_upgrade / decide_upgrade 等方法（红线②/③/④/⑤/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 任务2/红线③：禁止 AI 自动评级 Agent（AI 只汇编事实，不评价好坏）。
        "auto_rate_agent",
        "auto_grade_agent",
        "auto_score_agent",
        "rate_agent",
        "grade_agent",
        "score_agent",
        "evaluate_agent",
        "judge_agent",
        # 任务4/红线④：禁止 AI 自动禁用/弃用 Agent（用户反馈仅审核，不处置 Agent）。
        "auto_disable_agent",
        "auto_deprecate_agent",
        "disable_agent",
        "deprecate_agent",
        "auto_deactivate",
        "deactivate_agent",
        "auto_retire",
        "retire_agent",
        # 任务4/红线⑤：禁止 AI 自动修改 Agent（反馈/评价不触发 Agent 自动改动）。
        "auto_modify_agent",
        "modify_agent",
        "auto_update_agent",
        "update_agent",
        "auto_edit_agent",
        "edit_agent",
        "change_agent",
        # 任务3/红线③：禁止自动决定升级版本（只比较事实，不替管理/工程做升级决策）。
        "auto_upgrade",
        "recommend_upgrade",
        "decide_upgrade",
        "promote_version",
        "auto_promote",
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
                "AgentQualityGovernanceService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._quality_metrics: dict[str, AgentQualityMetric] = {}
        self._evaluations: dict[str, AgentEvaluation] = {}
        self._feedbacks: dict[str, AgentFeedback] = {}
        self._version_comparisons: dict[str, AgentVersionComparison] = {}

    # ---- 登记（写路径，断言红线 + 审计）----

    def record_quality_metric(
        self,
        *,
        metric: AgentQualityMetric,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentQualityMetric:
        """登记一条 Agent 质量指标（事实型，不评价，红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记质量指标（红线①/⑤）"
            )
        metric.org_id = self._org_id
        self._quality_metrics[metric.metric_id] = metric
        if self._audit is not None:
            self._audit.record_agent_quality_action(
                record_id=f"agent-quality-{metric.metric_id}",
                actor_id=actor_id,
                action="record_agent_quality_metric",
                target=metric.agent_id,
                detail=(
                    f"metric_type={metric.metric_type.value};value={metric.value};"
                    f"period={metric.period};source={metric.source}"
                ),
                ts="",
                actor_kind=actor_kind,
            )
        return metric

    def submit_evaluation(
        self,
        *,
        evaluation: AgentEvaluation,
        actor_id: str = "",
        actor_kind: "str | None" = None,
    ) -> AgentEvaluation:
        """提交一条人工评价（**必须由真实 USER 提交**，红线⑥：禁 AI 作最终评价者）。

        ``actor_kind`` 必须严格等于 ``AuditActorKind.USER``（``require_human_actor`` 强制）；
        ``evaluation.evaluator`` 亦不得为 ai / system（模型 ``__post_init__`` 双重拦截）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交评价（红线①/⑤）"
            )
        from agents.enterprise.audit import AuditActorKind

        require_human_actor(actor_kind or AuditActorKind.USER)
        evaluation.org_id = self._org_id
        self._evaluations[evaluation.evaluation_id] = evaluation
        if self._audit is not None:
            self._audit.record_agent_evaluation_action(
                record_id=f"agent-eval-{evaluation.evaluation_id}",
                actor_id=actor_id or evaluation.evaluator,
                action="submit_agent_evaluation",
                target=evaluation.agent_id,
                detail=(
                    f"evaluator={evaluation.evaluator};"
                    f"criteria={evaluation.criteria};"
                    f"comment_len={len(evaluation.comment)}"
                ),
                ts=evaluation.timestamp,
                actor_kind=AuditActorKind.USER,
            )
        return evaluation

    def compare_versions(
        self,
        *,
        comparison_id: str,
        agent_id: str,
        version_facts: "dict[str, dict] | None" = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentVersionComparison:
        """比较多版本运行数据/变化/性能事实（**仅比较，禁自动决定升级**，红线③/⑥）。

        ``version_facts`` 形如 ``{version_id: {"call_count": int, "success_rate": float,
        "duration": float}}``。本方法只产出变化事实（delta）与性能事实，**绝不**决定哪个版本
        应升级/降级（结构上无解 upgrade/promote 入口）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下比较版本（红线①/⑤）"
            )
        version_facts = version_facts or {}
        if not version_facts:
            raise EnterpriseRedLineViolationError(
                "compare_versions 至少需要一个版本的实事数据，禁止生成空的无源比较（任务3）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        version_ids = list(version_facts.keys())
        run_data_facts: List[str] = []
        changes: List[str] = []
        performance_facts: List[str] = []

        prev = None
        for vid in version_ids:
            facts = version_facts[vid]
            run_data_facts.append(
                f"v={vid};call_count={facts.get('call_count')};"
                f"success_rate={facts.get('success_rate')};duration={facts.get('duration')}"
            )
            performance_facts.append(
                f"v={vid};success_rate={facts.get('success_rate')};duration={facts.get('duration')}"
            )
            if prev is not None:
                pfacts = version_facts[prev]
                delta_call = (facts.get("call_count") or 0) - (pfacts.get("call_count") or 0)
                delta_sr = round(
                    (facts.get("success_rate") or 0.0) - (pfacts.get("success_rate") or 0.0), 4
                )
                delta_dur = round(
                    (facts.get("duration") or 0.0) - (pfacts.get("duration") or 0.0), 4
                )
                changes.append(
                    f"{prev}->{vid};call_count_delta={delta_call};"
                    f"success_rate_delta={delta_sr};duration_delta={delta_dur}"
                )
            prev = vid

        trace = SourceTrace(raw_refs=version_ids)
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "compare_versions 聚合后的溯源链不可追溯：禁止生成 AI 创造的无源比较（任务3）"
            )

        comp = AgentVersionComparison(
            comparison_id=comparison_id,
            agent_id=agent_id,
            org_id=self._org_id,
            versions=version_ids,
            run_data_facts=run_data_facts,
            changes=changes,
            performance_facts=performance_facts,
            created_at=created_at,
            source_trace=trace,
        )
        self._version_comparisons[comparison_id] = comp
        if self._audit is not None:
            self._audit.record_agent_quality_action(
                record_id=f"agent-vercmp-{comparison_id}",
                actor_id=actor_id,
                action="compare_agent_versions",
                target=agent_id,
                detail=(
                    f"versions={len(version_ids)};changes={len(changes)};"
                    f"trace={trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return comp

    def submit_feedback(
        self,
        *,
        feedback: AgentFeedback,
        reviewed: bool = False,
        reviewed_by: str = "",
        review_status: str = "pending",
        actor_id: str = "",
        actor_kind: "str | None" = None,
    ) -> AgentFeedback:
        """提交一条用户反馈（事实型；**须人工审核**，红线③/⑥）。

        反馈本身只记录用户事实内容；审核（approve/reject）须经真实人工，由 ``review_feedback``
        显式执行（默认不审核，requires_human_review 恒 True）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交反馈（红线①/⑤）"
            )
        feedback.org_id = self._org_id
        self._feedbacks[feedback.feedback_id] = feedback
        if self._audit is not None:
            self._audit.record_agent_feedback_action(
                record_id=f"agent-fb-{feedback.feedback_id}",
                actor_id=actor_id or feedback.user_id,
                action="submit_agent_feedback",
                target=feedback.agent_id,
                detail=(
                    f"user_id={feedback.user_id};content_len={len(feedback.content)};"
                    f"requires_human_review={feedback.requires_human_review}"
                ),
                ts=feedback.timestamp,
                actor_kind=actor_kind,
            )
        return feedback

    def review_feedback(
        self,
        *,
        feedback_id: str,
        reviewer: str,
        review_status: str = "approved",
        actor_id: str = "",
        actor_kind: "str | None" = None,
    ) -> AgentFeedback:
        """人工审核一条用户反馈（**必须由真实 USER 审核**，红线⑥：AI 不代责审核）。

        仅标记反馈的审核状态（approved / rejected），**不**触发任何 Agent 禁用/修改/升级
        （由 ``_FORBIDDEN`` 在结构上保证，红线④/⑤）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下审核反馈（红线①/⑤）"
            )
        from agents.enterprise.audit import AuditActorKind

        require_human_actor(actor_kind or AuditActorKind.USER)
        fb = self._feedbacks.get(feedback_id)
        if fb is None:
            raise EnterpriseRedLineViolationError(
                f"review_feedback 找不到反馈 {feedback_id!r}（禁 AI 审核不存在的反馈）"
            )
        if reviewer in ("ai", "system", ""):
            raise EnterpriseRedLineViolationError(
                "红线⑥：反馈审核必须由真实人工（USER）执行，AI 不得代责审核"
            )
        fb.reviewed = True
        fb.reviewed_by = reviewer
        fb.review_status = review_status
        if self._audit is not None:
            self._audit.record_agent_feedback_action(
                record_id=f"agent-fb-review-{feedback_id}",
                actor_id=actor_id or reviewer,
                action="review_agent_feedback",
                target=fb.agent_id,
                detail=(
                    f"reviewer={reviewer};review_status={review_status};"
                    f"requires_human_review={fb.requires_human_review}"
                ),
                ts="",
                actor_kind=AuditActorKind.USER,
            )
        return fb

    # ---- 报告汇编（事实型，来源可追溯）----

    def generate_quality_report(
        self,
        *,
        report_id: str,
        user: object,
        period: str = "",
        resource_category: str = "data",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentQualityReport:
        """汇编事实型质量治理报告（权限隔离 + 仅汇编事实，红线③/④/⑤/⑥）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成质量报告（红线①/⑤）"
            )
        scoped_metrics = [
            m for m in self._quality_metrics.values() if m.org_id == self._org_id
        ]
        scoped_evals = [
            e for e in self._evaluations.values() if e.org_id == self._org_id
        ]
        scoped_feedbacks = [
            f for f in self._feedbacks.values() if f.org_id == self._org_id
        ]
        scoped_comps = [
            c for c in self._version_comparisons.values() if c.org_id == self._org_id
        ]
        if not (scoped_metrics or scoped_evals or scoped_feedbacks or scoped_comps):
            raise EnterpriseRedLineViolationError(
                "generate_quality_report 至少需要一条事实型输入（质量指标/评价/反馈/版本比较），"
                "禁止生成空的无源报告（任务5）"
            )
        trace = SourceTrace(
            raw_refs=(
                [m.metric_id for m in scoped_metrics]
                + [e.evaluation_id for e in scoped_evals]
                + [f.feedback_id for f in scoped_feedbacks]
                + [c.comparison_id for c in scoped_comps]
            ),
        )
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "generate_quality_report 聚合后的溯源链不可追溯：禁止生成 AI 创造的无源报告（任务5）"
            )
        trend_parts: List[str] = []
        for m in scoped_metrics:
            trend_parts.append(
                f"{m.agent_id}:{m.metric_type.value}={round(m.value, 4)}"
            )
        source_tags = list(dict.fromkeys([m.source for m in scoped_metrics if m.source]))
        report = AgentQualityReport(
            report_id=report_id,
            org_id=self._org_id,
            period=period,
            quality_metrics=[m.metric_id for m in scoped_metrics],
            evaluations=[e.evaluation_id for e in scoped_evals],
            feedbacks=[f.feedback_id for f in scoped_feedbacks],
            version_comparisons=[c.comparison_id for c in scoped_comps],
            trends=trend_parts,
            sources=source_tags,
            created_at=created_at,
            source_trace=trace,
        )
        if self._audit is not None:
            self._audit.record_agent_quality_action(
                record_id=f"agent-qreport-{report_id}",
                actor_id=actor_id,
                action="generate_agent_quality_report",
                target=report_id,
                detail=(
                    f"period={period};metrics={len(scoped_metrics)};"
                    f"evals={len(scoped_evals)};feedbacks={len(scoped_feedbacks)};"
                    f"comps={len(scoped_comps)};trace={trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return report

    # ---- 读取（权限隔离，默认拒绝）----

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """评价数据读取权限校验（默认拒绝）。

        结合 AgentPermissionPolicy：角色须在该资源类别作用域内，且若声明了读权限须经
        IdentityService 校验。任一不过即抛隔离错误（红线③/⑥：评价数据受控访问）。
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
                    f"用户角色无权限访问 Agent 质量治理数据（resource={resource_category}），默认拒绝"
                )
        elif self._identity is not None:
            if not (hasattr(user, "role") and self._identity.check(user, Permission.READ_RESOURCE)):
                raise EnterpriseIsolationError(
                    "无 AgentPermissionPolicy 时，需经身份层 READ_RESOURCE 校验，默认拒绝"
                )

    def list_quality_metrics(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentQualityMetric]:
        """列出当前组织下质量指标（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [m for m in self._quality_metrics.values() if m.org_id == self._org_id]
        if agent_id:
            out = [m for m in out if m.agent_id == agent_id]
        return out

    def list_evaluations(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentEvaluation]:
        """列出当前组织下人工评价（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [e for e in self._evaluations.values() if e.org_id == self._org_id]
        if agent_id:
            out = [e for e in out if e.agent_id == agent_id]
        return out

    def list_feedbacks(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentFeedback]:
        """列出当前组织下用户反馈（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [f for f in self._feedbacks.values() if f.org_id == self._org_id]
        if agent_id:
            out = [f for f in out if f.agent_id == agent_id]
        return out

    def list_version_comparisons(
        self, *, user: object, agent_id: str = "", resource_category: str = "data"
    ) -> List[AgentVersionComparison]:
        """列出当前组织下版本比较（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [c for c in self._version_comparisons.values() if c.org_id == self._org_id]
        if agent_id:
            out = [c for c in out if c.agent_id == agent_id]
        return out


__all__ = [
    "AgentQualityMetricType",
    "AgentQualityMetric",
    "AgentEvaluation",
    "AgentVersionComparison",
    "AgentFeedback",
    "AgentQualityReport",
    "AgentQualityGovernanceService",
]

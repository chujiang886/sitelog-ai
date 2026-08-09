"""Phase 3.8.25 企业智能体治理工作流编排层 —— 模型层。

链路：**问题发现 → 事实辅助分析 → 人工研判 → 治理任务创建 → 执行跟踪 →
结果归档 → 审计闭环**。

与 Phase 3.8.21 的关系（**复用而非重建**）：
- 3.8.21 ``agent_governance_workflow`` 是**治理问责层**：以 ``GovernanceTask``
  为中心，回答「这条治理发现由谁负责、处理了什么、谁确认闭环」。
- 3.8.25 本层是**治理编排层**：以 ``GovernanceWorkflow`` 为中心，回答「一条治理
  线索如何从发现走到归档，人工研判卡在哪一步」。
- 两套状态机**并存且互不覆盖**：3.8.21 五态 ``created → assigned → processing
  → waiting_review → completed`` 描述**任务问责生命周期**；本层六态
  ``created → under_review → human_confirmed → in_progress → waiting_result
  → completed`` 描述**编排生命周期**。本层复用 3.8.21 的
  ``GovernanceTask`` / ``GovernanceAssignment`` 与语义扫描原语，不重复造轮子。

模型清单（任务1/3/4）：
- ``GovernanceWorkflowSourceType``：编排来源类型（只描述事实来源，无处置态）。
- ``GovernanceWorkflowStatus``：**六态**编排状态机。枚举中**刻意不存在**
  ``AUTO_APPROVED`` / ``AUTO_EXECUTED`` / ``AUTO_CLOSED``（红线③/④/⑥）。
- ``GovernanceWorkflow``：治理工作流主体（任务1）。
- ``WorkflowReviewDecision`` / ``GovernanceWorkflowReview``：人工确认节点
  （任务3，reviewer 必须真实 USER）。
- ``GovernanceExecutionRecord``：执行跟踪事实记录（任务4，执行者必须真实人工）。

红线（fail-closed，三层拦截之「类型级 + 语义级」）：
① 所有模型构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② 不承载 ``engineering_approved`` 语义；无任何 approve 字段。
③ 禁 AI 自动治理 / 自动审批 / 自动关闭问题：构造期只能落 ``CREATED``，
   ``confirmed_by`` / ``completed_at`` / ``archived`` 构造期必须为空 / False。
④ 禁 AI 自动执行治理动作：``GovernanceExecutionRecord.actor_kind`` 必须为
   ``user``，非人类执行者标识直接拒绝。
⑤ 禁 AI 自动生成治理策略：所有文本字段经 ``_POLICY_MARKERS`` 扫描，命中即拒绝。
⑥ 禁 AI 代替治理责任人：``GovernanceWorkflowReview`` 构造期强制
   ``require_human_actor(USER)``；``requires_human_confirmation`` 恒为 True。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from agents.enterprise.agent_governance_workflow import (
    _ASSIGNMENT_MARKERS,
    _PERMISSION_MARKERS,
    _REMEDIATION_MARKERS,
    _reject_markers,
    _reject_non_human,
)
from agents.enterprise.audit import AuditActorKind, require_human_actor
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# 编排层专属语义标记（在 3.8.21 三组标记之上增量补充）
# ---------------------------------------------------------------------------

# 红线③：禁止出现「自动审批 / 自动治理 / 自动关闭」语义。
_AUTO_GOVERNANCE_MARKERS = (
    "auto_approve",
    "auto approve",
    "auto_govern",
    "auto govern",
    "auto_adjudicate",
    "automatically approved",
    "approved by ai",
    "自动审批",
    "自动批准",
    "自动治理",
    "自动研判",
    "自动裁定",
    "ai审批",
    "ai批准",
)

# 红线④：禁止出现「自动执行 / 自动应用知识」语义。
_AUTO_EXECUTION_MARKERS = (
    "auto_execute",
    "auto execute",
    "automatically executed",
    "executed by ai",
    "auto_apply_knowledge",
    "auto apply knowledge",
    "auto_execute_knowledge",
    "auto_update_knowledge",
    "auto_merge_knowledge",
    "自动执行",
    "自动应用知识",
    "自动更新知识",
    "自动合并知识",
    "自动套用经验",
)

# 红线⑤：禁止出现「生成 / 推荐治理策略」语义。
_POLICY_MARKERS = (
    "generate_policy",
    "generate policy",
    "recommend_policy",
    "recommend policy",
    "auto_generate_policy",
    "policy recommendation",
    "生成策略",
    "生成治理策略",
    "推荐策略",
    "建议策略",
    "策略建议",
    "制定策略",
)


def _reject_orchestration_markers(text: str, *, ctx: str) -> None:
    """编排层文本三重语义扫描（红线③/④/⑤），命中即抛红线违例。

    与 3.8.21 的三组标记（整改 / 分配 / 权限）叠加使用，构成本层的语义级拦截。
    只读校验，**绝不改写文本**（改写等于 AI 悄悄美化事实）。
    """
    if not str(text).strip():
        return
    _reject_markers(
        text, _AUTO_GOVERNANCE_MARKERS,
        ctx=ctx, rule="治理研判必须由真实人工完成，禁止 AI 自动审批/自动治理（红线③）",
    )
    _reject_markers(
        text, _AUTO_EXECUTION_MARKERS,
        ctx=ctx, rule="治理动作必须由真实人工执行，禁止 AI 自动执行/自动应用知识（红线④）",
    )
    _reject_markers(
        text, _POLICY_MARKERS,
        ctx=ctx, rule="治理策略只能由真实人工制定，禁止 AI 生成/推荐策略（红线⑤）",
    )


def _reject_all_markers(text: str, *, ctx: str) -> None:
    """本层完整语义扫描 = 3.8.21 三组 + 3.8.25 三组（共六组）。"""
    if not str(text).strip():
        return
    _reject_markers(
        text, _REMEDIATION_MARKERS,
        ctx=ctx, rule="编排记录只陈述事实，禁止 AI 自动整改/自动关闭（红线③）",
    )
    _reject_markers(
        text, _ASSIGNMENT_MARKERS,
        ctx=ctx, rule="责任分配只能由真实人工执行，禁止自动分配（红线⑥）",
    )
    _reject_markers(
        text, _PERMISSION_MARKERS,
        ctx=ctx, rule="本层不得修改权限或策略（红线⑤）",
    )
    _reject_orchestration_markers(text, ctx=ctx)


# ---------------------------------------------------------------------------
# 任务1-①：编排来源类型
# ---------------------------------------------------------------------------

class GovernanceWorkflowSourceType(str, Enum):
    """治理工作流来源类型（**只描述线索来自哪一层事实**，无任何处置态）。

    刻意**不提供** ``ai_decision`` / ``auto_detected_action`` 之类的来源：
    编排只能源自上游的**事实发现**或**真实人工上报**，不能源自 AI 的处置意图
    （红线③）。
    """

    ASSISTANT_DRAFT = "assistant_draft"        # 3.8.24 助手事实答案草稿
    GOVERNANCE_TASK = "governance_task"        # 3.8.21 治理任务
    SECURITY_RISK = "security_risk"            # 3.8.18 安全风险候选
    COMPLIANCE_RISK = "compliance_risk"        # 3.8.19 合规风险候选
    GOVERNANCE_INSIGHT = "governance_insight"  # 3.8.20 治理洞察（事实趋势）
    QUALITY_ISSUE = "quality_issue"            # 3.8.15 质量事实
    OBSERVABILITY_ANOMALY = "observability_anomaly"  # 3.8.14 运行事实
    HUMAN_REPORTED = "human_reported"          # 真实人工上报


# ---------------------------------------------------------------------------
# 任务1-②：六态编排状态机
# ---------------------------------------------------------------------------

class GovernanceWorkflowStatus(str, Enum):
    """治理工作流编排状态机（主理人明列六态）。

    ``created`` → ``under_review`` → ``human_confirmed`` → ``in_progress``
    → ``waiting_result`` → ``completed``。

    - ``created``：线索登记为**候选工作流**，尚未进入人工研判（AI 可发起）。
    - ``under_review``：已送入**人工研判队列**，等待真实责任人研判（AI 可推送，
      但推送不构成任何治理决定）。
    - ``human_confirmed``：**真实人工研判通过**，只能由
      ``GovernanceWorkflowOrchestrator.human_confirm`` 在
      ``require_human_actor(USER)`` 守卫下推进（红线③/⑥）。
    - ``in_progress``：真实人工开始执行治理动作（红线④）。
    - ``waiting_result``：真实人工提交执行结果，等待归档确认。
    - ``completed``：**必须人工确认**，只能由 ``human_complete`` 在 USER 守卫下推进。

    枚举中**刻意不存在** ``AUTO_APPROVED`` / ``AUTO_EXECUTED`` / ``AUTO_CLOSED``：
    「AI 自动批准 / 自动执行 / 自动关闭」在类型层面即不可表达（红线③/④/⑥）。
    """

    CREATED = "created"
    UNDER_REVIEW = "under_review"
    HUMAN_CONFIRMED = "human_confirmed"
    IN_PROGRESS = "in_progress"
    WAITING_RESULT = "waiting_result"
    COMPLETED = "completed"


# 合法状态迁移（**只前进，不回退**；任何非法迁移直接拒绝）。
_ALLOWED_WORKFLOW_TRANSITIONS: Dict[
    GovernanceWorkflowStatus, "tuple[GovernanceWorkflowStatus, ...]"
] = {
    GovernanceWorkflowStatus.CREATED: (GovernanceWorkflowStatus.UNDER_REVIEW,),
    GovernanceWorkflowStatus.UNDER_REVIEW: (GovernanceWorkflowStatus.HUMAN_CONFIRMED,),
    GovernanceWorkflowStatus.HUMAN_CONFIRMED: (GovernanceWorkflowStatus.IN_PROGRESS,),
    GovernanceWorkflowStatus.IN_PROGRESS: (GovernanceWorkflowStatus.WAITING_RESULT,),
    GovernanceWorkflowStatus.WAITING_RESULT: (GovernanceWorkflowStatus.COMPLETED,),
    GovernanceWorkflowStatus.COMPLETED: (),
}

# 禁止在类型层出现的自动态名（结构级自检，供测试断言）。
_FORBIDDEN_STATUS_NAMES = (
    "AUTO_APPROVED",
    "AUTO_EXECUTED",
    "AUTO_CLOSED",
    "AUTO_COMPLETED",
    "AUTO_CONFIRMED",
    "CLOSED_BY_AI",
    "APPROVED_BY_AI",
)


# ---------------------------------------------------------------------------
# 任务1-③：治理工作流主体
# ---------------------------------------------------------------------------

@dataclass
class GovernanceWorkflow:
    """治理工作流（任务1，**人工确认才能推进，AI 无法自动关闭**）。

    字段对应主理人指令的编排语义，并额外携带 ``org_id`` / ``source_facts`` /
    ``references`` 以支撑企业隔离与强可溯源。

    红线约束：
    - ``source_id`` 为空即拒绝落库（禁止凭空造治理线索，红线⑥：可溯源）；
    - 构造期状态只能是 ``CREATED``（禁止直接落 human_confirmed / completed，
      红线③/④/⑥）；
    - 构造期 ``confirmed_by`` / ``confirmed_at`` / ``completed_by`` /
      ``completed_at`` 必须为空（禁止伪造人工确认与完成事实，红线③/⑥）；
    - 构造期 ``archived`` 必须为 False（禁止伪造归档事实）；
    - ``requires_human_confirmation`` 恒为 True，禁止置 False（红线⑥）；
    - ``title`` / ``description`` / ``source_facts`` 经**六组语义扫描**，命中
      自动整改 / 自动分配 / 改权限 / 自动审批 / 自动执行 / 生成策略即拒绝；
    - 模型层**不提供**任何 approve / confirm / execute / close / archive 方法。
    """

    workflow_id: str
    source_type: GovernanceWorkflowSourceType = (
        GovernanceWorkflowSourceType.HUMAN_REPORTED
    )
    source_id: str = ""
    status: GovernanceWorkflowStatus = GovernanceWorkflowStatus.CREATED
    org_id: str = ""
    title: str = ""
    description: str = ""
    source_facts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    created_at: str = ""
    created_by: str = ""          # 创建者（AI 创建时如实记为 ai，不伪装为人工）
    confirmed_by: str = ""        # 人工研判人（仅由服务层在 USER 守卫下写入）
    confirmed_at: str = ""
    completed_by: str = ""        # 人工归档人（仅由服务层在 USER 守卫下写入）
    completed_at: str = ""
    archived: bool = False
    archived_by: str = ""
    archived_at: str = ""
    draft_id: str = ""            # 3.8.24 GovernanceAnswerDraft 溯源（可空）
    task_id: str = ""             # 3.8.21 GovernanceTask 关联（可空）
    human_notes: List[str] = field(default_factory=list)
    requires_human_confirmation: bool = True

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceWorkflow（红线①）"
            )
        if not isinstance(self.source_type, GovernanceWorkflowSourceType):
            self.source_type = GovernanceWorkflowSourceType(self.source_type)
        if not isinstance(self.status, GovernanceWorkflowStatus):
            self.status = GovernanceWorkflowStatus(self.status)

        self.workflow_id = str(self.workflow_id).strip()
        self.source_id = str(self.source_id).strip()
        self.org_id = str(self.org_id).strip()
        self.source_facts = [str(f).strip() for f in self.source_facts if str(f).strip()]
        self.references = [str(r).strip() for r in self.references if str(r).strip()]
        self.human_notes = [str(n).strip() for n in self.human_notes if str(n).strip()]

        if not self.workflow_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceWorkflow 缺少 workflow_id：禁止落库无标识的治理工作流（红线⑥）"
            )
        if not self.source_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {self.workflow_id!r} 缺少 source_id："
                f"禁止落库无来源的治理工作流（红线⑥：治理线索必须可溯源）"
            )
        if self.requires_human_confirmation is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {self.workflow_id!r} 禁止置 "
                f"requires_human_confirmation=False："
                f"治理工作流的推进必须由真实人工确认（红线③/⑥）"
            )
        if self.status is not GovernanceWorkflowStatus.CREATED:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {self.workflow_id!r} 禁止在构造期落 "
                f"{self.status.value}：工作流只能以 created 候选态生成，后续状态须由"
                f"真实人工经 human_confirm / start_execution / "
                f"submit_execution_result / human_complete(actor_kind=USER) 推进"
                f"（红线③/④/⑥）"
            )
        for label, value in (
            ("confirmed_by", self.confirmed_by),
            ("confirmed_at", self.confirmed_at),
            ("completed_by", self.completed_by),
            ("completed_at", self.completed_at),
            ("archived_by", self.archived_by),
            ("archived_at", self.archived_at),
        ):
            if str(value).strip():
                raise EnterpriseRedLineViolationError(
                    f"GovernanceWorkflow {self.workflow_id!r} 禁止在构造期预填 "
                    f"{label}：人工研判 / 完成 / 归档事实只能由真实人工在服务层"
                    f"USER 守卫下写入（红线③/⑥）"
                )
        if self.archived is not False:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {self.workflow_id!r} 禁止在构造期置 "
                f"archived=True：归档是真实人工动作，不得伪造（红线③/⑥）"
            )

        _reject_all_markers(
            self.title, ctx=f"GovernanceWorkflow {self.workflow_id!r} 的 title"
        )
        _reject_all_markers(
            self.description,
            ctx=f"GovernanceWorkflow {self.workflow_id!r} 的 description",
        )
        for idx, fact in enumerate(self.source_facts):
            _reject_all_markers(
                fact,
                ctx=f"GovernanceWorkflow {self.workflow_id!r} 的 source_facts[{idx}]",
            )
        for idx, note in enumerate(self.human_notes):
            _reject_all_markers(
                note,
                ctx=f"GovernanceWorkflow {self.workflow_id!r} 的 human_notes[{idx}]",
            )

    # -- 只读事实属性 ---------------------------------------------------

    @property
    def is_human_confirmed(self) -> bool:
        """是否已由真实人工研判通过（只读事实，不做任何推断）。"""
        return bool(str(self.confirmed_by).strip()) and self.status in (
            GovernanceWorkflowStatus.HUMAN_CONFIRMED,
            GovernanceWorkflowStatus.IN_PROGRESS,
            GovernanceWorkflowStatus.WAITING_RESULT,
            GovernanceWorkflowStatus.COMPLETED,
        )

    @property
    def is_completed(self) -> bool:
        """是否已由真实人工确认完成（只读事实）。"""
        return self.status is GovernanceWorkflowStatus.COMPLETED

    @property
    def contains_recommendation(self) -> bool:
        """恒为 False：工作流只承载事实与人工记录，不承载 AI 治理建议（红线⑤/⑥）。

        写成计算属性而非字段，使「有没有建议」这件事不可被赋值伪造。
        """
        return False

    def can_transition_to(self, target: "GovernanceWorkflowStatus | str") -> bool:
        """只读判断状态迁移是否合法（**不执行迁移**）。"""
        tgt = (
            target
            if isinstance(target, GovernanceWorkflowStatus)
            else GovernanceWorkflowStatus(target)
        )
        return tgt in _ALLOWED_WORKFLOW_TRANSITIONS.get(self.status, ())

    def summary(self) -> str:
        """只读摘要（**不含处置建议、不含责任判定**）。"""
        return (
            f"workflow={self.workflow_id} "
            f"source={self.source_type.value}:{self.source_id} "
            f"status={self.status.value} "
            f"confirmed_by={self.confirmed_by or 'unconfirmed'}"
        )


# ---------------------------------------------------------------------------
# 任务3：人工确认节点
# ---------------------------------------------------------------------------

class WorkflowReviewDecision(str, Enum):
    """人工研判结论（**只有真实人工能给出**）。

    枚举中**刻意不存在** ``auto_approved`` / ``ai_confirmed``：AI 的研判结论
    在类型层面即不可表达（红线③/⑥）。``REJECTED`` / ``NEED_MORE_INFO`` 不推进
    状态，只登记人工研判事实。
    """

    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEED_MORE_INFO = "need_more_info"


@dataclass
class GovernanceWorkflowReview:
    """治理工作流人工确认记录（任务3，**reviewer 必须真实 USER**）。

    字段严格对应主理人指令：记录 actor / time / decision / reason。

    红线约束（红线③/⑥）：
    - ``reviewer_kind`` 构造期强制 ``require_human_actor(USER)``：AI
      （``ai`` / ``system`` / ``None``）构造必抛红线违例；
    - ``reviewer_id`` 为空、或命中 ai / system / bot / agent / auto / 机器人
      等非人类标识即拒绝（研判责任必须落到真实人身上）；
    - ``reason`` 为空即拒绝（人工研判必须留下理由，禁止空白盖章）；
    - ``reason`` 经六组语义扫描，命中自动审批 / 自动执行 / 生成策略等即拒绝；
    - 模型层**不提供**任何 approve / auto_confirm 方法。
    """

    review_id: str
    workflow_id: str = ""
    reviewer_id: str = ""
    reviewer_kind: "AuditActorKind | str | None" = None
    decision: WorkflowReviewDecision = WorkflowReviewDecision.NEED_MORE_INFO
    reason: str = ""
    reviewed_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceWorkflowReview（红线①）"
            )
        if not isinstance(self.decision, WorkflowReviewDecision):
            self.decision = WorkflowReviewDecision(self.decision)

        self.review_id = str(self.review_id).strip()
        self.workflow_id = str(self.workflow_id).strip()
        self.reviewer_id = str(self.reviewer_id).strip()
        self.reason = str(self.reason).strip()
        self.org_id = str(self.org_id).strip()

        if not self.review_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceWorkflowReview 缺少 review_id：禁止落库无标识的人工确认记录（红线⑥）"
            )
        if not self.workflow_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflowReview {self.review_id!r} 缺少 workflow_id："
                f"人工确认必须挂在一条真实工作流之上（红线⑥）"
            )
        # 红线⑥核心：确认人必须是真实 USER，AI 构造即抛。
        require_human_actor(self.reviewer_kind)
        if not self.reviewer_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflowReview {self.review_id!r} 缺少 reviewer_id："
                f"治理研判责任必须落到真实人工身上（红线⑥）"
            )
        _reject_non_human(
            self.reviewer_id,
            ctx=f"GovernanceWorkflowReview {self.review_id!r} 的 reviewer_id",
        )
        if not self.reason:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflowReview {self.review_id!r} 缺少 reason："
                f"人工研判必须留下真实理由，禁止空白盖章（红线⑥）"
            )
        _reject_all_markers(
            self.reason,
            ctx=f"GovernanceWorkflowReview {self.review_id!r} 的 reason",
        )

    @property
    def is_confirmed(self) -> bool:
        """人工研判是否通过（只读事实）。"""
        return self.decision is WorkflowReviewDecision.CONFIRMED

    def summary(self) -> str:
        """只读摘要（**只陈述谁在何时给出了什么研判结论**）。"""
        return (
            f"review={self.review_id} workflow={self.workflow_id} "
            f"reviewer={self.reviewer_id} decision={self.decision.value}"
        )


# ---------------------------------------------------------------------------
# 任务4：执行跟踪事实记录
# ---------------------------------------------------------------------------

@dataclass
class GovernanceExecutionRecord:
    """治理执行跟踪记录（任务4，**执行者必须真实人工**）。

    只登记「谁在何时对本工作流做了什么、结果是什么、来源是什么」这一事实，
    **绝不代表 AI 执行了任何治理动作**（红线④）。

    红线约束：
    - ``action`` / ``actor`` / ``source`` 任一为空即拒绝落库（红线⑥：可溯源）；
    - ``actor_kind`` 必须为 ``user``：AI 无法登记「自己执行了治理动作」（红线④）；
    - ``actor`` 命中非人类标识即拒绝；
    - ``action`` / ``result`` / ``note`` 经六组语义扫描，命中自动整改 / 自动执行 /
      自动审批 / 生成策略 / 改权限即拒绝；
    - 模型层**不提供**任何 execute / apply / close 方法。
    """

    record_id: str
    workflow_id: str = ""
    action: str = ""
    actor: str = ""
    actor_kind: str = "user"
    timestamp: str = ""
    result: str = ""
    source: str = ""
    note: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceExecutionRecord（红线①）"
            )
        self.record_id = str(self.record_id).strip()
        self.workflow_id = str(self.workflow_id).strip()
        self.action = str(self.action).strip()
        self.actor = str(self.actor).strip()
        self.actor_kind = str(self.actor_kind).strip().lower()
        self.result = str(self.result).strip()
        self.source = str(self.source).strip()
        self.note = str(self.note).strip()
        self.org_id = str(self.org_id).strip()

        if not self.record_id:
            raise EnterpriseRedLineViolationError(
                "GovernanceExecutionRecord 缺少 record_id：禁止落库无标识的执行记录（红线⑥）"
            )
        if not self.workflow_id:
            raise EnterpriseRedLineViolationError(
                f"GovernanceExecutionRecord {self.record_id!r} 缺少 workflow_id："
                f"执行事实必须挂在一条真实工作流之上（红线⑥）"
            )
        if not self.action:
            raise EnterpriseRedLineViolationError(
                f"GovernanceExecutionRecord {self.record_id!r} 缺少 action："
                f"禁止落库无动作内容的执行事实（红线⑥）"
            )
        if not self.actor:
            raise EnterpriseRedLineViolationError(
                f"GovernanceExecutionRecord {self.record_id!r} 缺少 actor："
                f"执行事实必须可追溯到具体执行人（红线⑥）"
            )
        if not self.source:
            raise EnterpriseRedLineViolationError(
                f"GovernanceExecutionRecord {self.record_id!r} 缺少 source："
                f"禁止落库无源的执行事实（红线⑥：事实必须可溯源）"
            )
        if self.actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                f"GovernanceExecutionRecord {self.record_id!r} 的 actor_kind="
                f"{self.actor_kind!r} 非 'user'：治理动作只能由真实人工执行，"
                f"AI 不得登记自身执行事实（红线④/⑥）"
            )
        _reject_non_human(
            self.actor,
            ctx=f"GovernanceExecutionRecord {self.record_id!r} 的 actor",
        )
        for label, text in (
            ("action", self.action),
            ("result", self.result),
            ("note", self.note),
        ):
            _reject_all_markers(
                text,
                ctx=f"GovernanceExecutionRecord {self.record_id!r} 的 {label}",
            )

    @property
    def is_human_execution(self) -> bool:
        """是否为真实人工执行（只读事实，恒 True —— 非人工构造期即被拒）。"""
        return self.actor_kind == "user"

    def summary(self) -> str:
        """只读摘要（**不含处置建议、不含责任判定**）。"""
        return (
            f"execution={self.record_id} workflow={self.workflow_id} "
            f"action={self.action} actor={self.actor} source={self.source}"
        )


__all__ = [
    "GovernanceWorkflowSourceType",
    "GovernanceWorkflowStatus",
    "GovernanceWorkflow",
    "WorkflowReviewDecision",
    "GovernanceWorkflowReview",
    "GovernanceExecutionRecord",
    "_ALLOWED_WORKFLOW_TRANSITIONS",
    "_FORBIDDEN_STATUS_NAMES",
    "_AUTO_GOVERNANCE_MARKERS",
    "_AUTO_EXECUTION_MARKERS",
    "_POLICY_MARKERS",
    "_reject_all_markers",
    "_reject_orchestration_markers",
]

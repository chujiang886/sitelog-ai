"""Enterprise Agent Governance Workflow & Accountability Layer（Phase 3.8.21）。

链路：**治理发现 → 治理任务 → 责任人 → 人工处理 → 结果记录 → 治理闭环**。

本层建立在 3.8.13~3.8.20 各治理层（能力注册 / 可观测性 / 质量 / 成本 / 运行时策略 /
安全风险 / 合规审计 / 治理中枢）之上：把上游产出的**治理发现**（风险候选、异常候选、
事实洞察）转化为**可追责的治理任务**，交由**真实人工责任人**处理，全程只登记事实，
最终由**真实人工**确认闭环。AI 在本层只能「发现→建候选任务」，绝不能分配责任、
绝不能整改风险、绝不能改权限、绝不能关闭任务。

新增（任务1–5）：
- ``GovernanceTaskSourceType`` / ``GovernanceTaskStatus`` / ``GovernanceTask``：
  治理任务（task_id / source_type / source_id / owner_id / status /
  created_at / completed_at）。状态机 created → assigned → processing →
  waiting_review → completed。**completed 必须人工确认**：构造期只能落
  ``created``，``owner_id`` / ``completed_at`` 构造期必须为空，任何终态推进
  强制 ``require_human_actor(USER)``（任务1，红线③/④/⑥）。
- ``GovernanceAssignment``：责任分配记录（assignment_id / task_id / assignee /
  role / timestamp）。**责任人必须真实 USER**：assignee 为空、或命中
  ai / system / bot / agent / auto / 机器人 等非人类标识即拒绝落库
  （任务2，红线④/⑥）。
- ``GovernanceActionRecord``：处理动作事实记录（action / actor / timestamp /
  result / source）。**只记录事实**：无 action / 无 actor / 无 source 即拒绝；
  result 命中自动整改语义（auto_remediate / auto_fix / auto_resolve / 自动整改
  ...）即拒绝（任务3，红线③/⑥）。
- ``GovernanceWorkflowService``：治理工作流服务（create_task / assign_owner /
  submit_result / human_close）。**AI 只能创建候选任务**：``create_task`` 允许
  AI 发起但只产出 ``created`` 态候选；``assign_owner`` / ``start_processing`` /
  ``submit_result`` / ``human_close`` 全部强制 ``require_human_actor(USER)``，
  AI 无论如何无法自动关闭任务（任务4，红线③/④/⑤/⑥）。
- ``GovernanceClosureReport``：治理闭环报告（问题来源 + 处理记录 + 人工结果 +
  来源链 ``SourceTrace``）。无来源链即拒绝生成；``human_result`` 必须由人工填写，
  且必须存在真实人工闭环人（任务5，红线⑥）。

红线（fail-closed，复用 3.8.0~3.8.20 基座 + 3.8.21 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved（forbidden 方法名结构性拦截）。
③ 不 AI 自动整改风险（``auto_remediate`` / ``auto_fix`` / ``auto_resolve`` 及同族
   方法名被 mixin 拦截；处理结果文本命中自动整改语义即拒绝；本层不持有任何
   修复/整改能力）。
④ 不 AI 自动分配责任（``auto_assign`` / ``auto_assign_owner`` 等被拦截；
   ``GovernanceTask`` 构造期禁止预填 ``owner_id``；分配强制 USER；
   assignee 必须是真实人类标识）。
⑤ 不 AI 自动修改权限策略（``auto_change_permission`` / ``auto_modify_policy`` 等
   被拦截；本层对 ``AgentPermissionPolicy`` / ``AgentRuntimeGovernanceService``
   **纯只读**，绝不写任何权限或策略）。
⑥ 不 AI 代替治理责任人（审计禁止 ``record_human_approval``；分配/处理/闭环节点
   强制 ``require_human_actor(USER)``；任务/记录/报告只陈述事实，不含处置建议）。
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
    # 红线③：禁止 AI 自动整改风险（主理人明列三项 + 同族收敛）
    "auto_remediate",
    "auto_fix",
    "auto_resolve",
    "auto_remediate_risk",
    "remediate_risk",
    "remediate",
    "auto_fix_risk",
    "fix_risk",
    "auto_fix_issue",
    "fix_issue",
    "auto_resolve_risk",
    "resolve_risk",
    "auto_resolve_task",
    "resolve_task",
    "auto_repair",
    "repair_risk",
    "auto_mitigate",
    "mitigate_risk",
    "auto_handle_risk",
    "handle_risk",
    "auto_rectify",
    "rectify_risk",
    "auto_correct",
    "correct_risk",
    "auto_patch",
    "patch_risk",
    # 红线③衍生：禁止 AI 自动关闭治理任务
    "auto_close",
    "auto_close_task",
    "close_task",
    "auto_complete_task",
    "complete_task",
    "auto_finish_task",
    "finish_task",
    "auto_dismiss_task",
    "dismiss_task",
    "auto_cancel_task",
    "cancel_task",
    "auto_signoff",
    "signoff_task",
    # 红线④：禁止 AI 自动分配责任
    "auto_assign",
    "auto_assign_owner",
    "assign_owner_automatically",
    "auto_assign_task",
    "auto_assign_responsibility",
    "assign_responsibility_automatically",
    "auto_delegate",
    "delegate_responsibility",
    "auto_designate_owner",
    "designate_owner",
    "auto_appoint_owner",
    "appoint_owner",
    "auto_route_task",
    "route_task_automatically",
    "auto_dispatch_task",
    "dispatch_task_automatically",
    # 红线⑤：禁止 AI 自动修改权限策略
    "auto_change_permission",
    "change_permission",
    "auto_modify_permission",
    "modify_permission",
    "auto_update_permission",
    "update_permission",
    "auto_grant_permission",
    "grant_permission",
    "auto_revoke_permission",
    "revoke_permission",
    "auto_change_policy",
    "change_policy",
    "auto_modify_policy",
    "modify_policy",
    "auto_update_policy",
    "update_policy",
    "auto_apply_policy",
    "apply_policy",
    "auto_escalate_privilege",
    "escalate_privilege",
    # 红线⑥：禁止 AI 代替治理责任人
    "act_as_governance_owner",
    "take_governance_ownership",
    "assume_governance_responsibility",
    "auto_govern",
    "auto_decide_governance",
    "decide_governance",
    "auto_confirm_closure",
    "confirm_closure_automatically",
    "auto_accept_result",
    "accept_result_automatically",
    "auto_recommend",
    "recommend_action",
    "auto_advise",
    "advise_governance",
    "auto_suggest",
    "suggest_governance_action",
)


# 文本中禁止出现的「自动整改」语义（红线③：AI 只能记录事实，不能整改）。
_REMEDIATION_MARKERS = (
    "auto_remediate",
    "auto remediate",
    "auto_fix",
    "auto fix",
    "auto_resolve",
    "auto resolve",
    "auto_repair",
    "auto repair",
    "automatically fixed",
    "automatically resolved",
    "自动整改",
    "自动修复",
    "自动处置",
    "自动关闭",
    "已由ai整改",
    "由ai自动",
)

# 文本/字段中禁止出现的「自动分配责任」语义（红线④）。
_ASSIGNMENT_MARKERS = (
    "auto_assign",
    "auto assign",
    "auto_delegate",
    "auto delegate",
    "automatically assigned",
    "自动分配",
    "自动指派",
    "自动派单",
    "ai指派",
)

# 文本中禁止出现的「修改权限/策略」语义（红线⑤）。
_PERMISSION_MARKERS = (
    "grant permission",
    "revoke permission",
    "change permission",
    "modify permission",
    "escalate privilege",
    "change policy",
    "modify policy",
    "修改权限",
    "调整权限",
    "授予权限",
    "撤销权限",
    "变更策略",
    "修改策略",
)

# 非人类责任人标识（红线④/⑥：责任人必须真实 USER）。
_NON_HUMAN_ASSIGNEES = (
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


def _reject_non_human(value: str, *, ctx: str) -> None:
    """拒绝非人类责任人标识（红线④/⑥）。

    只做**整体等值 / 前缀分段**判断，避免误伤 ``ai-ming`` 这类以字母开头的真实
    人名缩写以外的正常 id：判定规则为「整体等于」或「以 ``<marker>-`` /
    ``<marker>_`` / ``<marker>.`` / ``<marker>@`` 开头」。
    """
    raw = str(value).strip().lower()
    for marker in _NON_HUMAN_ASSIGNEES:
        if raw == marker or any(
            raw.startswith(f"{marker}{sep}") for sep in ("-", "_", ".", "@", ":")
        ):
            raise EnterpriseRedLineViolationError(
                f"{ctx} 拒绝非人类责任人标识 {value!r}："
                f"治理责任人必须是真实人工 USER（红线④/⑥）"
            )


# ---------------------------------------------------------------------------
# 任务1：治理任务（completed 必须人工确认）
# ---------------------------------------------------------------------------

class GovernanceTaskSourceType(str, Enum):
    """治理任务来源类型（**只描述发现来自哪一层事实**，无任何处置态）。

    刻意**不提供** ``ai_decision`` / ``auto_detected_fix`` 之类的来源：
    任务只能源自上游治理层的**事实发现**，不能源自 AI 的处置意图（红线③）。
    """

    SECURITY_RISK = "security_risk"            # 3.8.18 安全风险候选
    COMPLIANCE_RISK = "compliance_risk"        # 3.8.19 合规风险候选
    RISK_OVERVIEW = "risk_overview"            # 3.8.20 风险总览
    GOVERNANCE_INSIGHT = "governance_insight"  # 3.8.20 治理洞察（事实趋势/异常候选）
    QUALITY_ISSUE = "quality_issue"            # 3.8.15 质量事实
    COST_ANOMALY = "cost_anomaly"              # 3.8.16 成本事实
    OBSERVABILITY_ANOMALY = "observability_anomaly"  # 3.8.14 运行事实
    HUMAN_REPORTED = "human_reported"          # 真实人工上报


class GovernanceTaskStatus(str, Enum):
    """治理任务状态机（主理人明列五态）。

    ``created`` → ``assigned`` → ``processing`` → ``waiting_review`` → ``completed``。

    - ``created``：AI 或人工发现后创建的**候选任务**，尚无责任人（红线④）。
    - ``assigned``：真实人工完成责任分配后。
    - ``processing``：真实人工开始处理后。
    - ``waiting_review``：真实人工提交处理结果，等待闭环确认。
    - ``completed``：**必须人工确认**，只能由
      ``GovernanceWorkflowService.human_close`` 在 ``require_human_actor(USER)``
      守卫下推进。枚举中**不存在** ``auto_completed`` / ``closed_by_ai`` 之类的
      AI 终态（红线③/⑥）。
    """

    CREATED = "created"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"


# 合法状态迁移（**只前进，不回退**；任何非法迁移直接拒绝）。
_ALLOWED_TRANSITIONS: Dict[GovernanceTaskStatus, "tuple[GovernanceTaskStatus, ...]"] = {
    GovernanceTaskStatus.CREATED: (GovernanceTaskStatus.ASSIGNED,),
    GovernanceTaskStatus.ASSIGNED: (
        GovernanceTaskStatus.PROCESSING,
        GovernanceTaskStatus.WAITING_REVIEW,
    ),
    GovernanceTaskStatus.PROCESSING: (GovernanceTaskStatus.WAITING_REVIEW,),
    GovernanceTaskStatus.WAITING_REVIEW: (GovernanceTaskStatus.COMPLETED,),
    GovernanceTaskStatus.COMPLETED: (),
}


@dataclass
class GovernanceTask:
    """治理任务（任务1，**completed 必须人工确认**）。

    字段严格对应主理人指令：task_id / source_type / source_id / owner_id /
    status / created_at / completed_at；额外增加 org_id / title / detail /
    created_by 便于隔离与事实描述。

    红线约束：
    - ``source_id`` 为空即拒绝落库（禁止凭空造治理任务，红线⑥：发现必须可溯源）；
    - 构造期状态只能是 ``CREATED``（禁止直接落 assigned / completed，红线③/④/⑥）；
    - 构造期 ``owner_id`` 必须为空（**禁止 AI 预填责任人**，红线④）；
    - 构造期 ``completed_at`` 必须为空（禁止伪造完成事实，红线③/⑥）；
    - ``title`` / ``detail`` 命中自动整改 / 自动分配 / 改权限语义即拒绝
      （红线③/④/⑤）；
    - 模型层**不提供**任何 close / complete / resolve / assign 方法。
    """

    task_id: str
    source_type: GovernanceTaskSourceType = GovernanceTaskSourceType.SECURITY_RISK
    source_id: str = ""
    owner_id: str = ""
    status: GovernanceTaskStatus = GovernanceTaskStatus.CREATED
    created_at: str = ""
    completed_at: str = ""
    org_id: str = ""
    agent_id: str = ""
    title: str = ""          # 中性事实标题（不得含整改/分配/权限语义）
    detail: str = ""         # 中性事实说明（不得含整改/分配/权限语义）
    created_by: str = ""     # 创建者（AI 创建时如实记为 ai，不伪装为人工）
    closed_by: str = ""      # 人工闭环人（仅事实记录，由服务层在 USER 守卫下写入）
    requires_human_completion: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, GovernanceTaskSourceType):
            self.source_type = GovernanceTaskSourceType(self.source_type)
        if not isinstance(self.status, GovernanceTaskStatus):
            self.status = GovernanceTaskStatus(self.status)
        if not str(self.task_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceTask 缺少 task_id：禁止落库无标识的治理任务（红线⑥）"
            )
        if not str(self.source_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 缺少 source_id："
                f"禁止落库无来源的治理任务（红线⑥：治理发现必须可溯源）"
            )
        if self.requires_human_completion is not True:
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 禁止置 "
                f"requires_human_completion=False："
                f"治理任务的完成必须由真实人工确认（红线③/⑥）"
            )
        if self.status is not GovernanceTaskStatus.CREATED:
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 禁止在构造期落 "
                f"{self.status.value}：治理任务只能以 created 候选态生成，"
                f"后续状态须由真实人工经 assign_owner / start_processing / "
                f"submit_result / human_close(actor_kind=USER) 推进（红线③/④/⑥）"
            )
        if str(self.owner_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 禁止在构造期预填 owner_id="
                f"{self.owner_id!r}：责任人只能由真实人工经 "
                f"assign_owner(actor_kind=USER) 分配（红线④）"
            )
        if str(self.completed_at).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 禁止在构造期预填 completed_at："
                f"完成事实只能由真实人工闭环时写入（红线③/⑥）"
            )
        if str(self.closed_by).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceTask {self.task_id!r} 禁止在构造期预填 closed_by："
                f"闭环人只能是真实人工（红线⑥）"
            )
        for label, text in (("title", self.title), ("detail", self.detail)):
            if not str(text).strip():
                continue
            ctx = f"GovernanceTask {self.task_id!r} 的 {label}"
            _reject_markers(
                text, _REMEDIATION_MARKERS,
                ctx=ctx, rule="治理任务只陈述事实，禁止 AI 自动整改（红线③）",
            )
            _reject_markers(
                text, _ASSIGNMENT_MARKERS,
                ctx=ctx, rule="责任人只能由真实人工分配，禁止自动分配（红线④）",
            )
            _reject_markers(
                text, _PERMISSION_MARKERS,
                ctx=ctx, rule="本层不得修改权限或策略（红线⑤）",
            )

    @property
    def is_completed(self) -> bool:
        """是否已由真实人工确认闭环（只读事实）。"""
        return self.status is GovernanceTaskStatus.COMPLETED

    @property
    def has_owner(self) -> bool:
        """是否已有真实人工责任人（只读事实）。"""
        return bool(str(self.owner_id).strip())

    def can_transition_to(self, target: "GovernanceTaskStatus | str") -> bool:
        """只读判断状态迁移是否合法（**不执行迁移**）。"""
        tgt = (
            target
            if isinstance(target, GovernanceTaskStatus)
            else GovernanceTaskStatus(target)
        )
        return tgt in _ALLOWED_TRANSITIONS.get(self.status, ())

    def summary(self) -> str:
        """只读摘要（**不含整改建议、不含责任判定**）。"""
        return (
            f"task={self.task_id} source={self.source_type.value}:{self.source_id} "
            f"status={self.status.value} owner={self.owner_id or 'unassigned'}"
        )


# ---------------------------------------------------------------------------
# 任务2：责任分配记录（责任人必须真实 USER）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceAssignment:
    """治理责任分配记录（任务2，**责任人必须真实 USER**）。

    字段严格对应主理人指令：assignment_id / task_id / assignee / role /
    timestamp；额外增加 org_id / assigned_by / note 便于隔离与事实描述。

    红线约束（红线④/⑥）：
    - ``assignee`` 为空即拒绝落库（禁止无责任人的分配记录）；
    - ``assignee`` 命中 ai / system / bot / agent / auto / 机器人 等非人类标识
      即拒绝（责任人必须是真实人工）；
    - ``role`` 为空即拒绝（责任必须有明确角色归属）；
    - ``assigned_by`` 同样禁止为非人类标识（分配动作本身必须由真实人工发起）；
    - ``note`` 命中自动分配 / 自动整改语义即拒绝；
    - 模型层**不提供**任何 auto_assign / reassign_automatically 方法。
    """

    assignment_id: str
    task_id: str = ""
    assignee: str = ""
    role: str = ""
    timestamp: str = ""
    org_id: str = ""
    assigned_by: str = ""    # 分配动作发起者（必须真实人工，由服务层在 USER 守卫下写入）
    note: str = ""           # 中性事实备注

    def __post_init__(self) -> None:
        if not str(self.assignment_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceAssignment 缺少 assignment_id：禁止落库无标识的分配记录（红线⑥）"
            )
        if not str(self.task_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssignment {self.assignment_id!r} 缺少 task_id："
                f"禁止落库无归属治理任务的分配记录（红线⑥）"
            )
        if not str(self.assignee).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssignment {self.assignment_id!r} 缺少 assignee："
                f"治理责任必须落到真实人工身上（红线④/⑥）"
            )
        if not str(self.role).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceAssignment {self.assignment_id!r} 缺少 role："
                f"治理责任必须有明确角色归属（红线④/⑥）"
            )
        _reject_non_human(
            self.assignee,
            ctx=f"GovernanceAssignment {self.assignment_id!r} 的 assignee",
        )
        if str(self.assigned_by).strip():
            _reject_non_human(
                self.assigned_by,
                ctx=f"GovernanceAssignment {self.assignment_id!r} 的 assigned_by",
            )
        if str(self.note).strip():
            ctx = f"GovernanceAssignment {self.assignment_id!r} 的 note"
            _reject_markers(
                self.note, _ASSIGNMENT_MARKERS,
                ctx=ctx, rule="责任分配必须由真实人工执行，禁止自动分配（红线④）",
            )
            _reject_markers(
                self.note, _REMEDIATION_MARKERS,
                ctx=ctx, rule="分配记录只陈述事实，禁止 AI 自动整改（红线③）",
            )

    def summary(self) -> str:
        """只读摘要（**只陈述谁被分配了什么角色的责任**）。"""
        return (
            f"assignment={self.assignment_id} task={self.task_id} "
            f"assignee={self.assignee} role={self.role}"
        )


# ---------------------------------------------------------------------------
# 任务3：处理动作事实记录（只记录事实）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceActionRecord:
    """治理处理动作事实记录（任务3，**只记录事实**）。

    字段严格对应主理人指令：action / actor / timestamp / result / source；
    额外增加 record_id / task_id / org_id / actor_kind 便于索引与隔离。

    红线约束（红线③/⑥）：
    - ``action`` / ``actor`` / ``source`` 任一为空即拒绝落库
      （禁止无动作、无责任人、无来源的「处理事实」）；
    - ``actor`` 为真实处理人标识；``actor_kind`` 如实标注（AI 观察到的事实可记为
      ``ai``，但**人工处理结果**只能由服务层在 USER 守卫下写入）；
    - ``result`` / ``action`` 命中自动整改语义（auto_remediate / auto_fix /
      auto_resolve / 自动整改 ...）即拒绝（红线③）；
    - ``result`` 命中改权限语义即拒绝（红线⑤）；
    - 模型层**不提供**任何 remediate / fix / resolve / close 方法。
    """

    record_id: str
    task_id: str = ""
    action: str = ""
    actor: str = ""
    timestamp: str = ""
    result: str = ""
    source: str = ""
    org_id: str = ""
    actor_kind: str = ""   # 如实标注：ai / user / system（不伪造为人工审批）

    def __post_init__(self) -> None:
        if not str(self.record_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceActionRecord 缺少 record_id：禁止落库无标识的动作记录（红线⑥）"
            )
        if not str(self.action).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceActionRecord {self.record_id!r} 缺少 action："
                f"禁止落库无动作内容的处理事实（红线⑥）"
            )
        if not str(self.actor).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceActionRecord {self.record_id!r} 缺少 actor："
                f"处理事实必须可追溯到具体执行者（红线⑥）"
            )
        if not str(self.source).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceActionRecord {self.record_id!r} 缺少 source："
                f"禁止落库无源的处理事实（红线⑥：事实必须可溯源）"
            )
        for label, text in (
            ("action", self.action),
            ("result", self.result),
        ):
            if not str(text).strip():
                continue
            ctx = f"GovernanceActionRecord {self.record_id!r} 的 {label}"
            _reject_markers(
                text, _REMEDIATION_MARKERS,
                ctx=ctx, rule="动作记录只陈述已发生的事实，禁止 AI 自动整改（红线③）",
            )
            _reject_markers(
                text, _PERMISSION_MARKERS,
                ctx=ctx, rule="本层不得修改权限或策略（红线⑤）",
            )

    @property
    def is_human_action(self) -> bool:
        """是否为真实人工动作（只读事实，不做任何推断）。"""
        return str(self.actor_kind).strip().lower() == "user"

    def summary(self) -> str:
        """只读摘要（**不含处置建议、不含责任判定**）。"""
        return (
            f"record={self.record_id} task={self.task_id} action={self.action} "
            f"actor={self.actor} source={self.source}"
        )


# ---------------------------------------------------------------------------
# 任务5：治理闭环报告（问题来源 + 处理记录 + 人工结果 + 来源链）
# ---------------------------------------------------------------------------

@dataclass
class GovernanceClosureReport:
    """治理闭环报告（任务5，**强可溯源 + 人工结果**）。

    内容严格对应主理人指令四段：
    - **问题来源**：``source_type`` / ``source_id``（来自 ``GovernanceTask``）；
    - **处理记录**：``action_records``（``GovernanceActionRecord`` 事实列表）；
    - **人工结果**：``human_result``（由真实人工填写，AI 不代填）；
    - **来源链**：``source_trace``（``SourceTrace``，空链即拒绝生成）。

    红线约束（红线③/⑥）：
    - ``source_trace`` 不可溯源即拒绝构造（禁止输出无来源链的闭环报告）；
    - ``human_result`` 为空即拒绝（AI 不得代替治理责任人下结论）；
    - ``closed_by`` 必须是真实人工标识（命中非人类标识即拒绝）；
    - ``human_result`` 命中自动整改 / 改权限语义即拒绝；
    - 报告**不含**批准语义、不含处置建议、不含责任判定。
    """

    report_id: str
    task_id: str = ""
    org_id: str = ""
    agent_id: str = ""
    source_type: str = ""
    source_id: str = ""
    action_records: List[GovernanceActionRecord] = field(default_factory=list)
    human_result: str = ""
    closed_by: str = ""
    closed_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        if not str(self.report_id).strip():
            raise EnterpriseRedLineViolationError(
                "GovernanceClosureReport 缺少 report_id：禁止落库无标识的闭环报告（红线⑥）"
            )
        if not str(self.task_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceClosureReport {self.report_id!r} 缺少 task_id："
                f"闭环报告必须归属一个真实治理任务（红线⑥）"
            )
        if not str(self.source_id).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceClosureReport {self.report_id!r} 缺少问题来源 source_id："
                f"禁止输出无问题来源的闭环报告（红线⑥）"
            )
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"GovernanceClosureReport {self.report_id!r} 无来源链："
                f"禁止输出不可溯源的治理闭环报告（红线⑥）"
            )
        if not str(self.human_result).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceClosureReport {self.report_id!r} 缺少 human_result："
                f"闭环结论必须由真实治理责任人填写，AI 不得代填（红线⑥）"
            )
        if not str(self.closed_by).strip():
            raise EnterpriseRedLineViolationError(
                f"GovernanceClosureReport {self.report_id!r} 缺少 closed_by："
                f"闭环必须可追溯到真实人工（红线⑥）"
            )
        _reject_non_human(
            self.closed_by,
            ctx=f"GovernanceClosureReport {self.report_id!r} 的 closed_by",
        )
        ctx = f"GovernanceClosureReport {self.report_id!r} 的 human_result"
        _reject_markers(
            self.human_result, _REMEDIATION_MARKERS,
            ctx=ctx, rule="闭环结论必须是人工处理事实，禁止 AI 自动整改（红线③）",
        )
        _reject_markers(
            self.human_result, _PERMISSION_MARKERS,
            ctx=ctx, rule="本层不得修改权限或策略（红线⑤）",
        )

    @property
    def action_count(self) -> int:
        """只读处理记录条数。"""
        return len(self.action_records)

    @property
    def is_traceable(self) -> bool:
        """只读可溯源状态（构造期已强制为 True）。"""
        return self.source_trace is not None and self.source_trace.is_traceable

    def render_source(self) -> str:
        """只读渲染来源链（不改动任何状态）。"""
        return self.source_trace.render() if self.source_trace else "no_source"

    def summary(self) -> str:
        """只读摘要（**只陈述闭环事实与来源，不含建议**）。"""
        return (
            f"closure={self.report_id} task={self.task_id} "
            f"source={self.source_type}:{self.source_id} "
            f"actions={self.action_count} closed_by={self.closed_by} "
            f"trace={self.render_source()}"
        )


# ---------------------------------------------------------------------------
# 任务4：治理工作流服务（AI 只能创建候选任务，不能自动关闭）
# ---------------------------------------------------------------------------

class GovernanceWorkflowService(_RedLineForbiddenMixin):
    """Agent 治理工作流与责任闭环服务（任务1–8 统一入口）。

    承载链路：**治理发现 → 治理任务 → 责任人 → 人工处理 → 结果记录 → 治理闭环**。

    方法边界（主理人明列四法 + 一个人工守卫补充）：
    - ``create_task``：**AI 可发起**，但只产出 ``created`` 候选任务，无责任人、
      无完成时间（红线③/④）。
    - ``assign_owner``：**强制 ``require_human_actor(USER)``**，责任人必须是真实
      人工标识（红线④/⑥）。
    - ``start_processing``（补充）：**强制 USER**，登记人工开始处理的事实。
    - ``submit_result``：**强制 USER**，登记人工处理结果，任务进入
      ``waiting_review``（红线③/⑥）。
    - ``human_close``：**强制 USER**，唯一能把任务推进到 ``completed`` 的入口；
      AI 无论如何无法自动关闭（红线③/⑥）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - **不整改**：不持有任何 remediate / fix / resolve / repair 能力（红线③）。
    - **不分配**：AI 无法分配责任，构造期 owner_id 必须为空（红线④）。
    - **不改权限**：对 ``AgentPermissionPolicy`` / ``AgentRuntimeGovernanceService``
      纯只读，只用于访问校验，绝不写（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_remediate / auto_fix / auto_resolve /
      auto_assign / auto_change_permission 等方法。
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
        governance_center: "Any | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceWorkflowService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        # 只读使用：仅用于访问校验，绝不写任何权限或策略（红线⑤）。
        self._permission_policy = permission_policy
        self._runtime_policy = runtime_policy
        # 只读消费 3.8.20 治理中枢事实（可为空）；本层绝不回写中枢任何状态。
        self._governance_center = governance_center
        self._tasks: Dict[str, GovernanceTask] = {}
        self._assignments: Dict[str, GovernanceAssignment] = {}
        self._actions: Dict[str, GovernanceActionRecord] = {}
        self._closures: Dict[str, GovernanceClosureReport] = {}

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """治理任务数据访问权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误（红线⑥：治理数据受控访问）。

        本方法**只读校验**，绝不修改任何权限或策略（红线⑤）。
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
                    f"用户角色无权限访问 Agent 治理工作流数据"
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

    def _get_task_or_raise(self, task_id: str, *, op: str) -> GovernanceTask:
        """只读取出治理任务，不存在即拒绝（禁止凭空推进流程）。"""
        task = self._tasks.get(task_id)
        if task is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到治理任务 {task_id!r}：禁止凭空推进治理流程（红线⑥）"
            )
        return task

    @staticmethod
    def _ensure_transition(
        task: GovernanceTask, target: GovernanceTaskStatus, *, op: str
    ) -> None:
        """校验状态迁移合法性（非法迁移直接拒绝，只前进不回退）。"""
        if not task.can_transition_to(target):
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把任务 {task.task_id!r} 从 {task.status.value} 迁移到 "
                f"{target.value}：非法状态迁移（治理流程只能按 created → assigned → "
                f"processing → waiting_review → completed 由真实人工逐步推进，红线③/⑥）"
            )

    # ------------------------------------------------------------------
    # 任务4-①：create_task（AI 只能创建候选任务）
    # ------------------------------------------------------------------

    def create_task(
        self,
        *,
        task_id: str,
        source_type: "GovernanceTaskSourceType | str",
        source_id: str,
        agent_id: str = "",
        title: str = "",
        detail: str = "",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceTask:
        """从一条治理发现创建**候选治理任务**（红线③/④）。

        AI 可以发起本方法，但产出物在结构上只能是 ``created`` 候选态：
        无责任人（``owner_id`` 为空）、无完成时间、``requires_human_completion``
        恒为 True。AI 既不能借此分配责任（红线④），也不能借此整改或关闭（红线③）。

        ``source_id`` 为空即拒绝：治理任务必须源自一条真实的上游治理发现（红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建治理任务（红线①）"
            )
        if task_id in self._tasks:
            raise EnterpriseRedLineViolationError(
                f"create_task 拒绝重复创建治理任务 {task_id!r}：禁止覆盖既有治理事实（红线⑥）"
            )
        task = GovernanceTask(
            task_id=task_id,
            source_type=source_type,
            source_id=source_id,
            org_id=self._org_id,
            agent_id=agent_id,
            title=title,
            detail=detail,
            created_at=created_at,
            created_by=actor_id,
        )
        self._tasks[task_id] = task
        if self._audit is not None:
            self._audit.record_agent_governance_task_action(
                record_id=f"agent-governance-task-{task_id}",
                actor_id=actor_id,
                action="create_governance_task_candidate",
                target=task_id,
                detail=task.summary(),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return task

    # ------------------------------------------------------------------
    # 任务4-②：assign_owner（必须真实 USER）
    # ------------------------------------------------------------------

    def assign_owner(
        self,
        *,
        task_id: str,
        assignee: str,
        role: str,
        actor_kind: Any,
        actor_id: str,
        assignment_id: str = "",
        timestamp: str = "",
        note: str = "",
    ) -> GovernanceAssignment:
        """把治理任务分配给**真实人工责任人**（红线④/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError`` —— AI 永远无法自动分配责任。

        ``assignee`` 必须是真实人工标识（命中 ai / system / bot / agent / auto /
        机器人 等即拒绝）；``role`` 必须显式给出。分配成功后任务迁移
        ``created → assigned``，并把 ``owner_id`` 写为该真实人工。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分配治理责任（红线①）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "assign_owner 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        task = self._get_task_or_raise(task_id, op="assign_owner")
        self._ensure_transition(task, GovernanceTaskStatus.ASSIGNED, op="assign_owner")
        aid = assignment_id or f"assign-{task_id}"
        assignment = GovernanceAssignment(
            assignment_id=aid,
            task_id=task_id,
            assignee=assignee,
            role=role,
            timestamp=timestamp,
            org_id=self._org_id,
            assigned_by=actor_id,
            note=note,
        )
        self._assignments[aid] = assignment
        task.owner_id = assignment.assignee
        task.status = GovernanceTaskStatus.ASSIGNED
        if self._audit is not None:
            self._audit.record_agent_governance_task_action(
                record_id=f"agent-governance-assign-{aid}",
                actor_id=actor_id,
                action="human_assign_governance_owner",
                target=task_id,
                detail=assignment.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return assignment

    # ------------------------------------------------------------------
    # 任务4-③：start_processing（人工开始处理，补充守卫节点）
    # ------------------------------------------------------------------

    def start_processing(
        self,
        *,
        task_id: str,
        actor_kind: Any,
        actor_id: str,
        action: str = "human_start_processing",
        source: str = "",
        timestamp: str = "",
        result: str = "",
    ) -> GovernanceActionRecord:
        """登记「真实人工开始处理」的事实（红线③/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI 无法把任务推进到
        ``processing``。本方法只登记事实动作，绝不执行任何整改。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推进治理处理（红线①）"
            )
        task = self._get_task_or_raise(task_id, op="start_processing")
        self._ensure_transition(
            task, GovernanceTaskStatus.PROCESSING, op="start_processing"
        )
        record = self._append_action(
            record_id=f"gaction-start-{task_id}",
            task_id=task_id,
            action=action,
            actor=actor_id,
            actor_kind="user",
            timestamp=timestamp,
            result=result,
            source=source or f"task:{task_id}",
        )
        task.status = GovernanceTaskStatus.PROCESSING
        if self._audit is not None:
            self._audit.record_agent_governance_action(
                record_id=f"agent-governance-action-{record.record_id}",
                actor_id=actor_id,
                action="human_start_governance_processing",
                target=task_id,
                detail=record.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return record

    # ------------------------------------------------------------------
    # 任务4-④：submit_result（人工提交处理结果）
    # ------------------------------------------------------------------

    def submit_result(
        self,
        *,
        task_id: str,
        actor_kind: Any,
        actor_id: str,
        result: str,
        action: str = "human_submit_result",
        source: str = "",
        timestamp: str = "",
    ) -> GovernanceActionRecord:
        """由**真实人工**提交处理结果，任务进入 ``waiting_review``（红线③/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI 不得提交「处理结果」。
        ``result`` 必须由人工填写，且命中自动整改 / 改权限语义即拒绝
        （由 ``GovernanceActionRecord.__post_init__`` 强制）。

        本方法**只登记结果事实**，不关闭任务 —— 关闭只能走 ``human_close``。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交治理处理结果（红线①）"
            )
        if not str(result).strip():
            raise EnterpriseRedLineViolationError(
                "submit_result 必须由人工填写 result："
                "AI 不得代替治理责任人给出处理结果（红线⑥）"
            )
        task = self._get_task_or_raise(task_id, op="submit_result")
        self._ensure_transition(
            task, GovernanceTaskStatus.WAITING_REVIEW, op="submit_result"
        )
        record = self._append_action(
            record_id=f"gaction-result-{task_id}",
            task_id=task_id,
            action=action,
            actor=actor_id,
            actor_kind="user",
            timestamp=timestamp,
            result=result,
            source=source or f"task:{task_id}",
        )
        task.status = GovernanceTaskStatus.WAITING_REVIEW
        if self._audit is not None:
            self._audit.record_agent_governance_action(
                record_id=f"agent-governance-action-{record.record_id}",
                actor_id=actor_id,
                action="human_submit_governance_result",
                target=task_id,
                detail=record.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return record

    # ------------------------------------------------------------------
    # 任务4-⑤：human_close（唯一闭环入口，必须真实 USER）
    # ------------------------------------------------------------------

    def human_close(
        self,
        *,
        task_id: str,
        actor_kind: Any,
        actor_id: str,
        human_result: str,
        completed_at: str = "",
        report_id: str = "",
    ) -> GovernanceClosureReport:
        """由**真实人工**确认治理闭环（红线③/⑥）。

        这是**唯一**能把 ``GovernanceTask`` 推进到 ``completed`` 的入口：
        ``require_human_actor(actor_kind)`` 强制，AI 无论如何无法自动关闭任务。

        闭环时同步生成 ``GovernanceClosureReport``（问题来源 + 处理记录 +
        人工结果 + 来源链）；来源链为空即拒绝闭环（红线⑥）。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下闭环治理任务（红线①）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "human_close 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        if not str(human_result).strip():
            raise EnterpriseRedLineViolationError(
                "human_close 必须由人工填写 human_result："
                "AI 不得代替治理责任人下闭环结论（红线⑥）"
            )
        task = self._get_task_or_raise(task_id, op="human_close")
        self._ensure_transition(task, GovernanceTaskStatus.COMPLETED, op="human_close")
        records = self.list_action_records_of(task_id)
        trace = SourceTrace(trace_id=f"trace-closure-{task_id}")
        trace.add_entry(f"{task.source_type.value}:{task.source_id}")
        assignment = self._assignments.get(f"assign-{task_id}")
        if assignment is not None:
            trace.add_entry(f"assignment:{assignment.assignment_id}")
        for rec in records:
            trace.add_entry(f"action:{rec.record_id}")
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"human_close 拒绝闭环 {task_id!r}：无任何事实来源，"
                f"禁止输出无来源链的治理闭环（红线⑥）"
            )
        rid = report_id or f"closure-{task_id}"
        report = GovernanceClosureReport(
            report_id=rid,
            task_id=task_id,
            org_id=self._org_id,
            agent_id=task.agent_id,
            source_type=task.source_type.value,
            source_id=task.source_id,
            action_records=list(records),
            human_result=human_result,
            closed_by=actor_id,
            closed_at=completed_at,
            source_trace=trace,
        )
        self._closures[rid] = report
        task.status = GovernanceTaskStatus.COMPLETED
        task.completed_at = completed_at
        task.closed_by = actor_id
        if self._audit is not None:
            self._audit.record_agent_governance_closure_action(
                record_id=f"agent-governance-closure-{rid}",
                actor_id=actor_id,
                action="human_close_governance_task",
                target=task_id,
                detail=report.summary(),
                ts=completed_at,
                actor_kind=actor_kind,
            )
        return report

    # ------------------------------------------------------------------
    # 内部：动作事实登记（不对外承担任何处置语义）
    # ------------------------------------------------------------------

    def _append_action(
        self,
        *,
        record_id: str,
        task_id: str,
        action: str,
        actor: str,
        actor_kind: str,
        timestamp: str,
        result: str,
        source: str,
    ) -> GovernanceActionRecord:
        """内部登记一条处理动作事实（**只记录，不执行**，红线③）。"""
        suffix = 1
        final_id = record_id
        while final_id in self._actions:
            suffix += 1
            final_id = f"{record_id}-{suffix}"
        record = GovernanceActionRecord(
            record_id=final_id,
            task_id=task_id,
            action=action,
            actor=actor,
            actor_kind=actor_kind,
            timestamp=timestamp,
            result=result,
            source=source,
            org_id=self._org_id,
        )
        self._actions[final_id] = record
        return record

    def record_observed_action(
        self,
        *,
        record_id: str,
        task_id: str,
        action: str,
        actor: str,
        source: str,
        timestamp: str = "",
        result: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> GovernanceActionRecord:
        """登记一条**被观察到的**处理动作事实（AI 可调用，红线③）。

        AI 只能如实记录「谁在什么时候做了什么」，``actor_kind`` 如实标注为 ``ai``；
        本方法**不改变任务状态**、**不整改任何风险**、**不关闭任何任务**。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记治理动作（红线①）"
            )
        self._get_task_or_raise(task_id, op="record_observed_action")
        record = self._append_action(
            record_id=record_id,
            task_id=task_id,
            action=action,
            actor=actor,
            actor_kind="ai",
            timestamp=timestamp,
            result=result,
            source=source,
        )
        if self._audit is not None:
            self._audit.record_agent_governance_action(
                record_id=f"agent-governance-action-{record.record_id}",
                actor_id=actor_id,
                action="record_observed_governance_action",
                target=task_id,
                detail=record.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return record

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def list_action_records_of(self, task_id: str) -> List[GovernanceActionRecord]:
        """只读列出某任务的处理动作事实（内部使用，不做权限校验）。"""
        return [r for r in self._actions.values() if r.task_id == task_id]

    def list_tasks(
        self,
        *,
        user: object,
        status: "GovernanceTaskStatus | str | None" = None,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> List[GovernanceTask]:
        """只读列出治理任务（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._tasks.values())
        if status is not None:
            st = (
                status
                if isinstance(status, GovernanceTaskStatus)
                else GovernanceTaskStatus(status)
            )
            items = [t for t in items if t.status is st]
        if agent_id:
            items = [t for t in items if t.agent_id == agent_id]
        return items

    def list_assignments(
        self,
        *,
        user: object,
        task_id: str = "",
        resource_category: str = "data",
    ) -> List[GovernanceAssignment]:
        """只读列出责任分配记录（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._assignments.values())
        if task_id:
            items = [a for a in items if a.task_id == task_id]
        return items

    def list_action_records(
        self,
        *,
        user: object,
        task_id: str = "",
        resource_category: str = "data",
    ) -> List[GovernanceActionRecord]:
        """只读列出处理动作事实（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._actions.values())
        if task_id:
            items = [r for r in items if r.task_id == task_id]
        return items

    def list_closure_reports(
        self,
        *,
        user: object,
        task_id: str = "",
        resource_category: str = "data",
    ) -> List[GovernanceClosureReport]:
        """只读列出治理闭环报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        items = list(self._closures.values())
        if task_id:
            items = [c for c in items if c.task_id == task_id]
        return items

    def get_closure_report(
        self,
        *,
        user: object,
        report_id: str,
        resource_category: str = "data",
    ) -> "GovernanceClosureReport | None":
        """只读获取某份闭环报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return self._closures.get(report_id)


__all__ = [
    "GovernanceTaskSourceType",
    "GovernanceTaskStatus",
    "GovernanceTask",
    "GovernanceAssignment",
    "GovernanceActionRecord",
    "GovernanceClosureReport",
    "GovernanceWorkflowService",
    "_GOVERNANCE_FORBIDDEN",
]

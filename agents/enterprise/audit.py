"""Enterprise Operation Layer —— AI 操作审计（任务5，Phase 3.8.0 基础 + 3.8.1 权限审计增强）。

记录：AI action / user action / workflow event / **permission check & access decision**（3.8.1）。

红线⑥（最高，fail-closed）：
- ``AuditService`` **禁止**把任何动作记录为「人工审批」。
- ``record_human_approval`` 是被拦截的 forbidden 方法名（命中即抛
  ``EnterpriseRedLineViolationError``）。审计记录只能如实标注动作的真实发起方
  （actor_kind ∈ {ai, user, system}），**不得伪造 human approval**。
- 其余红线（①/②/③/④/⑤）同样适用：构造/写路径断言 ``safety_invariants_ok()``；
  不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` /
  ``sign`` / ``authorize`` 等方法。

Phase 3.8.1 增强（任务5：权限审计）：
- 新增 ``AuditActionCategory.PERMISSION`` 大类。
- 新增 ``record_permission_check`` / ``record_access_granted`` / ``record_access_denied``，
  供 ResourcePermissionService / ExpertAccessService / ReviewPermissionService 联动记录。

设计要点：
- ``AuditRecord``：纯数据载体（actor_kind / actor_id / action / target / org_id / ts / detail）。
- ``AuditService``：登记四类动作；跨域访问由 ``org_id`` 作用域拦截。
- 不写 verified.json、不开启 engineering_enabled、不输出 engineering_approved。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class AuditActorKind(str, Enum):
    """动作发起方类型（如实标注，不得伪造为 human approval）。"""

    AI = "ai"
    USER = "user"
    SYSTEM = "system"


class AuditActionCategory(str, Enum):
    """审计动作大类。"""

    AI_ACTION = "ai_action"
    USER_ACTION = "user_action"
    WORKFLOW_EVENT = "workflow_event"
    PERMISSION = "permission"  # Phase 3.8.1：权限校验与访问决策
    COLLABORATION = "collaboration"  # Phase 3.8.2：任务/评论/通知等协作动作
    DASHBOARD = "dashboard"  # Phase 3.8.5：驾驶舱查看/查询/导出（仅事实动作，绝不伪造人工审批）
    # Phase 3.8.6：企业数据智能与决策辅助层（仅如实记录 AI 的事实型洞察/趋势/异常/报告生成，
    # 绝不承载批准/报价/审批/经营决策/记录为人工责任语义，红线②/③/④/⑥）。
    DATA_INSIGHT = "data_insight"
    TREND_ANALYSIS = "trend_analysis"
    ANOMALY_DETECTION = "anomaly_detection"
    REPORT_GENERATION = "report_generation"
    # Phase 3.8.7：企业知识反馈与持续改进层（仅如实记录 feedback / knowledge candidate /
    # validation 等事实型动作；绝不承载批准/审批/记录为人工责任语义，红线②/③/④/⑥）。
    FEEDBACK = "feedback"
    KNOWLEDGE_CANDIDATE = "knowledge_candidate"
    VALIDATION = "validation"
    # Phase 3.8.8：企业知识治理与版本控制层（仅如实记录 knowledge version / review /
    # conflict 等事实型动作；绝不承载批准/审批/激活/记录为人工责任语义，红线②/③/④/⑥）。
    KNOWLEDGE_VERSION = "knowledge_version"
    KNOWLEDGE_REVIEW = "knowledge_review"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    # Phase 3.8.9：企业知识智能检索与语义理解层（仅如实记录 search / retrieval / query 等
    # 事实型动作；绝不承载批准/报价/审批/生成工程结论/记录为人工责任语义，红线②/③/④/⑥）。
    KNOWLEDGE_SEARCH = "knowledge_search"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    KNOWLEDGE_QUERY = "knowledge_query"
    # Phase 3.8.10：企业知识智能体编排层（编排 Query/Retrieve/Validate/Draft 四个 AI 智能体；
    # 仅如实记录各智能体的事实型动作；绝不承载批准/报价/审批/生成工程结论/记录为人工责任语义，红线②/③/④/⑥）。
    KNOWLEDGE_AGENT_QUERY = "knowledge_agent_query"
    KNOWLEDGE_AGENT_RETRIEVE = "knowledge_agent_retrieve"
    KNOWLEDGE_AGENT_VALIDATE = "knowledge_agent_validate"
    KNOWLEDGE_AGENT_DRAFT = "knowledge_agent_draft"
    # Phase 3.8.11：企业知识对话上下文与记忆层（用户→会话→上下文→知识引用→回答草稿→人工使用）。
    # 仅如实记录「会话创建/消息写入/记忆候选提议」等事实型动作；会话上下文只暂存、绝不自动写知识库；
    # 长期记忆候选必须经 human_review（红线③/④/⑥：禁止 AI 自动修改/学习并写入知识、禁止 AI 代责）。
    KNOWLEDGE_CONVERSATION = "knowledge_conversation"
    KNOWLEDGE_MESSAGE = "knowledge_message"
    KNOWLEDGE_MEMORY = "knowledge_memory"
    # Phase 3.8.12：企业知识任务规划与多智能体工作流层（仅如实记录 knowledge task /
    # subtask / agent workflow 等事实型动作；绝不承载批准/报价/审批/生成工程结论/记录为人工
    # 责任语义，红线②/③/④/⑥）。
    KNOWLEDGE_TASK = "knowledge_task"
    KNOWLEDGE_SUBTASK = "knowledge_subtask"
    KNOWLEDGE_AGENT_WORKFLOW = "knowledge_agent_workflow"
    # Phase 3.8.13：企业智能体能力注册与治理层（仅如实记录 agent register / execution /
    # version 等事实型动作；绝不承载批准/报价/审批/生成工程结论/记录为人工责任语义，红线②/③/④/⑥）。
    AGENT_REGISTER = "agent_register"
    AGENT_EXECUTION = "agent_execution"
    AGENT_VERSION = "agent_version"
    # Phase 3.8.14：企业智能体可观测性与性能智能层（仅如实记录 agent metric / trace /
    # health 等事实型动作；绝不承载批准/报价/审批/禁用 Agent / 自动优化 Agent / 记录为人工
    # 责任语义，红线②/③/④/⑥）。
    AGENT_METRIC = "agent_metric"
    AGENT_TRACE = "agent_trace"
    AGENT_HEALTH = "agent_health"
    # Phase 3.8.15：企业智能体评估与质量治理层（仅如实记录 agent quality metric /
    # human evaluation / user feedback 等事实型动作；绝不承载批准/报价/审批/自动评级 Agent /
    # 自动禁用 Agent / 自动修改 Agent / 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_QUALITY = "agent_quality"
    AGENT_EVALUATION = "agent_evaluation"
    AGENT_FEEDBACK = "agent_feedback"
    # Phase 3.8.16：企业智能体成本与资源智能层（仅如实记录 agent resource usage /
    # cost metric / cost attribution / cost report 等事实型动作；绝不承载批准/报价/审批/
    # 自动关停 Agent / 自动修改配置 / 自动优化资源策略 / 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_RESOURCE = "agent_resource"
    AGENT_COST = "agent_cost"
    AGENT_COST_REPORT = "agent_cost_report"
    # Phase 3.8.17：企业智能体策略与运行时治理层（仅如实记录 runtime policy 登记/人工确认、
    # 运行时前置核查结论、工具访问核查结论等事实型动作；绝不承载批准/报价/审批/
    # 自动批准 Agent 运行 / 自动修改 Agent 策略 / 自动放行工具访问 / 记录为人工责任语义，
    # 红线②/③/④/⑤/⑥）。
    AGENT_POLICY = "agent_policy"
    AGENT_RUNTIME_CHECK = "agent_runtime_check"
    AGENT_TOOL_ACCESS = "agent_tool_access"
    # Phase 3.8.18：企业智能体安全与风险治理层（仅如实记录 security event / risk
    # candidate / 人工风险处置等事实型动作；绝不承载批准/报价/审批/自动封禁 Agent /
    # 自动修改权限 / 自动处置安全风险 / 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_SECURITY_EVENT = "agent_security_event"
    AGENT_RISK = "agent_risk"
    AGENT_RISK_REVIEW = "agent_risk_review"
    # Phase 3.8.19：企业智能体合规与审计智能层（仅如实记录 compliance rule 登记/
    # 人工确认、compliance check 事实、compliance risk 候选与人工整改等事实型动作；
    # 绝不承载批准/报价/审批/自动判定违法违规 / 自动处罚 Agent / 自动修改权限或策略 /
    # 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_COMPLIANCE_RULE = "agent_compliance_rule"
    AGENT_COMPLIANCE_CHECK = "agent_compliance_check"
    AGENT_COMPLIANCE_RISK = "agent_compliance_risk"
    # Phase 3.8.20：企业智能体治理智能中枢层（仅如实记录 governance dashboard 创建、
    # health/risk overview 与 governance report 生成、governance insight 产出与人工
    # 确认等事实型动作；绝不承载批准/报价/审批/自动控制 Agent（禁用·修改·升级·改策略）/
    # 自动处理风险 / 自动判定合规 / 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_DASHBOARD = "agent_governance_dashboard"
    AGENT_GOVERNANCE_REPORT = "agent_governance_report"
    AGENT_GOVERNANCE_INSIGHT = "agent_governance_insight"
    # Phase 3.8.21：企业智能体治理流程与责任闭环层（仅如实记录治理任务创建、
    # 人工责任分配、人工处理动作事实、人工闭环确认等事实型动作；绝不承载批准/报价/
    # 审批/自动整改风险（auto_remediate·auto_fix·auto_resolve）/ 自动分配责任 /
    # 自动修改权限策略 / 记录为人工责任语义，红线②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_TASK = "agent_governance_task"
    AGENT_GOVERNANCE_ACTION = "agent_governance_action"
    AGENT_GOVERNANCE_CLOSURE = "agent_governance_closure"
    # Phase 3.8.22：企业智能体治理知识与持续改进层（仅如实记录治理案例沉淀、
    # 知识候选生成 / 模式事实归纳、人工审核结论等事实型动作；绝不承载批准/报价/
    # 审批/自动修改 Agent（auto_modify_agent·auto_update_agent）/ 自动修改治理策略
    # （auto_update_policy·auto_apply_policy）/ 自动关闭治理任务 / 代替治理责任人
    # 语义，红线①/②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_CASE = "agent_governance_case"
    AGENT_GOVERNANCE_KNOWLEDGE = "agent_governance_knowledge"
    AGENT_GOVERNANCE_IMPROVEMENT = "agent_governance_improvement"
    # Phase 3.8.23：企业智能体治理知识检索与辅助学习层（仅如实记录治理知识检索
    # 请求提交 / 只读相似检索执行 / 辅助报告生成等事实型动作；绝不承载批准/报价/
    # 审批/自动修改治理知识（auto_update_knowledge·auto_merge_knowledge）/ 自动应用
    # 治理经验（auto_apply_knowledge·auto_execute_knowledge）/ 自动生成治理策略
    # （auto_generate_policy·generate_policy）/ 代替治理责任人语义，红线①/②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_KNOWLEDGE_QUERY = "agent_governance_knowledge_query"
    AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL = "agent_governance_knowledge_retrieval"
    AGENT_GOVERNANCE_ASSISTANCE = "agent_governance_assistance"
    # Phase 3.8.24：企业智能体治理知识助手层（仅如实记录治理问题提交 / 只读相似检索
    # 上下文构建 / 纯事实答案草稿生成等事实型动作；绝不承载批准/报价/审批/自动修改治理
    # 知识（auto_update_knowledge·auto_merge_knowledge）/ 自动应用治理经验（
    # auto_apply_knowledge·auto_execute_knowledge）/ 自动生成治理策略（generate_policy·
    # recommend_policy）/ 代替治理责任人确认答案语义，红线①/②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_ASSISTANT_QUERY = "agent_governance_assistant_query"
    AGENT_GOVERNANCE_ASSISTANT_CONTEXT = "agent_governance_assistant_context"
    AGENT_GOVERNANCE_ASSISTANT_DRAFT = "agent_governance_assistant_draft"
    # Phase 3.8.25：企业智能体治理工作流编排层（仅如实记录治理线索登记 / 真实人工研判
    # 确认 / 真实人工执行跟踪等事实型动作；绝不承载批准/报价/审批/自动治理（auto_govern·
    # auto_approve）/ 自动执行治理动作（auto_execute·auto_apply_knowledge）/ 自动关闭
    # 问题（auto_close_workflow·auto_archive）/ 自动生成治理策略（generate_policy·
    # recommend_policy）/ 代替治理责任人研判语义，红线①/②/③/④/⑤/⑥）。
    AGENT_GOVERNANCE_WORKFLOW_CREATE = "agent_governance_workflow_create"
    AGENT_GOVERNANCE_WORKFLOW_REVIEW = "agent_governance_workflow_review"
    AGENT_GOVERNANCE_WORKFLOW_EXECUTION = "agent_governance_workflow_execution"
    # Phase 3.8.26（Task 7）：新增 VIEW 审计大类（审计动作大类 68 → 69），仅如实记录
    # 「真实人工查看治理工作流」这一事实动作；绝不承载批准/审批/记录为人工责任语义（红线②/⑥）。
    AGENT_GOVERNANCE_WORKFLOW_VIEW = "agent_governance_workflow_view"
    # Phase 3.8.30（Task 6）：企业智能体治理全链路追踪与统一审计智能层（审计动作大类
    # 69 → 72）。三类均为**只读事实型**动作：仅如实记录「真实人工登记/查看治理链路
    # 追踪」「真实人工查看统一审计时间线」「真实人工查看治理事实重放视图」。
    # 绝不承载批准/报价/审批/自动修改治理记录（auto_modify_audit·auto_delete_record）/
    # 自动生成治理结论（auto_generate_conclusion·auto_conclude）/ 自动关闭事件
    # （auto_close_incident·auto_resolve）/ 代替审计责任人语义（红线①/②/③/④/⑤/⑥）。
    GOVERNANCE_TRACE = "governance_trace"
    GOVERNANCE_TIMELINE = "governance_timeline"
    GOVERNANCE_REPLAY = "governance_replay"
    # Phase 3.9.0（T7）：生产就绪与受控激活准备层（审计动作大类 72 → 75）。三类均为
    # **只读事实型**动作：仅如实记录「真实人工查看/登记生产就绪检查」「真实人工查看/
    # 登记部署清单」「真实人工查看/登记回滚计划」。绝不承载批准/放行/自动激活/
    # 自动修改生产状态（红线①~⑥）。
    PRODUCTION_READINESS_CHECK = "production_readiness_check"
    DEPLOYMENT_MANIFEST = "deployment_manifest"
    ROLLBACK_PLAN = "rollback_plan"


def require_human_actor(actor_kind: Any) -> None:
    """红线⑥ human-gating：强制人工责任节点必须由真实 USER 发起。

    用于 feedback 的 accept/reject/start_review、insight validation 创建、knowledge
    candidate 的 human_review 等必须由专家/主理人显式执行的操作。

    ``actor_kind`` 必须严格等于 ``AuditActorKind.USER``（接受枚举值或字符串 ``"user"``，
    但不接受 ``None`` / ``"ai"`` / ``"system"`` 等），否则抛
    ``EnterpriseRedLineViolationError`` —— AI 不得代替人工责任。
    """

    if actor_kind is None or actor_kind != AuditActorKind.USER:
        raise EnterpriseRedLineViolationError(
            "红线⑥：该操作必须由真实人工（USER）执行，AI 不得代替人工责任"
        )


@dataclass
class AuditRecord:
    """审计记录（任务5，纯数据）。"""

    record_id: str
    org_id: str
    actor_kind: AuditActorKind
    actor_id: str
    category: AuditActionCategory
    action: str
    target: str = ""          # 受影响对象 id（project / file / user 等）
    detail: str = ""
    ts: str = ""


class AuditService(_RedLineForbiddenMixin):
    """AI 操作审计服务（任务5）。

    仅如实记录 AI / user / workflow / permission 四类动作；**禁止**把动作记录为人工审批
    （``record_human_approval`` 被 mixin 拦截，红线⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",   # 红线⑥：核心拦截点
    )

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 AuditService（红线①/⑤）"
            )
        self._org_id = org_id
        self._records: list[AuditRecord] = []

    def record_ai_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次 AI 动作（actor_kind 恒为 AI，如实标注）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AI_ACTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_user_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次用户动作（actor_kind 恒为 USER）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.USER_ACTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_workflow_event(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次工作流事件（actor_kind 恒为 SYSTEM，如实标注为 workflow event）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.SYSTEM,
            actor_id=actor_id,
            category=AuditActionCategory.WORKFLOW_EVENT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.1：权限审计（任务5）----

    def record_permission_check(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次权限校验（actor_kind 恒为 USER——校验的主体是请求访问的用户）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.PERMISSION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_access_granted(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次访问被授予（permission 类别，如实标注结果）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.PERMISSION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_access_denied(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次访问被拒绝（permission 类别，如实标注结果与原因）。"""
        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.PERMISSION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.2：协作审计增强（任务5）----
    # 记录任务 / 评论 / 通知动作；actor 必须真实（默认 USER，可显式指定 AI/SYSTEM）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）。

    def record_task_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次任务协作动作（actor 真实；默认 USER，因任务动作由人发起）。"""
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.COLLABORATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_comment_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次评论协作动作（actor 真实；默认 USER）。"""
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.COLLABORATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_notification_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次通知动作（actor 真实；默认 USER）。

        注意：本方法仅如实记录「推送/已读」事件，**不**伪造人工审批通知（红线⑥）；
        伪造审批由 NotificationService 的 forbidden 方法名拦截。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.COLLABORATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.5：驾驶舱审计（任务5）----
    # 记录驾驶舱查看/查询/导出动作；actor 必须真实（默认 USER，因查看/导出由人发起）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「查看/查询/导出」事件，绝不承载批准/报价/审批语义。

    def record_dashboard_view(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "dashboard_view",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次驾驶舱查看（actor 真实；默认 USER）。"""
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.DASHBOARD,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_dashboard_query(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "dashboard_query",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次驾驶舱查询（actor 真实；默认 USER）。"""
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.DASHBOARD,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_dashboard_export(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "dashboard_export",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次驾驶舱导出（actor 真实；默认 USER）。"""
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.DASHBOARD,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.6：企业数据智能与决策辅助层审计（任务7）----
    # 记录 AI 的事实型洞察 / 趋势分析 / 异常发现 / 管理报告生成动作；actor 必须真实
    # （AI 生成默认 AI；用户手动创建/查看可显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把 AI 洞察记录为人工审批/决策）；
    # 下述四种方法仅如实记录「生成/分析/发现」事件，绝不承载批准/报价/审批/经营决策语义。

    def record_data_insight(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_data_insight",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次数据洞察生成（actor 真实；AI 生成默认 AI，红线⑥：绝不伪造为人工审批）。

        注意：本方法仅如实记录「洞察被生成」这一事实事件；洞察对象本身只描述 pattern，
        不包含任何决策/建议/审批语义（由 DataInsight 模型在结构上保证）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.DATA_INSIGHT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_trend_analysis(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "trend_analysis",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次趋势分析（actor 真实；AI 生成默认 AI，红线⑥：绝不伪造为人工审批）。

        注意：本方法仅如实记录「趋势被分析」这一事实事件；趋势对象本身只描述 change_pattern，
        不包含任何自动优化/经营建议语义（由 TrendInsight 模型在结构上保证）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.TREND_ANALYSIS,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_anomaly_detection(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "detect_anomaly",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次异常发现（actor 真实；AI 生成默认 AI，红线⑥：绝不伪造为人工审批）。

        注意：本方法仅如实记录「异常被发现」这一事实事件；异常对象本身只描述 pattern/severity，
        并要求人工确认（requires_human_confirmation 恒为 True），不提供任何 resolve/mitigate/fix
        处置入口（由 AnomalyDetector 模型在结构上保证，红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.ANOMALY_DETECTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_report_generation(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "generate_management_report",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次管理报告生成（actor 真实；AI 生成默认 AI，红线⑥：绝不伪造为人工审批）。

        注意：本方法仅如实记录「报告被生成」这一事实事件；管理报告对象本身只汇编 facts/trends/
        risks/sources（全部事实型且可溯源），不包含任何经营建议/管理决策/执行方案（由
        ManagementReport 模型在结构上保证，红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.REPORT_GENERATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.7：企业知识反馈与持续改进层审计（任务5）----
    # 记录用户反馈 / 知识更新候选 / 洞察验证等事实型动作；actor 必须真实
    # （默认 AI，因候选可由 AI 提议；人工审核节点显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「提交/创建/验证」事件，绝不承载批准/报价/审批语义。

    def record_feedback_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "feedback_action",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次用户反馈动作（actor 真实；AI 提交默认 AI，人工审核节点显式 USER）。

        注意：本方法仅如实记录「反馈被提交/被审核」这一事实事件；不含任何决策/批准语义
        （由 FeedbackService 在结构上保证，红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.FEEDBACK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_candidate_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "propose_knowledge_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识更新候选动作（actor 真实；AI 提议默认 AI，人工复核节点显式 USER）。

        注意：本方法仅如实记录「候选被提议/被审核」这一事实事件；候选模块**绝不**自动写入
        任何 KnowledgeRepository（由 KnowledgeUpdateCandidateService 在结构上保证，红线③）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_CANDIDATE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_validation_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "validate_insight",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次洞察验证动作（actor 真实；必须由 USER 显式验证，AI 不得自动验证，红线⑥）。

        注意：本方法仅如实记录「验证被执行」这一事实事件；验证由专家人工发起
        （InsightValidationService.create_validation 强制 require_human_actor），红线⑥。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.VALIDATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.8：企业知识治理与版本控制层审计（任务5）----
    # 记录知识版本 / 变更审核 / 版本冲突等事实型动作；actor 必须真实
    # （默认 AI，因版本创建/冲突发现可由 AI 促成；人工审核/激活节点显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「创建/审核/发现」事件，绝不承载批准/激活/审批语义
    # （activate_version / create_review 由服务层强制 require_human_actor，红线⑥）。

    def record_knowledge_version_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_version",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识版本动作（actor 真实；AI 创建默认 AI，人工激活节点显式 USER）。

        注意：本方法仅如实记录「版本被创建/被提交审核/被激活/被弃用」这一事实事件；
        版本的 active 状态必须由人工激活（KnowledgeLifecycleService.activate_version
        强制 require_human_actor），AI 不得自动激活，红线⑥。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_VERSION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_review_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_review",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识变更审核动作（actor 真实；必须由 USER 显式审核，AI 不得自动审核，红线⑥）。

        注意：本方法仅如实记录「审核被执行」这一事实事件；审核由专家人工发起
        （KnowledgeChangeReviewService.create_review 强制 require_human_actor），红线⑥。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_REVIEW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_conflict_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "discover_knowledge_conflict",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识版本冲突发现动作（actor 真实；AI 仅发现冲突，绝不自动 merge，红线③）。

        注意：本方法仅如实记录「冲突被发现」这一事实事件；冲突解决必须由人工执行
        （KnowledgeConflictService 结构上禁用 auto_merge_knowledge，红线③）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_CONFLICT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.9：企业知识智能检索与语义理解层审计（任务7）----
    # 记录知识检索查询 / 候选检索 / 回答起草等事实型动作；actor 必须真实
    # （检索由人发起默认 USER；回答由 AI 起草默认 AI，但 requires_human_review 强制 True）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「查询/检索/起草」事件，绝不承载批准/报价/审批/生成工程结论语义。

    def record_knowledge_search_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_search",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识检索查询（actor 真实；检索由人发起默认 USER，红线⑥）。

        注意：本方法仅如实记录「查询被发起」这一事实事件；检索结果仅为候选知识，
        不含任何工程结论（由 KnowledgeSearchService 在结构上保证，红线③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_SEARCH,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_retrieval_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "retrieve_knowledge_candidates",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次候选知识检索/推荐（actor 真实；默认 USER，红线⑥）。

        注意：本方法仅如实记录「候选被检索/被推荐」这一事实事件；返回的知识项**仅为候选**，
        绝不自动应用知识或生成工程结论（由 KnowledgeRetrievalEngine /
        KnowledgeRecommendationService 在结构上保证，红线③/④/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_RETRIEVAL,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_query_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "draft_knowledge_answer",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识回答起草（actor 真实；AI 起草默认 AI，但 requires_human_review 强制 True，红线⑥）。

        注意：本方法仅如实记录「回答草稿被起草」这一事实事件；草稿必须引用来源，
        且仅作候选，最终采用须经真实人工（由 KnowledgeAnswerService 在结构上保证，
        任务4 + 红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_QUERY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_agent_query_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "understand_user_query",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识智能体「查询理解」动作（actor 真实；AI 智能体默认 AI，红线⑥）。

        注意：本方法仅如实记录「用户查询被 AI 智能体解析/意图识别」这一事实事件；
        查询理解智能体**只理解用户需求**，**绝不生成任何工程判断/工程结论**
        （由 KnowledgeQueryAgent 在结构上保证，红线④/⑤）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_AGENT_QUERY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_agent_retrieve_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "agent_retrieve_knowledge",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识智能体「检索」动作（actor 真实；AI 智能体默认 AI，红线⑥）。

        注意：本方法仅如实记录「检索智能体调用检索引擎」这一事实事件；检索结果仅为可追溯的
        候选知识上下文（KnowledgeContext），**绝不自动应用知识或生成工程结论**
        （由 KnowledgeRetrievalAgent 在结构上保证，红线③/④/⑤）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_AGENT_RETRIEVE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_agent_validate_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "agent_validate_knowledge",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识智能体「校验」动作（actor 真实；AI 智能体默认 AI，红线⑥）。

        注意：本方法仅如实记录「校验智能体对知识上下文做来源/版本/权限/溯源校验」这一事实事件；
        校验智能体**只输出校验结果（ValidationResult），绝不自动批准回答**
        （由 KnowledgeValidationAgent 在结构上保证，红线⑥：禁止 AI 代责审批）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_AGENT_VALIDATE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_agent_draft_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "agent_draft_answer",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次知识智能体「回答起草」动作（actor 真实；AI 智能体默认 AI，红线⑥）。

        注意：本方法仅如实记录「回答起草智能体产出草稿」这一事实事件；草稿必须引用来源，
        且 ``requires_human_review`` 强制为 True（由 KnowledgeAnswerAgent 在结构上保证，
        最终采用须经真实人工复核，红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_AGENT_DRAFT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_conversation_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_conversation",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「知识会话」事实动作（actor 真实；会话由用户发起默认 USER，红线⑥）。

        注意：本方法仅如实记录「用户创建/归档知识会话」这一事实事件；会话上下文只暂存于会话
        作用域，**绝不自动写知识库、绝不自动学习用户信息**（由 KnowledgeConversationService
        在结构上保证，红线③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_CONVERSATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_message_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "append_knowledge_message",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「知识会话消息」事实动作（actor 真实；角色由服务如实标注，红线⑥）。

        注意：本方法仅如实记录「用户提问 / AI 回答草稿」这一事实事件；AI 消息必须引用来源
        （references 非空），且会话上下文只暂存、绝不自动写知识库（由 KnowledgeMessageService
        在结构上保证，红线③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_MESSAGE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_memory_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "propose_long_term_memory",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「知识记忆候选」事实动作（actor 真实；AI 提议默认 AI，红线⑥）。

        注意：本方法仅如实记录「AI 基于会话上下文提议长期记忆候选」这一事实事件；候选
        ``requires_human_review`` 强制为 True，最终纳入长期记忆须经真实人工复核
        （由 MemoryPolicyService 在结构上保证，红线③/④/⑥：禁止 AI 自动保存知识、禁止 AI 代责）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_MEMORY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_task_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_task",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「知识任务」事实动作（actor 真实；任务由用户发起默认 USER，红线⑥）。

        注意：本方法仅如实记录「用户创建/规划知识任务」这一事实事件；任务本身只承载目标拆解
        与 Agent 规划的中间态，**绝不自动写知识库、绝不自动生成工程结论**
        （由 KnowledgeTaskService / KnowledgeTaskPlanner 在结构上保证，红线③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_TASK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_subtask_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_knowledge_subtask",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「子任务」事实动作（actor 真实；子任务调度默认 AI，红线⑥）。

        注意：本方法仅如实记录「子任务被拆解/被调度执行」这一事实事件；子任务调用各 Agent 只做
        检索/校验/分析/起草，**绝不自动应用知识或生成工程结论**
        （由 KnowledgeSubTaskService / KnowledgeTaskOrchestrator 在结构上保证，红线③/④/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_SUBTASK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_knowledge_agent_workflow_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "run_knowledge_agent_workflow",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「多智能体工作流」事实动作（actor 真实；工作流编排默认 AI，红线⑥）。

        注意：本方法仅如实记录「编排器调度多智能体完成一次任务」这一事实事件；编排器只协调
        Agent、**绝不审批/绝不落地工程结论**（由 KnowledgeTaskOrchestrator 在结构上保证，
        红线③/④/⑥：AI 不得代替专家/管理责任）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.KNOWLEDGE_AGENT_WORKFLOW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_register_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_agent",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体注册/生命周期」事实动作（actor 真实；注册默认 AI，激活/弃用须 USER，红线⑥）。

        本方法仅如实记录「智能体被注册/提交复核/被人工激活/被人工弃用」这一事实事件；
        状态流转由 AgentLifecycleService 在结构上保证（active 须真实 USER，红线⑥），
        **绝不**伪造 human approval、绝不承载批准/报价/审批语义（红线②/③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_REGISTER,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_execution_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "invoke_agent",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体调用」事实动作（actor 真实；调用默认 AI，红线⑥）。

        本方法仅如实记录「某 Agent 被调用执行某能力」这一事实事件；Agent 访问资源受
        AgentPermissionPolicy 约束（默认拒绝，红线③/⑥），本方法**不**执行任何 Agent 动作、
        不写任何知识资产。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_EXECUTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_version_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_agent_version",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体版本」事实动作（actor 真实；版本创建默认 AI，激活/弃用须 USER，红线⑥）。

        本方法仅如实记录「智能体版本被创建/提交复核/被人工激活/被人工弃用」这一事实事件；
        版本仅元数据与状态流转，**绝不**写入任何运行态/知识资产（red line ③），
        绝不承载批准/报价/审批/记录为人工责任语义（红线②/③/④/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_VERSION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.14：企业智能体可观测性与性能智能层审计（任务6）----
    # 记录智能体指标 / 调用链 / 健康候选等事实型动作；actor 必须真实
    # （默认 AI，因指标/追踪/检测可由 AI 促成；人工复核节点显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「登记/记录/检测」事件，绝不承载批准/报价/审批/禁用 Agent/
    # 自动优化 Agent/记录为人工责任语义（红线②/③/④/⑥）。

    def record_agent_metric_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_metric",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体指标」事实动作（actor 真实；AI 登记默认 AI，红线⑥）。

        本方法仅如实记录「指标被登记/被派生」这一事实事件；指标只描述事实数字
        （调用次数/成功率/耗时），**绝不评价 Agent 好坏**（由 AgentMetric 在结构上保证，
        红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_METRIC,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_trace_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_trace",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体调用链」事实动作（actor 真实；AI 记录默认 AI，红线⑥）。

        本方法仅如实记录「调用链被记录」这一事实事件；调用链只描述 parent/child 关系，
        **绝不承载批准/报价/审批/禁用 Agent 语义**（红线②/③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_TRACE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_health_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "detect_agent_health",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体健康候选」事实动作（actor 真实；AI 检测默认 AI，红线⑥）。

        本方法仅如实记录「健康候选被发现」这一事实事件；候选要求人工复核
        （requires_human_review 恒为 True），**绝不自动禁用/处置 Agent**
        （由 AgentHealthCandidate / AgentHealthDetector 在结构上保证，红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_HEALTH,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.15：企业智能体评估与质量治理层审计（任务6）----
    # 记录智能体质量指标 / 人工评价 / 用户反馈等事实型动作；actor 必须真实
    # （默认 AI，因指标可由 AI 登记；人工评价/反馈审核节点显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述三种方法仅如实记录「登记/提交/审核」事件，绝不承载批准/报价/审批/自动评级 Agent/
    # 自动禁用 Agent/自动修改 Agent/记录为人工责任语义（红线②/③/④/⑤/⑥）。

    def record_agent_quality_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_quality_metric",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体质量指标」事实动作（actor 真实；AI 登记默认 AI，红线⑥）。

        本方法仅如实记录「质量指标被登记/版本被比较/质量报告被生成」这一事实事件；
        质量指标只描述事实数字（任务计数/反馈计数），**绝不评价 Agent 好坏**
        （由 AgentQualityMetric 在结构上保证，红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_QUALITY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_evaluation_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "submit_agent_evaluation",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「人工评价」事实动作（actor 真实；必须由 USER 显式提交，AI 不得代评，红线⑥）。

        本方法仅如实记录「评价被真实人工提交」这一事实事件；评价由专家/主理人人工发起
        （AgentQualityGovernanceService.submit_evaluation 强制 require_human_actor），红线⑥。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_EVALUATION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_feedback_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "submit_agent_feedback",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「用户反馈」事实动作（actor 真实；默认 AI，由用户提交；反馈审核须 USER，红线⑥）。

        本方法仅如实记录「反馈被提交/被人工审核」这一事实事件；反馈只记录用户事实内容，
        **绝不自动禁用/修改 Agent**（由 AgentFeedback / AgentQualityGovernanceService
        在结构上强制 requires_human_review，红线③/④/⑤/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_FEEDBACK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.16：企业智能体成本与资源智能层审计（任务6）----
    # 记录智能体资源用量 / 成本指标 / 成本归属 / 成本报告等事实型动作；actor 必须真实
    # （默认 AI，因用量/成本可由 AI 登记；人工提交/审核节点显式传 actor_kind=USER）。
    # 始终**不**提供 record_human_approval（红线⑥：禁止把动作记录为人工审批）；
    # 下述四种方法仅如实记录「登记/计算/归属/生成报告」事件，绝不承载批准/报价/审批/
    # 自动关停 Agent / 自动修改配置 / 自动优化资源策略 / 记录为人工责任语义（红线②/③/④/⑤/⑥）。
    # 成本单价必须来自外部 rate_card / 财务台账，AI 不得编造单价（红线⑥）。

    def record_agent_resource_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_resource_usage",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体资源用量」事实动作（actor 真实；AI 登记默认 AI，红线⑥）。

        本方法仅如实记录「资源用量被登记/聚合」这一事实事件；用量只描述事实数字
        （token/compute/storage/external_api 计数），**绝不自动关停/停止 Agent**
        （由 AgentResourceUsage / AgentCostResourceService 在结构上强制，红线③）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_RESOURCE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_cost_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_cost_metric",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体成本指标」事实动作（actor 真实；AI 登记默认 AI，红线⑥）。

        本方法仅如实记录「成本指标被登记/计算」这一事实事件；成本只描述事实数字
        （value/period/currency），**单价必须来自外部台账**，AI 不得编造单价（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_COST,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_cost_report_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "generate_agent_cost_report",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体成本报告」事实动作（actor 真实；AI 生成默认 AI，红线⑥）。

        本方法仅如实记录「成本报告被生成」这一事实事件；报告只汇总事实用量/成本/归属，
        **绝不自动优化资源策略/自动修改配置/自动关停 Agent**（由 AgentCostReport /
        AgentCostResourceService 在结构上强制，红线④/⑤）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_COST_REPORT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.17：企业智能体策略与运行时治理层审计（任务5）----
    # 下述三种方法仅如实记录「策略登记/人工确认生效/运行时核查/工具访问核查」事件，
    # 绝不承载批准/报价/审批/自动批准 Agent 运行 / 自动修改 Agent 策略 /
    # 自动放行工具访问 / 记录为人工责任语义（红线②/③/④/⑤/⑥）。
    # actor 必须如实：AI 登记默认 AI；策略生效/弃用由服务层强制 require_human_actor(USER)。

    def record_agent_policy_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_agent_runtime_policy",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体运行策略」事实动作（actor 真实，红线⑥）。

        本方法仅如实记录「运行策略被登记 / 被人工确认生效 / 被人工弃用」这一事实事件；
        **绝不自动修改 Agent 策略**（策略状态推进由 AgentRuntimeGovernanceService 强制
        ``require_human_actor(USER)``，红线④），也绝不把 AI 动作记为人工审批（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_POLICY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_runtime_check_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "run_agent_runtime_check",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体运行时前置核查」事实动作（actor 真实，红线⑥）。

        本方法仅如实记录「策略/权限/作用域/工具四项核查得出何种结论」这一事实事件；
        核查结论**不构成运行批准**，AI 不得据此自动放行运行（由 AgentExecutionGuard /
        RuntimeDecisionRecord 在结构上强制，红线③）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_RUNTIME_CHECK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_tool_access_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "check_agent_tool_access",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体工具访问」事实动作（actor 真实，红线⑥）。

        本方法仅如实记录「工具访问策略被登记 / 工具访问核查得出何种结论」这一事实事件；
        工具策略**默认拒绝**，AI 不得自动放行工具访问（由 AgentToolAccessPolicy /
        AgentExecutionGuard 在结构上强制，红线⑤）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_TOOL_ACCESS,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.18：企业智能体安全与风险治理层审计（任务6）----
    # 下述三种方法仅如实记录「安全事件登记 / 风险候选发现 / 人工风险处置」事件，
    # 绝不承载批准/报价/审批/自动封禁 Agent / 自动修改权限 / 自动处置安全风险 /
    # 记录为人工责任语义（红线②/③/④/⑤/⑥）。
    # actor 必须如实：AI 登记默认 AI；风险处置由服务层强制 require_human_actor(USER)。

    def record_agent_security_event_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_agent_security_event",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体安全事件」事实动作（actor 真实，红线⑥）。

        本方法仅如实记录「某安全事实事件被登记」这一事件本身；
        **绝不自动封禁 Agent**（红线③）、**绝不自动修改权限**（红线④），
        也绝不把 AI 动作记为人工审批（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_SECURITY_EVENT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_risk_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_agent_risk_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「智能体风险候选 / 安全报告」事实动作（actor 真实，红线⑥）。

        本方法仅如实记录「风险候选被发现并登记 / 安全报告被生成」这一事实事件；
        风险候选恒为**待人工复核**，AI 不得据此自动处置风险（由 AgentRiskCandidate /
        AgentSecurityRiskService 在结构上强制，红线⑤）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_RISK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_risk_review_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "human_review_agent_risk",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「安全风险人工处置」事实动作（actor 真实，红线⑤/⑥）。

        本方法仅如实记录「某真实人工完成了风险处置」这一事实事件；
        处置动作本身由 ``AgentSecurityRiskService.human_review_risk`` 在
        ``require_human_actor(USER)`` 守卫下执行，AI 无论如何无法自行处置，
        也不得把 AI 动作伪造为人工审批（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_RISK_REVIEW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ---- Phase 3.8.19：企业智能体合规与审计智能层审计（任务7）----
    # 下述三种方法仅如实记录「合规规则登记/人工确认 / 合规检查事实 /
    # 合规风险候选与人工整改」事件，绝不承载批准/报价/审批 /
    # 自动判定违法违规 / 自动处罚 Agent / 自动修改权限或策略 /
    # 记录为人工合规责任语义（红线②/③/④/⑤/⑥）。
    # actor 必须如实：AI 登记默认 AI；规则生效/废止与风险整改由服务层
    # 强制 require_human_actor(USER)，AI 无论如何无法伪造为人工。
    # 本层不提供也不允许 record_human_approval 之类的人工审批伪造入口。

    def record_agent_compliance_rule_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_compliance_rule",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「合规规则」事实动作（actor 真实，红线⑤/⑥）。

        本方法仅如实记录「某条合规规则被登记 / 被真实人工确认生效或废止」
        这一事实事件；规则的生效与废止本身由
        ``AgentComplianceService.confirm_rule_active`` /
        ``confirm_rule_deprecated`` 在 ``require_human_actor(USER)`` 守卫下执行，
        **AI 绝不能自动修改策略或使规则生效**（红线⑤），
        也绝不把 AI 动作伪造为人工合规确认（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_COMPLIANCE_RULE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_compliance_check_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_compliance_check",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「合规检查」事实动作（actor 真实，红线③/⑥）。

        本方法仅如实记录「某次规则检查得出何种中性结论」这一事实事件。
        检查结论枚举 ``ComplianceCheckResult`` 在结构上**只有**
        ``pass`` / ``attention`` / ``not_applicable``，
        **不存在** violation / illegal / penalty 等判罚态 ——
        AI 绝不判定违法违规、绝不处罚 Agent（红线③/④）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_COMPLIANCE_CHECK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_compliance_risk_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_compliance_risk_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「合规风险候选 / 合规报告 / 人工整改」事实动作（actor 真实，红线④/⑥）。

        本方法仅如实记录「合规风险候选被发现并登记 / 合规报告被生成 /
        某真实人工完成了合规风险处置」这一事实事件；
        风险候选恒为**待人工复核**（``requires_human_review is True`` 由
        ``ComplianceRiskCandidate.__post_init__`` 强制），
        AI 不得据此自动暂停或封禁 Agent（红线④），
        人工整改由 ``AgentComplianceService.human_review_compliance_risk``
        在 ``require_human_actor(USER)`` 守卫下执行（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_COMPLIANCE_RISK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.8.20：企业智能体治理智能中枢层（任务6，+3 类）
    # ------------------------------------------------------------------

    def record_agent_governance_dashboard_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_governance_dashboard",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理看板」事实动作（actor 真实，红线③/⑥）。

        本方法仅如实记录「某个治理看板被创建 / 被查看」这一事实事件。
        看板在结构上**只能展示事实**（``GovernanceWidget`` 强制 source 且拒绝
        任何控制/处置/批准语义），AI 绝不能通过看板自动禁用、修改、升级 Agent
        或改动任何策略（红线③），也绝不把 AI 动作伪造为人工治理决策（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_DASHBOARD,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_report_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "generate_agent_governance_report",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理报告 / 健康总览 / 风险总览 / 人工处置」事实动作（红线③/④/⑥）。

        本方法仅如实记录「五段治理事实被汇总成报告 / 健康总览被生成 /
        风险总览被生成 / 某真实人工完成了风险处置」这一事实事件。
        健康总览**不含任何评级**（键名命中评级语义即被
        ``AgentHealthOverview.__post_init__`` 拒绝，红线③）；
        风险总览 ``requires_human_handling`` 恒为 True 且构造期只能是
        ``pending_human_review``，AI 不得自动处理风险（红线④）；
        人工处置由 ``AgentGovernanceCenterService.human_handle_risk_overview``
        在 ``require_human_actor(USER)`` 守卫下执行（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_REPORT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_insight_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "generate_fact_trend_insight",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理洞察」事实动作（actor 真实，红线⑤/⑥）。

        本方法仅如实记录「某条事实趋势 / 异常候选洞察被产出，或某真实人工
        确认了该洞察」这一事实事件。洞察类型枚举
        ``GovernanceInsightKind`` 在结构上**只有** ``fact_trend`` /
        ``anomaly_candidate``，**不存在** recommendation / advice /
        compliance_verdict 等建议或判定态 —— AI 绝不给治理建议、
        绝不自动判定合规（红线⑤）；人工确认由
        ``AgentGovernanceCenterService.human_confirm_insight`` 在
        ``require_human_actor(USER)`` 守卫下执行，AI 不代替治理责任人（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_INSIGHT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.8.21：企业智能体治理流程与责任闭环层（任务6，+3 类）
    # ------------------------------------------------------------------

    def record_agent_governance_task_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_governance_task_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理任务 / 责任分配」事实动作（actor 真实，红线③/④/⑥）。

        本方法仅如实记录「某条治理发现被转成候选治理任务」或「某真实人工把任务
        分配给了某位真实责任人」这一事实事件。

        - AI 创建任务时 ``actor_kind`` 如实为 ``AI``，且产出物在结构上只能是
          ``created`` 候选态（``GovernanceTask.__post_init__`` 禁止预填
          ``owner_id`` / ``completed_at``），AI 绝不能借此分配责任（红线④）
          或整改风险（红线③）。
        - 责任分配由 ``GovernanceWorkflowService.assign_owner`` 在
          ``require_human_actor(USER)`` 守卫下执行，``assignee`` 必须是真实人工
          标识（命中 ai / system / bot / agent / auto 等即拒绝，红线④/⑥）。
        - 本方法绝不把 AI 动作伪造为人工治理决策（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_TASK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_observed_governance_action",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理处理动作」事实（actor 真实，红线③/⑤/⑥）。

        本方法仅如实记录「谁在什么时候对某治理任务做了什么、结果是什么、
        来源是什么」这一事实事件。

        - ``GovernanceActionRecord`` 强制 ``action`` / ``actor`` / ``source``
          非空，且 ``action`` / ``result`` 命中自动整改语义
          （auto_remediate / auto_fix / auto_resolve / 自动整改 ...）即拒绝落库
          （红线③），命中改权限语义即拒绝（红线⑤）。
        - 人工处理节点（``start_processing`` / ``submit_result``）由
          ``require_human_actor(USER)`` 守卫；AI 只能经 ``record_observed_action``
          如实登记**被观察到的**事实，且不改变任务状态（红线③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_ACTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_closure_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "human_close_governance_task",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理闭环」事实动作（actor 真实，红线③/⑥）。

        本方法仅如实记录「某真实人工确认了某治理任务闭环，并给出人工结论」
        这一事实事件。

        - ``GovernanceTaskStatus`` 中**不存在** ``auto_completed`` /
          ``closed_by_ai`` 之类的 AI 终态；唯一能推进到 ``completed`` 的入口是
          ``GovernanceWorkflowService.human_close``，其上有
          ``require_human_actor(USER)`` 守卫 —— AI 无论如何无法自动关闭任务（红线③）。
        - ``GovernanceClosureReport`` 强制 ``human_result`` 由人工填写、
          ``closed_by`` 必须是真实人工标识、``source_trace`` 必须可溯源，
          否则拒绝生成（红线⑥）。
        - 本方法绝不把 AI 动作伪造为人工闭环决策（红线⑥，
          ``record_human_approval`` 始终被结构性拦截）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_CLOSURE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.8.22：企业智能体治理知识与持续改进层（任务6，+3 类）
    # ------------------------------------------------------------------

    def record_agent_governance_case_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "record_governance_case_from_human_closure",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理案例沉淀」事实动作（actor 真实，红线③/⑤/⑥）。

        本方法仅如实记录「某条**已由真实人工闭环**的治理任务被沉淀为治理案例」
        这一事实事件，绝不代表任何批准 / 处置 / 责任承担。

        - ``GovernanceCase.__post_init__`` 强制 ``source_task_id`` /
          ``problem_pattern`` / ``human_resolution`` / ``resolved_by`` 非空，且
          ``resolved_by`` 必须是真实人工标识（命中 ai / system / bot / agent /
          auto / 机器人 / 自动 等即拒绝，红线⑥）。
        - ``GovernanceImprovementWorkflowService._assert_human_closed_task``
          在沉案例前强制校验来源治理任务已处于 ``completed`` 且 ``closed_by``
          为真实人工 —— AI 无法借沉淀之名把未闭环任务标为已了结（红线⑤）。
        - ``problem_pattern`` / ``human_resolution`` 均经
          ``_reject_governance_markers`` 语义拦截：命中自动改 Agent
          （auto_modify_agent / auto_update_agent，红线③）、自动改策略
          （auto_update_policy / auto_apply_policy，红线④）、自动关任务
          （auto_close_task，红线⑤）语义即拒绝落库。
        - 本方法绝不把 AI 动作伪造为人工治理结论（红线⑥，
          ``record_human_approval`` 始终被结构性拦截）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_CASE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_knowledge_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "generate_governance_knowledge_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识候选 / 模式归纳 / 知识报告」事实动作（红线③/④/⑥）。

        本方法仅如实记录「AI 从已闭环案例中归纳出某条**候选**知识 / 某个事实
        模式」或「某次只读知识报告被汇编」这一事实事件。

        - ``GovernanceKnowledgeCandidate`` 在结构上只能是候选态：
          ``requires_human_review`` 恒为 ``True``，构造期 ``status`` 只能是
          ``candidate``，``reviewed_by`` / ``reviewed_at`` 必须为空 —— AI 产出
          绝不可能直接成为已生效知识或治理策略（红线④）。
        - ``GovernanceKnowledgeType`` / ``GovernancePatternKind`` 中**不存在**
          policy 类枚举，``GovernancePattern.is_policy`` 恒为 ``False``；模式只
          做事实归纳，不构成任何策略（红线④）。
        - 当 ``generated_by`` 为非人类主体时，``content`` 额外经
          ``_ADVICE_MARKERS`` 拦截：命中「建议 / 应当 / 必须整改 / recommend /
          should」等指令性语义即拒绝，AI 不得以知识之名下达治理指令（红线③/⑥）。
        - ``GovernanceKnowledgeReport`` 的经验段只收 ``accepted`` 候选，混入未
          经人工审核的候选即拒绝生成（红线⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_improvement_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "human_start_knowledge_review",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「持续改进人工审核」事实动作（actor 真实，红线④/⑥）。

        本方法仅如实记录「某真实人工开始审核 / 采纳 / 驳回某条治理知识候选」
        这一事实事件。

        - ``GovernanceImprovementStage`` 的推进只允许
          ``case_created → candidate_generated → human_review →
          accepted/rejected``，且**不存在** AI 终态；``start_human_review`` /
          ``accept_candidate`` / ``reject_candidate`` 三个入口全部由
          ``require_human_actor(USER)`` 守卫 —— AI 无论如何无法自行完成审核
          （红线⑥）。
        - 采纳 / 驳回必须附人工 ``review_comment``，且该结论文本同样经
          ``_reject_governance_markers`` 拦截，不得挟带自动改 Agent（红线③）、
          自动改策略（红线④）、自动关任务（红线⑤）语义。
        - 知识被人工采纳后，仅进入知识资产层供人查阅，**不会**自动转成治理策略、
          不会自动修改任何 Agent、不会自动关闭任何治理任务（红线③/④/⑤）。
        - 本方法绝不把 AI 动作伪造为人工审核结论（红线⑥，
          ``record_human_approval`` 始终被结构性拦截）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_IMPROVEMENT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_knowledge_query_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "submit_governance_knowledge_query",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识检索请求提交」事实动作（AI 可发起，纯只读，红线③/④/⑤/⑥）。

        本方法仅如实记录「某（人类/AI）发起了一个治理知识检索请求」这一事实事件。
        它**不**承载任何批准/审批语义、不承载「自动修改治理知识」「自动应用治理经验」
        「自动生成治理策略」语义；``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE_QUERY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_knowledge_retrieval_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "retrieve_governance_knowledge",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识只读相似检索执行」事实动作（AI 可发起，纯只读，红线③/④/⑤/⑥）。

        本方法仅如实记录「针对某检索请求执行了一次只读相似检索（仅摆候选、摆来源）」
        这一事实事件。检索结果恒为候选态（``requires_human_use=True``），本方法绝不
        承载「自动应用经验」「自动采纳知识」「自动生成策略」语义（红线④/⑤），
        ``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_assistance_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "build_governance_assistance_report",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理辅助报告生成」事实动作（AI 可发起，纯只读，红线⑥）。

        本方法仅如实记录「针对某检索请求生成了一份事实型辅助报告（不含任何建议/
        处置/责任判定）」这一事实事件。报告 ``contains_recommendation`` 恒为 False，
        本方法绝不承载「代替治理责任人」「自动生成策略」「自动应用经验」语义
        （红线④/⑤/⑥），``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_ASSISTANCE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_assistant_query_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "submit_assistant_query",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识助手问题提交」事实动作（AI 可发起，纯只读，红线③/④/⑤/⑥）。

        本方法仅如实记录「某（人类/AI）提交了一个治理知识助手问题」这一事实事件。
        它**不**承载任何批准/审批语义、不承载「自动修改治理知识」「自动应用治理经验」
        「自动生成治理策略」语义；``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_QUERY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_assistant_context_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "retrieve_assistant_context",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识助手只读检索上下文构建」事实动作（AI 可发起，纯只读，红线③/④/⑤/⑥）。

        本方法仅如实记录「针对某问题执行了一次只读相似检索并攒出辅助上下文」这一事实。
        上下文恒为候选态（``requires_human_use=True``），本方法绝不承载「自动应用经验」
        「自动采纳知识」「自动生成策略」语义（红线④/⑤），
        ``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_CONTEXT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_assistant_draft_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "build_assistant_answer_draft",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理知识助手纯事实答案草稿生成」事实动作（AI 可发起，纯事实，红线⑥）。

        本方法仅如实记录「针对某上下文生成了一份事实型答案草稿（不含任何建议/
        处置/责任判定/策略）」这一事实事件。草稿 ``contains_recommendation`` 恒为 False，
        本方法绝不承载「代替治理责任人确认答案」「自动生成策略」「自动应用经验」语义
        （红线④/⑤/⑥），``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_DRAFT,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.8.25：企业智能体治理工作流编排层（3 类事实型审计）
    # ------------------------------------------------------------------

    def record_agent_governance_workflow_create_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_governance_workflow_candidate",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理工作流线索登记 / 送入人工研判队列」事实动作（AI 可发起，红线③）。

        本方法仅如实记录「某条上游治理事实被登记为候选工作流」或「候选工作流被推送到
        人工研判队列」这一事实事件。候选工作流恒为 ``created`` 态、``requires_human_
        confirmation`` 恒为 True，本方法绝不承载「自动审批」「自动治理」「自动关闭问题」
        语义（红线③/④/⑥），``record_human_approval`` 始终被结构性拦截（红线②/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_workflow_review_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "human_confirm_governance_workflow",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理工作流人工研判」事实动作（**只应由真实 USER 触发**，红线⑥）。

        调用方（``GovernanceWorkflowOrchestrator.human_confirm``）已在业务层强制
        ``require_human_actor(USER)``，本方法仅如实登记「谁在何时给出了什么研判结论」。
        本方法**不是** ``record_human_approval``（后者被结构性拦截）：它记录的是研判
        事实本身，不代表任何工程批准，也不得被 AI 用来伪装人工确认（红线②/③/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_workflow_execution_action(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "human_track_governance_execution",
        target: str = "",
        detail: str = "",
        ts: str = "",
        actor_kind: "AuditActorKind | None" = None,
    ) -> AuditRecord:
        """记录一次「治理执行跟踪 / 结果归档」事实动作（**只应由真实 USER 触发**，红线④）。

        调用方在业务层强制 ``require_human_actor(USER)``，且
        ``GovernanceExecutionRecord.actor_kind`` 必须为 ``user``。本方法仅如实登记
        「真实人工执行了什么治理动作、结果如何」，绝不承载「AI 自动执行治理动作」
        「自动应用治理知识」「自动关闭问题」语义（红线③/④/⑥）。
        """
        return self._append(
            record_id=record_id,
            actor_kind=actor_kind or AuditActorKind.AI,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def query(
        self,
        *,
        actor_kind: Any = None,
        category: Any = None,
        target: str = "",
    ) -> list[AuditRecord]:
        """按条件查询审计记录（只读；跨域由 org_id 作用域过滤）。

        Phase 3.8.1：新增 ``category`` 过滤（可查 PERMISSION 类记录）。
        """
        out: list[AuditRecord] = []
        for r in self._records:
            if r.org_id != self._org_id:
                continue
            if actor_kind is not None and r.actor_kind != actor_kind:
                continue
            if category is not None and r.category != category:
                continue
            if target and r.target != target:
                continue
            out.append(r)
        return out

    # ---- Phase 3.8.26（Task 5 / Task 7）：治理工作流审计（复用而非重建）----
    # 仅如实记录真实人工的「登记 / 研判 / 执行跟踪 / 查看」事实动作；
    # 绝不提供 record_human_approval（红线⑥），绝不承载批准/报价/审批语义（红线②/④）。

    def record_agent_governance_workflow_create(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "create_workflow",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次治理工作流登记（actor_kind 恒为 USER——由真实人工上报/创建）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_workflow_review(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "confirm_review",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工研判确认（actor_kind 恒为 USER，红线③/④/⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_workflow_execution(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "submit_result",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工执行/结果提交（actor_kind 恒为 USER，红线⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_agent_governance_workflow_view(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "view_workflow",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看治理工作流（Task 7 新增 VIEW 审计大类，红线⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_VIEW,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.8.30（Task 6）：治理全链路追踪与统一审计智能层审计入口
    #
    # 三个方法均**强制** actor_kind = USER（actor 真实，红线⑥），仅如实记录人工
    # 发起的只读事实动作；不提供任何「AI 自动写审计」入口，也绝不提供
    # ``record_human_approval``（已被 ``_FORBIDDEN`` 于 mixin 层拦截，红线②/⑥）。
    # ------------------------------------------------------------------

    def record_governance_trace(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "register_trace",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工发起的治理链路追踪登记/查看（红线③/④/⑥）。

        仅承载「哪条治理事实由谁在何时被串联/查看」这一客观事实；不承载治理结论、
        不承载事件关闭、不代替审计责任人。
        """

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.GOVERNANCE_TRACE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_governance_timeline(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "view_timeline",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看统一审计时间线（只读，红线③/④/⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.GOVERNANCE_TIMELINE,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_governance_replay(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "view_replay",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看治理事实重放视图（只读重建，红线③/④/⑤/⑥）。

        「重放」仅指按时间序**重建既有事实**供人工复核，绝不重新执行任何治理动作。
        """

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.GOVERNANCE_REPLAY,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    # ------------------------------------------------------------------
    # Phase 3.9.0（T7）：生产就绪与受控激活准备层审计入口
    #
    # 三个方法均**强制** actor_kind = USER（actor 真实，红线⑥），仅如实记录人工
    # 发起的只读事实动作；不提供任何「AI 自动写审计」入口，也绝不提供
    # ``record_human_approval``（已被 ``_FORBIDDEN`` 于 mixin 层拦截，红线②/⑥）。
    # ------------------------------------------------------------------

    def record_production_readiness_check(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "review_readiness_checklist",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看/登记生产就绪检查（只读，红线①/③/⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.PRODUCTION_READINESS_CHECK,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_deployment_manifest(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "review_deployment_manifest",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看/登记部署清单（只读，禁止写真实密钥，红线②/⑤/⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.DEPLOYMENT_MANIFEST,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def record_rollback_plan(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str = "review_rollback_plan",
        target: str = "",
        detail: str = "",
        ts: str = "",
    ) -> AuditRecord:
        """记录一次真实人工查看/登记回滚计划（只读，红线③/⑤/⑥）。"""

        return self._append(
            record_id=record_id,
            actor_kind=AuditActorKind.USER,
            actor_id=actor_id,
            category=AuditActionCategory.ROLLBACK_PLAN,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )

    def _append(
        self,
        *,
        record_id: str,
        actor_kind: AuditActorKind,
        actor_id: str,
        category: AuditActionCategory,
        action: str,
        target: str,
        detail: str,
        ts: str,
    ) -> AuditRecord:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下写入审计（红线①/⑤）"
            )
        rec = AuditRecord(
            record_id=record_id,
            org_id=self._org_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            category=category,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
        )
        self._records.append(rec)
        return rec


__all__ = [
    "AuditActorKind",
    "AuditActionCategory",
    "AuditRecord",
    "AuditService",
    "require_human_actor",
]

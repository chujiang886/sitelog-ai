"""Enterprise Operation Layer —— 聚合服务入口（Phase 3.8.0 + 3.8.1 增强）。

``EnterpriseOperationLayer`` 把身份/组织/项目/文件/审计五类能力，以及 Phase 3.8.1 新增的
资源权限 / 专家权限隔离 / 审核职责分离能力，聚合为一个组织作用域内的运营层门面。

所有构造/写路径统一断言 ``safety_invariants_ok()``（红线①/⑤），并以 ``org_id`` 作用域隔离。

红线总闸：
- ① 不开 engineering_enabled（构造即断言）。
- ② 不输出 engineering_approved（各子服务不含该动作）。
- ③ 不自动报价（各子服务不含 quote/pricing）。
- ④ 不自动审批（各子服务不含 approve/sign/authorize）。
- ⑤ 不绕过 UnifiedActivationGate（以 safety_invariants_ok 作为统一前置护栏）。
- ⑥ 不 AI 代责（审计服务禁止 record_human_approval）。
"""

from __future__ import annotations

from agents.enterprise.audit import AuditService
from agents.enterprise.comment import CommentService
from agents.enterprise.expert_access import ExpertAccessService
from agents.enterprise.file_asset import FileAssetService
from agents.enterprise.identity import IdentityService
from agents.enterprise.notification import NotificationService
from agents.enterprise.organization import OrganizationService
from agents.enterprise.project import ProjectService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.review_permission import ReviewPermissionService
from agents.enterprise.resource_permission import ResourcePermissionService
from agents.enterprise.task import TaskService
from agents.enterprise.task_workflow import TaskWorkflowService
from agents.enterprise.workflow_metrics import WorkflowMetricsService
from agents.enterprise.workflow_sla import WorkflowSLAService
from agents.enterprise.workflow_template import WorkflowTemplateService
from agents.enterprise.workflow_trigger import WorkflowTriggerService
from agents.enterprise.workflow_version import WorkflowVersionService
from agents.enterprise.operation_metric import OperationMetricService
from agents.enterprise.project_analytics import ProjectAnalyticsService
from agents.enterprise.workflow_analytics import WorkflowAnalyticsService
from agents.enterprise.ai_usage_analytics import AIUsageAnalyticsService
from agents.enterprise.operation_risk import OperationRiskDetector
from agents.enterprise.dashboard import (
    Dashboard,
    DashboardService,
    DashboardWidget,
    WidgetType,
)
from agents.enterprise.dashboard_views import (
    AIDashboard,
    ProjectDashboard,
    RiskDashboard,
    WorkflowDashboard,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.data_insight import DataInsightService
from agents.enterprise.trend_analysis import TrendAnalyzer
from agents.enterprise.anomaly_detection import AnomalyDetector
from agents.enterprise.management_report import ManagementReportService
from agents.enterprise.feedback import FeedbackService
from agents.enterprise.insight_validation import InsightValidationService
from agents.enterprise.knowledge_candidate import KnowledgeUpdateCandidateService
from agents.enterprise.knowledge_improvement_workflow import KnowledgeImprovementWorkflow
from agents.enterprise.knowledge_version import KnowledgeLifecycleService
from agents.enterprise.knowledge_change_review import KnowledgeChangeReviewService
from agents.enterprise.knowledge_conflict import KnowledgeConflictService
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.knowledge_retrieval import (
    KnowledgeItem,
    KnowledgeRetrievalEngine,
)
from agents.enterprise.knowledge_context import KnowledgeContext, KnowledgeTrace
from agents.enterprise.knowledge_search import (
    KnowledgeSearchQuery,
    KnowledgeSearchService,
)
from agents.enterprise.knowledge_answer import (
    KnowledgeAnswerDraft,
    KnowledgeAnswerService,
)
from agents.enterprise.knowledge_recommendation import (
    KnowledgeRecommendationCandidate,
    KnowledgeRecommendationService,
)
from agents.enterprise.knowledge_query_agent import (
    KnowledgeQuery,
    KnowledgeQueryAgent,
)
from agents.enterprise.knowledge_retrieval_agent import KnowledgeRetrievalAgent
from agents.enterprise.knowledge_validation_agent import (
    KnowledgeAgentValidationResult,
    KnowledgeValidationAgent,
)
from agents.enterprise.knowledge_answer_agent import KnowledgeAnswerAgent
from agents.enterprise.knowledge_agent_orchestrator import (
    KnowledgeAgentEvent,
    KnowledgeAgentOrchestrator,
)
from agents.enterprise.knowledge_answer_review import (
    KnowledgeAnswerReview,
    KnowledgeAnswerReviewRecord,
)
from agents.enterprise.knowledge_conversation import (
    ConversationStatus,
    KnowledgeConversation,
    KnowledgeConversationService,
)
from agents.enterprise.knowledge_message import (
    MessageRole,
    KnowledgeMessage,
    KnowledgeMessageService,
)
from agents.enterprise.knowledge_conversation_context import (
    KnowledgeConversationContext,
    KnowledgeConversationContextService,
)
from agents.enterprise.knowledge_memory_policy import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryPolicyService,
)
from agents.enterprise.knowledge_task import (
    KnowledgeTask,
    KnowledgeTaskService,
    KnowledgeTaskStatus,
)
from agents.enterprise.knowledge_task_planner import (
    GoalAnalysis,
    KnowledgeTaskPlanner,
    SubTaskSpec,
    TaskPlan,
)
from agents.enterprise.knowledge_subtask import (
    KnowledgeSubTask,
    KnowledgeSubTaskService,
    KnowledgeSubTaskStatus,
    KnowledgeSubTaskType,
)
from agents.enterprise.knowledge_task_orchestrator import (
    KnowledgeTaskOrchestrator,
    KnowledgeTaskWorkflowEvent,
)
from agents.enterprise.task_review_checkpoint import TaskReviewCheckpoint
from agents.enterprise.agent_registry import AgentRegistry, AgentStatus
from agents.enterprise.agent_capability import AgentCapability
from agents.enterprise.agent_version import (
    AgentVersion,
    AgentVersionManager,
    AgentVersionStatus,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_lifecycle_service import AgentLifecycleService
from agents.enterprise.agent_observability import AgentObservabilityService
from agents.enterprise.agent_quality_governance import (
    AgentQualityGovernanceService,
)
from agents.enterprise.agent_cost_resource import (
    AgentResourceType,
    AgentCostType,
    AgentResourceUsage,
    AgentCostMetric,
    AgentCostAttribution,
    AgentResourceAnalyzer,
    AgentCostReport,
    AgentCostResourceService,
)
from agents.enterprise.agent_runtime_policy import (
    AgentRuntimePolicyStatus,
    RuntimeCheckOutcome,
    AgentRuntimePolicy,
    AgentToolAccessPolicy,
    RuntimeDecisionRecord,
    AgentExecutionGuard,
    AgentRuntimeGovernanceService,
)
from agents.enterprise.agent_security_risk import (
    AgentSecurityEventType,
    AgentSecuritySeverity,
    AgentRiskReviewStatus,
    SourceTrace,
    AgentSecurityEvent,
    AgentRiskCandidate,
    AgentRiskReview,
    AgentSecurityReport,
    AgentSecurityDetector,
    AgentSecurityRiskService,
)
from agents.enterprise.agent_compliance import (
    ComplianceRuleScope,
    ComplianceRuleStatus,
    ComplianceCheckResult,
    ComplianceReviewStatus,
    ComplianceRule,
    ComplianceCheck,
    ComplianceRiskCandidate,
    ComplianceReview,
    AgentComplianceReport,
    AgentComplianceDetector,
    AgentComplianceService,
)
from agents.enterprise.agent_governance_center import (
    GovernanceWidgetKind,
    GovernanceVisibility,
    GovernanceWidget,
    AgentGovernanceDashboard,
    AgentHealthOverview,
    RiskOverviewStatus,
    AgentRiskOverview,
    AgentGovernanceReport,
    GovernanceInsightKind,
    GovernanceTrendDirection,
    AgentGovernanceInsight,
    AgentGovernanceAggregator,
    AgentGovernanceCenterService,
)
from agents.enterprise.agent_governance_workflow import (
    GovernanceTaskSourceType,
    GovernanceTaskStatus,
    GovernanceTask,
    GovernanceAssignment,
    GovernanceActionRecord,
    GovernanceClosureReport,
    GovernanceWorkflowService,
)
from agents.enterprise.agent_governance_knowledge import (
    GovernanceCase,
    GovernancePatternKind,
    GovernancePattern,
    GovernanceKnowledgeType,
    GovernanceKnowledgeStatus,
    GovernanceKnowledgeCandidate,
    GovernanceKnowledgeReport,
    GovernanceImprovementStage,
    GovernanceImprovementWorkflowService,
)
from agents.enterprise.agent_governance_knowledge_retrieval import (
    GovernanceKnowledgeRetrievalService,
)
# Phase 3.8.24：企业智能体治理知识助手层（复用既有审计/身份/可见性/权限策略）。
from agents.enterprise.agent_governance_knowledge_assistant import (
    GovernanceAssistantAgent,
)
# Phase 3.8.25：企业智能体治理工作流编排层（复用 3.8.21 问责层 + 3.8.24 助手）。
from agents.enterprise.governance_workflow.orchestrator import (
    GovernanceWorkflowOrchestrator,
)
from agents.enterprise.governance_workflow.models import (
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    GovernanceWorkflow,
    WorkflowReviewDecision,
    GovernanceWorkflowReview,
    GovernanceExecutionRecord,
)
# Phase 3.8.26：企业智能体治理驾驶舱层（只读查询 + 单一人工确认入口）。
from agents.enterprise.governance_dashboard import (
    GovernanceDashboardService,
)
# Phase 3.8.30：企业智能体治理全链路追踪与统一审计智能层（**纯只读**，无任何治理状态写入口）。
from agents.enterprise.governance_traceability import (
    GovernanceTraceabilityService,
)


class EnterpriseOperationLayer:
    """企业运营层聚合门面（任务1–5 统一入口 + Phase 3.8.1 访问与权限智能）。"""

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 EnterpriseOperationLayer"
                "（红线①/⑤）。企业运营层只编排运营数据，绝不开启工程计算。"
            )
        self.org_id = org_id
        self.identity = IdentityService(org_id=org_id)
        self.organization = OrganizationService(org_id=org_id)
        self.projects = ProjectService(org_id=org_id)
        self.files = FileAssetService(org_id=org_id)
        self.audit = AuditService(org_id=org_id)
        # Phase 3.8.1：访问与权限智能层（共享同一审计实例，联动记录权限决策）
        self.resources = ResourcePermissionService(org_id=org_id, audit=self.audit)
        self.expert_access = ExpertAccessService(org_id=org_id, audit=self.audit)
        self.review = ReviewPermissionService(org_id=org_id, audit=self.audit)
        # Phase 3.8.2：企业协作与任务工作流层（共享同一审计实例，联动记录协作动作）
        self.tasks = TaskService(org_id=org_id, audit=self.audit)
        self.comments = CommentService(org_id=org_id, audit=self.audit)
        self.notifications = NotificationService(org_id=org_id, audit=self.audit)
        self.workflow = TaskWorkflowService(org_id=org_id, audit=self.audit)
        # Phase 3.8.3：企业流程模板与自动化层（共享同一审计实例）
        self.workflow_templates = WorkflowTemplateService(org_id=org_id, audit=self.audit)
        self.workflow_versions = WorkflowVersionService(org_id=org_id, audit=self.audit)
        self.workflow_triggers = WorkflowTriggerService(org_id=org_id, audit=self.audit)
        self.workflow_slas = WorkflowSLAService(org_id=org_id, audit=self.audit)
        self.workflow_metrics = WorkflowMetricsService(org_id=org_id, audit=self.audit)
        # Phase 3.8.4：企业运营分析与智能洞察层（共享同一审计实例）
        self.operation_metrics = OperationMetricService(org_id=org_id, audit=self.audit)
        self.project_analytics = ProjectAnalyticsService(
            org_id=org_id, audit=self.audit, project_service=self.projects
        )
        self.workflow_analytics = WorkflowAnalyticsService(
            org_id=org_id,
            audit=self.audit,
            metrics_service=self.workflow_metrics,
            sla_service=self.workflow_slas,
        )
        self.ai_usage_analytics = AIUsageAnalyticsService(org_id=org_id, audit=self.audit)
        self.operation_risk = OperationRiskDetector(org_id=org_id, audit=self.audit)
        # Phase 3.8.5：企业智能驾驶舱层（共享同一审计实例）
        self.dashboards = DashboardService(org_id=org_id, audit=self.audit)
        self.project_dashboard = ProjectDashboard(org_id=org_id)
        self.workflow_dashboard = WorkflowDashboard(org_id=org_id)
        self.ai_dashboard = AIDashboard(org_id=org_id)
        self.risk_dashboard = RiskDashboard(org_id=org_id)
        self.dashboard_visibility = AnalyticsVisibilityPolicy(org_id=org_id)
        # Phase 3.8.6：企业数据智能与决策辅助层（共享同一审计实例 + 身份 + 可见性策略）
        self.data_insights = DataInsightService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.trend_analysis = TrendAnalyzer(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.anomaly_detection = AnomalyDetector(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.management_reports = ManagementReportService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        # Phase 3.8.7：企业知识反馈与持续改进层（共享同一审计实例 + 身份 + 可见性策略）
        self.feedback = FeedbackService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.insight_validation = InsightValidationService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.knowledge_candidates = KnowledgeUpdateCandidateService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.knowledge_improvement = KnowledgeImprovementWorkflow(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
            feedback_service=self.feedback,
            candidate_service=self.knowledge_candidates,
            validation_service=self.insight_validation,
        )
        # Phase 3.8.8：企业知识治理与版本控制层（共享同一审计实例 + 身份 + 可见性策略）
        self.knowledge_versions = KnowledgeLifecycleService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.knowledge_change_reviews = KnowledgeChangeReviewService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        self.knowledge_conflicts = KnowledgeConflictService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.dashboard_visibility,
        )
        # Phase 3.8.9：企业知识智能检索与语义理解层（共享同一审计实例 + 身份 + 知识可见性策略）
        self.knowledge_visibility = KnowledgeVisibilityPolicy(org_id=org_id)
        self.knowledge_retrieval = KnowledgeRetrievalEngine(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_search = KnowledgeSearchService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            engine=self.knowledge_retrieval,
        )
        self.knowledge_answers = KnowledgeAnswerService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_recommendations = KnowledgeRecommendationService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        # Phase 3.8.10：企业知识智能体编排层（共享同一审计实例 + 身份 + 知识可见性策略）
        self.knowledge_query_agent = KnowledgeQueryAgent(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_retrieval_agent = KnowledgeRetrievalAgent(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_validation_agent = KnowledgeValidationAgent(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_answer_agent = KnowledgeAnswerAgent(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_agent_orchestrator = KnowledgeAgentOrchestrator(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_answer_review = KnowledgeAnswerReview(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        # Phase 3.8.11：企业知识对话上下文与记忆层（共享同一审计实例 + 身份 + 知识可见性策略）
        self.knowledge_conversations = KnowledgeConversationService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_messages = KnowledgeMessageService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            conversations=self.knowledge_conversations,
        )
        self.knowledge_conversation_context = KnowledgeConversationContextService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            conversations=self.knowledge_conversations,
        )
        self.knowledge_memory_policy = MemoryPolicyService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        # Phase 3.8.12：企业知识任务规划与多智能体工作流层（共享同一审计实例 + 身份 +
        # 知识可见性策略；编排器/检查点复用同一 task/subtask 服务实例，保证状态一致）。
        self.knowledge_task_planner = KnowledgeTaskPlanner(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_tasks = KnowledgeTaskService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_subtasks = KnowledgeSubTaskService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
        )
        self.knowledge_task_orchestrator = KnowledgeTaskOrchestrator(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            task_service=self.knowledge_tasks,
            subtask_service=self.knowledge_subtasks,
            planner=self.knowledge_task_planner,
        )
        self.task_review_checkpoint = TaskReviewCheckpoint(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            task_service=self.knowledge_tasks,
        )
        # Phase 3.8.13：企业智能体能力注册与治理层
        self.agent_permission_policy = AgentPermissionPolicy(
            org_id=org_id, identity=self.identity,
        )
        self.agent_registry = AgentLifecycleService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.14：企业智能体可观测性与性能智能层
        # 复用身份层 + AgentPermissionPolicy + 知识可见性策略做监控数据权限隔离；
        # 共享同一审计实例。本服务只观测，不评价/禁用/优化 Agent（红线③/④/⑥）。
        self.agent_observability = AgentObservabilityService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.15：企业智能体评估与质量治理层
        # 复用身份层 + AgentPermissionPolicy + 知识可见性策略做评价数据权限隔离；
        # 共享同一审计实例。本服务只治理事实（指标/评价/反馈/版本比较），不评价/禁用/
        # 修改/升级 Agent（红线③/④/⑤/⑥）。
        self.agent_quality_governance = AgentQualityGovernanceService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.16：企业智能体成本与资源智能层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做成本数据权限隔离；本服务只治理事实
        # （资源用量/成本指标/成本归属/成本报告），不关停/修改/优化 Agent（红线③/④/⑤/⑥）。
        self.agent_cost_resource = AgentCostResourceService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.17：企业智能体策略与运行时治理层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做策略/运行时核查数据权限隔离；
        # 本服务只登记/核查/记录事实（策略/工具访问/执行核查），禁 AI 自动批准 Agent
        # 运行、禁 AI 自动修改策略、禁 AI 自动放行工具访问、禁 AI 代替管理责任
        # （红线③/④/⑤/⑥）。ACTIVE 策略须人工确认（require_human_actor）。
        self.agent_runtime_governance = AgentRuntimeGovernanceService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.18：企业智能体安全与风险治理层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做安全数据权限隔离（默认拒绝）；
        # 本服务只登记事实（安全事件）、只发现疑点（风险候选）、只汇总报告，
        # 禁 AI 自动封禁 Agent、禁 AI 自动修改权限、禁 AI 自动处置安全风险、
        # 禁 AI 代替安全责任（红线③/④/⑤/⑥）。风险处置须真实 USER
        # （require_human_actor），风险候选 requires_human_review 恒为 True。
        self.agent_security_risk = AgentSecurityRiskService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.19：企业智能体合规与审计智能层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做合规数据权限隔离（默认拒绝），
        # 并只读消费 AgentRuntimeGovernanceService 的运行时判定事实（不改运行时策略）。
        # 本服务只登记规则、只做中性检查（pass/attention/not_applicable，无判罚态）、
        # 只发现合规风险候选、只汇总报告；禁 AI 自动判定违法违规、禁 AI 自动处罚
        # Agent、禁 AI 自动修改权限或策略、禁 AI 代替合规责任人（红线③/④/⑤/⑥）。
        # 规则生效/废止与风险整改须真实 USER（require_human_actor），
        # 风险候选 requires_human_review 恒为 True。
        self.agent_compliance = AgentComplianceService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            runtime_policy=self.agent_runtime_governance,
        )
        # Phase 3.8.20：企业智能体治理智能中枢层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做治理数据隔离（默认拒绝），
        # 并**纯只读**汇聚 3.8.14/15/16/18/19 五层治理事实（可观测性 / 质量 /
        # 成本 / 安全 / 合规）+ 只读消费 3.8.17 运行时治理服务。
        # 本服务只汇聚、只呈现、只陈述事实：看板只展示事实、健康总览禁止自动评级、
        # 风险总览禁止自动处理、治理报告强可溯源、治理洞察只有事实趋势与异常候选；
        # 禁 AI 自动控制 Agent（禁用/修改/升级/改策略）、禁 AI 自动处理风险、
        # 禁 AI 自动判定合规、禁 AI 代替治理责任人（红线③/④/⑤/⑥）。
        # 风险处置与洞察确认须真实 USER（require_human_actor），
        # 风险总览 requires_human_handling 恒为 True。
        self.agent_governance_center = AgentGovernanceCenterService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            runtime_policy=self.agent_runtime_governance,
            observability=self.agent_observability,
            quality=self.agent_quality_governance,
            cost=self.agent_cost_resource,
            security=self.agent_security_risk,
            compliance=self.agent_compliance,
        )
        # Phase 3.8.21：企业智能体治理流程与责任闭环层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做治理任务数据隔离（默认拒绝），
        # 并**纯只读**消费 3.8.17 运行时治理服务与 3.8.20 治理中枢事实。
        # 链路：治理发现 → 治理任务 → 责任人 → 人工处理 → 结果记录 → 治理闭环。
        # AI 只能创建 created 候选任务（构造期禁填 owner_id / completed_at）；
        # 禁 AI 自动整改风险（auto_remediate / auto_fix / auto_resolve）、
        # 禁 AI 自动分配责任、禁 AI 自动修改权限策略、禁 AI 代替治理责任人
        # （红线③/④/⑤/⑥）。责任分配 / 开始处理 / 提交结果 / 闭环确认四个节点
        # 全部强制 require_human_actor(USER)，任务 requires_human_completion 恒为 True。
        self.agent_governance_workflow = GovernanceWorkflowService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            runtime_policy=self.agent_runtime_governance,
            governance_center=self.agent_governance_center,
        )
        # Phase 3.8.22：企业智能体治理知识与持续改进层。复用同一审计实例、身份层、
        # 知识可见性策略与 AgentPermissionPolicy 做治理知识数据隔离（默认拒绝），
        # 并**纯只读**消费 3.8.21 治理流程服务的已闭环任务事实。
        # 链路：治理事件 → 人工处理 → 治理经验 → 知识候选 → 人工审核 → 知识沉淀。
        # AI 只能产出 candidate 候选知识（requires_human_review 恒 True、构造期
        # status 只能 candidate、reviewed_by/reviewed_at 必须为空）；
        # 禁 AI 自动修改 Agent（auto_modify_agent / auto_update_agent）、
        # 禁 AI 自动修改治理策略（auto_update_policy / auto_apply_policy）、
        # 禁 AI 自动关闭治理任务、禁 AI 代替治理责任人（红线③/④/⑤/⑥）。
        # 审核开始 / 采纳 / 驳回三个节点全部强制 require_human_actor(USER)。
        self.agent_governance_knowledge = GovernanceImprovementWorkflowService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            governance_workflow=self.agent_governance_workflow,
        )
        # Phase 3.8.23：企业智能体治理知识检索与辅助学习层。复用同一审计实例、
        # 身份层、知识可见性策略与 AgentPermissionPolicy 做治理知识数据隔离（默认
        # 拒绝）；并**纯只读**消费 3.8.22 治理知识层与 3.8.21 治理流程层的已沉淀
        # 事实（绝不修改任何知识、绝不推进任何治理任务）。链路：治理事件 → 历史
        # 案例检索 → 知识匹配 → 辅助分析 → 人工使用。AI 只能「检索事实 → 摆候选
        # → 摆来源」；禁 AI 自动改知识（auto_update_knowledge·auto_merge_knowledge）、
        # 禁 AI 自动应用治理经验（auto_apply_knowledge·auto_execute_knowledge）、
        # 禁 AI 自动生成治理策略（auto_generate_policy·generate_policy）、禁 AI
        # 代替治理责任人（红线③/④/⑤/⑥）。唯一人工终态 mark_human_used 强制
        # require_human_actor(USER)。
        self.agent_governance_knowledge_retrieval = GovernanceKnowledgeRetrievalService(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            knowledge_service=self.agent_governance_knowledge,
            governance_workflow=self.agent_governance_workflow,
        )
        # Phase 3.8.24：企业智能体治理知识助手层（任务1-5 统一入口）。复用同一审计实例、
        # 身份层、知识可见性策略与 AgentPermissionPolicy 做治理知识数据隔离（默认拒绝）；
        # 链路：治理问题 → 知识检索 → 事实候选 → 来源引用 → 事实摘要 → 人工审核。
        # AI 只摆事实/摆来源，禁自动改知识、禁自动生成策略、禁代替责任人（红线③/④/⑤/⑥）。
        self.agent_governance_knowledge_assistant = GovernanceAssistantAgent(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            knowledge_service=self.agent_governance_knowledge_retrieval,
            governance_workflow=self.agent_governance_workflow,
        )
        # Phase 3.8.25：企业智能体治理工作流编排层。复用 3.8.21 问责层服务与 3.8.24 助手，
        # 把「问题发现 → 事实辅助 → 人工研判 → 治理任务 → 执行跟踪 → 归档 → 审计」串成
        # 可追踪流水线。编排器自身 fail-closed：AI 仅能登记候选/推送研判队列，所有前进转移
        # 强制 require_human_actor(USER)，绝不自动审批/执行/关闭（红线③/④/⑤/⑥）。
        self.agent_governance_workflow_orchestrator = GovernanceWorkflowOrchestrator(
            org_id=org_id, audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
            governance_workflow=self.agent_governance_workflow,
            assistant=self.agent_governance_knowledge_assistant,
        )
        # Phase 3.8.26：企业智能体治理驾驶舱层。在编排层之上提供「只读查询 + 单一人工确认
        # 入口」的驾驶舱 API，供真实责任人查看/审核/确认/追踪/归档；默认拒绝 + 组织隔离 +
        # 强制 USER + 审计留痕，AI 无法越权（红线③/④/⑤/⑥）。
        self.agent_governance_dashboard = GovernanceDashboardService(
            org_id=org_id, orchestrator=self.agent_governance_workflow_orchestrator,
            audit=self.audit, identity=self.identity,
            visibility=self.knowledge_visibility,
            permission_policy=self.agent_permission_policy,
        )
        # Phase 3.8.30：企业智能体治理全链路追踪与统一审计智能层。在驾驶舱之上提供「纯只读」
        # 的事实串联与重建能力，回答审计责任人的三个问题：牵扯了哪些对象 / 按时间发生了什么 /
        # 能不能原样重看一遍。本层**没有任何治理状态写入口**，不修改任何被关联对象；三道闸门
        # （组织隔离 + 权限默认拒绝 + 强制 USER）+ 审计留痕 + 红线①（safety_invariants_ok），
        # 比驾驶舱更严格（红线③/④/⑤/⑥）。复用同一审计实例、身份层、AgentPermissionPolicy，
        # 以及 3.8.25 编排器（只读消费其事实，绝不回写）。
        self.agent_governance_traceability = GovernanceTraceabilityService(
            org_id=org_id,
            audit=self.audit,
            identity=self.identity,
            permission_policy=self.agent_permission_policy,
            orchestrator=self.agent_governance_workflow_orchestrator,
        )

    def is_activation_safe(self) -> bool:
        """对外暴露只读护栏状态（不得用于翻转 engineering_enabled）。"""
        return safety_invariants_ok()


__all__ = ["EnterpriseOperationLayer"]

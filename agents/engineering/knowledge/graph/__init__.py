"""Knowledge Graph Foundation（Phase 3.7.1）+ Query & Reasoning Layer（Phase 3.7.2）+ Case Knowledge Layer（Phase 3.7.3）+ Solution Generation Layer（Phase 3.7.4）+ Solution Constraint & Optimization Layer（Phase 3.7.5）+ Cost Intelligence Layer（Phase 3.7.6）+ Drawing Intelligence Layer（Phase 3.7.7）+ Workflow Orchestration Layer（Phase 3.7.8）+ Assistant Interface Layer（Phase 3.7.9）。

公开 API：
- 实体：``KnowledgeGraphEntityType`` / ``GraphNode`` / 七实体 dataclass（含 ``SolutionCandidateEntity`` / ``DesignCandidate``）；
- 关系：``KnowledgeGraphRelationType`` / ``RELATIONSHIP_SPECS``（17 类，含 4 类 solution_*）/ ``GraphEdge`` / ``validate_edge``；
- 仓库：``KnowledgeGraphRepository`` / ``GraphAuditLog`` / ``GraphAuditEvent``；
- 集成：``KnowledgeRepositoryToGraphSync``（Repository→Graph 单向）；
- 冲突：``KnowledgeGraphConflictDetector`` / ``GraphConflictReport``；
- 案例生命周期：``CaseLifecycleStage`` / ``CaseLifecycle`` / ``CaseLifecycleError``（Phase 3.7.3）；
- 推理：``KnowledgeGraphQueryEngine`` / ``KnowledgePathTrace`` / ``ThresholdImpactReport`` /
       ``ReasoningConflictCandidate`` / ``CaseSimilarityReport`` / ``CasePathReport`` /
       ``CaseImpactReport`` / ``CalcAgentCandidate``（只读层）；
- 方案生成：``SolutionGenerator`` / ``SolutionEvaluator`` / ``SolutionReviewQueue`` /
       ``SolutionRedLineViolationError`` / ``SolutionReviewError`` +
       报告载体（Phase 3.7.4，产出多候选、评价、人工审核）。
- 成本智能：``BOMEntity`` / ``CostRule``（独立数据壳，非图谱实体）+ ``CostEstimator`` /
       ``CostEstimateDraft`` / ``CostExplanation`` / ``CostExplanationReport`` /
       ``CostReviewQueue``（Phase 3.7.6，仅占位估算、禁止报价/成交价/伪造市场价、仅人工审核）。
- 图纸智能：``DesignCandidate`` 增强（source_files / geometry / opening_type / glass_config /
       profile_config / confidence / verification_status，全部默认占位，红线③/④）+ ``DrawingParser``
       （PDF/CAD/Image → 带 source_ref + confidence 占位的 DesignCandidate）+ ``VisionAdapter``
       （image_analysis / drawing_analysis → 只读分析壳，禁止工程结论）+ ``DesignReviewQueue``
       （parsed / reviewing / verified_by_human / rejected，仅人工可入 verified_by_human）+
       ``DesignGraphConnector``（只读关联 Solution / Case / KnowledgeItem / SourceRef，不写图、
       不新增关系到 17 白名单）（Phase 3.7.7）。
- 工作流编排：``EngineeringWorkflow``（workflow_id / input_source / stages / status / created_at /
       requires_human_review，非图谱节点、零回归）+ ``WorkflowStage`` / ``WorkflowEvent``（阶段追踪 +
       审计事件）+ ``EngineeringWorkflowEngine``（start_workflow / execute_stage / pause_for_review /
       resume_workflow，编排 DrawingParser / DesignReviewQueue / SolutionGenerator /
       SolutionConstraintEngine / CostEstimator，仅编排不改模块职责）+ ``HumanReviewCheckpoint``
       （drawing_verified / solution_reviewed / cost_reviewed，AI 不能自动通过，mark 仅 by_human=True
       可放行）       （Phase 3.7.8）。
- 助手交互层：``AssistantSession``（session_id / user_input / files / workflow_id / status /
       created_at，非图谱节点、零回归）+ ``WorkflowRequest``（direct_judgment 恒 False，红线③）
       + ``AssistantWorkflowBridge``（create_workflow / attach_files / query_status，仅桥接
       ``EngineeringWorkflowEngine``，不改职责）+ ``AssistantResponse``（workflow_status /
       candidate_results / review_required / source_trace，results_confirmed 恒 False，红线③）
       + ``HumanReviewPortal``（只读 view_drawing_review / view_solution_review /
       view_cost_review，submit_human_decision 强制 by_human=True，红线⑤）（Phase 3.7.9）。

红线：本包不写 verified.json、不开启 engineering_enabled、不输出 engineering_approved、
不 AI 代签/代授权、不自动 merge/delete/approve；Case/Rule/SolutionCandidate 为 pending_build 骨架；
案例生命周期仅人工驱动、AI 不自动推进；推理层全为只读；方案生成层产出候选但**不自动选终/不批准**
（``SolutionReviewQueue.approve`` 仅 ``by_human=True`` 可入），绝不编造真实工程参数；图纸智能层
**不自动确认图纸尺寸**（红线③）、**不自动生成真实工程参数**（红线④）、**不自动报价**（红线⑤），
仅产出占位解析/分析壳与人工审核队列（``DesignReviewQueue.verify`` 仅 ``by_human=True`` 可入
verified_by_human）。
"""

from __future__ import annotations

from agents.engineering.knowledge.graph.conflict import (
    CONFLICT_DANGLING_EDGE,
    CONFLICT_DUPLICATE_NODE,
    CONFLICT_PENDING_BUILD_EDGE,
    CONFLICT_TYPE_MISMATCH,
    GraphConflictReport,
    KnowledgeGraphConflictDetector,
)
from agents.engineering.knowledge.graph.entities import (
    CaseEntity,
    DesignCandidate,
    ExpertEntity,
    GraphNode,
    KnowledgeGraphEntityType,
    KnowledgeItemEntity,
    PENDING_VERIFICATION,
    RuleEntity,
    SourceRefEntity,
    SolutionCandidateEntity,
    SolutionConstraint,
    BOMEntity,
    CostRule,
    ThresholdEntity,
    entity_to_node,
)
from agents.engineering.knowledge.graph.integration import (
    KnowledgeRepositoryToGraphSync,
)
from agents.engineering.knowledge.graph.relationships import (
    GraphEdge,
    KnowledgeGraphRelationType,
    RELATIONSHIP_SPECS,
    RelationSpec,
    validate_edge,
)
from agents.engineering.knowledge.graph.repository import (
    DEFAULT_GRAPH_STORE_FILENAME,
    FORBIDDEN_GRAPH_EVENT_TYPES,
    GRAPH_AUDIT_EVENT_TYPES,
    GRAPH_SCHEMA_VERSION,
    GraphAuditEvent,
    GraphAuditLog,
    KnowledgeGraphRepository,
)
from agents.engineering.knowledge.graph.case_lifecycle import (
    CaseLifecycle,
    CaseLifecycleError,
    CaseLifecycleStage,
)
from agents.engineering.knowledge.graph.query import (
    CaseImpactReport,
    CasePathReport,
    CaseSimilarityReport,
    CalcAgentCandidate,
    KnowledgeGraphQueryEngine,
    KnowledgePathTrace,
    ReasoningConflictCandidate,
    RedLineViolationError,
    ThresholdImpactReport,
)
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionCompatibilityReport,
    SolutionEvaluator,
    SolutionGenerator,
    SolutionRedLineViolationError,
    SolutionReviewError,
    SolutionReviewQueue,
    SolutionRiskReport,
    SolutionTraceReport,
)
from agents.engineering.knowledge.graph.solution_constraint import (
    SolutionComparison,
    SolutionComparisonReport,
    SolutionConstraintEngine,
    SolutionConstraintReport,
    SolutionExplanation,
    SolutionExplanationReport,
)
from agents.engineering.knowledge.graph.solution_cost import (
    CostEstimateDraft,
    CostEstimator,
    CostExplanation,
    CostExplanationReport,
    CostReviewItem,
    CostReviewQueue,
)
from agents.engineering.knowledge.graph.solution_drawing import (
    DesignGraphConnector,
    DesignKnowledgeLinkReport,
    DesignReviewItem,
    DesignReviewQueue,
    DrawingParser,
    ParsedDesignDraft,
    VisionAdapter,
    VisionAnalysisReport,
)
from agents.engineering.knowledge.graph.solution_workflow import (
    EngineeringWorkflow,
    EngineeringWorkflowEngine,
    HumanReviewCheckpoint,
    SolutionRedLineViolationError,
    WorkflowEvent,
    WorkflowStage,
)
from agents.engineering.knowledge.graph.solution_assistant import (
    AssistantResponse,
    AssistantSession,
    AssistantWorkflowBridge,
    HumanReviewPortal,
    WorkflowRequest,
)

__all__ = [
    "KnowledgeGraphEntityType",
    "GraphNode",
    "KnowledgeItemEntity",
    "ThresholdEntity",
    "ExpertEntity",
    "SourceRefEntity",
    "CaseEntity",
    "RuleEntity",
    "SolutionCandidateEntity",
    "DesignCandidate",
    "PENDING_VERIFICATION",
    "entity_to_node",
    "KnowledgeGraphRelationType",
    "RelationSpec",
    "RELATIONSHIP_SPECS",
    "GraphEdge",
    "validate_edge",
    "GRAPH_SCHEMA_VERSION",
    "DEFAULT_GRAPH_STORE_FILENAME",
    "GRAPH_AUDIT_EVENT_TYPES",
    "FORBIDDEN_GRAPH_EVENT_TYPES",
    "GraphAuditEvent",
    "GraphAuditLog",
    "KnowledgeGraphRepository",
    "KnowledgeRepositoryToGraphSync",
    "KnowledgeGraphConflictDetector",
    "GraphConflictReport",
    "CONFLICT_DUPLICATE_NODE",
    "CONFLICT_DANGLING_EDGE",
    "CONFLICT_PENDING_BUILD_EDGE",
    "CONFLICT_TYPE_MISMATCH",
    "CaseLifecycleStage",
    "CaseLifecycle",
    "CaseLifecycleError",
    "KnowledgeGraphQueryEngine",
    "KnowledgePathTrace",
    "ThresholdImpactReport",
    "ReasoningConflictCandidate",
    "CaseSimilarityReport",
    "CasePathReport",
    "CaseImpactReport",
    "CalcAgentCandidate",
    "RedLineViolationError",
    "SolutionGenerator",
    "SolutionEvaluator",
    "SolutionReviewQueue",
    "SolutionRedLineViolationError",
    "SolutionReviewError",
    "SolutionCompatibilityReport",
    "SolutionRiskReport",
    "SolutionTraceReport",
    "SolutionConstraint",
    "SolutionConstraintEngine",
    "SolutionConstraintReport",
    "SolutionComparison",
    "SolutionComparisonReport",
    "SolutionExplanation",
    "SolutionExplanationReport",
    "BOMEntity",
    "CostRule",
    "CostEstimator",
    "CostEstimateDraft",
    "CostExplanation",
    "CostExplanationReport",
    "CostReviewQueue",
    "CostReviewItem",
    "DrawingParser",
    "ParsedDesignDraft",
    "VisionAdapter",
    "VisionAnalysisReport",
    "DesignReviewQueue",
    "DesignReviewItem",
    "DesignGraphConnector",
    "DesignKnowledgeLinkReport",
    "EngineeringWorkflow",
    "WorkflowStage",
    "WorkflowEvent",
    "HumanReviewCheckpoint",
    "EngineeringWorkflowEngine",
    "AssistantSession",
    "WorkflowRequest",
    "AssistantWorkflowBridge",
    "AssistantResponse",
    "HumanReviewPortal",
    "SolutionRedLineViolationError",
]

"""Phase 3.8.30 企业智能体治理全链路追踪与统一审计智能层（包入口）。

本包是**纯只读**的治理事实串联与重建层，对外只暴露：

- 模型：``GovernanceTrace`` / ``GovernanceTraceLink``（任务1/2）、
  ``GovernanceAuditTimeline``（任务3）、``GovernanceReplayView``（任务4）、
  ``GovernanceTraceReport`` + ``SourceTrace``（任务5）；
- 服务：``GovernanceTraceabilityService``（任务3/4/5/7 执行体）；
- 结构级禁名集：``_TRACEABILITY_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何写治理状态的能力——因为它根本不存在（红线③/④/⑤/⑥）。
"""

from agents.enterprise.governance_traceability.forbidden import (
    _TRACEABILITY_EXTRA_FORBIDDEN,
    _TRACEABILITY_FORBIDDEN,
    TRACEABILITY_FORBIDDEN_COUNT,
)
from agents.enterprise.governance_traceability.models import (
    _AUDIT_MUTATION_MARKERS,
    _CONCLUSION_MARKERS,
    _FORBIDDEN_TRACE_FIELDS,
    _INCIDENT_CLOSURE_MARKERS,
    AuditViewer,
    GovernanceAuditTimeline,
    GovernanceAuditTimelineEntry,
    GovernanceReplayStep,
    GovernanceReplayView,
    GovernanceTrace,
    GovernanceTraceLink,
    GovernanceTraceLinkKind,
    GovernanceTraceReport,
    GovernanceTraceSourceType,
    SourceTrace,
    _reject_traceability_markers,
)
from agents.enterprise.governance_traceability.service import (
    GovernanceTraceabilityError,
    GovernanceTraceabilityService,
)

__all__ = [
    # 任务7：审计查看者载体
    "AuditViewer",
    # 任务1/2：链路与关联
    "GovernanceTraceSourceType",
    "GovernanceTrace",
    "GovernanceTraceLinkKind",
    "GovernanceTraceLink",
    # 任务3：统一审计时间线
    "GovernanceAuditTimelineEntry",
    "GovernanceAuditTimeline",
    # 任务4：事实重放
    "GovernanceReplayStep",
    "GovernanceReplayView",
    # 任务5：来源链报告
    "SourceTrace",
    "GovernanceTraceReport",
    # 任务3/4/5/7：服务
    "GovernanceTraceabilityService",
    "GovernanceTraceabilityError",
    # 红线取证
    "_TRACEABILITY_FORBIDDEN",
    "_TRACEABILITY_EXTRA_FORBIDDEN",
    "TRACEABILITY_FORBIDDEN_COUNT",
    "_AUDIT_MUTATION_MARKERS",
    "_CONCLUSION_MARKERS",
    "_INCIDENT_CLOSURE_MARKERS",
    "_FORBIDDEN_TRACE_FIELDS",
    "_reject_traceability_markers",
]

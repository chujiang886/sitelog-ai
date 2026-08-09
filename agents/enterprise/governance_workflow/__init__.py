"""Phase 3.8.25 企业智能体治理工作流编排层（Governance Workflow Orchestration）。

链路：**问题发现 → 事实辅助分析 → 人工研判 → 治理任务创建 → 执行跟踪 →
结果归档 → 审计闭环**。

包内分工：
- ``models``：六态编排状态机 + 工作流 / 人工确认 / 执行跟踪三个模型；
- ``forbidden``：结构级禁名（3.8.21 问责层 98 项 ∪ 本层编排专属新增）；
- ``orchestrator``：``GovernanceWorkflowOrchestrator`` 编排服务（**唯一真实实现**、
  唯一写入口）；
- ``service``：Phase 3.8.27 起降级为**向后兼容再导出垫片**（不含任何实现）。

.. note:: Phase 3.8.27 治理基础设施收敛层

   3.8.25 曾在 ``orchestrator.py`` 与 ``service.py`` 各写一份同名
   ``GovernanceWorkflowOrchestrator``，导致同一个类名在不同 import 路径上解析为两个
   不同的类对象。3.8.27 已把两份合并到 ``orchestrator.py``，本包一律从
   ``orchestrator`` 再导出。

复用声明（**不重建轮子**）：Phase 3.8.21 ``agent_governance_workflow`` 已建成
治理**问责层**（``GovernanceTask`` / ``GovernanceAssignment`` /
``GovernanceActionRecord`` / ``GovernanceClosureReport``）。本层为治理**编排层**，
在其之上增量补齐「六态编排状态机 + 人工研判节点 + 执行跟踪」，并原样再导出
3.8.21 的问责原语，便于上层一处引入、两层协作。

最高红线（fail-closed，AI 不可破）：
① ``engineering_enabled`` 恒为 False；② 禁输出 ``engineering_approved``；
③ 禁 AI 自动治理 / 自动审批 / 自动关闭问题；④ 禁 AI 自动执行治理动作 /
自动应用治理知识；⑤ 禁 AI 自动生成治理策略；⑥ 禁 AI 代替治理责任人
（所有人工节点强制 ``require_human_actor(USER)``）。
"""

from __future__ import annotations

# --- Phase 3.8.21 问责层原语（复用再导出，不重建） ---
from agents.enterprise.agent_governance_workflow import (
    GovernanceAssignment,
    GovernanceTask,
    GovernanceTaskSourceType,
    GovernanceTaskStatus,
    GovernanceWorkflowService,
)

# --- Phase 3.8.25 编排层新增 ---
from agents.enterprise.governance_workflow.forbidden import (
    _ORCHESTRATION_FORBIDDEN,
    _WORKFLOW_FORBIDDEN,
)
from agents.enterprise.governance_workflow.models import (
    _ALLOWED_WORKFLOW_TRANSITIONS,
    _FORBIDDEN_STATUS_NAMES,
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
)
from agents.enterprise.governance_workflow.orchestrator import (
    GovernanceWorkflowAccessDenied,
    GovernanceWorkflowOrchestrator,
)

__all__ = [
    # Phase 3.8.25 编排层
    "GovernanceWorkflow",
    "GovernanceWorkflowStatus",
    "GovernanceWorkflowSourceType",
    "GovernanceWorkflowReview",
    "WorkflowReviewDecision",
    "GovernanceExecutionRecord",
    "GovernanceWorkflowOrchestrator",
    "GovernanceWorkflowAccessDenied",
    "_ALLOWED_WORKFLOW_TRANSITIONS",
    "_FORBIDDEN_STATUS_NAMES",
    "_WORKFLOW_FORBIDDEN",
    "_ORCHESTRATION_FORBIDDEN",
    # Phase 3.8.21 问责层（复用再导出）
    "GovernanceTask",
    "GovernanceTaskStatus",
    "GovernanceTaskSourceType",
    "GovernanceAssignment",
    "GovernanceWorkflowService",
]

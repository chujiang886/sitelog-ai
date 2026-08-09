"""Phase 3.8.25 治理工作流编排服务 —— **向后兼容再导出垫片（无实现）**。

.. warning:: 本模块自 Phase 3.8.27 起**不再包含任何实现**。

   历史背景（架构债）：Phase 3.8.25 曾在 ``orchestrator.py`` 与本文件各写一份同名
   ``GovernanceWorkflowOrchestrator``：

   - ``orchestrator.py``（570 行）被生产装配层 ``agents/enterprise/service.py``、
     驾驶舱 ``governance_dashboard/service.py`` 与 FastAPI
     ``backend/app/api/governance_dashboard.py`` 使用；
   - ``service.py``（913 行）被本包 ``__init__`` 再导出，进而被
     ``agents/enterprise/__init__.py`` 与另一套测试使用。

   于是 ``from agents.enterprise.governance_workflow import
   GovernanceWorkflowOrchestrator`` 与 ``from
   agents.enterprise.governance_workflow.orchestrator import
   GovernanceWorkflowOrchestrator`` 会解析出**两个不同的类对象**：红线守卫、六态
   状态机语义、审计口径、存储模型全部各写一遍，任一侧修补都无法保证另一侧同步 ——
   这对一个以 fail-closed 红线为生命线的治理平台是不可接受的结构性风险。

   Phase 3.8.27 治理基础设施收敛层已将两份实现合并至
   :mod:`agents.enterprise.governance_workflow.orchestrator`（**唯一真实实现**），
   合并原则**取严不取宽**：任一侧更严格的守卫全部保留，任一侧更宽松的默认值全部
   收紧。本文件仅保留 import 路径以免破坏既有调用方，**不得**在此新增任何实现；
   新代码请直接从 :mod:`agents.enterprise.governance_workflow` 或
   :mod:`agents.enterprise.governance_workflow.orchestrator` 导入。
"""

from __future__ import annotations

from agents.enterprise.governance_workflow.orchestrator import (
    GovernanceWorkflowAccessDenied,
    GovernanceWorkflowOrchestrator,
)

__all__ = [
    "GovernanceWorkflowOrchestrator",
    "GovernanceWorkflowAccessDenied",
]

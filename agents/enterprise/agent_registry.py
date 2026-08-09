"""Enterprise Agent Capability Registry & Governance Layer —— 智能体注册模型（任务1，Phase 3.8.13）。

新增：
- ``AgentStatus``：智能体状态（draft / reviewing / active / deprecated）。
- ``AgentRegistry``：智能体注册记录（agent_id / name / type / version / capabilities /
  status / owner / created_at）；``status`` 初始为 ``DRAFT``，**active 必须人工确认**（红线⑥）。

红线（fail-closed）：
- 本模块仅为数据载体，不持有任何批准/报价/审批/自动激活方法（红线②/③/④/⑥）。
- 状态流转（DRAFT → REVIEWING → ACTIVE → DEPRECATED）由 ``AgentLifecycleService`` 控制，
  ACTIVE 仅能由真实人工激活（红线⑥），AI 不得自动 active。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class AgentStatus(str, Enum):
    """智能体状态（任务1）。

    draft → reviewing → active → deprecated。ACTIVE 仅能由真实人工激活（红线⑥），
    AI 不得自动 active（对应任务1「active必须人工确认」）。
    """

    DRAFT = "draft"
    REVIEWING = "reviewing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class AgentRegistry:
    """智能体注册记录（任务1）。

    字段严格对应任务1 要求：agent_id / name / type / version / capabilities / status /
    owner / created_at。

    ``status`` 初始为 ``DRAFT``（禁 AI 自动 active，须人工激活，红线⑥）。
    ``capabilities`` 为 capability_id 列表，指向 ``AgentCapability`` 记录。
    ``org_id`` 为 Enterprise 层统一组织隔离字段。
    """

    agent_id: str
    name: str
    type: str
    version: str
    capabilities: List[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.DRAFT
    owner: str = ""
    org_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        # status 统一以枚举存储，避免字符串漂移。
        if not isinstance(self.status, AgentStatus):
            self.status = AgentStatus(self.status)

    @property
    def is_active(self) -> bool:
        """是否已激活（仅人工可达成）。"""
        return self.status == AgentStatus.ACTIVE

    @property
    def is_deprecated(self) -> bool:
        """是否已弃用。"""
        return self.status == AgentStatus.DEPRECATED


__all__ = ["AgentStatus", "AgentRegistry"]

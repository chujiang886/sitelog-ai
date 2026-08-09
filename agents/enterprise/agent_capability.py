"""Enterprise Agent Capability Registry & Governance Layer —— 智能体能力模型（任务2，Phase 3.8.13）。

新增：
- ``AgentCapability``：智能体能力声明（capability_id / agent_id / input_types /
  output_types / permissions / limitations）；明确 Agent 边界。

红线（fail-closed）：
- 本模块仅为数据载体，声明 Agent 能做什么、不能做什么（边界），不持有任何执行/批准/落地方法
  （红线②/③/④/⑥）。
- ``permissions`` 仅描述 Agent 被授权访问的权限范围（结构性边界），实际准入仍由
  ``AgentPermissionPolicy`` + ``IdentityService`` 在调用时校验（默认拒绝）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentCapability:
    """智能体能力声明（任务2）。

    明确 Agent 的能力边界：它接受哪些 ``input_types``、产出哪些 ``output_types``、被授权访问哪些
    ``permissions``、以及 ``limitations``（不可逾越的约束）。

    ``permissions`` 为权限字符串列表（建议取自 ``identity.Permission`` 取值）；``limitations``
    为自然语言约束列表（如「不得修改知识库」「不得生成工程参数」）。
    """

    capability_id: str
    agent_id: str
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def forbids(self, keyword: str) -> bool:
        """该能力是否声明禁止某类操作（按关键词匹配 ``limitations``）。"""
        return any(keyword in lim for lim in self.limitations)

    @property
    def denies_write(self) -> bool:
        """该能力是否声明禁止写入（只读/建议性边界）。"""
        return self.forbids("write") or self.forbids("写入") or self.forbids("修改知识库")


__all__ = ["AgentCapability"]

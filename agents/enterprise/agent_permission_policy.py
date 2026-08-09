"""Enterprise Agent Capability Registry & Governance Layer —— 智能体权限策略（任务4，Phase 3.8.13）。

新增：``AgentPermissionPolicy``，控制 Agent 可访问的知识/工具/数据范围（**默认拒绝**）。

设计要点（fail-closed，默认拒绝）：
- ``_AGENT_RESOURCE_SCOPE``：每个角色仅显式允许若干资源类别（knowledge / tool / data）；
  未列出的类别默认不可访问。
- ``is_agent_resource_permitted(role, resource_category)``：角色是否可访问某资源类别（默认拒绝）。
- ``check_agent_access(user, resource_category, required_permission)``：结合身份层权限校验，
  二者皆过才放行（默认拒绝）；真实权限仍由 ``IdentityService.check`` 校验。
- 本策略**仅**决定「Agent 可触及哪些资源类别」，不授予任何权限、不做任何决策（红线③/⑥）。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
"""

from __future__ import annotations

from agents.enterprise.identity import IdentityService, Permission, RoleKind


# 角色 → 允许 Agent 访问的资源类别（默认拒绝：未列出的类别对该角色不可访问）。
# 取值对应资源类别：knowledge / tool / data。ADMIN 含 "all"（全可访问）；
# 其余角色按职责最小化授权（与知识可见性策略一致）。
_AGENT_RESOURCE_SCOPE: dict[RoleKind, set[str]] = {
    RoleKind.ADMIN: {"knowledge", "tool", "data", "all"},
    RoleKind.DESIGNER: {"knowledge", "tool"},
    RoleKind.ENGINEER: {"knowledge", "tool", "data"},
    RoleKind.EXPERT: {"knowledge"},
    RoleKind.REVIEWER: {"knowledge"},
}


class AgentPermissionPolicy:
    """智能体权限策略（任务4）。

    按角色控制 Agent 可访问的知识/工具/数据范围；**默认拒绝**：角色未显式允许的资源类别不可访问。
    """

    def __init__(self, org_id: str, identity: "IdentityService | None" = None) -> None:
        self._org_id = org_id
        self._identity = identity

    def is_agent_resource_permitted(self, role: RoleKind, resource_category: str) -> bool:
        """某角色是否可让 Agent 访问某资源类别（空类别视为未分类，默认拒绝）。"""
        if not resource_category:
            return False
        allowed = _AGENT_RESOURCE_SCOPE.get(role, set())
        if "all" in allowed:
            return True
        return resource_category in allowed

    def check_agent_access(
        self,
        *,
        user: object,
        resource_category: str,
        required_permission: "Permission | None" = None,
    ) -> bool:
        """校验某用户（以角色）是否可让 Agent 访问某资源类别（默认拒绝）。

        两步皆过才放行：① 角色在资源类别作用域内（``is_agent_resource_permitted``）；
        ② 若提供了 ``IdentityService`` 且声明了 ``required_permission``，须通过
        ``IdentityService.check``。任一不过即拒绝（默认拒绝）。
        """
        role = getattr(user, "role", None)
        role_kind = getattr(role, "kind", role)
        if not self.is_agent_resource_permitted(role_kind, resource_category):
            return False
        if self._identity is not None and required_permission is not None:
            try:
                return self._identity.check(user, required_permission)
            except Exception:
                return False
        return True


__all__ = ["AgentPermissionPolicy", "_AGENT_RESOURCE_SCOPE"]

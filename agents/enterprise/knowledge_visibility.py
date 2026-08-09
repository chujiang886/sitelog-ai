"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 知识可见性策略（任务6，Phase 3.8.9）。

新增：``KnowledgeVisibilityPolicy``，按角色（``RoleKind``）控制不同知识类型在检索中的可见性。

设计要点（fail-closed，默认拒绝）：
- ``_ROLE_VISIBLE_KNOWLEDGE``：每个角色仅显式允许若干知识类型；未列出的类型默认不可检索。
- 检索 ``filter_by_permission`` 接入本策略：角色未授权检索的知识类型被剔除（默认拒绝）。
- 本策略**仅**决定「检索阶段展示哪些候选知识」，不授予任何权限、不做任何决策（红线③/⑥）。
- 真实权限（如 read_resource）仍由 identity 层 ``IdentityService.check`` 校验；本策略是
  「检索展示层」的细化，而非权限替代。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
"""

from __future__ import annotations

from agents.enterprise.identity import RoleKind


# 角色 → 允许检索的知识类型（默认拒绝：未列出的类型对该角色不可检索）。
# 取值对应各 KnowledgeItem.knowledge_type（design_spec / regulation / case / manual /
# governance / feedback）。ADMIN 含 "all"（全可见）；其余角色按职责最小化授权。
_ROLE_VISIBLE_KNOWLEDGE: dict[RoleKind, set[str]] = {
    RoleKind.ADMIN: {
        "design_spec",
        "regulation",
        "case",
        "manual",
        "governance",
        "feedback",
        "all",
    },
    RoleKind.DESIGNER: {
        "design_spec",
        "manual",
        "case",
        "governance",
    },
    RoleKind.ENGINEER: {
        "design_spec",
        "manual",
        "case",
        "regulation",
        "governance",
    },
    RoleKind.EXPERT: {
        "design_spec",
        "regulation",
        "case",
        "governance",
        "feedback",
    },
    RoleKind.REVIEWER: {
        "governance",
        "feedback",
        "regulation",
    },
}


class KnowledgeVisibilityPolicy:
    """知识检索可见性策略（任务6）。

    按角色决定哪些知识类型可进入检索候选；**默认拒绝**：角色未显式允许的知识类型不可检索。
    """

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def is_knowledge_permitted(self, role: RoleKind, knowledge_type: str) -> bool:
        """某角色是否可检索某知识类型（空类型视为未分类，默认拒绝）。"""
        if not knowledge_type:
            return False
        allowed = _ROLE_VISIBLE_KNOWLEDGE.get(role, set())
        if "all" in allowed:
            return True
        return knowledge_type in allowed

    def can_retrieve(self, role: RoleKind, item: object) -> bool:
        """校验某角色是否可检索某知识项（按 knowledge_type 类型策略）。"""
        ktype = getattr(item, "knowledge_type", "") or ""
        return self.is_knowledge_permitted(role, ktype)


__all__ = ["KnowledgeVisibilityPolicy", "_ROLE_VISIBLE_KNOWLEDGE"]

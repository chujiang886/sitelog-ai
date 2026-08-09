"""Enterprise Operation Layer —— 用户权限模型（任务1，Phase 3.8.0 基础 + 3.8.1 RBAC 增强）。

Phase 3.8.1 增强（RBAC 增强）：
- 角色继承（``Role.inherits`` 父角色权限并集，``effective_permissions`` 解析）。
- 权限组合（``PermissionBundle`` + ``compose_permissions``，支持并集/交集/差集）。
- 权限检查增强（``User.has_permission`` / ``IdentityService.check`` 解析继承链）。

红线：
- 任何「授权/权限决策」路径（如 ``grant_permission`` / ``assign_role``）先断言
  ``safety_invariants_ok()``（红线①/⑤）。
- 本模块为权限数据载体 + 校验器，不持有任何批准/报价方法（红线②/③/④）。
- 任何角色都**不得**被授予 forbidden 权限（结构性红线，``_FORBIDDEN_PERMISSIONS`` 恒空）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class Permission(str, Enum):
    """权限原子（字符串枚举，便于序列化与比较）。"""

    # 通用
    VIEW_PROJECT = "view_project"
    CREATE_PROJECT = "create_project"
    # 设计
    CREATE_DESIGN = "create_design"
    VIEW_DESIGN = "view_design"
    # 方案 / 工程阅读（只读，不生成）
    VIEW_SOLUTION = "view_solution"
    RUN_WORKFLOW = "run_workflow"
    # 文件
    MANAGE_FILES = "manage_files"
    # 专家 / 审核
    REVIEW_SOLUTION = "review_solution"
    PROVIDE_EXPERTISE = "provide_expertise"
    REVIEW_AUDIT = "review_audit"
    VIEW_AUDIT = "view_audit"
    # 管理
    MANAGE_USERS = "manage_users"
    MANAGE_ORG = "manage_org"
    # 资源级访问控制（Phase 3.8.1，任务2 复用）
    READ_RESOURCE = "read_resource"
    WRITE_RESOURCE = "write_resource"


class RoleKind(str, Enum):
    """五类内置角色。"""

    ADMIN = "admin"
    DESIGNER = "designer"
    ENGINEER = "engineer"
    EXPERT = "expert"
    REVIEWER = "reviewer"


# 内置角色 → 权限集（fail-closed：所有角色都**不含**任何批准/报价/审批权限；
# 这类动作不通过 RBAC 授予，必须真实人工线下执行）。
ROLE_PERMISSIONS: dict[RoleKind, set[Permission]] = {
    RoleKind.ADMIN: {
        Permission.VIEW_PROJECT,
        Permission.CREATE_PROJECT,
        Permission.CREATE_DESIGN,
        Permission.VIEW_DESIGN,
        Permission.VIEW_SOLUTION,
        Permission.RUN_WORKFLOW,
        Permission.MANAGE_FILES,
        Permission.REVIEW_SOLUTION,
        Permission.PROVIDE_EXPERTISE,
        Permission.REVIEW_AUDIT,
        Permission.VIEW_AUDIT,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ORG,
        Permission.READ_RESOURCE,
        Permission.WRITE_RESOURCE,
    },
    RoleKind.DESIGNER: {
        Permission.VIEW_PROJECT,
        Permission.CREATE_PROJECT,
        Permission.CREATE_DESIGN,
        Permission.VIEW_DESIGN,
        Permission.VIEW_SOLUTION,
        Permission.MANAGE_FILES,
        Permission.READ_RESOURCE,
        Permission.WRITE_RESOURCE,
    },
    RoleKind.ENGINEER: {
        Permission.VIEW_PROJECT,
        Permission.VIEW_DESIGN,
        Permission.VIEW_SOLUTION,
        Permission.RUN_WORKFLOW,
        Permission.MANAGE_FILES,
        Permission.READ_RESOURCE,
        Permission.WRITE_RESOURCE,
    },
    RoleKind.EXPERT: {
        Permission.VIEW_PROJECT,
        Permission.VIEW_SOLUTION,
        Permission.REVIEW_SOLUTION,
        Permission.PROVIDE_EXPERTISE,
        Permission.READ_RESOURCE,
    },
    RoleKind.REVIEWER: {
        Permission.VIEW_PROJECT,
        Permission.VIEW_AUDIT,
        Permission.REVIEW_AUDIT,
        Permission.READ_RESOURCE,
    },
}

# 任何角色都**不得**被授予的权限（结构性红线，恒为空集）。
_FORBIDDEN_PERMISSIONS: set[Permission] = set()


@dataclass(frozen=True)
class PermissionBundle:
    """权限组合单元（Phase 3.8.1，权限组合）。

    一个具名、不可变的权限集合；支持并集/交集/差集运算，便于把一组相关权限打包授予。
    """

    name: str
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    def union(self, other: "PermissionBundle") -> "PermissionBundle":
        return PermissionBundle(
            name=f"{self.name}+{other.name}",
            permissions=self.permissions | other.permissions,
        )

    def intersection(self, other: "PermissionBundle") -> "PermissionBundle":
        return PermissionBundle(
            name=f"{self.name}&{other.name}",
            permissions=self.permissions & other.permissions,
        )

    def difference(self, other: "PermissionBundle") -> "PermissionBundle":
        return PermissionBundle(
            name=f"{self.name}-{other.name}",
            permissions=self.permissions - other.permissions,
        )

    def requires(self, perm: Permission) -> bool:
        return perm in self.permissions

    def to_list(self) -> list[str]:
        return sorted(p.value for p in self.permissions)


def compose_permissions(*bundles: PermissionBundle) -> frozenset[Permission]:
    """把多个权限组合并集成一个不可变权限集合（权限组合）。"""
    out: set[Permission] = set()
    for b in bundles:
        out |= set(b.permissions)
    return frozenset(out)


def bundle_from_role(kind: RoleKind, name: str = "") -> PermissionBundle:
    """把内置角色的权限集封装为一个 ``PermissionBundle``（便于组合/比较）。"""
    return PermissionBundle(
        name=name or f"role:{kind.value}",
        permissions=frozenset(ROLE_PERMISSIONS.get(kind, set())),
    )


@dataclass
class Role:
    """角色：名称 + 权限集合 + 角色继承链（Phase 3.8.1）。

    ``inherits`` 声明本角色要继承的父角色（按 ``RoleKind``）；有效权限为
    自有权限与所有父角色权限的并集（``effective_permissions``）。
    """

    kind: RoleKind
    permissions: set[Permission] = field(default_factory=set)
    inherits: tuple[RoleKind, ...] = ()

    def __post_init__(self) -> None:
        if not self.permissions:
            self.permissions = set(ROLE_PERMISSIONS.get(self.kind, set()))

    def effective_permissions(self) -> set[Permission]:
        """解析继承链后的有效权限（自有 ∪ 所有父角色权限）。"""
        out = set(self.permissions)
        for parent in self.inherits:
            out |= ROLE_PERMISSIONS.get(parent, set())
        return out

    def has(self, perm: Permission) -> bool:
        # 权限检查解析继承链（Phase 3.8.1 增强）。
        return perm in self.effective_permissions()

    def permissions_list(self) -> list[str]:
        return sorted(p.value for p in self.permissions)

    def effective_permissions_list(self) -> list[str]:
        return sorted(p.value for p in self.effective_permissions())


@dataclass
class User:
    """用户：归属组织 + 角色 + 基础信息。

    ``org_id`` 用于企业级隔离（任务2）。跨组织访问由组织层/项目层统一拦截。
    """

    user_id: str
    name: str
    org_id: str
    role: Role
    email: str = ""

    def has_permission(self, perm: Permission) -> bool:
        # 解析继承链后的权限检查。
        return self.role.has(perm)

    def is_admin(self) -> bool:
        return self.role.kind == RoleKind.ADMIN


class IdentityService:
    """用户/权限服务（任务1）。

    仅做权限校验与用户登记，**不持有**任何批准/报价/审批方法；但所有写/授权决策路径
    先断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 IdentityService（红线①/⑤）"
            )
        self._org_id = org_id

    def make_user(
        self,
        *,
        user_id: str,
        name: str,
        role_kind: RoleKind,
        email: str = "",
    ) -> User:
        """在组织内创建用户（仅登记，不授予任何红线权限）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建用户（红线①/⑤）"
            )
        return User(
            user_id=user_id,
            name=name,
            org_id=self._org_id,
            role=Role(kind=role_kind),
            email=email,
        )

    def assign_role(self, user: User, role_kind: RoleKind) -> User:
        """变更用户角色（授权决策路径，断言红线①/⑤）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下变更角色（红线①/⑤）"
            )
        if user.org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"用户 {user.user_id!r} 归属组织 {user.org_id!r} 与本服务组织 "
                f"{self._org_id!r} 不一致，禁止跨域授权"
            )
        user.role = Role(kind=role_kind)
        return user

    def check(self, user: User, perm: Permission) -> bool:
        """权限校验（只读，不触发红线；解析角色继承）。"""
        if perm in _FORBIDDEN_PERMISSIONS:
            return False
        return user.has_permission(perm)


__all__ = [
    "Permission",
    "RoleKind",
    "ROLE_PERMISSIONS",
    "PermissionBundle",
    "compose_permissions",
    "bundle_from_role",
    "Role",
    "User",
    "IdentityService",
]

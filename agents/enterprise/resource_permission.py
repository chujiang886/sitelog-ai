"""Enterprise Operation Layer —— 资源权限模型（任务2，Phase 3.8.1）。

新增 ``ResourcePermission``，支持对 ``Project`` / ``FileAsset`` / ``Workflow`` / ``Solution``
四类资源的资源级访问控制（ACL）。

设计：
- ``ResourceKind`` 枚举：PROJECT / FILE_ASSET / WORKFLOW / SOLUTION。
- ``ResourcePermission`` 数据载体：资源 id + 类型 + 归属组织 + 被授予者（user/role）+ 权限集。
- ``ResourcePermissionService``：grant / revoke / check（资源级 ACL）。
- 跨域访问抛 ``EnterpriseIsolationError``（企业级隔离）。
- 所有构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有任何批准/报价/审批方法（红线②/③/④）。
- 可选地接入 ``AuditService``，在 check / grant 时记录 permission_check / access_granted /
  access_denied（任务5 联动），但审计层仍禁止 record_human_approval（红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import Permission, Role
from agents.enterprise.organization import EnterpriseIsolationError, OrganizationService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class ResourceKind(str, Enum):
    """受控资源类型。"""

    PROJECT = "project"
    FILE_ASSET = "file_asset"
    WORKFLOW = "workflow"
    SOLUTION = "solution"


@dataclass
class ResourcePermission:
    """资源级访问控制条目（ACL 一行）。

    ``grantee_type`` 为 ``"user"`` 时 ``grantee_id`` 为用户 id；为 ``"role"`` 时
    ``grantee_id`` 为 ``RoleKind`` 字符串值（角色级授权对所有该角色用户生效）。
    """

    resource_id: str
    kind: ResourceKind
    org_id: str
    grantee_id: str
    grantee_type: str  # "user" | "role"
    permissions: set[Permission] = field(default_factory=set)
    granted_by: str = ""
    ts: str = ""


class ResourcePermissionService:
    """资源级权限服务（任务2）。

    资源按 ``org_id`` 作用域隔离；跨域授予/校验一律抛 ``EnterpriseIsolationError``。
    """

    def __init__(self, org_id: str, audit: Optional[AuditService] = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 ResourcePermissionService"
                "（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._acls: list[ResourcePermission] = []

    def grant(
        self,
        *,
        resource_id: str,
        kind: ResourceKind,
        resource_org_id: str,
        grantee_id: str,
        grantee_type: str,
        permissions: Iterable[Permission],
        granted_by: str = "",
        ts: str = "",
    ) -> ResourcePermission:
        """对资源授予权限（写路径，断言红线①/⑤ + 跨域隔离）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下授予资源权限（红线①/⑤）"
            )
        OrganizationService.assert_same_org(
            self._org_id, resource_org_id, context=f"授予资源 {resource_id!r} 权限"
        )
        if grantee_type not in ("user", "role"):
            raise ValueError(f"grantee_type 必须为 'user' 或 'role'，收到 {grantee_type!r}")
        rp = ResourcePermission(
            resource_id=resource_id,
            kind=kind,
            org_id=self._org_id,
            grantee_id=grantee_id,
            grantee_type=grantee_type,
            permissions=set(permissions),
            granted_by=granted_by,
            ts=ts,
        )
        self._acls.append(rp)
        if self._audit is not None:
            self._audit.record_access_granted(
                record_id=f"rp-grant-{resource_id}-{grantee_id}",
                actor_id=granted_by or "system",
                action="grant_resource_permission",
                target=resource_id,
                detail=f"kind={kind.value};grantee={grantee_type}:{grantee_id};"
                f"perms={sorted(p.value for p in rp.permissions)}",
                ts=ts,
            )
        return rp

    def revoke(
        self,
        *,
        resource_id: str,
        grantee_id: str,
        grantee_type: str,
    ) -> int:
        """撤销某资源上某个被授予者的全部权限；返回被移除的条目数。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下撤销资源权限（红线①/⑤）"
            )
        before = len(self._acls)
        self._acls = [
            a
            for a in self._acls
            if not (
                a.resource_id == resource_id
                and a.grantee_id == grantee_id
                and a.grantee_type == grantee_type
                and a.org_id == self._org_id
            )
        ]
        return before - len(self._acls)

    def check(self, *, user, resource_id: str, kind: ResourceKind, perm: Permission) -> bool:
        """资源级权限校验（只读，但记录 permission_check + 结果）。

        ``user`` 需具备 ``org_id`` / ``user_id`` / ``role``（``Role``）属性。
        跨域用户（``user.org_id != self._org_id``）一律拒绝并抛隔离错误。
        """
        OrganizationService.assert_same_org(
            self._org_id, user.org_id, context=f"校验资源 {resource_id!r} 访问"
        )
        granted = False
        for a in self._acls:
            if a.org_id != self._org_id:
                continue
            if a.resource_id != resource_id or a.kind != kind:
                continue
            if a.grantee_type == "user" and a.grantee_id != user.user_id:
                continue
            if a.grantee_type == "role" and a.grantee_id != user.role.kind.value:
                continue
            if perm in a.permissions:
                granted = True
                break
        if self._audit is not None:
            self._audit.record_permission_check(
                record_id=f"rp-check-{resource_id}-{user.user_id}",
                actor_id=user.user_id,
                action="resource_permission_check",
                target=resource_id,
                detail=f"kind={kind.value};perm={perm.value};granted={granted}",
            )
            if granted:
                self._audit.record_access_granted(
                    record_id=f"rp-granted-{resource_id}-{user.user_id}",
                    actor_id=user.user_id,
                    action="resource_access_granted",
                    target=resource_id,
                    detail=f"kind={kind.value};perm={perm.value}",
                )
            else:
                self._audit.record_access_denied(
                    record_id=f"rp-denied-{resource_id}-{user.user_id}",
                    actor_id=user.user_id,
                    action="resource_access_denied",
                    target=resource_id,
                    detail=f"kind={kind.value};perm={perm.value}",
                )
        return granted


__all__ = [
    "ResourceKind",
    "ResourcePermission",
    "ResourcePermissionService",
]

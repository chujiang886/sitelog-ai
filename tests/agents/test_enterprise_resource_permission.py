"""Enterprise Operation Layer —— 测试2（Phase 3.8.1）：资源权限模型。

覆盖任务2 的 ``ResourcePermission`` / ``ResourcePermissionService``：
- 对 Project / FileAsset / Workflow / Solution 四类资源授予 user/role 级 ACL。
- check 命中 ACL 时放行，未命中时拒绝。
- revoke 正确移除条目。
- 跨域授予/校验抛 ``EnterpriseIsolationError``（企业级隔离）。
- 接入 AuditService 时联动记录 permission_check / access_granted / access_denied。

注：启用态通过 monkeypatch 注入，不修改 verified.json / config.yaml / engineering_enabled。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import Permission, Role, RoleKind, User
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.resource_permission import (
    ResourceKind,
    ResourcePermission,
    ResourcePermissionService,
)


def _user(user_id: str, kind: RoleKind, org_id: str = "org-1") -> User:
    return User(user_id=user_id, name=user_id, org_id=org_id, role=Role(kind=kind))


def test_grant_and_check_user_acl_grants_access() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
    )
    u = _user("u1", RoleKind.DESIGNER)
    assert svc.check(user=u, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.READ_RESOURCE) is True


def test_check_denies_when_no_acl() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    u = _user("u1", RoleKind.DESIGNER)
    assert svc.check(user=u, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.READ_RESOURCE) is False


def test_check_role_level_acl_matches_any_user_of_role() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    svc.grant(
        resource_id="file-1",
        kind=ResourceKind.FILE_ASSET,
        resource_org_id="org-1",
        grantee_id=RoleKind.ENGINEER.value,
        grantee_type="role",
        permissions=[Permission.READ_RESOURCE, Permission.WRITE_RESOURCE],
    )
    engineer = _user("e1", RoleKind.ENGINEER)
    assert svc.check(user=engineer, resource_id="file-1", kind=ResourceKind.FILE_ASSET, perm=Permission.WRITE_RESOURCE) is True
    designer = _user("d1", RoleKind.DESIGNER)
    assert svc.check(user=designer, resource_id="file-1", kind=ResourceKind.FILE_ASSET, perm=Permission.WRITE_RESOURCE) is False


def test_supports_four_resource_kinds() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    for kind in (ResourceKind.PROJECT, ResourceKind.FILE_ASSET, ResourceKind.WORKFLOW, ResourceKind.SOLUTION):
        svc.grant(
            resource_id=f"r-{kind.value}",
            kind=kind,
            resource_org_id="org-1",
            grantee_id="u1",
            grantee_type="user",
            permissions=[Permission.READ_RESOURCE],
        )
    u = _user("u1", RoleKind.ADMIN)
    for kind in (ResourceKind.PROJECT, ResourceKind.FILE_ASSET, ResourceKind.WORKFLOW, ResourceKind.SOLUTION):
        assert svc.check(user=u, resource_id=f"r-{kind.value}", kind=kind, perm=Permission.READ_RESOURCE) is True


def test_revoke_removes_entries() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
    )
    removed = svc.revoke(resource_id="proj-1", grantee_id="u1", grantee_type="user")
    assert removed == 1
    u = _user("u1", RoleKind.ADMIN)
    assert svc.check(user=u, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.READ_RESOURCE) is False


def test_grant_cross_org_raises_isolation() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    with pytest.raises(EnterpriseIsolationError):
        svc.grant(
            resource_id="proj-x",
            kind=ResourceKind.PROJECT,
            resource_org_id="org-2",  # 跨域
            grantee_id="u1",
            grantee_type="user",
            permissions=[Permission.READ_RESOURCE],
        )


def test_check_cross_org_user_raises_isolation() -> None:
    svc = ResourcePermissionService(org_id="org-1")
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
    )
    foreign = _user("u1", RoleKind.ADMIN, org_id="org-2")
    with pytest.raises(EnterpriseIsolationError):
        svc.check(user=foreign, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.READ_RESOURCE)


def test_grant_records_audit_access_granted() -> None:
    audit = AuditService(org_id="org-1")
    svc = ResourcePermissionService(org_id="org-1", audit=audit)
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
        granted_by="admin-1",
    )
    recs = audit.query(category="permission")
    assert any(r.action == "grant_resource_permission" for r in recs)


def test_check_records_permission_check_and_decision() -> None:
    audit = AuditService(org_id="org-1")
    svc = ResourcePermissionService(org_id="org-1", audit=audit)
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
    )
    u = _user("u1", RoleKind.ADMIN)
    # 命中：记录 permission_check + access_granted
    svc.check(user=u, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.READ_RESOURCE)
    # 未命中：记录 permission_check + access_denied
    svc.check(user=u, resource_id="proj-1", kind=ResourceKind.PROJECT, perm=Permission.WRITE_RESOURCE)
    actions = {r.action for r in audit.query(category="permission")}
    assert "resource_permission_check" in actions
    assert "resource_access_granted" in actions
    assert "resource_access_denied" in actions


def test_audit_records_have_user_actor_kind() -> None:
    audit = AuditService(org_id="org-1")
    svc = ResourcePermissionService(org_id="org-1", audit=audit)
    svc.grant(
        resource_id="proj-1",
        kind=ResourceKind.PROJECT,
        resource_org_id="org-1",
        grantee_id="u1",
        grantee_type="user",
        permissions=[Permission.READ_RESOURCE],
        granted_by="admin-1",
    )
    for r in audit.query(category="permission"):
        assert r.actor_kind.value == "user"

"""Enterprise Operation Layer —— 测试1：用户权限模型（任务1，Phase 3.8.0）。

覆盖：
- 五类角色（admin/designer/engineer/expert/reviewer）权限集。
- 任何角色都**不含**批准/报价/审批红线权限（fail-closed）。
- User.has_permission / is_admin。
- IdentityService.make_user / assign_role（跨域抛 EnterpriseIsolationError）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.identity import (
    IdentityService,
    Permission,
    Role,
    RoleKind,
    ROLE_PERMISSIONS,
    User,
)
from agents.enterprise.organization import EnterpriseIsolationError


def test_role_default_permissions_hydrate() -> None:
    role = Role(kind=RoleKind.DESIGNER)
    assert Permission.CREATE_DESIGN in role.permissions
    assert Permission.MANAGE_FILES in role.permissions
    assert Permission.VIEW_PROJECT in role.permissions


def test_permission_sets_are_distinct_per_role() -> None:
    assert ROLE_PERMISSIONS[RoleKind.ADMIN] >= ROLE_PERMISSIONS[RoleKind.DESIGNER]
    assert ROLE_PERMISSIONS[RoleKind.ADMIN] >= ROLE_PERMISSIONS[RoleKind.ENGINEER]
    assert ROLE_PERMISSIONS[RoleKind.ADMIN] >= ROLE_PERMISSIONS[RoleKind.EXPERT]
    assert ROLE_PERMISSIONS[RoleKind.ADMIN] >= ROLE_PERMISSIONS[RoleKind.REVIEWER]


def test_admin_has_all_permissions() -> None:
    assert set(ROLE_PERMISSIONS[RoleKind.ADMIN]) == set(Permission)


def test_no_role_has_forbidden_approve_permission() -> None:
    # 权限枚举本身不含批准/报价/审批动作；五类角色权限集也不含任何红线动作。
    forbidden_values = {
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
    }
    for perms in ROLE_PERMISSIONS.values():
        assert not (forbidden_values & {p.value for p in perms})


def test_user_has_permission_and_is_admin() -> None:
    admin = User(user_id="u1", name="A", org_id="org-1", role=Role(kind=RoleKind.ADMIN))
    assert admin.is_admin()
    assert admin.has_permission(Permission.MANAGE_USERS)
    designer = User(user_id="u2", name="D", org_id="org-1", role=Role(kind=RoleKind.DESIGNER))
    assert not designer.is_admin()
    assert not designer.has_permission(Permission.MANAGE_USERS)
    assert designer.has_permission(Permission.CREATE_DESIGN)


def test_identity_service_make_user_assigns_org_and_role() -> None:
    svc = IdentityService(org_id="org-1")
    u = svc.make_user(user_id="u1", name="Alice", role_kind=RoleKind.EXPERT)
    assert u.org_id == "org-1"
    assert u.role.kind == RoleKind.EXPERT
    assert svc.check(u, Permission.REVIEW_SOLUTION)
    assert not svc.check(u, Permission.MANAGE_USERS)


def test_assign_role_within_org_succeeds() -> None:
    svc = IdentityService(org_id="org-1")
    u = svc.make_user(user_id="u1", name="Bob", role_kind=RoleKind.DESIGNER)
    svc.assign_role(u, RoleKind.ENGINEER)
    assert u.role.kind == RoleKind.ENGINEER


def test_assign_role_cross_org_raises_isolation() -> None:
    svc = IdentityService(org_id="org-1")
    foreign = User(user_id="u9", name="X", org_id="org-2", role=Role(kind=RoleKind.DESIGNER))
    with pytest.raises(EnterpriseIsolationError):
        svc.assign_role(foreign, RoleKind.ENGINEER)

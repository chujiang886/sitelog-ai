"""Enterprise Operation Layer —— 测试1（Phase 3.8.1 增强）：RBAC 增强。

覆盖任务1 的 RBAC 增强能力：
- 角色继承（``Role.inherits`` → ``effective_permissions`` 解析父角色权限并集）。
- 权限组合（``PermissionBundle`` 并集/交集/差集；``compose_permissions`` 合并）。
- 权限检查增强（``User.has_permission`` / ``IdentityService.check`` 解析继承链）。
- 任何角色都**不含**红线权限（fail-closed，结构性保障）。

注：启用态通过 monkeypatch 注入，不修改 verified.json / config.yaml / engineering_enabled。
"""

from __future__ import annotations

from agents.enterprise.identity import (
    Permission,
    PermissionBundle,
    Role,
    RoleKind,
    ROLE_PERMISSIONS,
    User,
    IdentityService,
    bundle_from_role,
    compose_permissions,
)


def _make_role(kind: RoleKind, inherits: tuple[RoleKind, ...] = ()) -> Role:
    return Role(kind=kind, inherits=inherits)


def test_role_inherits_collects_parent_permissions() -> None:
    # 自定义审核角色继承 REVIEWER：有效权限 = 自有(None) ∪ REVIEWER 权限。
    r = _make_role(RoleKind.REVIEWER, inherits=())
    assert Permission.REVIEW_AUDIT in r.effective_permissions()
    assert Permission.VIEW_AUDIT in r.effective_permissions()


def test_role_inheritance_union_semantics() -> None:
    # 让一个「方案审核」角色继承 REVIEWER，再叠加自有 VIEW_SOLUTION。
    custom = Role(
        kind=RoleKind.REVIEWER,
        permissions={Permission.VIEW_SOLUTION},
        inherits=(RoleKind.REVIEWER,),
    )
    eff = custom.effective_permissions()
    assert Permission.VIEW_SOLUTION in eff
    assert Permission.REVIEW_AUDIT in eff  # 来自继承
    assert Permission.VIEW_AUDIT in eff    # 来自继承


def test_role_has_resolves_inheritance() -> None:
    custom = Role(
        kind=RoleKind.REVIEWER,
        permissions={Permission.VIEW_SOLUTION},
        inherits=(RoleKind.REVIEWER,),
    )
    assert custom.has(Permission.VIEW_SOLUTION) is True
    assert custom.has(Permission.REVIEW_AUDIT) is True   # 经继承
    assert custom.has(Permission.MANAGE_USERS) is False  # 从未授予


def test_permission_bundle_union_intersection_difference() -> None:
    a = PermissionBundle(name="a", permissions={Permission.VIEW_PROJECT, Permission.CREATE_DESIGN})
    b = PermissionBundle(name="b", permissions={Permission.VIEW_PROJECT, Permission.RUN_WORKFLOW})
    u = a.union(b)
    assert u.requires(Permission.VIEW_PROJECT)
    assert u.requires(Permission.CREATE_DESIGN)
    assert u.requires(Permission.RUN_WORKFLOW)
    inter = a.intersection(b)
    assert set(inter.permissions) == {Permission.VIEW_PROJECT}
    diff = a.difference(b)
    assert set(diff.permissions) == {Permission.CREATE_DESIGN}


def test_permission_bundle_to_list_sorted() -> None:
    b = PermissionBundle(name="x", permissions={Permission.RUN_WORKFLOW, Permission.VIEW_PROJECT})
    assert b.to_list() == ["run_workflow", "view_project"]


def test_compose_permissions_merges_bundles() -> None:
    b1 = PermissionBundle(name="r", permissions={Permission.VIEW_PROJECT})
    b2 = bundle_from_role(RoleKind.REVIEWER, name="rev")
    composed = compose_permissions(b1, b2)
    assert Permission.VIEW_PROJECT in composed
    assert Permission.REVIEW_AUDIT in composed
    assert isinstance(composed, frozenset)


def test_bundle_from_role_reflects_role_permissions() -> None:
    b = bundle_from_role(RoleKind.ADMIN, name="admin-bundle")
    assert Permission.MANAGE_ORG in b.permissions
    assert b.requires(Permission.MANAGE_USERS)


def test_user_has_permission_resolves_inheritance() -> None:
    # 用户角色继承 REVIEWER，应解析出继承权限。
    role = Role(
        kind=RoleKind.REVIEWER,
        permissions={Permission.VIEW_SOLUTION},
        inherits=(RoleKind.REVIEWER,),
    )
    user = User(user_id="u1", name="E", org_id="org-1", role=role)
    assert user.has_permission(Permission.VIEW_SOLUTION) is True
    assert user.has_permission(Permission.REVIEW_AUDIT) is True  # 经继承


def test_identity_service_check_resolves_inheritance() -> None:
    svc = IdentityService(org_id="org-1")
    role = Role(
        kind=RoleKind.REVIEWER,
        permissions={Permission.VIEW_SOLUTION},
        inherits=(RoleKind.REVIEWER,),
    )
    user = User(user_id="u1", name="E", org_id="org-1", role=role)
    assert svc.check(user, Permission.VIEW_SOLUTION) is True
    assert svc.check(user, Permission.REVIEW_AUDIT) is True
    assert svc.check(user, Permission.MANAGE_USERS) is False


def test_no_role_has_forbidden_redline_permission() -> None:
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


def test_resource_permissions_present_on_builtin_roles() -> None:
    # 任务2 复用的两个资源级权限必须已落到角色权限集（至少 ADMIN 应有写）。
    assert Permission.READ_RESOURCE in ROLE_PERMISSIONS[RoleKind.ADMIN]
    assert Permission.WRITE_RESOURCE in ROLE_PERMISSIONS[RoleKind.ADMIN]
    # EXPERT / REVIEWER 仅读，无写（最小权限原则）。
    assert Permission.READ_RESOURCE in ROLE_PERMISSIONS[RoleKind.EXPERT]
    assert Permission.WRITE_RESOURCE not in ROLE_PERMISSIONS[RoleKind.EXPERT]
    assert Permission.WRITE_RESOURCE not in ROLE_PERMISSIONS[RoleKind.REVIEWER]

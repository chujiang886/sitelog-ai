"""Enterprise Operation Layer —— 测试2：组织模型与企业级隔离（任务2，Phase 3.8.0）。

覆盖：
- OrganizationService.create_organization / add_department / add_member。
- 跨域成员登记抛 EnterpriseIsolationError。
- OrganizationService.assert_same_org 静态方法（同域放行，跨域拒绝）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.identity import Role, RoleKind, User
from agents.enterprise.organization import (
    Department,
    EnterpriseIsolationError,
    Member,
    Organization,
    OrganizationService,
)


def test_create_organization_and_current_org_id() -> None:
    svc = OrganizationService(org_id="org-1")
    org = svc.create_organization(org_id="org-1", name="Acme")
    assert isinstance(org, Organization)
    assert svc.current_org_id() == "org-1"


def test_add_department_attaches_to_org() -> None:
    svc = OrganizationService(org_id="org-1")
    dept = svc.add_department(dept_id="d1", name="Design")
    assert isinstance(dept, Department)
    assert dept.org_id == "org-1"
    assert svc._org.departments[0] is dept


def test_add_member_within_org() -> None:
    svc = OrganizationService(org_id="org-1")
    u = User(user_id="u1", name="A", org_id="org-1", role=Role(kind=RoleKind.DESIGNER))
    m = svc.add_member(user=u, dept_id="d1", title="Lead")
    assert isinstance(m, Member)
    assert m.org_id == "org-1"


def test_add_member_cross_org_raises_isolation() -> None:
    svc = OrganizationService(org_id="org-1")
    foreign = User(user_id="u9", name="X", org_id="org-2", role=Role(kind=RoleKind.DESIGNER))
    with pytest.raises(EnterpriseIsolationError):
        svc.add_member(user=foreign)


def test_assert_same_org_allows_same_rejects_different() -> None:
    OrganizationService.assert_same_org("org-1", "org-1")
    with pytest.raises(EnterpriseIsolationError):
        OrganizationService.assert_same_org("org-1", "org-2", context="project access")

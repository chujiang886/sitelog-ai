"""Enterprise Operation Layer —— 组织模型与企业级隔离（任务2，Phase 3.8.0）。

新增：``Organization`` / ``Department`` / ``Member``，支持企业级隔离。

隔离语义（fail-closed）：
- 所有资源按 ``org_id`` 作用域过滤；跨域访问（不同 org_id 互访资源）一律抛
  ``EnterpriseIsolationError``。
- ``OrganizationService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价方法（红线②/③/④）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.identity import User
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class EnterpriseIsolationError(Exception):
    """跨企业组织域访问被拒（企业级隔离护栏）。"""


@dataclass
class Department:
    """部门：归属组织 + 名称 + 父部门（可选）。"""

    dept_id: str
    org_id: str
    name: str
    parent_dept_id: str = ""


@dataclass
class Member:
    """成员：用户在某组织/部门的从属关系。"""

    user_id: str
    org_id: str
    dept_id: str = ""
    title: str = ""


@dataclass
class Organization:
    """组织（企业租户）。"""

    org_id: str
    name: str
    departments: list = field(default_factory=list)
    members: list = field(default_factory=list)


class OrganizationService:
    """组织服务（任务2）。

    维护组织/部门/成员，提供跨域隔离检查 ``assert_same_org``。
    """

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 OrganizationService（红线①/⑤）"
            )
        self._org_id = org_id
        self._org = Organization(org_id=org_id, name="")

    def create_organization(self, *, org_id: str, name: str) -> Organization:
        """登记组织（仅元数据，不持有任何红线动作）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记组织（红线①/⑤）"
            )
        self._org = Organization(org_id=org_id, name=name)
        self._org_id = org_id
        return self._org

    def add_department(self, *, dept_id: str, name: str, parent_dept_id: str = "") -> Department:
        """在组织内新增部门。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下新增部门（红线①/⑤）"
            )
        dept = Department(
            dept_id=dept_id,
            org_id=self._org_id,
            name=name,
            parent_dept_id=parent_dept_id,
        )
        self._org.departments.append(dept)
        return dept

    def add_member(self, *, user: User, dept_id: str = "", title: str = "") -> Member:
        """把用户登记为组织成员（跨域访问抛隔离错误）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记成员（红线①/⑤）"
            )
        if user.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"用户 {user.user_id!r} 归属组织 {user.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域登记成员"
            )
        member = Member(user_id=user.user_id, org_id=self._org_id, dept_id=dept_id, title=title)
        self._org.members.append(member)
        return member

    @staticmethod
    def assert_same_org(expected_org_id: str, actual_org_id: str, context: str = "") -> None:
        """跨域隔离断言（fail-closed）。

        凡涉及资源归属校验之处调用：``actual_org_id`` 与 ``expected_org_id`` 不一致即抛
        ``EnterpriseIsolationError``。绝不静默放行跨域访问。
        """
        if expected_org_id != actual_org_id:
            raise EnterpriseIsolationError(
                f"企业级隔离违例{('：' + context) if context else ''}："
                f"期望组织 {expected_org_id!r} 但资源归属 {actual_org_id!r}，"
                f"跨域访问被拒绝"
            )

    def current_org_id(self) -> str:
        return self._org_id


__all__ = [
    "EnterpriseIsolationError",
    "Department",
    "Member",
    "Organization",
    "OrganizationService",
]

"""Enterprise Operation Layer —— 测试3（Phase 3.8.1）：专家权限隔离。

覆盖任务3 的 ``ExpertAccessPolicy`` / ``ExpertAccessService``：
- define_policy 登记专家授权范围（project / solution / domain 三维）。
- can_review 在授权范围内返回 True。
- can_review 在范围外默认拒绝（fail-closed，返回 False）。
- 跨域专家抛 ``EnterpriseIsolationError``（企业级隔离）。
- 接入审计时联动记录 permission_check / access_granted / access_denied。

注：启用态通过 monkeypatch 注入，不修改 verified.json / config.yaml / engineering_enabled。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.expert_access import ExpertAccessPolicy, ExpertAccessService
from agents.enterprise.identity import Role, RoleKind, User
from agents.enterprise.organization import EnterpriseIsolationError


def _expert(user_id: str, org_id: str = "org-1") -> User:
    return User(user_id=user_id, name=user_id, org_id=org_id, role=Role(kind=RoleKind.EXPERT))


def test_define_policy_and_review_within_scope() -> None:
    svc = ExpertAccessService(org_id="org-1")
    svc.define_policy(
        expert_user_id="exp-1",
        authorized_project_ids=["proj-1", "proj-2"],
        authorized_domains=["structural"],
    )
    exp = _expert("exp-1")
    assert svc.can_review(expert=exp, project_id="proj-1") is True
    assert svc.can_review(expert=exp, domain="structural") is True


def test_can_review_out_of_scope_default_deny() -> None:
    svc = ExpertAccessService(org_id="org-1")
    svc.define_policy(expert_user_id="exp-1", authorized_project_ids=["proj-1"])
    exp = _expert("exp-1")
    # 未授权项目 → 默认拒绝
    assert svc.can_review(expert=exp, project_id="proj-99") is False
    # 完全未提供任何目标 → 默认拒绝
    assert svc.can_review(expert=exp) is False


def test_undefined_expert_cannot_review() -> None:
    svc = ExpertAccessService(org_id="org-1")
    exp = _expert("exp-unknown")
    assert svc.can_review(expert=exp, project_id="proj-1") is False


def test_can_review_solution_scope() -> None:
    svc = ExpertAccessService(org_id="org-1")
    svc.define_policy(expert_user_id="exp-2", authorized_solution_ids=["sol-7"])
    exp = _expert("exp-2")
    assert svc.can_review(expert=exp, solution_id="sol-7") is True
    assert svc.can_review(expert=exp, solution_id="sol-8") is False


def test_cross_org_expert_raises_isolation() -> None:
    svc = ExpertAccessService(org_id="org-1")
    foreign = _expert("exp-x", org_id="org-2")
    with pytest.raises(EnterpriseIsolationError):
        svc.can_review(expert=foreign, project_id="proj-1")


def test_policy_is_frozen_set() -> None:
    svc = ExpertAccessService(org_id="org-1")
    policy = svc.define_policy(expert_user_id="exp-1", authorized_project_ids=["proj-1"])
    assert isinstance(policy, ExpertAccessPolicy)
    assert isinstance(policy.authorized_project_ids, frozenset)
    assert "proj-1" in policy.authorized_project_ids


def test_audit_records_permission_check_and_decision() -> None:
    audit = AuditService(org_id="org-1")
    svc = ExpertAccessService(org_id="org-1", audit=audit)
    svc.define_policy(expert_user_id="exp-1", authorized_project_ids=["proj-1"])
    exp = _expert("exp-1")
    svc.can_review(expert=exp, project_id="proj-1")  # 命中
    svc.can_review(expert=exp, project_id="proj-99")  # 拒绝
    actions = {r.action for r in audit.query(category="permission")}
    assert "expert_review_permission_check" in actions
    assert "expert_review_access_granted" in actions
    assert "expert_review_access_denied" in actions

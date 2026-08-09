"""Enterprise Operation Layer —— 测试4（Phase 3.8.1）：审核权限隔离 / 职责分离（SoD）。

覆盖任务4 的 ``ReviewDecision`` / ``ReviewPermissionService.validate``：
- 允许：审核者为 REVIEWER、提交者 ≠ 审核者、专家无冲突。
- 拒绝（自审）：提交者 == 审核者 → DENIED_SUBMITTER_IS_REVIEWER。
- 拒绝（审核者越权）：审核者非 REVIEWER/ADMIN → DENIED_REVIEWER_NOT_AUTHORIZED。
- 拒绝（专家冲突）：专家兼任提交者或审核者 → DENIED_EXPERT_CONFLICT。
- 跨域（submitter/reviewer/expert 任一非本组织）抛 ``EnterpriseIsolationError``。
- 接入审计时联动记录 permission_check / access_granted / access_denied。

注：启用态通过 monkeypatch 注入，不修改 verified.json / config.yaml / engineering_enabled。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import Role, RoleKind, User
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.review_permission import (
    ReviewDecision,
    ReviewPermissionService,
)


def _u(user_id: str, kind: RoleKind, org_id: str = "org-1") -> User:
    return User(user_id=user_id, name=user_id, org_id=org_id, role=Role(kind=kind))


def test_validate_allowed_when_reviewer_and_distinct() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.REVIEWER)
    assert svc.validate(submitter=submitter, reviewer=reviewer) is True


def test_validate_denied_submitter_is_reviewer() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    same = _u("s1", RoleKind.REVIEWER)
    assert svc.validate(submitter=same, reviewer=same) is False
    # 决策值应被明确标注为自审拒绝
    svc2 = ReviewPermissionService(org_id="org-1")
    # 通过审计复盘决策（不依赖返回值布尔）
    audit = AuditService(org_id="org-1")
    svc3 = ReviewPermissionService(org_id="org-1", audit=audit)
    svc3.validate(submitter=same, reviewer=same, review_id="rv-1")
    denied = [r for r in audit.query(category="permission") if r.action == "review_access_denied"]
    assert denied and "denied_submitter_is_reviewer" in denied[0].detail


def test_validate_denied_reviewer_not_authorized() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.DESIGNER)  # 非 REVIEWER/ADMIN
    assert svc.validate(submitter=submitter, reviewer=reviewer) is False


def test_validate_allowed_when_admin_reviews_distinct() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("a1", RoleKind.ADMIN)
    assert svc.validate(submitter=submitter, reviewer=reviewer) is True


def test_validate_denied_expert_conflict_with_reviewer() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.REVIEWER)
    expert = _u("r1", RoleKind.EXPERT)  # 专家与审核者同人 → 冲突
    assert svc.validate(submitter=submitter, reviewer=reviewer, expert=expert) is False


def test_validate_denied_expert_conflict_with_submitter() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.REVIEWER)
    expert = _u("s1", RoleKind.EXPERT)  # 专家与提交者同人 → 冲突
    assert svc.validate(submitter=submitter, reviewer=reviewer, expert=expert) is False


def test_validate_cross_org_submitter_raises_isolation() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER, org_id="org-2")
    reviewer = _u("r1", RoleKind.REVIEWER)
    with pytest.raises(EnterpriseIsolationError):
        svc.validate(submitter=submitter, reviewer=reviewer)


def test_validate_cross_org_reviewer_raises_isolation() -> None:
    svc = ReviewPermissionService(org_id="org-1")
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.REVIEWER, org_id="org-2")
    with pytest.raises(EnterpriseIsolationError):
        svc.validate(submitter=submitter, reviewer=reviewer)


def test_review_decision_enum_values() -> None:
    assert ReviewDecision.ALLOWED.value == "allowed"
    assert ReviewDecision.DENIED_SUBMITTER_IS_REVIEWER.value == "denied_submitter_is_reviewer"
    assert ReviewDecision.DENIED_REVIEWER_NOT_AUTHORIZED.value == "denied_reviewer_not_authorized"
    assert ReviewDecision.DENIED_EXPERT_CONFLICT.value == "denied_expert_conflict"


def test_audit_records_for_review_decision() -> None:
    audit = AuditService(org_id="org-1")
    svc = ReviewPermissionService(org_id="org-1", audit=audit)
    submitter = _u("s1", RoleKind.DESIGNER)
    reviewer = _u("r1", RoleKind.REVIEWER)
    svc.validate(submitter=submitter, reviewer=reviewer, review_id="rv-1")
    actions = {r.action for r in audit.query(category="permission")}
    assert "review_permission_check" in actions
    assert "review_access_granted" in actions

"""Enterprise Operation Layer —— 测试5（Phase 3.8.1）：权限审计增强。

覆盖任务5 的 ``AuditService`` 权限审计扩展：
- 新增 ``AuditActionCategory.PERMISSION`` 类别。
- ``record_permission_check`` / ``record_access_granted`` / ``record_access_denied``
  生成的记录 category=PERMISSION、actor_kind=USER。
- ``query(category=...)`` 可过滤 PERMISSION 类。
- 红线⑥：``record_human_approval`` 被 mixin 拦截，禁止伪造 human approval。
- 构造/写路径在启用态下 fail-closed（红线①/⑤）。

注：启用态通过 monkeypatch 注入，不修改 verified.json / config.yaml / engineering_enabled。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditService,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def test_permission_category_exists() -> None:
    assert AuditActionCategory.PERMISSION.value == "permission"


def test_record_permission_check_metadata() -> None:
    audit = AuditService(org_id="org-1")
    rec = audit.record_permission_check(
        record_id="pc-1",
        actor_id="u1",
        action="resource_permission_check",
        target="proj-1",
        detail="perm=read_resource;granted=True",
    )
    assert rec.category == AuditActionCategory.PERMISSION
    assert rec.actor_kind.value == "user"
    assert rec.action == "resource_permission_check"


def test_record_access_granted_and_denied_metadata() -> None:
    audit = AuditService(org_id="org-1")
    g = audit.record_access_granted(
        record_id="g-1", actor_id="u1", action="resource_access_granted", target="proj-1"
    )
    d = audit.record_access_denied(
        record_id="d-1", actor_id="u1", action="resource_access_denied", target="proj-1",
        detail="decision=denied",
    )
    for r in (g, d):
        assert r.category == AuditActionCategory.PERMISSION
        assert r.actor_kind.value == "user"


def test_query_filters_by_permission_category() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_permission_check(record_id="pc-1", actor_id="u1", action="x", target="t")
    audit.record_ai_action(record_id="ai-1", actor_id="ai", action="y", target="t")
    perm_recs = audit.query(category=AuditActionCategory.PERMISSION)
    assert len(perm_recs) == 1
    assert perm_recs[0].action == "x"
    # 不带 category 时返回全部
    assert len(audit.query()) == 2


def test_query_filters_by_target() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_permission_check(record_id="pc-1", actor_id="u1", action="x", target="proj-1")
    audit.record_permission_check(record_id="pc-2", actor_id="u1", action="x", target="proj-2")
    assert len(audit.query(category=AuditActionCategory.PERMISSION, target="proj-1")) == 1


def test_record_human_approval_is_forbidden_red_line_six() -> None:
    audit = AuditService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        audit.record_human_approval(  # type: ignore[attr-defined]
            record_id="bad", actor_id="ai", action="fake_approval"
        )


def test_audit_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        AuditService(org_id="org-1")


def test_audit_write_fail_closed_under_enabled(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    audit = AuditService.__new__(AuditService)  # 绕过 __init__ 护栏
    audit._org_id = "org-1"
    audit._records = []
    with pytest.raises(EnterpriseRedLineViolationError):
        audit.record_permission_check(record_id="pc-x", actor_id="u1", action="x")

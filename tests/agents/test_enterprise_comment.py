"""Enterprise Operation Layer —— 测试：协作评论模型（任务2，Phase 3.8.2）。

覆盖：
- Comment 三类资源（PROJECT / TASK / REVIEW）与字段（author / timestamp / resource）。
- CommentService 新增 / 读取 / 列表（按资源类型 / 资源 id 过滤）。
- 跨域访问抛 EnterpriseIsolationError（组织隔离，fail-closed）。
- 写路径联动审计（record_comment_action，actor 真实）。
- CommentService 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.comment import Comment, CommentResourceKind, CommentService
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_add_comment_three_resource_kinds() -> None:
    svc = CommentService(org_id="org-1")
    p = svc.add_comment(comment_id="C1", author_id="u1", resource_kind="project",
                        resource_id="P1", content="项目说明", timestamp="t1")
    tk = svc.add_comment(comment_id="C2", author_id="u2", resource_kind="task",
                         resource_id="T1", content="请复核", timestamp="t2")
    rv = svc.add_comment(comment_id="C3", author_id="u3", resource_kind="review",
                         resource_id="R1", content="审核意见", timestamp="t3")
    assert p.resource_kind == CommentResourceKind.PROJECT
    assert tk.resource_kind == CommentResourceKind.TASK
    assert rv.resource_kind == CommentResourceKind.REVIEW
    assert all(isinstance(c, Comment) for c in (p, tk, rv))
    assert p.author_id == "u1" and p.timestamp == "t1"


def test_list_comments_filter_by_resource() -> None:
    svc = CommentService(org_id="org-1")
    svc.add_comment(comment_id="C1", author_id="u1", resource_kind="task", resource_id="T1", content="a")
    svc.add_comment(comment_id="C2", author_id="u2", resource_kind="task", resource_id="T1", content="b")
    svc.add_comment(comment_id="C3", author_id="u3", resource_kind="project", resource_id="P1", content="c")
    assert len(svc.list_comments(resource_kind="task")) == 2
    assert len(svc.list_comments(resource_kind="task", resource_id="T1")) == 2
    assert len(svc.list_comments(resource_id="P1")) == 1


def test_cross_org_isolation_raises() -> None:
    svc1 = CommentService(org_id="org-1")
    svc2 = CommentService(org_id="org-2")
    svc2.add_comment(comment_id="C2", author_id="u2", resource_kind="task", resource_id="T2", content="x")
    with pytest.raises(EnterpriseIsolationError):
        svc1.get(comment_id="C2")


def test_comment_audit_linkage_records_real_actor() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = CommentService(org_id="org-1", audit=audit)
    svc.add_comment(comment_id="C1", author_id="u1", resource_kind="task", resource_id="T1",
                    content="hi", timestamp="t1")
    collab = audit.query(category=AuditActionCategory.COLLABORATION)
    assert len(collab) == 1
    assert collab[0].action == "add_comment"
    assert collab[0].actor_id == "u1"
    assert collab[0].actor_kind == AuditActorKind.USER


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        CommentService(org_id="org-1")

"""Enterprise Operation Layer —— 协作评论模型（任务2，Phase 3.8.2）。

新增：``Comment``，支持「项目评论 / 任务评论 / 审核评论」三类资源，记录真实作者与时间戳。

隔离与耦合约束：
- 评论以字符串外键引用资源（``resource_id`` + ``resource_kind``），**绝不**反向依赖
  工程模块内部类型，保持零耦合。
- 所有评论按 ``org_id`` 作用域过滤；跨域访问由 ``OrganizationService.assert_same_org``
  在调用层统一拦截（fail-closed）。
- ``CommentService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；如实记录 author（真实发起方，红线⑥）。
- 可选联动 ``AuditService.record_comment_action``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class CommentResourceKind(str, Enum):
    """评论挂载的资源类型（项目 / 任务 / 审核）。"""

    PROJECT = "project"
    TASK = "task"
    REVIEW = "review"


@dataclass
class Comment:
    """协作评论（任务2）。

    记录 author / timestamp / resource（resource_kind + resource_id），并要求组织隔离。
    """

    comment_id: str
    org_id: str
    author_id: str
    resource_kind: CommentResourceKind
    resource_id: str
    content: str
    timestamp: str = ""


class CommentService:
    """协作评论服务（任务2）。

    仅做评论登记与读取；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 CommentService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._comments: dict[str, Comment] = {}

    def add_comment(
        self,
        *,
        comment_id: str,
        author_id: str,
        resource_kind: "CommentResourceKind | str",
        resource_id: str,
        content: str,
        timestamp: str = "",
    ) -> Comment:
        """在组织内新增评论（仅登记；author 为真实发起方）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下新增评论（红线①/⑤）"
            )
        kind = (
            resource_kind
            if isinstance(resource_kind, CommentResourceKind)
            else CommentResourceKind(resource_kind)
        )
        comment = Comment(
            comment_id=comment_id,
            org_id=self._org_id,
            author_id=author_id,
            resource_kind=kind,
            resource_id=resource_id,
            content=content,
            timestamp=timestamp,
        )
        self._comments[comment_id] = comment
        if self._audit is not None:
            self._audit.record_comment_action(
                record_id=f"comment-add-{comment_id}",
                actor_id=author_id,
                action="add_comment",
                target=resource_id,
                detail=f"kind={kind.value}",
                ts=timestamp,
            )
        return comment

    def get(self, *, comment_id: str) -> Comment:
        """按组织作用域读取评论（跨域访问抛隔离错误）。"""
        return self._get_scoped(comment_id)

    def list_comments(
        self,
        *,
        resource_kind: "CommentResourceKind | str | None" = None,
        resource_id: str = "",
    ) -> list[Comment]:
        """列出当前组织下评论（可按资源类型 / 资源 id 过滤）。"""
        out = [c for c in self._comments.values() if c.org_id == self._org_id]
        if resource_kind is not None:
            kind = (
                resource_kind
                if isinstance(resource_kind, CommentResourceKind)
                else CommentResourceKind(resource_kind)
            )
            out = [c for c in out if c.resource_kind == kind]
        if resource_id:
            out = [c for c in out if c.resource_id == resource_id]
        return out

    def _get_scoped(self, comment_id: str) -> Comment:
        from agents.enterprise.organization import EnterpriseIsolationError

        comment = self._comments.get(comment_id)
        if comment is None:
            raise EnterpriseIsolationError(f"评论 {comment_id!r} 不存在")
        if comment.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"评论 {comment_id!r} 归属组织 {comment.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return comment


__all__ = ["CommentResourceKind", "Comment", "CommentService"]

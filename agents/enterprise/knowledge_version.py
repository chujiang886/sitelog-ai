"""Enterprise Knowledge Governance & Version Control Layer —— 知识版本与生命周期（任务1+2，Phase 3.8.8）。

新增：
- ``VersionStatus``：版本状态（draft / reviewing / active / deprecated）。
- ``KnowledgeVersion``：知识版本（version_id / knowledge_id / version / content_hash /
  source / created_by / created_at / status）；版本可追踪。
- ``KnowledgeLifecycleService``：知识生命周期服务，提供 create_version / submit_review /
  activate_version / deprecate_version。

红线（fail-closed，复用 3.8.0~3.8.7 基座 + 3.8.8 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **activate_version 必须由真实 USER 执行**（``require_human_actor``，红线⑥）：AI 不得激活
  任何版本为 active（禁 AI 自动 active，任务1 明确要求）。
- **deprecate_version 必须由真实 USER 执行**（红线⑥）：弃用是权威性状态变更，AI 不得代行。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动落地/发布/合并/批准入口（``auto_update_knowledge`` / ``auto_publish_knowledge``
  / ``auto_merge_knowledge`` / ``auto_approve_knowledge`` / ``publish`` / ``auto_activate``
  / ``apply`` / ``merge`` / ``commit`` / ``write``，红线③/⑤）。
- 本服务**不**承载任何经营决策/审批/管理建议入口（auto_business_decision / decide 等，红线④/⑤）。
- 可选联动 ``AuditService.record_knowledge_version_action`` 如实标注发起方 actor
  （AI 创建默认 AI，激活/弃用节点显式 USER，红线⑥）。

代码库无 KnowledgeRepository：本服务仅维护版本元数据与状态流转，**绝不**写入任何知识资产
（red line ③），版本 active 后的知识落地须由真实人工在知识库侧执行。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


class VersionStatus(str, Enum):
    """知识版本状态（任务1）。

    draft → reviewing → active → deprecated。状态流转由 ``KnowledgeLifecycleService`` 控制；
    active 仅能由真实人工激活（红线⑥），AI 不得自动 active。
    """

    DRAFT = "draft"
    REVIEWING = "reviewing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class KnowledgeVersion:
    """知识版本（任务1）。

    版本可追踪：同一 ``knowledge_id`` 可有多条版本记录，每条携带内容哈希与状态，支持审计溯源。
    ``status`` 初始为 ``DRAFT``，**禁 AI 自动 active**（须人工激活，红线⑥）。

    ``org_id`` 为 Enterprise 层统一组织隔离字段（与 ``KnowledgeUpdateCandidate`` 一致）。
    """

    version_id: str
    knowledge_id: str
    version: int                       # 同一 knowledge_id 下的单调递增版本号
    content_hash: str                  # 内容 sha256（缺省时由 content 派生）
    source: str                       # 版本来源（如 candidate-xxx / manual / import ...）
    created_by: str                    # 版本创建者（actor_id）
    org_id: str = ""                   # 归属组织（隔离作用域）
    created_at: str = ""
    status: VersionStatus = VersionStatus.DRAFT

    def __post_init__(self) -> None:
        # status 统一以枚举存储，避免字符串漂移。
        if not isinstance(self.status, VersionStatus):
            self.status = VersionStatus(self.status)


class KnowledgeLifecycleService(_RedLineForbiddenMixin):
    """知识生命周期服务（任务2）。

    提供 create_version / submit_review / activate_version / deprecate_version。
    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。

    **activate_version / deprecate_version 必须由真实 USER 执行**（红线⑥）：AI 不得激活或弃用
    版本。本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize
    / record_human_approval / auto_update_knowledge / auto_publish_knowledge /
    auto_merge_knowledge / auto_approve_knowledge 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并知识（核心：版本仅元数据，绝不写知识资产）
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "publish",
        "auto_activate",
        "apply",
        "merge",
        "commit",
        "write",
        # 红线④/⑤：禁止自动经营决策 / 审批 / 管理建议
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "AnalyticsVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeLifecycleService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._versions: dict[str, KnowledgeVersion] = {}
        self._knowledge_versions: dict[str, list[str]] = {}  # knowledge_id -> [version_id]

    def create_version(
        self,
        *,
        version_id: str,
        knowledge_id: str,
        content: str,
        source: str,
        created_by: str = "ai",
        content_hash: str = "",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeVersion:
        """创建一条知识版本（默认 AI 创建，状态恒为 DRAFT，待人工复核与激活）。

        本方法**只**登记版本元数据，**绝不**写入任何知识资产（red line ③）。版本创建后如实
        记录 ``record_knowledge_version_action``（actor 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建知识版本（红线①/⑤）"
            )
        chash = content_hash or self._hash_content(content)
        # 计算同一 knowledge_id 下的下一个版本号。
        seq = self._knowledge_versions.get(knowledge_id, [])
        version_no = len(seq) + 1
        ver = KnowledgeVersion(
            version_id=version_id,
            knowledge_id=knowledge_id,
            version=version_no,
            content_hash=chash,
            source=source,
            created_by=created_by,
            org_id=self._org_id,
            created_at=created_at,
            status=VersionStatus.DRAFT,
        )
        self._versions[version_id] = ver
        self._knowledge_versions.setdefault(knowledge_id, []).append(version_id)
        if self._audit is not None:
            self._audit.record_knowledge_version_action(
                record_id=f"version-{version_id}",
                actor_id=actor_id,
                action="create_knowledge_version",
                target=version_id,
                detail=(
                    f"knowledge_id={knowledge_id};version={version_no};"
                    f"content_hash={chash};source={source}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return ver

    def submit_review(
        self,
        *,
        version_id: str,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
        ts: str = "",
    ) -> KnowledgeVersion:
        """将版本从 DRAFT 转入 REVIEWING（提交人工复核）。

        这是非权威状态流转：仅「标记待审」，仍须人工 ``activate_version`` 才能 active（红线⑥）。
        AI 可提交以供复核，但不得代行激活。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交版本复核（红线①/⑤）"
            )
        ver = self._get_scoped(version_id)
        if ver.status != VersionStatus.DRAFT:
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 DRAFT 可提交复核"
            )
        ver.status = VersionStatus.REVIEWING
        if self._audit is not None:
            self._audit.record_knowledge_version_action(
                record_id=f"version-review-{version_id}",
                actor_id=actor_id,
                action="submit_version_review",
                target=version_id,
                detail=f"knowledge_id={ver.knowledge_id};status=reviewing",
                ts=ts,
                actor_kind=actor_kind,
            )
        return ver

    def activate_version(
        self,
        *,
        version_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
    ) -> KnowledgeVersion:
        """激活版本为 ACTIVE —— **必须由真实 USER 执行**（红线⑥）。

        AI 不得激活（``require_human_actor`` 守卫）。仅 REVIEWING 状态可激活；激活后如实记录
        ``KNOWLEDGE_VERSION`` 审计（actor_kind 强制 USER）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下激活知识版本（红线①/⑤）"
            )
        # 红线⑥：激活是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        ver = self._get_scoped(version_id)
        if ver.status != VersionStatus.REVIEWING:
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 REVIEWING 可被人工激活"
            )
        ver.status = VersionStatus.ACTIVE
        if self._audit is not None:
            self._audit.record_knowledge_version_action(
                record_id=f"version-activate-{version_id}",
                actor_id=actor_id,
                action="activate_knowledge_version",
                target=version_id,
                detail=f"knowledge_id={ver.knowledge_id};status=active",
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )
        return ver

    def deprecate_version(
        self,
        *,
        version_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
    ) -> KnowledgeVersion:
        """弃用版本为 DEPRECATED —— **必须由真实 USER 执行**（红线⑥）。

        弃用是权威性状态变更（会让某版本退出可用集），AI 不得代行。仅 ACTIVE / REVIEWING
        可被人工弃用；弃用后如实记录 ``KNOWLEDGE_VERSION`` 审计（actor_kind 强制 USER）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下弃用知识版本（红线①/⑤）"
            )
        # 红线⑥：弃用是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        ver = self._get_scoped(version_id)
        if ver.status in (VersionStatus.DRAFT, VersionStatus.DEPRECATED):
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 ACTIVE/REVIEWING 可被人工弃用"
            )
        ver.status = VersionStatus.DEPRECATED
        if self._audit is not None:
            self._audit.record_knowledge_version_action(
                record_id=f"version-deprecate-{version_id}",
                actor_id=actor_id,
                action="deprecate_knowledge_version",
                target=version_id,
                detail=f"knowledge_id={ver.knowledge_id};status=deprecated",
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )
        return ver

    def get(self, *, version_id: str) -> KnowledgeVersion:
        """按组织作用域读取版本（跨域访问抛隔离错误）。"""
        return self._get_scoped(version_id)

    def list_versions(
        self,
        *,
        knowledge_id: str = "",
        status: "VersionStatus | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[KnowledgeVersion]:
        """列出当前组织下版本（可按 knowledge_id / status 过滤）。"""
        out = [v for v in self._versions.values() if v.org_id == self._org_id]
        if knowledge_id:
            out = [v for v in out if v.knowledge_id == knowledge_id]
        if status is not None:
            out = [v for v in out if v.status == status]
        return out

    def active_version(self, *, knowledge_id: str) -> "KnowledgeVersion | None":
        """返回某 knowledge_id 当前的 ACTIVE 版本（若有）。"""
        actives = [
            v
            for v in self._versions.values()
            if v.knowledge_id == knowledge_id
            and v.org_id == self._org_id
            and v.status == VersionStatus.ACTIVE
        ]
        return actives[-1] if actives else None

    def _get_scoped(self, version_id: str) -> KnowledgeVersion:
        from agents.enterprise.organization import EnterpriseIsolationError

        ver = self._versions.get(version_id)
        if ver is None:
            raise EnterpriseIsolationError(f"知识版本 {version_id!r} 不存在")
        if ver.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识版本 {version_id!r} 归属组织 {ver.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return ver

    @staticmethod
    def _hash_content(content: str) -> str:
        """对内容派生确定性 sha256（小写 hex）。"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "VersionStatus",
    "KnowledgeVersion",
    "KnowledgeLifecycleService",
]

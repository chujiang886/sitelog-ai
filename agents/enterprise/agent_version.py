"""Enterprise Agent Capability Registry & Governance Layer —— 智能体版本管理（任务3，Phase 3.8.13）。

新增：
- ``AgentVersionStatus``：版本状态（draft / reviewing / active / deprecated）。
- ``AgentVersion``：智能体版本（version_id / agent_id / version / change_log / created_by /
  created_at / status / org_id）；版本可追踪。
- ``AgentVersionManager``：智能体版本生命周期管理（create_version / submit_review /
  activate_version / deprecate_version）。

红线（fail-closed，复用 3.8.0 基座 + 3.8.13 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **activate_version / deprecate_version 必须由真实 USER 执行**（``require_human_actor``，
  红线⑥）：AI 不得激活或弃用智能体版本（对应任务1「active必须人工确认」）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval`` / ``publish`` / ``auto_activate`` / ``apply`` 等
  方法（红线②/③/④/⑥）。
- 版本仅元数据与状态流转，**绝不**写入任何智能体运行态/知识资产（red line ③）；版本 active
  后的智能体落地须由真实人工在运行侧执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class AgentVersionStatus(str, Enum):
    """智能体版本状态（任务3）。

    draft → reviewing → active → deprecated。ACTIVE 仅能由真实人工激活（红线⑥）。
    """

    DRAFT = "draft"
    REVIEWING = "reviewing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class AgentVersion:
    """智能体版本（任务3）。

    版本可追踪：同一 ``agent_id`` 可有多条版本记录，每条携带变更日志与状态，支持审计溯源。
    ``status`` 初始为 ``DRAFT``，**禁 AI 自动 active**（须人工激活，红线⑥）。
    """

    version_id: str
    agent_id: str
    version: int                       # 同一 agent_id 下的单调递增版本号
    change_log: str
    created_by: str = "ai"             # 版本创建者（actor_id）
    org_id: str = ""                   # 归属组织（隔离作用域）
    created_at: str = ""
    status: AgentVersionStatus = AgentVersionStatus.DRAFT

    def __post_init__(self) -> None:
        # status 统一以枚举存储，避免字符串漂移。
        if not isinstance(self.status, AgentVersionStatus):
            self.status = AgentVersionStatus(self.status)


class AgentVersionManager(_RedLineForbiddenMixin):
    """智能体版本生命周期管理（任务3）。

    提供 create_version / submit_review / activate_version / deprecate_version。
    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    activate_version / deprecate_version 必须由真实 USER 执行（红线⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_activate",
        "apply",
        "publish",
        "write",
        "decide",
        "recommend",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: Any = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentVersionManager（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._versions: Dict[str, AgentVersion] = {}
        self._agent_versions: Dict[str, List[str]] = {}  # agent_id -> [version_id]

    def create_version(
        self,
        *,
        version_id: str,
        agent_id: str,
        change_log: str,
        created_by: str = "ai",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentVersion:
        """创建一条智能体版本（默认 AI 创建，状态恒为 DRAFT，待人工复核与激活）。

        本方法**只**登记版本元数据，**绝不**写入任何运行态/知识资产（red line ③）。版本创建后
        如实记录 ``record_agent_version_action``（actor 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建智能体版本（红线①/⑤）"
            )
        # 计算同一 agent_id 下的下一个版本号。
        seq = self._agent_versions.get(agent_id, [])
        version_no = len(seq) + 1
        ver = AgentVersion(
            version_id=version_id,
            agent_id=agent_id,
            version=version_no,
            change_log=change_log,
            created_by=created_by,
            org_id=self._org_id,
            created_at=created_at,
            status=AgentVersionStatus.DRAFT,
        )
        self._versions[version_id] = ver
        self._agent_versions.setdefault(agent_id, []).append(version_id)
        if self._audit is not None:
            self._audit.record_agent_version_action(
                record_id=f"agent-version-{version_id}",
                actor_id=actor_id,
                action="create_agent_version",
                target=version_id,
                detail=(
                    f"agent_id={agent_id};version={version_no};change_log={change_log}"
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
    ) -> AgentVersion:
        """将版本从 DRAFT 转入 REVIEWING（提交人工复核）。

        非权威状态流转：仅「标记待审」，仍须人工 ``activate_version`` 才能 active（红线⑥）。
        AI 可提交以供复核，但不得代行激活。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交智能体版本复核（红线①/⑤）"
            )
        ver = self._get_scoped(version_id)
        if ver.status != AgentVersionStatus.DRAFT:
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 DRAFT 可提交复核"
            )
        ver.status = AgentVersionStatus.REVIEWING
        if self._audit is not None:
            self._audit.record_agent_version_action(
                record_id=f"agent-version-review-{version_id}",
                actor_id=actor_id,
                action="submit_agent_version_review",
                target=version_id,
                detail=f"agent_id={ver.agent_id};status=reviewing",
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
    ) -> AgentVersion:
        """激活版本为 ACTIVE —— **必须由真实 USER 执行**（红线⑥）。

        AI 不得激活（``require_human_actor`` 守卫）。仅 REVIEWING 状态可激活；激活后如实记录
        ``AGENT_VERSION`` 审计（actor_kind 强制 USER）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下激活智能体版本（红线①/⑤）"
            )
        # 红线⑥：激活是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        ver = self._get_scoped(version_id)
        if ver.status != AgentVersionStatus.REVIEWING:
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 REVIEWING 可被人工激活"
            )
        ver.status = AgentVersionStatus.ACTIVE
        if self._audit is not None:
            self._audit.record_agent_version_action(
                record_id=f"agent-version-activate-{version_id}",
                actor_id=actor_id,
                action="activate_agent_version",
                target=version_id,
                detail=f"agent_id={ver.agent_id};status=active",
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
    ) -> AgentVersion:
        """弃用版本为 DEPRECATED —— **必须由真实 USER 执行**（红线⑥）。

        弃用是权威性状态变更（会让某版本退出可用集），AI 不得代行。仅 ACTIVE / REVIEWING
        可被人工弃用；弃用后如实记录 ``AGENT_VERSION`` 审计（actor_kind 强制 USER）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下弃用智能体版本（红线①/⑤）"
            )
        # 红线⑥：弃用是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        ver = self._get_scoped(version_id)
        if ver.status in (AgentVersionStatus.DRAFT, AgentVersionStatus.DEPRECATED):
            raise ValueError(
                f"版本 {version_id!r} 当前状态为 {ver.status.value!r}，"
                f"仅 ACTIVE/REVIEWING 可被人工弃用"
            )
        ver.status = AgentVersionStatus.DEPRECATED
        if self._audit is not None:
            self._audit.record_agent_version_action(
                record_id=f"agent-version-deprecate-{version_id}",
                actor_id=actor_id,
                action="deprecate_agent_version",
                target=version_id,
                detail=f"agent_id={ver.agent_id};status=deprecated",
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )
        return ver

    def get(self, *, version_id: str) -> AgentVersion:
        """按组织作用域读取版本（跨域访问抛隔离错误）。"""
        return self._get_scoped(version_id)

    def list_versions(
        self,
        *,
        agent_id: str = "",
        status: "AgentVersionStatus | None" = None,
    ) -> List[AgentVersion]:
        """列出当前组织下版本（可按 agent_id / status 过滤）。"""
        out = [v for v in self._versions.values() if v.org_id == self._org_id]
        if agent_id:
            out = [v for v in out if v.agent_id == agent_id]
        if status is not None:
            out = [v for v in out if v.status == status]
        return out

    def active_version(self, *, agent_id: str) -> "AgentVersion | None":
        """返回某 agent_id 当前的 ACTIVE 版本（若有）。"""
        actives = [
            v
            for v in self._versions.values()
            if v.agent_id == agent_id
            and v.org_id == self._org_id
            and v.status == AgentVersionStatus.ACTIVE
        ]
        return actives[-1] if actives else None

    def latest_version(self, *, agent_id: str) -> "AgentVersion | None":
        """返回某 agent_id 最新（最后登记）的版本（不限状态），用于状态推进。"""
        ids = self._agent_versions.get(agent_id, [])
        if not ids:
            return None
        return self._versions[ids[-1]]

    def _get_scoped(self, version_id: str) -> AgentVersion:
        from agents.enterprise.organization import EnterpriseIsolationError

        ver = self._versions.get(version_id)
        if ver is None:
            raise EnterpriseIsolationError(f"智能体版本 {version_id!r} 不存在")
        if ver.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"智能体版本 {version_id!r} 归属组织 {ver.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return ver


__all__ = [
    "AgentVersionStatus",
    "AgentVersion",
    "AgentVersionManager",
]

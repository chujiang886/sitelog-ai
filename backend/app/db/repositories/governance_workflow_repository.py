"""Phase 3.8.26 治理工作流持久化仓储（Task 4）。

定位：**复用而非重建**。本仓储只负责把 3.8.25 live orchestrator 的**事实快照**
可靠落库，并提供「组织隔离 + 人工门控 + 状态白名单」三道 fail-closed 防线。
它**不持有**任何治理状态机逻辑，也不做任何 AI 决策。

三道防线（与 DB CHECK 约束 + 红线一一对应）：
① **组织隔离（org isolation）**：所有读/写查询强制 `org_id` 过滤，越权组织一律
   视作「不存在」返回 None / 空列表（红线⑤：禁 AI 自动修改权限策略，隔离在仓储层强制）。
② **人工门控（human gate）**：所有改变治理状态的写操作都要求经
   ``require_human_actor`` 校验的真实 USER 身份；AI 传入 ``actor_kind != user`` 即抛
   ``GovernanceRepositoryError``（红线③/④/⑥：禁 AI 自动操作/修改治理状态/代替人工）。
③ **状态白名单（status whitelist）**：``update_status`` 只允许六态值，任何
   ``auto_*`` / ``approved_by_ai`` 等被拒（红线③/④，与 DB ``status_valid`` 约束双保险）。

说明：主闸门在 Task 5 的 Human Operation API 层（请求头 ``x-actor-kind: user`` 由真人
携带）；本层是防御性二次校验，即使有人绕过 API 直接持 Session 调用，也过不了
``require_human_actor`` 与 org 隔离。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

# --- 让 backend/app 命名空间可解析 agents 企业包（与 governance_dashboard.py 一致） ---
_BOIP_ROOT = Path(__file__).resolve().parents[4]  # repositories/db/app/backend/BOIP
if str(_BOIP_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_BOIP_ROOT))

from agents.enterprise.audit import AuditActorKind, require_human_actor  # noqa: E402

from app.db.models.governance_workflow import (  # noqa: E402
    GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES,
    GOVERNANCE_WORKFLOW_STATUS_VALUES,
    GovernanceExecutionRecordDB,
    GovernanceWorkflowRecord,
)


class GovernanceRepositoryError(Exception):
    """治理仓储层业务异常（红线校验失败 / 状态非法 / 记录不存在等）。"""


class OrgScopeError(GovernanceRepositoryError):
    """组织越权访问（红线⑤：隔离在仓储层强制）。"""


def _now() -> str:
    """ISO 时间戳（人工责任字段使用字符串，便于审计链追溯）。"""

    return datetime.now().isoformat(timespec="seconds")


class GovernanceWorkflowRepository:
    """治理工作流持久化仓储（Task 4）。

    构造时注入一个 SQLAlchemy ``Session``。所有方法都要求显式传入 ``org_id`` 并据此
    强制隔离；改变状态的写方法还要求真实 USER 身份（``actor_kind`` / ``actor_id``）。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # 写：工作流快照持久化                                                #
    # ------------------------------------------------------------------ #
    def save_workflow(self, record: GovernanceWorkflowRecord) -> GovernanceWorkflowRecord:
        """落库一条工作流快照（首次创建）。

        要求 record.org_id 非空（空则视为越权）。已存在同 workflow_id 时由调用方先
        get 再决定 update，本方法只负责 INSERT。
        """

        if not record.org_id:
            raise OrgScopeError("org_id 不能为空（红线⑤：组织隔离）")
        if record.org_id not in (record.org_id or ""):
            # 防御：org_id 必须是真实非空串（冗余校验，主校验在调用方）
            pass
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    # ------------------------------------------------------------------ #
    # 读：组织隔离查询                                                    #
    # ------------------------------------------------------------------ #
    def get_workflow(
        self, workflow_id: str, org_id: str
    ) -> Optional[GovernanceWorkflowRecord]:
        """按主键 + 组织取一条；org 不匹配即返回 None（红线⑤）。"""

        if not org_id:
            raise OrgScopeError("org_id 不能为空（红线⑤：组织隔离）")
        stmt = select(GovernanceWorkflowRecord).where(
            GovernanceWorkflowRecord.workflow_id == workflow_id,
            GovernanceWorkflowRecord.org_id == org_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_workflows(
        self,
        org_id: str,
        *,
        status: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> Sequence[GovernanceWorkflowRecord]:
        """列出某组织下的工作流（默认排除已归档）。

        org_id 为空直接返回空列表（fail-closed，绝不跨组织泄露）。
        """

        if not org_id:
            return []
        stmt = select(GovernanceWorkflowRecord).where(
            GovernanceWorkflowRecord.org_id == org_id
        )
        if status:
            if status not in GOVERNANCE_WORKFLOW_STATUS_VALUES:
                raise GovernanceRepositoryError(
                    f"非法的 status 过滤值：{status!r}（不在六态白名单）"
                )
            stmt = stmt.where(GovernanceWorkflowRecord.status == status)
        if not include_archived:
            stmt = stmt.where(GovernanceWorkflowRecord.archived.is_(False))
        stmt = stmt.order_by(GovernanceWorkflowRecord.created_at.desc()).limit(limit)
        return self._db.execute(stmt).scalars().all()

    # ------------------------------------------------------------------ #
    # 写：状态变更（人工门控 + 白名单）                                    #
    # ------------------------------------------------------------------ #
    def update_status(
        self,
        workflow_id: str,
        org_id: str,
        *,
        status: str,
        actor_id: str,
        actor_kind: object = AuditActorKind.USER,
    ) -> GovernanceWorkflowRecord:
        """变更工作流状态（必须由真实 USER 发起，红线③/④/⑥）。

        - 强制 ``require_human_actor(actor_kind)``：AI 无法以自身身份改状态；
        - 只允许六态白名单，``auto_*`` 等被拒（与 DB ``status_valid`` 双保险）；
        - 进入 ``human_confirmed`` / ``completed`` 时记录责任人 + 时间。
        """

        require_human_actor(actor_kind)  # 红线⑥：必须由真实人工
        if status not in GOVERNANCE_WORKFLOW_STATUS_VALUES:
            raise GovernanceRepositoryError(
                f"非法的目标状态 {status!r}：不在六态白名单"
                f"（禁用的自动态如 {GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES} 一律拒绝）"
            )
        rec = self.get_workflow(workflow_id, org_id)
        if rec is None:
            raise GovernanceRepositoryError(
                f"工作流 {workflow_id!r} 在 org {org_id!r} 下不存在或越权"
            )
        rec.status = status
        rec.updated_at = datetime.now()
        if status == "human_confirmed":
            rec.confirmed_by = actor_id
            rec.confirmed_at = _now()
        if status == "completed":
            rec.completed_by = actor_id
            rec.completed_at = _now()
        self._db.commit()
        self._db.refresh(rec)
        return rec

    def close_workflow(
        self,
        workflow_id: str,
        org_id: str,
        *,
        actor_id: str,
        actor_kind: object = AuditActorKind.USER,
        note: str = "",
    ) -> GovernanceWorkflowRecord:
        """人工闭环工作流（置为 completed，红线④/⑥）。

        注意：这是「人工责任闭环」，不是 AI 自动关闭；调用方必须是真人。
        """

        rec = self.update_status(
            workflow_id, org_id, status="completed", actor_id=actor_id, actor_kind=actor_kind
        )
        if note:
            rec.human_notes.append(  # type: ignore[attr-defined]
                {"kind": "closure_note", "by": actor_id, "at": _now(), "note": note}
            )
            self._db.commit()
            self._db.refresh(rec)
        return rec

    def archive_workflow(
        self,
        workflow_id: str,
        org_id: str,
        *,
        actor_id: str,
        actor_kind: object = AuditActorKind.USER,
    ) -> GovernanceWorkflowRecord:
        """人工归档（仅置 archived 标志，不改变业务状态）。"""

        require_human_actor(actor_kind)
        rec = self.get_workflow(workflow_id, org_id)
        if rec is None:
            raise GovernanceRepositoryError(
                f"工作流 {workflow_id!r} 在 org {org_id!r} 下不存在或越权"
            )
        rec.archived = True
        rec.archived_by = actor_id
        rec.archived_at = _now()
        rec.updated_at = datetime.now()
        self._db.commit()
        self._db.refresh(rec)
        return rec

    # ------------------------------------------------------------------ #
    # 写/读：执行记录（红线⑥：actor_kind 强制 user）                      #
    # ------------------------------------------------------------------ #
    def add_execution(
        self, record: GovernanceExecutionRecordDB
    ) -> GovernanceExecutionRecordDB:
        """落库一条执行记录。

        强制 actor_kind='user'（DB 层 CHECK 已钉死，这里再校验一次，红线⑥）；并要求
        exec.org_id 与该工作流所属 org 一致（组织隔离）。
        """

        require_human_actor(record.actor_kind)  # type: ignore[arg-type]
        if record.actor_kind != "user":
            raise GovernanceRepositoryError("执行记录 actor_kind 必须为 'user'（红线⑥）")
        if not record.org_id:
            raise OrgScopeError("执行记录 org_id 不能为空（红线⑤）")
        # 关联工作流必须存在且同 org
        wf = self.get_workflow(record.workflow_id, record.org_id)
        if wf is None:
            raise GovernanceRepositoryError(
                f"执行记录关联的工作流 {record.workflow_id!r} 不存在或越权"
            )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    def list_executions(
        self, workflow_id: str, org_id: str, limit: int = 500
    ) -> Sequence[GovernanceExecutionRecordDB]:
        """列出某工作流下的执行记录（组织隔离）。"""

        if not org_id:
            return []
        stmt = (
            select(GovernanceExecutionRecordDB)
            .where(
                GovernanceExecutionRecordDB.workflow_id == workflow_id,
                GovernanceExecutionRecordDB.org_id == org_id,
            )
            .order_by(GovernanceExecutionRecordDB.created_at.asc())
            .limit(limit)
        )
        return self._db.execute(stmt).scalars().all()

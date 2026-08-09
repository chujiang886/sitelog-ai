"""Phase 3.8.26 企业智能体治理持久化模型（Task 1 / Task 2）。

定位：**复用而非重建**。Phase 3.8.25 的
``agents.enterprise.governance_workflow.orchestrator.GovernanceWorkflowOrchestrator``
是治理状态的**单一真相源**（内存态六态机）；本模块只把该真相源的**事实快照**
落到关系库，使治理工作流在进程重启后仍可被真实责任人查看与继续处置。

两张表：
- ``GovernanceWorkflowRecord``（``governance_workflow_records``）：工作流状态持久化
  （Task 1，主理人明列字段 workflow_id / status / source_id / created_at /
  updated_at / org_id）。
- ``GovernanceExecutionRecordDB``（``governance_execution_records``）：执行记录持久化
  （Task 2，保存执行记录、人工结果、来源链、审计关联）。

红线在**数据库类型层**的落法（fail-closed，DB 级不可绕过）：
① ``engineering_enabled`` 保持 False —— 本模块不含任何激活态字段，也不提供写开关。
② 禁 ``engineering_approved`` —— 两表**刻意不存在** approve / approved /
   engineering_approved / quote / sign 任何列；``_FORBIDDEN_COLUMN_NAMES``
   供测试做结构级自检。
③ 禁 AI 自动操作治理流程 —— ``ck_governance_workflow_records_status_valid``
   只允许六态 ``created / under_review / human_confirmed / in_progress /
   waiting_result / completed``；``auto_approved`` / ``auto_executed`` /
   ``auto_closed`` 在 DB 约束层即写不进去。
④ 禁 AI 自动修改治理状态 —— ``requires_human_confirmation`` 由
   ``ck_governance_workflow_records_requires_human`` 强制恒真，任何把它置 False
   的 UPDATE 都会被数据库拒绝。
⑤ 禁 AI 自动修改权限策略 —— 本模块不含任何权限/策略列，``org_id`` 为
   NOT NULL + 索引，隔离在仓储层强制。
⑥ 禁 AI 代替人工操作 —— ``ck_governance_execution_records_actor_kind_user``
   强制执行记录 ``actor_kind='user'``：AI 无法在数据库里登记「自己执行了治理动作」。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base

# ---------------------------------------------------------------------------
# 类型层白名单 / 黑名单（供 DB 约束与结构级测试共用，避免手抄漂移）
# ---------------------------------------------------------------------------

#: 与 3.8.25 ``GovernanceWorkflowStatus`` 六态严格一致（顺序即状态机前进顺序）。
GOVERNANCE_WORKFLOW_STATUS_VALUES: tuple[str, ...] = (
    "created",
    "under_review",
    "human_confirmed",
    "in_progress",
    "waiting_result",
    "completed",
)

#: 红线③/④：这些「自动态」在数据库 CHECK 约束层即不可表达。
GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES: tuple[str, ...] = (
    "auto_approved",
    "auto_executed",
    "auto_closed",
    "auto_completed",
    "auto_confirmed",
    "closed_by_ai",
    "approved_by_ai",
)

#: 红线②/⑥：两张表**永远不得**出现的列名（测试做结构级断言）。
_FORBIDDEN_COLUMN_NAMES: tuple[str, ...] = (
    "engineering_approved",
    "engineering_enabled",
    "approved",
    "approval",
    "approved_by",
    "auto_approved",
    "auto_confirmed",
    "auto_executed",
    "auto_closed",
    "quote",
    "price",
    "pricing",
    "signature",
    "signed_by",
    "human_approval",
)

#: 人工研判结论（与 3.8.25 ``WorkflowReviewDecision`` 一致，无 auto_* 项）。
GOVERNANCE_REVIEW_DECISION_VALUES: tuple[str, ...] = (
    "confirmed",
    "rejected",
    "need_more_info",
)


def _status_check_expr() -> str:
    """生成六态 CHECK 表达式（由白名单派生，杜绝手抄污染）。"""
    inner = ", ".join(f"'{s}'" for s in GOVERNANCE_WORKFLOW_STATUS_VALUES)
    return f"status in ({inner})"


class GovernanceWorkflowRecord(Base):
    """治理工作流持久化记录（Task 1）。

    ``workflow_id`` 直接作为主键：治理线索的业务标识天然唯一且可溯源，避免再引入
    一层代理键造成审计链断裂。``org_id`` NOT NULL 且索引，仓储层强制过滤。

    本表只存**事实快照**，不含任何 AI 建议、不含任何批准语义（红线②）。
    """

    __tablename__ = "governance_workflow_records"

    # -- 主理人明列的六个必备字段 -------------------------------------
    workflow_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="created", server_default="created"
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # -- 溯源与事实字段（强可追溯，红线⑥） ---------------------------
    source_type: Mapped[str] = mapped_column(
        String(48), nullable=False, default="human_reported"
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_facts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    human_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # -- 人工责任字段（只能由服务层在 USER 守卫下写入，红线③/④/⑥） ----
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    confirmed_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    confirmed_at: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    completed_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    completed_at: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    archived_at: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # -- 上下游关联（3.8.24 草稿 / 3.8.21 治理任务） ------------------
    draft_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    task_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    # -- 红线④：人工确认要求恒真，DB 层拒绝置 False -------------------
    requires_human_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    executions: Mapped[list["GovernanceExecutionRecordDB"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(_status_check_expr(), name="status_valid"),
        CheckConstraint("source_id <> ''", name="source_id_not_empty"),
        CheckConstraint("org_id <> ''", name="org_id_not_empty"),
        # 红线④：requires_human_confirmation 恒真（SQLite 存 0/1，PG 存 bool）。
        CheckConstraint(
            "requires_human_confirmation in (1, true)", name="requires_human"
        ),
        Index("ix_governance_workflow_records_org_status", "org_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<GovernanceWorkflowRecord workflow_id={self.workflow_id!r} "
            f"status={self.status!r} org_id={self.org_id!r}>"
        )


class GovernanceExecutionRecordDB(Base):
    """治理执行记录持久化（Task 2）。

    保存四类内容（主理人明列）：
    - **执行记录**：``action`` / ``actor`` / ``timestamp``；
    - **人工结果**：``result`` / ``note`` / ``decision``；
    - **来源链**：``source`` + ``source_chain``（JSON 数组，逐级溯源）；
    - **审计关联**：``audit_record_id`` + ``audit_category``。

    ``actor_kind`` 被 CHECK 约束钉死为 ``'user'``：AI 在数据库层就无法登记
    「自己执行了治理动作」（红线⑥），这是内存层 ``GovernanceExecutionRecord``
    同名校验在持久层的镜像，构成双保险。
    """

    __tablename__ = "governance_execution_records"

    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("governance_workflow_records.workflow_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # -- 执行事实 -----------------------------------------------------
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default="user"
    )
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # -- 人工结果 -----------------------------------------------------
    result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    # -- 来源链 -------------------------------------------------------
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    source_chain: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # -- 审计关联 -----------------------------------------------------
    audit_record_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    audit_category: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    workflow: Mapped["GovernanceWorkflowRecord"] = relationship(
        back_populates="executions"
    )

    __table_args__ = (
        # 红线⑥核心：执行者必须是真实人工。
        CheckConstraint("actor_kind = 'user'", name="actor_kind_user"),
        CheckConstraint("action <> ''", name="action_not_empty"),
        CheckConstraint("actor <> ''", name="actor_not_empty"),
        CheckConstraint("source <> ''", name="source_not_empty"),
        CheckConstraint("org_id <> ''", name="org_id_not_empty"),
        UniqueConstraint("record_id", "org_id", name="uq_execution_record_org"),
        Index(
            "ix_governance_execution_records_org_workflow", "org_id", "workflow_id"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<GovernanceExecutionRecordDB record_id={self.record_id!r} "
            f"workflow_id={self.workflow_id!r} actor={self.actor!r}>"
        )


__all__ = [
    "GovernanceWorkflowRecord",
    "GovernanceExecutionRecordDB",
    "GOVERNANCE_WORKFLOW_STATUS_VALUES",
    "GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES",
    "GOVERNANCE_REVIEW_DECISION_VALUES",
    "_FORBIDDEN_COLUMN_NAMES",
]

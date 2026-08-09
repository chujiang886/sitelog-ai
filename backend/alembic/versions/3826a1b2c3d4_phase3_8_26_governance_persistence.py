"""Phase 3.8.26 治理持久化：governance_workflow_records / governance_execution_records

Revision ID: 3826a1b2c3d4
Revises: 637cbf3eafca
Create Date: 2026-08-09 09:50:00.000000

说明（fail-closed，DB 级红线，与 ORM 模型 ``app.db.models.governance_workflow`` 严格对齐）：
- 两张表只存 3.8.25 live orchestrator 的**事实快照**，不重写状态机。
- CHECK 约束把六条红线钉进数据库：
  ① ``status_valid``：只允许六态（created/under_review/human_confirmed/in_progress/
     waiting_result/completed），auto_* 在 DB 层写不进去（红线③）。
  ② ``requires_human``：requires_human_confirmation 恒真（1/true），任何置 False 的
     UPDATE 被数据库拒绝（红线④）。
  ③ ``actor_kind_user``：执行记录 actor_kind 强制 = 'user'，AI 无法登记自身执行
     （红线⑥）。
  ④ source_id/org_id/action/actor/source 非空（红线⑥ 责任可追溯）。
- 表内**刻意不出现** engineering_approved / approved / quote / sign / human_approval
  等列（红线②/⑤），由结构级测试断言（Task 8）。
- 外键 workflow_id → governance_workflow_records.workflow_id ON DELETE CASCADE，
  删除工作流级联清理执行记录。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3826a1b2c3d4'
down_revision: str | Sequence[str] | None = '637cbf3eafca'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === 表 1：governance_workflow_records（Task 1 状态持久化） =============
    op.create_table(
        'governance_workflow_records',
        sa.Column('workflow_id', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
        sa.Column('source_id', sa.String(length=128), nullable=False),
        sa.Column('org_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # 溯源与事实字段（强可追溯，红线⑥）
        sa.Column('source_type', sa.String(length=48), nullable=False, server_default=sa.text("'human_reported'")),
        sa.Column('title', sa.String(length=256), nullable=False, server_default=sa.text("''")),
        sa.Column('description', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('source_facts', sa.JSON(), nullable=False),
        sa.Column('references', sa.JSON(), nullable=False),
        sa.Column('human_notes', sa.JSON(), nullable=False),
        # 人工责任字段（只能由服务层在 USER 守卫下写入，红线③/④/⑥）
        sa.Column('created_by', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('confirmed_by', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('confirmed_at', sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column('completed_by', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('completed_at', sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column('archived_by', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('archived_at', sa.String(length=64), nullable=False, server_default=sa.text("''")),
        # 上下游关联（3.8.24 草稿 / 3.8.21 治理任务）
        sa.Column('draft_id', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('task_id', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        # 红线④：人工确认要求恒真，DB 层拒绝置 False
        sa.Column('requires_human_confirmation', sa.Boolean(), nullable=False, server_default=sa.text("1")),
        # --- 红线 CHECK 约束（显式 name，不受 naming_convention 改写） ---
        sa.CheckConstraint(
            "status in ('created', 'under_review', 'human_confirmed', 'in_progress', 'waiting_result', 'completed')",
            name=op.f('status_valid'),
        ),
        sa.CheckConstraint("source_id <> ''", name=op.f('source_id_not_empty')),
        sa.CheckConstraint("org_id <> ''", name=op.f('org_id_not_empty')),
        sa.CheckConstraint("requires_human_confirmation in (1, true)", name=op.f('requires_human')),
        sa.PrimaryKeyConstraint('workflow_id', name=op.f('pk_governance_workflow_records')),
    )
    op.create_index(
        op.f('ix_governance_workflow_records_org_status'),
        'governance_workflow_records',
        ['org_id', 'status'],
        unique=False,
    )

    # === 表 2：governance_execution_records（Task 2 执行记录持久化） ======
    op.create_table(
        'governance_execution_records',
        sa.Column('record_id', sa.String(length=128), nullable=False),
        sa.Column('workflow_id', sa.String(length=128), nullable=False),
        sa.Column('org_id', sa.String(length=64), nullable=False),
        # 执行事实
        sa.Column('action', sa.String(length=256), nullable=False),
        sa.Column('actor', sa.String(length=128), nullable=False),
        sa.Column('actor_kind', sa.String(length=16), nullable=False, server_default=sa.text("'user'")),
        sa.Column('timestamp', sa.String(length=64), nullable=False, server_default=sa.text("''")),
        # 人工结果
        sa.Column('result', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('note', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('decision', sa.String(length=32), nullable=False, server_default=sa.text("''")),
        # 来源链
        sa.Column('source', sa.String(length=256), nullable=False, server_default=sa.text("''")),
        sa.Column('source_chain', sa.JSON(), nullable=False),
        # 审计关联
        sa.Column('audit_record_id', sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column('audit_category', sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # --- 红线⑥ CHECK 约束：执行者必须是真实人工 ---
        sa.CheckConstraint("actor_kind = 'user'", name=op.f('actor_kind_user')),
        sa.CheckConstraint("action <> ''", name=op.f('action_not_empty')),
        sa.CheckConstraint("actor <> ''", name=op.f('actor_not_empty')),
        sa.CheckConstraint("source <> ''", name=op.f('source_not_empty')),
        sa.CheckConstraint("org_id <> ''", name=op.f('org_id_not_empty')),
        sa.ForeignKeyConstraint(
            ['workflow_id'],
            ['governance_workflow_records.workflow_id'],
            ondelete='CASCADE',
            name=op.f('fk_governance_execution_records_workflow_id_governance_workflow_records'),
        ),
        sa.PrimaryKeyConstraint('record_id', name=op.f('pk_governance_execution_records')),
        sa.UniqueConstraint('record_id', 'org_id', name=op.f('uq_execution_record_org')),
    )
    op.create_index(
        op.f('ix_governance_execution_records_org_workflow'),
        'governance_execution_records',
        ['org_id', 'workflow_id'],
        unique=False,
    )


def downgrade() -> None:
    # 反向：先删执行记录表（含外键），再删工作流表。
    op.drop_index(
        op.f('ix_governance_execution_records_org_workflow'),
        table_name='governance_execution_records',
    )
    op.drop_table('governance_execution_records')
    op.drop_index(
        op.f('ix_governance_workflow_records_org_status'),
        table_name='governance_workflow_records',
    )
    op.drop_table('governance_workflow_records')

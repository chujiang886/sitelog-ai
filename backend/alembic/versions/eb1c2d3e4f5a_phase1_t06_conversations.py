"""phase1_t06_conversations

Phase 1 / T06b：新增会话 (conversations) + 消息 (messages) 表，用于
对接 Core Agent 的 chat 编排。所有工程数值保持 pending_verification。

Revision ID: eb1c2d3e4f5a
Revises: d17f02429ce9
Create Date: 2026-07-23 23:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.models.tenant import GUID


# revision identifiers, used by Alembic.
revision: str = "eb1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "d17f02429ce9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 conversations + messages 表（含 FK / CheckConstraint / Index）。"""

    op.create_table(
        "conversations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status in ('Active', 'Closed', 'Archived')",
            name=op.f("ck_conversations_conversation_status_valid"),
        ),
        sa.CheckConstraint(
            "state in ('Active', 'Closed', 'Archived')",
            name=op.f("ck_conversations_conversation_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_conversations_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_conversations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_conversations_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_conversations_tenant_id"), ["tenant_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_conversations_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            "ix_conversations_tenant_updated", ["tenant_id", "updated_at"], unique=False
        )
        batch_op.create_index(
            "ix_conversations_tenant_user", ["tenant_id", "user_id"], unique=False
        )

    op.create_table(
        "messages",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("conversation_id", GUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('user', 'assistant', 'system')",
            name=op.f("ck_messages_message_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_messages_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_messages_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_messages_tenant_id"), ["tenant_id"], unique=False
        )
        batch_op.create_index(
            "ix_messages_tenant_conversation",
            ["tenant_id", "conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_messages_conversation_created",
            ["conversation_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """删除 messages → conversations 表（反向顺序）。"""

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_conversation_created")
        batch_op.drop_index("ix_messages_tenant_conversation")
        batch_op.drop_index(batch_op.f("ix_messages_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_messages_conversation_id"))

    op.drop_table("messages")

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index("ix_conversations_tenant_user")
        batch_op.drop_index("ix_conversations_tenant_updated")
        batch_op.drop_index(batch_op.f("ix_conversations_user_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_project_id"))

    op.drop_table("conversations")
"""phase1_t08_images

Phase 1 / T08：新增 images 表，用于存储用户上传的图片元数据与 Vision Agent
分析结果。所有工程数值保持 pending_verification。

Revision ID: c2f4a6b8d901
Revises: eb1c2d3e4f5a
Create Date: 2026-07-24 09:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.models.tenant import GUID


# revision identifiers, used by Alembic.
revision: str = "c2f4a6b8d901"
down_revision: str | Sequence[str] | None = "eb1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 images 表（含 FK / CheckConstraint / Index）。"""

    op.create_table(
        "images",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=True),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("vision_status", sa.String(length=16), nullable=False),
        sa.Column("vision_result", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "vision_status in ('Pending', 'Processing', 'Done', 'Failed')",
            name=op.f("ck_images_image_vision_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_images_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_images_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_images_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_images")),
    )
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_images_owner_id"), ["owner_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_images_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_images_tenant_id"), ["tenant_id"], unique=False
        )
        batch_op.create_index(
            "ix_images_tenant_project", ["tenant_id", "project_id"], unique=False
        )
        batch_op.create_index(
            "ix_images_tenant_sha256", ["tenant_id", "sha256"], unique=False
        )


def downgrade() -> None:
    """删除 images 表。"""

    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_index("ix_images_tenant_sha256")
        batch_op.drop_index("ix_images_tenant_project")
        batch_op.drop_index(batch_op.f("ix_images_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_images_project_id"))
        batch_op.drop_index(batch_op.f("ix_images_owner_id"))

    op.drop_table("images")
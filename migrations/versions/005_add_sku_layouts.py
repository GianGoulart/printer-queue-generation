"""Add sku_layouts table

Revision ID: 005
Revises: 004
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sku_layouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("pattern_type", sa.String(length=20), nullable=False, server_default="regex"),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("example_samples", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allow_hyphen_variants", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sku_layouts_id", "sku_layouts", ["id"], unique=False)
    op.create_index("ix_sku_layouts_tenant_id", "sku_layouts", ["tenant_id"], unique=False)
    op.create_index("ix_sku_layouts_tenant_active_priority", "sku_layouts", ["tenant_id", "active", "priority"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sku_layouts_tenant_active_priority", table_name="sku_layouts")
    op.drop_index("ix_sku_layouts_tenant_id", table_name="sku_layouts")
    op.drop_index("ix_sku_layouts_id", table_name="sku_layouts")
    op.drop_table("sku_layouts")

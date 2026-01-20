"""Add trigram index for fuzzy SKU search

Revision ID: 002
Revises: 001
Create Date: 2026-01-14 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create trigram GIN index on assets.sku_normalized for fuzzy matching
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_sku_normalized_trgm "
        "ON assets USING gin (sku_normalized gin_trgm_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_assets_sku_normalized_trgm;")

"""Add picklist_position to job_items

Revision ID: 004
Revises: 003
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add picklist_position column to job_items table."""
    # Add column
    op.add_column(
        'job_items',
        sa.Column('picklist_position', sa.Integer(), nullable=True)
    )
    
    # Create index for better performance
    op.create_index(
        'ix_job_items_picklist_position',
        'job_items',
        ['picklist_position'],
        unique=False
    )


def downgrade() -> None:
    """Remove picklist_position column from job_items table."""
    op.drop_index('ix_job_items_picklist_position', table_name='job_items')
    op.drop_column('job_items', 'picklist_position')

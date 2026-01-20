"""add job mode and sizing profile

Revision ID: 003
Revises: 002
Create Date: 2026-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sizing_profile_id column
    op.add_column('jobs', sa.Column('sizing_profile_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_jobs_sizing_profile_id'), 'jobs', ['sizing_profile_id'], unique=False)
    op.create_foreign_key('fk_jobs_sizing_profile_id', 'jobs', 'sizing_profiles', ['sizing_profile_id'], ['id'], ondelete='SET NULL')
    
    # Add mode column with default 'sequence'
    op.add_column('jobs', sa.Column('mode', sa.String(length=50), nullable=False, server_default='sequence'))
    
    # Update existing jobs status from 'pending' to 'queued' if any exist
    op.execute("UPDATE jobs SET status = 'queued' WHERE status = 'pending'")


def downgrade() -> None:
    # Remove mode column
    op.drop_column('jobs', 'mode')
    
    # Remove sizing_profile_id column
    op.drop_constraint('fk_jobs_sizing_profile_id', 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_sizing_profile_id'), table_name='jobs')
    op.drop_column('jobs', 'sizing_profile_id')
    
    # Revert status back to pending
    op.execute("UPDATE jobs SET status = 'pending' WHERE status = 'queued'")

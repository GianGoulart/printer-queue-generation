"""Initial schema with all tables

Revision ID: 001
Revises: 
Create Date: 2026-01-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)

    # Create machines table
    op.create_table(
        'machines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('max_width_mm', sa.Float(), nullable=False),
        sa.Column('max_length_mm', sa.Float(), nullable=False),
        sa.Column('min_dpi', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_machines_id'), 'machines', ['id'], unique=False)
    op.create_index(op.f('ix_machines_tenant_id'), 'machines', ['tenant_id'], unique=False)

    # Create tenant_storage_configs table
    op.create_table(
        'tenant_storage_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('base_path', sa.String(length=500), nullable=False),
        sa.Column('credentials_encrypted', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index(op.f('ix_tenant_storage_configs_id'), 'tenant_storage_configs', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_storage_configs_tenant_id'), 'tenant_storage_configs', ['tenant_id'], unique=False)

    # Create assets table
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('file_uri', sa.String(length=1000), nullable=False),
        sa.Column('sku_normalized', sa.String(length=255), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_assets_id'), 'assets', ['id'], unique=False)
    op.create_index(op.f('ix_assets_tenant_id'), 'assets', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_assets_sku_normalized'), 'assets', ['sku_normalized'], unique=False)

    # Create sizing_profiles table
    op.create_table(
        'sizing_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('size_label', sa.String(length=50), nullable=False),
        sa.Column('target_width_mm', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sizing_profiles_id'), 'sizing_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_sizing_profiles_tenant_id'), 'sizing_profiles', ['tenant_id'], unique=False)

    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('machine_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('picklist_uri', sa.String(length=1000), nullable=False),
        sa.Column('manifest_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)
    op.create_index(op.f('ix_jobs_tenant_id'), 'jobs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_jobs_machine_id'), 'jobs', ['machine_id'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)

    # Create job_items table
    op.create_table(
        'job_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('size_label', sa.String(length=50), nullable=True),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('final_width_mm', sa.Float(), nullable=True),
        sa.Column('final_height_mm', sa.Float(), nullable=True),
        sa.Column('base_index', sa.Integer(), nullable=True),
        sa.Column('x_mm', sa.Float(), nullable=True),
        sa.Column('y_mm', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_items_id'), 'job_items', ['id'], unique=False)
    op.create_index(op.f('ix_job_items_job_id'), 'job_items', ['job_id'], unique=False)
    op.create_index(op.f('ix_job_items_sku'), 'job_items', ['sku'], unique=False)
    op.create_index(op.f('ix_job_items_asset_id'), 'job_items', ['asset_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_items_asset_id'), table_name='job_items')
    op.drop_index(op.f('ix_job_items_sku'), table_name='job_items')
    op.drop_index(op.f('ix_job_items_job_id'), table_name='job_items')
    op.drop_index(op.f('ix_job_items_id'), table_name='job_items')
    op.drop_table('job_items')
    
    op.drop_index(op.f('ix_jobs_created_at'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_machine_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_tenant_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_id'), table_name='jobs')
    op.drop_table('jobs')
    
    op.drop_index(op.f('ix_sizing_profiles_tenant_id'), table_name='sizing_profiles')
    op.drop_index(op.f('ix_sizing_profiles_id'), table_name='sizing_profiles')
    op.drop_table('sizing_profiles')
    
    op.drop_index(op.f('ix_assets_sku_normalized'), table_name='assets')
    op.drop_index(op.f('ix_assets_tenant_id'), table_name='assets')
    op.drop_index(op.f('ix_assets_id'), table_name='assets')
    op.drop_table('assets')
    
    op.drop_index(op.f('ix_tenant_storage_configs_tenant_id'), table_name='tenant_storage_configs')
    op.drop_index(op.f('ix_tenant_storage_configs_id'), table_name='tenant_storage_configs')
    op.drop_table('tenant_storage_configs')
    
    op.drop_index(op.f('ix_machines_tenant_id'), table_name='machines')
    op.drop_index(op.f('ix_machines_id'), table_name='machines')
    op.drop_table('machines')
    
    op.drop_index(op.f('ix_tenants_id'), table_name='tenants')
    op.drop_table('tenants')
    
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")

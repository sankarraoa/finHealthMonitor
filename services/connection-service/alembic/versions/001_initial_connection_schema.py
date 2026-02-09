"""initial connection schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create connections table
    op.create_table(
        'connections',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('software', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_in', sa.Integer(), nullable=True),
        sa.Column('token_created_at', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.Column('extra_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_connections_id'), 'connections', ['id'], unique=False)
    op.create_index(op.f('ix_connections_software'), 'connections', ['software'], unique=False)
    op.create_index(op.f('ix_connections_tenant_id'), 'connections', ['tenant_id'], unique=False)
    
    # Create xero_tenants table
    op.create_table(
        'xero_tenants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('connection_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('tenant_name', sa.String(), nullable=False),
        sa.Column('xero_connection_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_xero_tenants_id'), 'xero_tenants', ['id'], unique=False)
    op.create_index(op.f('ix_xero_tenants_connection_id'), 'xero_tenants', ['connection_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_xero_tenants_connection_id'), table_name='xero_tenants')
    op.drop_index(op.f('ix_xero_tenants_id'), table_name='xero_tenants')
    op.drop_table('xero_tenants')
    op.drop_index(op.f('ix_connections_tenant_id'), table_name='connections')
    op.drop_index(op.f('ix_connections_software'), table_name='connections')
    op.drop_index(op.f('ix_connections_id'), table_name='connections')
    op.drop_table('connections')

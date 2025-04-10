"""create_devices_table

Revision ID: 434a03f19f49
Revises: 63ee941215d0
Create Date: 2025-04-09 07:51:23.917743

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '434a03f19f49'
down_revision = '63ee941215d0'
branch_labels = None
depends_on = None


def upgrade():
    # Create devices table
    op.create_table('devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('stream_key', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    op.create_index(op.f('ix_devices_stream_key'), 'devices', ['stream_key'], unique=True)


def downgrade():
    # Drop indexes first
    op.drop_index(op.f('ix_devices_stream_key'), table_name='devices')
    op.drop_index(op.f('ix_devices_id'), table_name='devices')
    
    # Drop the table
    op.drop_table('devices') 
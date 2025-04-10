"""remove_stream_key_from_users

Revision ID: 63ee941215d0
Revises: 2f5fbc810c75
Create Date: 2025-04-09 07:50:11.917743

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '63ee941215d0'
down_revision = '2f5fbc810c75'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the index first
    op.drop_index('ix_users_stream_key', table_name='users')
    # Then drop the column
    op.drop_column('users', 'stream_key')


def downgrade():
    # Add back the stream_key column
    op.add_column('users', sa.Column('stream_key', sa.String(8), nullable=True))
    # Create unique index on stream_key
    op.create_index('ix_users_stream_key', 'users', ['stream_key'], unique=True)
    # Make the column not nullable
    op.alter_column('users', 'stream_key',
                    existing_type=sa.String(8),
                    nullable=False) 
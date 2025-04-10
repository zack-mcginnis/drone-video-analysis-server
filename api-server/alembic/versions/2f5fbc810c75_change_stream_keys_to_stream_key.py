"""change_stream_keys_to_stream_key

Revision ID: 2f5fbc810c75
Revises: 2f06cb6c0805
Create Date: 2025-04-08 22:31:27.780102

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import random
import string


# revision identifiers, used by Alembic.
revision = '2f5fbc810c75'
down_revision = '2f06cb6c0805'
branch_labels = None
depends_on = None


def generate_stream_key():
    """Generate a random 8-character alphanumeric string."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def upgrade():
    # Create new stream_key column
    op.add_column('users', sa.Column('stream_key', sa.String(8), nullable=True))
    
    # Create a temporary connection to execute SQL
    connection = op.get_bind()
    
    # For each user, generate a new stream key
    users = connection.execute(sa.text('SELECT id FROM users')).fetchall()
    for user in users:
        stream_key = generate_stream_key()
        connection.execute(
            sa.text('UPDATE users SET stream_key = :key WHERE id = :id'),
            parameters=dict(key=stream_key, id=user[0])
        )
    
    # Make stream_key not nullable after data migration
    op.alter_column('users', 'stream_key',
                    existing_type=sa.String(8),
                    nullable=False)
    
    # Create unique index on stream_key
    op.create_index('ix_users_stream_key', 'users', ['stream_key'], unique=True)
    
    # Drop the old stream_keys column
    op.drop_column('users', 'stream_keys')


def downgrade():
    # Add back the stream_keys column
    op.add_column('users', sa.Column('stream_keys', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Create a temporary connection to execute SQL
    connection = op.get_bind()
    
    # Convert single stream_key back to array of stream_keys
    connection.execute(
        sa.text('UPDATE users SET stream_keys = jsonb_build_array(stream_key::text)')
    )
    
    # Make stream_keys not nullable
    op.alter_column('users', 'stream_keys',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    nullable=False)
    
    # Drop the stream_key column and its index
    op.drop_index('ix_users_stream_key', table_name='users')
    op.drop_column('users', 'stream_key') 
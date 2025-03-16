"""Create initial tables

Revision ID: a4b3774c528f
Revises: 
Create Date: 2025-03-16T14:31:42.507184

"""

# revision identifiers, used by Alembic.
revision = 'a4b3774c528f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create tables
    from alembic import op
    import sqlalchemy as sa
    
    # Create recordings table
    op.create_table(
        'recordings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stream_key', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('file_path', sa.String(length=255), nullable=True),
        sa.Column('s3_key', sa.String(length=255), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for faster queries
    op.create_index(op.f('ix_recordings_stream_key'), 'recordings', ['stream_key'], unique=False)
    op.create_index(op.f('ix_recordings_status'), 'recordings', ['status'], unique=False)
    op.create_index(op.f('ix_recordings_start_time'), 'recordings', ['start_time'], unique=False)


def downgrade():
    # Drop tables in reverse order
    op.drop_index(op.f('ix_recordings_start_time'), table_name='recordings')
    op.drop_index(op.f('ix_recordings_status'), table_name='recordings')
    op.drop_index(op.f('ix_recordings_stream_key'), table_name='recordings')
    op.drop_table('recordings')

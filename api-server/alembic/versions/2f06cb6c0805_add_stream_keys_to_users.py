"""add stream_keys to users

Revision ID: 2f06cb6c0805
Revises: 5d2d18dc4492
Create Date: 2025-04-08 11:22:11.588681

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f06cb6c0805'
down_revision = '5d2d18dc4492'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('stream_keys', sa.JSON(), nullable=False, server_default='[]'))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'stream_keys')
    # ### end Alembic commands ### 
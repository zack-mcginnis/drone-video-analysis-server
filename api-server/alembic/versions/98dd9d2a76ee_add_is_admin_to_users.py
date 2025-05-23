"""add_is_admin_to_users

Revision ID: 98dd9d2a76ee
Revises: 434a03f19f49
Create Date: 2025-04-11 16:13:32.864827

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '98dd9d2a76ee'
down_revision = '434a03f19f49'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # First add the column as nullable
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows
    op.execute("UPDATE users SET is_admin = false WHERE is_admin IS NULL")
    
    # Make the column non-nullable
    op.alter_column('users', 'is_admin',
               existing_type=sa.Boolean(),
               nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'is_admin')
    # ### end Alembic commands ### 
"""add user device many to many relationship

Revision ID: 58f1895de0de
Revises: 98dd9d2a76ee
Create Date: 2025-04-18 08:06:21.243120

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select
from sqlalchemy.exc import SQLAlchemyError


# revision identifiers, used by Alembic.
revision = '58f1895de0de'
down_revision = '98dd9d2a76ee'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    try:
        # Create the new association table
        op.create_table('user_device_association',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('user_id', 'device_id')
        )

        # Create SQLAlchemy table objects for the migration
        devices = table('devices',
            column('id', sa.Integer),
            column('user_id', sa.Integer)
        )

        connection = op.get_bind()
        
        # Get all existing device-user relationships
        # Wrap in a try block in case the query fails
        try:
            device_users = connection.execute(
                select(devices.c.id, devices.c.user_id).where(devices.c.user_id.isnot(None))
            ).fetchall()

            # Insert the relationships into the new association table
            if device_users:
                # Insert in batches to avoid memory issues
                batch_size = 1000
                for i in range(0, len(device_users), batch_size):
                    batch = device_users[i:i + batch_size]
                    op.bulk_insert(
                        table('user_device_association',
                            column('user_id', sa.Integer),
                            column('device_id', sa.Integer),
                            column('created_at', sa.DateTime(timezone=True))
                        ),
                        [{'user_id': user_id, 'device_id': device_id} 
                         for device_id, user_id in batch]
                    )
        except SQLAlchemyError as e:
            print(f"Error during data migration: {str(e)}")
            raise

        # Remove the old foreign key and column
        # First check if the constraint exists
        inspector = sa.inspect(connection)
        for fk in inspector.get_foreign_keys('devices'):
            if fk['referred_table'] == 'users':
                op.drop_constraint(fk['name'], 'devices', type_='foreignkey')
                break

        op.drop_column('devices', 'user_id')

    except Exception as e:
        print(f"Migration failed: {str(e)}")
        raise

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    try:
        # Add back the user_id column
        op.add_column('devices', sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        
        connection = op.get_bind()
        
        # Create SQLAlchemy table objects for the migration
        user_device_assoc = table('user_device_association',
            column('user_id', sa.Integer),
            column('device_id', sa.Integer)
        )
        
        try:
            # Get all associations
            device_users = connection.execute(
                select(
                    user_device_assoc.c.device_id,
                    user_device_assoc.c.user_id
                ).distinct(user_device_assoc.c.device_id)
            ).fetchall()
            
            # Update devices table with the first user for each device
            if device_users:
                for device_id, user_id in device_users:
                    connection.execute(
                        sa.text('UPDATE devices SET user_id = :user_id WHERE id = :device_id AND user_id IS NULL'),
                        user_id=user_id,
                        device_id=device_id
                    )
        
            # Make the column non-nullable after data migration
            op.alter_column('devices', 'user_id', nullable=False)
            
            # Recreate the foreign key
            op.create_foreign_key('devices_user_id_fkey', 'devices', 'users', ['user_id'], ['id'])
            
        except SQLAlchemyError as e:
            print(f"Error during data migration in downgrade: {str(e)}")
            raise
            
        # Drop the association table
        op.drop_table('user_device_association')
        
    except Exception as e:
        print(f"Downgrade failed: {str(e)}")
        raise
    # ### end Alembic commands ### 
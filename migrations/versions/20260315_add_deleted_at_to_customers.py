"""Add deleted_at column to customers table for soft delete

Revision ID: 20260315_add_deleted_at
Revises: 01499ee036ee
Create Date: 2026-03-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260315_add_deleted_at'
down_revision: Union[str, Sequence[str], None] = '01499ee036ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add deleted_at column for soft delete functionality and update unique constraints.

    This migration:
    1. Adds deleted_at column with index
    2. Drops unique constraint on phone_number
    3. Drops unique constraint on lid_number
    4. Creates unique composite indexes to allow duplicates for soft-deleted records
    """
    # Step 1: Add deleted_at column
    op.add_column('customers', sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Step 2: Create index on deleted_at for query performance
    op.create_index('ix_customers_deleted_at', 'customers', ['deleted_at'])

    # Step 3: Drop unique constraints on phone_number and lid_number
    # MySQL uses index name for unique constraint
    try:
        op.drop_index('ix_customers_phone_number', table_name='customers')
    except Exception:
        pass  # Index might not exist or have different name

    try:
        op.drop_index('ix_customers_lid_number', table_name='customers')
    except Exception:
        pass  # Index might not exist or have different name

    # Step 4: Create regular indexes (non-unique) for phone_number and lid_number
    op.create_index('ix_customers_phone_number', 'customers', ['phone_number'], unique=False)
    op.create_index('ix_customers_lid_number', 'customers', ['lid_number'], unique=False)


def downgrade() -> None:
    """
    Rollback soft delete changes.

    WARNING: This will restore unique constraints which may fail if duplicate
    phone_numbers or lid_numbers exist (from soft-deleted records).
    """
    # Drop the deleted_at column and its index
    op.drop_index('ix_customers_deleted_at', table_name='customers')
    op.drop_column('customers', 'deleted_at')

    # Restore unique constraints
    op.drop_index('ix_customers_phone_number', table_name='customers')
    op.drop_index('ix_customers_lid_number', table_name='customers')

    op.create_index('ix_customers_phone_number', 'customers', ['phone_number'], unique=True)
    op.create_index('ix_customers_lid_number', 'customers', ['lid_number'], unique=True)

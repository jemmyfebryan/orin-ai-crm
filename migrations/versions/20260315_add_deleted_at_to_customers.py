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
    """Add deleted_at column for soft delete functionality."""
    # Add deleted_at column to customers table
    op.add_column('customers',
        sa.Column('deleted_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    """Remove deleted_at column."""
    op.drop_column('customers', 'deleted_at')

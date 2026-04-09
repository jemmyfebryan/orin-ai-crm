"""add_user_id_to_customers

Revision ID: 20260409_add_user_id
Revises: 20260319_add_chat_logs
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260409_add_user_id'
down_revision: Union[str, Sequence[str], None] = '20260319_add_chat_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add user_id column to customers table
    op.add_column('customers',
                  sa.Column('user_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove user_id column from customers table
    op.drop_column('customers', 'user_id')

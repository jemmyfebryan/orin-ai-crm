"""add_content_type_to_chat_sessions

Revision ID: 20260317_add_content_type
Revises: 0bd89c249479
Create Date: 2026-03-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260317_add_content_type'
down_revision: Union[str, Sequence[str], None] = '0bd89c249479'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add content_type column to chat_sessions table
    # Default value 'text' for existing rows
    op.add_column('chat_sessions',
                  sa.Column('content_type',
                            sa.String(20),
                            server_default='text',
                            nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove content_type column from chat_sessions table
    op.drop_column('chat_sessions', 'content_type')

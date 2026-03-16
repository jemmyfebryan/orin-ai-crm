"""Add prompts table for storing AI agent prompts

Revision ID: 20260316_add_prompts_table
Revises: 20260315_add_deleted_at
Create Date: 2026-03-16 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260316_add_prompts_table'
down_revision: Union[str, Sequence[str], None] = '20260315_add_deleted_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create prompts table for storing AI agent system prompts.

    This migration creates the prompts table with:
    - Unique prompt_key for fast lookups
    - Support for multiple prompt types (system, user, tool)
    - is_active flag for enabling/disabling prompts
    - Automatic timestamps
    """
    op.create_table(
        'prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prompt_key', sa.String(length=100), nullable=False),
        sa.Column('prompt_name', sa.String(length=200), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prompt_type', sa.String(length=50), nullable=True, server_default='system'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create unique index on prompt_key for fast lookups and uniqueness
    op.create_index('ix_prompts_prompt_key', 'prompts', ['prompt_key'], unique=True)

    # Create index on prompt_type for filtering by type
    op.create_index('ix_prompts_prompt_type', 'prompts', ['prompt_type'], unique=False)


def downgrade() -> None:
    """
    Rollback prompts table creation.

    WARNING: This will delete all prompts data.
    """
    op.drop_index('ix_prompts_prompt_type', table_name='prompts')
    op.drop_index('ix_prompts_prompt_key', table_name='prompts')
    op.drop_table('prompts')

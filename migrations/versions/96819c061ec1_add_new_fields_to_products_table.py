"""add_new_fields_to_products_table

Revision ID: 96819c061ec1
Revises: 20260316_add_prompts_table
Create Date: 2026-03-17 03:07:34.553304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96819c061ec1'
down_revision: Union[str, Sequence[str], None] = '20260316_add_prompts_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns to products table
    op.add_column('products', sa.Column('can_wiretap', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('portable', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('battery_life', sa.String(100), nullable=True))
    op.add_column('products', sa.Column('power_source', sa.String(100), nullable=True))
    op.add_column('products', sa.Column('tracking_type', sa.String(100), nullable=True))
    op.add_column('products', sa.Column('monthly_fee', sa.String(100), nullable=True))

    # Update installation_type enum to include 'pasang_mandiri'
    # Note: MySQL doesn't support ALTER COLUMN for ENUM, need to modify the column type
    op.execute("ALTER TABLE products MODIFY COLUMN installation_type VARCHAR(50) NOT NULL COMMENT 'pasang_technisi, colok_sendiri, pasang_mandiri'")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove new columns from products table
    op.drop_column('products', 'monthly_fee')
    op.drop_column('products', 'tracking_type')
    op.drop_column('products', 'power_source')
    op.drop_column('products', 'battery_life')
    op.drop_column('products', 'portable')
    op.drop_column('products', 'can_wiretap')

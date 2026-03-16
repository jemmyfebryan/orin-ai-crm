"""increase_vehicle_type_column_length

Revision ID: 0bd89c249479
Revises: 96819c061ec1
Create Date: 2026-03-17 03:22:43.219868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bd89c249479'
down_revision: Union[str, Sequence[str], None] = '96819c061ec1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Increase vehicle_type column length from VARCHAR(50) to VARCHAR(255)
    op.alter_column('products', 'vehicle_type',
                   existing_type=sa.String(50),
                   type_=sa.String(255),
                   existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert vehicle_type column length back to VARCHAR(50)
    op.alter_column('products', 'vehicle_type',
                   existing_type=sa.String(255),
                   type_=sa.String(50),
                   existing_nullable=True)

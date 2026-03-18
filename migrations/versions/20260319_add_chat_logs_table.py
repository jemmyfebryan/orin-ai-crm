"""add_chat_logs_table

Revision ID: 20260319_add_chat_logs
Revises: 20260317_add_content_type
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260319_add_chat_logs'
down_revision: Union[str, Sequence[str], None] = '20260317_add_content_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create chat_logs table
    op.create_table(
        'chat_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.String(100), nullable=True),
        sa.Column('user_id', sa.String(100), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=True),
        sa.Column('contact_name', sa.String(100), nullable=True),
        sa.Column('user_message_ids', sa.Text(), nullable=True),
        sa.Column('ai_reply_ids', sa.Text(), nullable=True),
        sa.Column('batch_message_count', sa.Integer(), server_default='1', nullable=True),
        sa.Column('batch_total_chars', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('processing_duration_ms', sa.Integer(), nullable=True),
        sa.Column('timeout_triggered', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('human_takeover_triggered', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('ai_model', sa.String(100), nullable=True),
        sa.Column('ai_reply_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('tool_calls', sa.Text(), nullable=True),
        sa.Column('images_sent', sa.Integer(), server_default='0', nullable=True),
        sa.Column('pdfs_sent', sa.Integer(), server_default='0', nullable=True),
        sa.Column('agent_route', sa.String(50), nullable=True),
        sa.Column('agents_called', sa.Text(), nullable=True),
        sa.Column('orchestrator_step', sa.Integer(), nullable=True),
        sa.Column('max_orchestrator_steps', sa.Integer(), nullable=True),
        sa.Column('orchestrator_plan', sa.Text(), nullable=True),
        sa.Column('orchestrator_decision', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('error_stage', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for frequently queried columns
    op.create_index(op.f('ix_chat_logs_customer_id'), 'chat_logs', ['customer_id'])
    op.create_index(op.f('ix_chat_logs_conversation_id'), 'chat_logs', ['conversation_id'])
    op.create_index(op.f('ix_chat_logs_user_id'), 'chat_logs', ['user_id'])
    op.create_index(op.f('ix_chat_logs_phone_number'), 'chat_logs', ['phone_number'])
    op.create_index(op.f('ix_chat_logs_started_at'), 'chat_logs', ['started_at'])
    op.create_index(op.f('ix_chat_logs_completed_at'), 'chat_logs', ['completed_at'])
    op.create_index(op.f('ix_chat_logs_status'), 'chat_logs', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f('ix_chat_logs_status'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_completed_at'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_started_at'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_phone_number'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_user_id'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_conversation_id'), table_name='chat_logs')
    op.drop_index(op.f('ix_chat_logs_customer_id'), table_name='chat_logs')

    # Drop chat_logs table
    op.drop_table('chat_logs')

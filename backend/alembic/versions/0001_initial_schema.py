"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("telegram_chat_id", sa.String(50), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "oauth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Enum("gmail", "splitwise", name="oauthprovider"), nullable=False),
        sa.Column("access_token", sa.String(2048), nullable=False),
        sa.Column("refresh_token", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(512), nullable=True),
    )
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])

    op.create_table(
        "gmail_watch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("history_id", sa.String(50), nullable=False),
        sa.Column("watch_expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pubsub_topic", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gmail_watch_user_id", "gmail_watch", ["user_id"])

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("merchant", sa.String(255), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
        sa.Column("raw_email_id", sa.String(255), nullable=True),
        sa.Column("source", sa.Enum("gmail", "receipt", "manual", name="transactionsource"), nullable=False),
        sa.Column("status", sa.Enum("pending", "added", "skipped", name="transactionstatus"), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])

    op.create_table(
        "conversation_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.Enum("CONFIRM", "SELECT_GROUP", "SELECT_MEMBERS", "SELECT_SPLIT_TYPE", "CUSTOM_SPLIT", "DONE", name="conversationstateenum"), nullable=False),
        sa.Column("context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversation_state_user_id", "conversation_state", ["user_id"])
    op.create_index("ix_conversation_state_transaction_id", "conversation_state", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("conversation_state")
    op.drop_table("transactions")
    op.drop_table("gmail_watch")
    op.drop_table("oauth_tokens")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS conversationstateenum")
    op.execute("DROP TYPE IF EXISTS transactionstatus")
    op.execute("DROP TYPE IF EXISTS transactionsource")
    op.execute("DROP TYPE IF EXISTS oauthprovider")

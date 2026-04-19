import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    gmail_watch: Mapped["GmailWatch | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversation_states: Mapped[list["ConversationState"]] = relationship(back_populates="user", cascade="all, delete-orphan")

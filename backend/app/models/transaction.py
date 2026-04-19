import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum


class TransactionSource(str, enum.Enum):
    gmail = "gmail"
    receipt = "receipt"
    manual = "manual"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    added = "added"
    skipped = "skipped"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    raw_email_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[TransactionSource] = mapped_column(SAEnum(TransactionSource), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus), nullable=False, default=TransactionStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")
    conversation_states: Mapped[list["ConversationState"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )

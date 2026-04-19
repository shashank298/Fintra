import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
import enum


class ConversationStateEnum(str, enum.Enum):
    CONFIRM = "CONFIRM"
    SELECT_GROUP = "SELECT_GROUP"
    SELECT_MEMBERS = "SELECT_MEMBERS"
    SELECT_SPLIT_TYPE = "SELECT_SPLIT_TYPE"
    CUSTOM_SPLIT = "CUSTOM_SPLIT"
    DONE = "DONE"


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[ConversationStateEnum] = mapped_column(SAEnum(ConversationStateEnum), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="conversation_states")
    transaction: Mapped["Transaction"] = relationship(back_populates="conversation_states")

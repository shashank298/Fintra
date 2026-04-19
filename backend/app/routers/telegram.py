import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


class LinkRequest(BaseModel):
    telegram_chat_id: str
    user_email: str


class WebhookRequest(BaseModel):
    pass


@router.post("/link")
async def link_telegram(
    body: LinkRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == body.user_email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.telegram_chat_id = body.telegram_chat_id
    await db.commit()
    return {"detail": "Telegram linked"}


@router.get("/status")
async def telegram_status(
    current_user: User = Depends(get_current_user),
):
    return {"linked": current_user.telegram_chat_id is not None}


@router.post("/webhook")
async def telegram_webhook(request: Request):
    from app.bot.handlers import build_application
    app = build_application()
    data = await request.json()
    from telegram import Update
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return {"ok": True}

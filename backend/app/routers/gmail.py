import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.middleware import get_current_user
from app.models.user import User
from app.models.gmail_watch import GmailWatch
from app.services import gmail as gmail_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/connect")
async def connect(current_user: User = Depends(get_current_user)):
    url = gmail_service.get_oauth_url(state=str(current_user.id))
    return {"oauth_url": url}


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token_data = await gmail_service.exchange_code(code)
    await gmail_service.save_token(db, current_user.id, token_data)
    await gmail_service.setup_watch(db, current_user.id)
    return {"detail": "Gmail connected and watch registered"}


@router.post("/watch")
async def setup_watch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await gmail_service.setup_watch(db, current_user.id)
    return result


@router.get("/status")
async def status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connected = await gmail_service.is_connected(db, current_user.id)
    return {"connected": connected}


@router.post("/webhook")
async def pubsub_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives Google Pub/Sub push notifications. Must return 200 immediately."""
    try:
        body = await request.json()
        message = body.get("message", {})
        data_b64 = message.get("data", "")
        if data_b64:
            decoded = base64.b64decode(data_b64).decode("utf-8")
            payload = json.loads(decoded)
            email_address = payload.get("emailAddress")
            history_id = payload.get("historyId")
            if email_address and history_id:
                background_tasks.add_task(process_pubsub_notification, email_address, str(history_id))
    except Exception as e:
        logger.error(f"Pub/Sub webhook parse error: {e}")
    return {"status": "ok"}


async def process_pubsub_notification(email_address: str, history_id: str) -> None:
    from app.services.parser import run_parser_pipeline
    from app.models.transaction import Transaction, TransactionSource, TransactionStatus
    from app.bot.notifications import notify_new_transaction
    import uuid

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(User).where(User.email == email_address))
            user = result.scalar_one_or_none()
            if not user:
                return

            watch_result = await db.execute(select(GmailWatch).where(GmailWatch.user_id == user.id))
            watch = watch_result.scalar_one_or_none()
            if not watch:
                return

            emails = await gmail_service.get_new_emails(db, user.id, watch.history_id)

            for email in emails:
                parsed = await run_parser_pipeline(email["body"], email["sender"])
                if not parsed:
                    continue

                tx_date = datetime.now(timezone.utc)
                if parsed.get("date"):
                    try:
                        tx_date = datetime.fromisoformat(parsed["date"]).replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

                transaction = Transaction(
                    user_id=user.id,
                    amount=parsed["amount"],
                    merchant=parsed.get("merchant", "Unknown"),
                    date=tx_date,
                    currency=parsed.get("currency", "INR"),
                    raw_email_id=email["id"],
                    source=TransactionSource.gmail,
                    status=TransactionStatus.pending,
                )
                db.add(transaction)
                await db.commit()
                await db.refresh(transaction)

                await notify_new_transaction(user, transaction)

        except Exception as e:
            logger.error(f"Error processing Pub/Sub notification for {email_address}: {e}")

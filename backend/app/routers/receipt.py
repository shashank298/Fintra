import base64
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware import get_current_user
from app.models.transaction import Transaction, TransactionSource, TransactionStatus
from app.models.user import User
from app.services.parser import ocr_receipt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/receipt", tags=["receipt"])

ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}


@router.post("/upload")
async def upload_receipt(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or PDF files are accepted")

    content = await file.read()
    image_b64 = base64.b64encode(content).decode()

    parsed = await ocr_receipt(image_b64, file.content_type)
    if not parsed or not parsed.get("amount"):
        raise HTTPException(status_code=422, detail="Could not extract transaction details from the receipt")

    tx_date = datetime.now(timezone.utc)
    if parsed.get("date"):
        try:
            tx_date = datetime.fromisoformat(parsed["date"]).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    transaction = Transaction(
        user_id=current_user.id,
        amount=float(parsed["amount"]),
        merchant=parsed.get("merchant", "Unknown"),
        date=tx_date,
        currency=parsed.get("currency", "INR"),
        source=TransactionSource.receipt,
        status=TransactionStatus.pending,
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)

    from app.bot.notifications import notify_new_transaction
    await notify_new_transaction(current_user, transaction)

    return {
        "transaction_id": str(transaction.id),
        "amount": parsed["amount"],
        "merchant": parsed.get("merchant"),
        "date": parsed.get("date"),
        "currency": parsed.get("currency", "INR"),
        "line_items": parsed.get("line_items", []),
    }

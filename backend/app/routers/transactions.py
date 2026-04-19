from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware import get_current_user
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
async def list_transactions(
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    transactions = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "amount": t.amount,
            "merchant": t.merchant,
            "date": t.date.isoformat(),
            "currency": t.currency,
            "source": t.source.value,
            "status": t.status.value,
            "created_at": t.created_at.isoformat(),
        }
        for t in transactions
    ]

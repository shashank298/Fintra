from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware import get_current_user
from app.models.user import User
from app.services import splitwise as sw_service

router = APIRouter(prefix="/splitwise", tags=["splitwise"])


class SplitEntry(BaseModel):
    user_id: int
    paid_share: float
    owed_share: float


class CreateExpenseRequest(BaseModel):
    description: str
    amount: float
    currency: str = "INR"
    date: str
    group_id: int
    splits: list[SplitEntry]


@router.get("/connect")
async def connect(current_user: User = Depends(get_current_user)):
    return {"oauth_url": sw_service.get_oauth_url()}


@router.get("/callback")
async def callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token_data = await sw_service.exchange_code(code)
    await sw_service.save_token(db, current_user.id, token_data)
    return {"detail": "Splitwise connected"}


@router.get("/status")
async def status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connected = await sw_service.is_connected(db, current_user.id)
    return {"connected": connected}


@router.get("/groups")
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = await sw_service.get_token(db, current_user.id)
    if not token:
        raise HTTPException(status_code=401, detail="SPLITWISE_RECONNECT_REQUIRED")
    try:
        raw = await sw_service.api_get(token, "/get_groups")
    except PermissionError:
        raise HTTPException(status_code=401, detail="SPLITWISE_RECONNECT_REQUIRED")
    return sw_service.parse_groups(raw)


@router.get("/groups/{group_id}/members")
async def list_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = await sw_service.get_token(db, current_user.id)
    if not token:
        raise HTTPException(status_code=401, detail="SPLITWISE_RECONNECT_REQUIRED")
    try:
        raw = await sw_service.api_get(token, f"/get_group/{group_id}")
    except PermissionError:
        raise HTTPException(status_code=401, detail="SPLITWISE_RECONNECT_REQUIRED")
    return sw_service.parse_members(raw.get("group", {}))


@router.post("/expense")
async def create_expense(
    body: CreateExpenseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await sw_service.create_expense(
            db,
            current_user.id,
            body.description,
            body.amount,
            body.currency,
            body.date,
            body.group_id,
            [s.model_dump() for s in body.splits],
        )
    except PermissionError:
        raise HTTPException(status_code=401, detail="SPLITWISE_RECONNECT_REQUIRED")
    return result

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.oauth_token import OAuthToken, OAuthProvider
from app.services.crypto import encrypt, decrypt

settings = get_settings()

SPLITWISE_AUTH_URL = "https://secure.splitwise.com/oauth/authorize"
SPLITWISE_TOKEN_URL = "https://secure.splitwise.com/oauth/token"
SPLITWISE_API_BASE = "https://secure.splitwise.com/api/v3.0"


def get_oauth_url() -> str:
    return (
        f"{SPLITWISE_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.SPLITWISE_CONSUMER_KEY}"
        f"&redirect_uri={settings.SPLITWISE_REDIRECT_URI}"
    )


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SPLITWISE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.SPLITWISE_CONSUMER_KEY,
                "client_secret": settings.SPLITWISE_CONSUMER_SECRET,
                "redirect_uri": settings.SPLITWISE_REDIRECT_URI,
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def save_token(db: AsyncSession, user_id: uuid.UUID, token_data: dict) -> OAuthToken:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.splitwise,
        )
    )
    token = result.scalar_one_or_none()

    expires_at = None
    if token_data.get("expires_in"):
        expires_at = datetime.now(timezone.utc).replace(microsecond=0)

    if token:
        token.access_token = encrypt(token_data["access_token"])
        token.refresh_token = encrypt(token_data.get("refresh_token", "")) if token_data.get("refresh_token") else None
        token.expires_at = expires_at
        token.scope = token_data.get("scope")
    else:
        token = OAuthToken(
            user_id=user_id,
            provider=OAuthProvider.splitwise,
            access_token=encrypt(token_data["access_token"]),
            refresh_token=encrypt(token_data["refresh_token"]) if token_data.get("refresh_token") else None,
            expires_at=expires_at,
            scope=token_data.get("scope"),
        )
        db.add(token)

    await db.commit()
    return token


async def get_token(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.splitwise,
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        return None
    return decrypt(token.access_token)


async def is_connected(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.splitwise,
        )
    )
    return result.scalar_one_or_none() is not None


async def api_get(access_token: str, path: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SPLITWISE_API_BASE}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 401:
            raise PermissionError("SPLITWISE_RECONNECT_REQUIRED")
        resp.raise_for_status()
        return resp.json()


async def api_post(access_token: str, path: str, payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SPLITWISE_API_BASE}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 401:
            raise PermissionError("SPLITWISE_RECONNECT_REQUIRED")
        resp.raise_for_status()
        return resp.json()


def parse_groups(raw: dict) -> list[dict]:
    groups = []
    for g in raw.get("groups", []):
        groups.append({
            "id": g["id"],
            "name": g["name"],
            "members_count": len(g.get("members", [])),
        })
    return groups


def parse_members(raw: dict) -> list[dict]:
    members = []
    for m in raw.get("members", []):
        members.append({
            "id": m["id"],
            "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
            "email": m.get("email", ""),
            "avatar": m.get("picture", {}).get("medium", ""),
        })
    return members


async def create_expense(
    db: AsyncSession,
    user_id: uuid.UUID,
    description: str,
    amount: float,
    currency: str,
    date: str,
    group_id: int,
    splits: list[dict],
) -> dict:
    access_token = await get_token(db, user_id)
    if not access_token:
        raise PermissionError("SPLITWISE_RECONNECT_REQUIRED")

    users_payload = []
    for s in splits:
        users_payload.append({
            "user_id": s["user_id"],
            "paid_share": f"{s['paid_share']:.2f}",
            "owed_share": f"{s['owed_share']:.2f}",
        })

    payload = {
        "cost": f"{amount:.2f}",
        "description": description,
        "currency_code": currency,
        "date": date,
        "group_id": group_id,
        "users": users_payload,
    }

    data = await api_post(access_token, "/create_expense", payload)
    expense = data.get("expenses", [{}])[0]
    expense_id = expense.get("id")
    deep_link = f"https://splitwise.com/expenses/{expense_id}" if expense_id else ""
    return {"expense_id": expense_id, "deep_link": deep_link}

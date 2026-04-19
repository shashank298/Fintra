import uuid
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.oauth_token import OAuthToken, OAuthProvider
from app.models.gmail_watch import GmailWatch
from app.services.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)
settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]

ALLOWED_SENDERS = {
    "alerts@hdfcbank.net",
    "alerts@axisbank.com",
    "donotreply@icicibank.com",
    "gpay-noreply@google.com",
    "noreply@phonepe.com",
    "noreply@paytm.com",
    "alerts@kotak.com",
    "care@indusind.com",
}


def get_oauth_url(state: str = "") -> str:
    import urllib.parse
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def save_token(db: AsyncSession, user_id: uuid.UUID, token_data: dict) -> OAuthToken:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.gmail,
        )
    )
    token = result.scalar_one_or_none()

    expires_at = None
    if token_data.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))

    if token:
        token.access_token = encrypt(token_data["access_token"])
        if token_data.get("refresh_token"):
            token.refresh_token = encrypt(token_data["refresh_token"])
        token.expires_at = expires_at
        token.scope = token_data.get("scope")
    else:
        token = OAuthToken(
            user_id=user_id,
            provider=OAuthProvider.gmail,
            access_token=encrypt(token_data["access_token"]),
            refresh_token=encrypt(token_data["refresh_token"]) if token_data.get("refresh_token") else None,
            expires_at=expires_at,
            scope=token_data.get("scope"),
        )
        db.add(token)

    await db.commit()
    return token


async def get_credentials(db: AsyncSession, user_id: uuid.UUID) -> Optional[Credentials]:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.gmail,
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        return None

    access_token = decrypt(token.access_token)
    refresh_token = decrypt(token.refresh_token) if token.refresh_token else None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )

    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        if refresh_token:
            try:
                new_data = await refresh_access_token(refresh_token)
                await save_token(db, user_id, new_data)
                creds = Credentials(
                    token=new_data["access_token"],
                    refresh_token=refresh_token,
                    token_uri=GOOGLE_TOKEN_URL,
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET,
                    scopes=SCOPES,
                )
            except Exception as e:
                logger.error(f"Gmail token refresh failed for user {user_id}: {e}")
                return None

    return creds


async def is_connected(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == OAuthProvider.gmail,
        )
    )
    return result.scalar_one_or_none() is not None


async def setup_watch(db: AsyncSession, user_id: uuid.UUID) -> dict:
    creds = await get_credentials(db, user_id)
    if not creds:
        raise ValueError("No Gmail credentials for user")

    service = build("gmail", "v1", credentials=creds)
    watch_response = service.users().watch(
        userId="me",
        body={"topicName": settings.PUBSUB_TOPIC, "labelIds": ["INBOX"]},
    ).execute()

    history_id = str(watch_response["historyId"])
    expiry = datetime.now(timezone.utc) + timedelta(days=7)

    result = await db.execute(select(GmailWatch).where(GmailWatch.user_id == user_id))
    watch = result.scalar_one_or_none()

    if watch:
        watch.history_id = history_id
        watch.watch_expiry = expiry
        watch.pubsub_topic = settings.PUBSUB_TOPIC
    else:
        watch = GmailWatch(
            user_id=user_id,
            history_id=history_id,
            watch_expiry=expiry,
            pubsub_topic=settings.PUBSUB_TOPIC,
        )
        db.add(watch)

    await db.commit()
    return {"history_id": history_id, "watch_expiry": expiry.isoformat()}


async def get_new_emails(db: AsyncSession, user_id: uuid.UUID, since_history_id: str) -> list[dict]:
    creds = await get_credentials(db, user_id)
    if not creds:
        return []

    service = build("gmail", "v1", credentials=creds)
    emails = []

    try:
        history = service.users().history().list(
            userId="me",
            startHistoryId=since_history_id,
            historyTypes=["messageAdded"],
        ).execute()

        messages = []
        for record in history.get("history", []):
            for msg_added in record.get("messagesAdded", []):
                messages.append(msg_added["message"]["id"])

        for msg_id in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()

                sender = ""
                for header in msg.get("payload", {}).get("headers", []):
                    if header["name"].lower() == "from":
                        sender = header["value"].lower()
                        break

                if not any(allowed in sender for allowed in ALLOWED_SENDERS):
                    continue

                body = _extract_body(msg)
                emails.append({
                    "id": msg_id,
                    "sender": sender,
                    "body": body,
                    "snippet": msg.get("snippet", ""),
                })
            except Exception as e:
                logger.error(f"Error fetching message {msg_id}: {e}")

        new_history_id = history.get("historyId", since_history_id)
        result = await db.execute(select(GmailWatch).where(GmailWatch.user_id == user_id))
        watch = result.scalar_one_or_none()
        if watch:
            watch.history_id = str(new_history_id)
            await db.commit()

    except Exception as e:
        logger.error(f"Gmail history fetch failed for user {user_id}: {e}")

    return emails


def _extract_body(msg: dict) -> str:
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
    return msg.get("snippet", "")

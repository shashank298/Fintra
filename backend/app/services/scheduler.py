import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.gmail_watch import GmailWatch
from app.services.gmail import setup_watch

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def renew_expiring_gmail_watches():
    """Renew Gmail watches expiring within the next 24 hours."""
    logger.info("Running Gmail watch renewal job")
    threshold = datetime.now(timezone.utc) + timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GmailWatch).where(GmailWatch.watch_expiry <= threshold)
        )
        watches = result.scalars().all()

        for watch in watches:
            try:
                await setup_watch(db, watch.user_id)
                logger.info(f"Renewed Gmail watch for user {watch.user_id}")
            except Exception as e:
                logger.error(f"Failed to renew Gmail watch for user {watch.user_id}: {e}")


def start_scheduler():
    scheduler.add_job(
        renew_expiring_gmail_watches,
        "interval",
        hours=144,
        id="gmail_watch_renewal",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler():
    scheduler.shutdown()

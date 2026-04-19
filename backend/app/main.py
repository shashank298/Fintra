import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, splitwise, gmail, receipt, telegram, transactions
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

_telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _telegram_app
    start_scheduler()

    from app.bot.handlers import build_application
    _telegram_app = build_application()
    await _telegram_app.initialize()

    if settings.TELEGRAM_WEBHOOK_URL and settings.TELEGRAM_BOT_TOKEN:
        try:
            await _telegram_app.bot.set_webhook(
                url=f"{settings.TELEGRAM_WEBHOOK_URL}",
                drop_pending_updates=True,
            )
            logger.info("Telegram webhook set")
        except Exception as e:
            logger.warning(f"Could not set Telegram webhook: {e}")

    yield

    stop_scheduler()
    if _telegram_app:
        await _telegram_app.shutdown()


app = FastAPI(
    title="SplitEase API",
    description="Multi-user expense automation with Gmail, Splitwise, and Telegram",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(splitwise.router)
app.include_router(gmail.router)
app.include_router(receipt.router)
app.include_router(telegram.router)
app.include_router(transactions.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SplitEase"}

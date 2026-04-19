import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

_bot = None


def get_bot():
    global _bot
    if _bot is None:
        from telegram import Bot
        from app.config import get_settings
        settings = get_settings()
        _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


async def notify_new_transaction(user: "User", transaction: "Transaction") -> None:
    if not user.telegram_chat_id:
        return
    try:
        bot = get_bot()
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        text = (
            f"💳 New transaction detected!\n\n"
            f"Amount: ₹{transaction.amount:,.2f}\n"
            f"Merchant: {transaction.merchant}\n"
            f"Date: {transaction.date.strftime('%d %b %Y')}\n"
            f"Source: {transaction.source.value}\n\n"
            f"Add to Splitwise?"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"confirm_yes:{transaction.id}"),
                InlineKeyboardButton("❌ Skip", callback_data=f"confirm_skip:{transaction.id}"),
            ]
        ])
        await bot.send_message(chat_id=user.telegram_chat_id, text=text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Failed to notify user {user.id} via Telegram: {e}")


async def notify_splitwise_expired(user: "User") -> None:
    if not user.telegram_chat_id:
        return
    try:
        bot = get_bot()
        await bot.send_message(
            chat_id=user.telegram_chat_id,
            text="⚠️ Your Splitwise connection expired. Please reconnect in the app.",
        )
    except Exception as e:
        logger.error(f"Failed to send Splitwise expiry notice to user {user.id}: {e}")


async def notify_gmail_expired(user: "User") -> None:
    if not user.telegram_chat_id:
        return
    try:
        bot = get_bot()
        await bot.send_message(
            chat_id=user.telegram_chat_id,
            text="⚠️ Your Gmail connection expired and could not be refreshed. Please reconnect in the app.",
        )
    except Exception as e:
        logger.error(f"Failed to send Gmail expiry notice to user {user.id}: {e}")

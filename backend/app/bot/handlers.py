import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.transaction import Transaction, TransactionStatus
from app.models.conversation_state import ConversationState, ConversationStateEnum
from app.bot.states import CONFIRM, SELECT_GROUP, SELECT_MEMBERS, SELECT_SPLIT_TYPE, CUSTOM_SPLIT, DONE
from app.services import splitwise as sw_service
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GROUPS_PER_PAGE = 8
CONVERSATION_TIMEOUT = 30 * 60  # 30 minutes


async def _get_user_by_chat_id(chat_id: str) -> Optional[User]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_chat_id == str(chat_id)))
        return result.scalar_one_or_none()


async def _get_transaction(tx_id: str) -> Optional[Transaction]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Transaction).where(Transaction.id == uuid.UUID(tx_id)))
        return result.scalar_one_or_none()


async def _save_conv_state(user_id: uuid.UUID, tx_id: uuid.UUID, state: str, context_data: dict):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(
                ConversationState.user_id == user_id,
                ConversationState.transaction_id == tx_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.state = ConversationStateEnum(state)
            conv.context = context_data
            conv.updated_at = datetime.now(timezone.utc)
        else:
            conv = ConversationState(
                user_id=user_id,
                transaction_id=tx_id,
                state=ConversationStateEnum(state),
                context=context_data,
            )
            db.add(conv)
        await db.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to SplitEase!\n\nPlease send your registered email address to link your account."
    )
    context.user_data["awaiting_email"] = True


async def handle_email_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_email"):
        return
    email = update.message.text.strip().lower()
    chat_id = str(update.effective_chat.id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("❌ No account found with that email. Please sign up in the app first.")
            return
        user.telegram_chat_id = chat_id
        await db.commit()

    context.user_data.pop("awaiting_email", None)
    await update.message.reply_text(
        f"✅ Account linked! You'll receive transaction notifications here.\n\n"
        f"Use /pending to see pending transactions, /help for all commands."
    )


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    user = await _get_user_by_chat_id(chat_id)
    if not user:
        await update.message.reply_text("❌ Account not linked. Send /start and enter your email.")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.status == TransactionStatus.pending,
            ).order_by(Transaction.created_at.desc()).limit(10)
        )
        transactions = result.scalars().all()

    if not transactions:
        await update.message.reply_text("✅ No pending transactions.")
        return

    keyboard = []
    for tx in transactions:
        label = f"₹{tx.amount:,.0f} at {tx.merchant[:20]} ({tx.date.strftime('%d %b')})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"pending_tx:{tx.id}")])

    await update.message.reply_text(
        "📋 Pending transactions (tap to process):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *SplitEase Commands*\n\n"
        "/start — Link your account\n"
        "/pending — View pending transactions\n"
        "/skip — Skip the current active transaction\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tx_id = context.user_data.get("active_tx_id")
    if not tx_id:
        await update.message.reply_text("No active transaction to skip.")
        return ConversationHandler.END

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Transaction)
            .where(Transaction.id == uuid.UUID(tx_id))
            .values(status=TransactionStatus.skipped)
        )
        await db.commit()

    context.user_data.clear()
    await update.message.reply_text("⏭️ Transaction skipped.")
    return ConversationHandler.END


# ─── CONFIRM state ───────────────────────────────────────────────────────────

async def handle_pending_tx_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tx_id = query.data.split(":")[1]
    tx = await _get_transaction(tx_id)
    if not tx:
        await query.edit_message_text("Transaction not found.")
        return ConversationHandler.END

    context.user_data["active_tx_id"] = tx_id
    context.user_data["user_id"] = str(tx.user_id)
    context.user_data["amount"] = tx.amount
    context.user_data["merchant"] = tx.merchant
    context.user_data["currency"] = tx.currency
    context.user_data["tx_date"] = tx.date.strftime("%Y-%m-%d")

    text = (
        f"💳 New transaction detected!\n\n"
        f"Amount: ₹{tx.amount:,.2f}\n"
        f"Merchant: {tx.merchant}\n"
        f"Date: {tx.date.strftime('%d %b %Y')}\n"
        f"Source: {tx.source.value}\n\n"
        f"Add to Splitwise?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"confirm_yes:{tx_id}"),
            InlineKeyboardButton("❌ Skip", callback_data=f"confirm_skip:{tx_id}"),
        ]
    ])
    await query.edit_message_text(text, reply_markup=keyboard)
    return CONFIRM


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action, tx_id = query.data.split(":", 1)

    tx = await _get_transaction(tx_id)
    if not tx:
        await query.edit_message_text("Transaction not found.")
        return ConversationHandler.END

    context.user_data["active_tx_id"] = tx_id
    context.user_data["user_id"] = str(tx.user_id)
    context.user_data["amount"] = tx.amount
    context.user_data["merchant"] = tx.merchant
    context.user_data["currency"] = tx.currency
    context.user_data["tx_date"] = tx.date.strftime("%Y-%m-%d")

    if action == "confirm_skip":
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Transaction)
                .where(Transaction.id == tx.id)
                .values(status=TransactionStatus.skipped)
            )
            await db.commit()
        await query.edit_message_text("⏭️ Transaction skipped.")
        return ConversationHandler.END

    return await _show_groups(query, context, page=0)


async def _show_groups(query, context: ContextTypes.DEFAULT_TYPE, page: int) -> int:
    user_id = uuid.UUID(context.user_data["user_id"])
    async with AsyncSessionLocal() as db:
        token = await sw_service.get_token(db, user_id)

    if not token:
        await query.edit_message_text("❌ Splitwise not connected. Please reconnect in the app.")
        return ConversationHandler.END

    try:
        raw = await sw_service.api_get(token, "/get_groups")
        groups = sw_service.parse_groups(raw)
    except PermissionError:
        await query.edit_message_text("❌ Splitwise session expired. Please reconnect in the app.")
        return ConversationHandler.END

    context.user_data["groups"] = groups
    context.user_data["groups_page"] = page

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    page_groups = groups[start:end]

    keyboard = []
    for g in page_groups:
        keyboard.append([InlineKeyboardButton(g["name"], callback_data=f"group:{g['id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Previous", callback_data=f"groups_page:{page-1}"))
    if end < len(groups):
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"groups_page:{page+1}"))
    if nav:
        keyboard.append(nav)

    await query.edit_message_text(
        "👥 Select a Splitwise group:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_GROUP


async def groups_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    return await _show_groups(query, context, page=page)


async def group_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split(":")[1])
    groups = context.user_data.get("groups", [])
    group_name = next((g["name"] for g in groups if g["id"] == group_id), str(group_id))

    context.user_data["group_id"] = group_id
    context.user_data["group_name"] = group_name
    context.user_data["selected_members"] = []

    user_id = uuid.UUID(context.user_data["user_id"])
    async with AsyncSessionLocal() as db:
        token = await sw_service.get_token(db, user_id)

    try:
        raw = await sw_service.api_get(token, f"/get_group/{group_id}")
        members = sw_service.parse_members(raw.get("group", {}))
    except Exception:
        await query.edit_message_text("❌ Failed to fetch group members.")
        return ConversationHandler.END

    context.user_data["members"] = members
    return await _show_members(query, context)


async def _show_members(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    members = context.user_data.get("members", [])
    selected = context.user_data.get("selected_members", [])

    keyboard = []
    for m in members:
        prefix = "✅" if m["id"] in selected else "◻️"
        keyboard.append([InlineKeyboardButton(
            f"{prefix} {m['name']}", callback_data=f"toggle_member:{m['id']}"
        )])
    keyboard.append([InlineKeyboardButton("✔️ Confirm Selection", callback_data="members_confirm")])

    await query.edit_message_text(
        "👤 Select members to split with (tap to toggle):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_MEMBERS


async def toggle_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    member_id = int(query.data.split(":")[1])
    selected = context.user_data.get("selected_members", [])

    if member_id in selected:
        selected.remove(member_id)
    else:
        selected.append(member_id)
    context.user_data["selected_members"] = selected

    return await _show_members(query, context)


async def members_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected = context.user_data.get("selected_members", [])
    if not selected:
        await query.answer("Please select at least one member.", show_alert=True)
        return SELECT_MEMBERS

    amount = context.user_data["amount"]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚖️ Split Equally", callback_data="split_equal"),
            InlineKeyboardButton("✏️ Custom %", callback_data="split_custom"),
        ]
    ])
    await query.edit_message_text(
        f"How should ₹{amount:,.2f} be split?",
        reply_markup=keyboard,
    )
    return SELECT_SPLIT_TYPE


async def split_equal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await _finalize_expense(query, context, splits=None)


async def split_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    members = context.user_data.get("members", [])
    selected_ids = context.user_data.get("selected_members", [])
    selected_names = [m["name"] for m in members if m["id"] in selected_ids]

    member_list = "\n".join(f"{i+1}. {name}" for i, name in enumerate(selected_names))
    await query.edit_message_text(
        f"Enter percentages as comma-separated values (must sum to 100):\n\n{member_list}\n\n"
        f"Example for {len(selected_names)} people: {','.join(['50'] * len(selected_names))}"
    )
    return CUSTOM_SPLIT


async def custom_split_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        parts = [float(p.strip()) for p in text.split(",")]
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter numbers separated by commas.")
        return CUSTOM_SPLIT

    selected_ids = context.user_data.get("selected_members", [])
    if len(parts) != len(selected_ids):
        await update.message.reply_text(
            f"❌ Expected {len(selected_ids)} values, got {len(parts)}. Try again."
        )
        return CUSTOM_SPLIT

    if abs(sum(parts) - 100) > 0.01:
        await update.message.reply_text(
            f"❌ Percentages sum to {sum(parts):.1f}, must be exactly 100. Try again."
        )
        return CUSTOM_SPLIT

    context.user_data["custom_percentages"] = parts

    class FakeQuery:
        async def edit_message_text(self, *a, **kw):
            await update.message.reply_text(*a, **kw)

    return await _finalize_expense(FakeQuery(), context, splits=parts)


async def _finalize_expense(query, context: ContextTypes.DEFAULT_TYPE, splits: Optional[list]) -> int:
    amount = context.user_data["amount"]
    merchant = context.user_data["merchant"]
    currency = context.user_data["currency"]
    tx_date = context.user_data["tx_date"]
    group_id = context.user_data["group_id"]
    group_name = context.user_data["group_name"]
    selected_ids = context.user_data["selected_members"]
    members = context.user_data["members"]
    user_id = uuid.UUID(context.user_data["user_id"])
    tx_id = context.user_data["active_tx_id"]

    if splits is None:
        per_person = amount / len(selected_ids)
        split_data = [{"user_id": mid, "paid_share": 0.0, "owed_share": per_person} for mid in selected_ids]
        split_data[0]["paid_share"] = amount
        split_summary = f"Equal (₹{per_person:,.2f} each)"
    else:
        split_data = []
        for i, mid in enumerate(selected_ids):
            owed = amount * splits[i] / 100
            split_data.append({"user_id": mid, "paid_share": 0.0, "owed_share": owed})
        split_data[0]["paid_share"] = amount
        names = [m["name"] for m in members if m["id"] in selected_ids]
        split_summary = ", ".join(f"{n}: {p:.0f}%" for n, p in zip(names, splits))

    async with AsyncSessionLocal() as db:
        try:
            result = await sw_service.create_expense(
                db, user_id, merchant, amount, currency, tx_date, group_id, split_data
            )
        except PermissionError:
            await query.edit_message_text("❌ Splitwise session expired. Please reconnect in the app.")
            return ConversationHandler.END

        await db.execute(
            update(Transaction)
            .where(Transaction.id == uuid.UUID(tx_id))
            .values(status=TransactionStatus.added)
        )
        await db.commit()

    deep_link = result.get("deep_link", "")
    keyboard = None
    if deep_link:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("View on Splitwise 🔗", url=deep_link)
        ]])

    await query.edit_message_text(
        f"✅ Expense added!\n\n"
        f"₹{amount:,.2f} at {merchant}\n"
        f"Split: {split_summary}\n"
        f"Group: {group_name}",
        reply_markup=keyboard,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat:
        try:
            bot = context.bot
            await bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏰ Session expired. Your transaction is saved. Use /pending to resume.",
            )
        except Exception:
            pass
    context.user_data.clear()
    return ConversationHandler.END


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_pending_tx_callback, pattern=r"^pending_tx:"),
            CallbackQueryHandler(confirm_callback, pattern=r"^confirm_(yes|skip):"),
        ],
        states={
            CONFIRM: [
                CallbackQueryHandler(confirm_callback, pattern=r"^confirm_(yes|skip):"),
            ],
            SELECT_GROUP: [
                CallbackQueryHandler(group_selected_callback, pattern=r"^group:"),
                CallbackQueryHandler(groups_page_callback, pattern=r"^groups_page:"),
            ],
            SELECT_MEMBERS: [
                CallbackQueryHandler(toggle_member_callback, pattern=r"^toggle_member:"),
                CallbackQueryHandler(members_confirm_callback, pattern=r"^members_confirm$"),
            ],
            SELECT_SPLIT_TYPE: [
                CallbackQueryHandler(split_equal_callback, pattern=r"^split_equal$"),
                CallbackQueryHandler(split_custom_callback, pattern=r"^split_custom$"),
            ],
            CUSTOM_SPLIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_split_input),
            ],
        },
        fallbacks=[
            CommandHandler("skip", skip),
        ],
        conversation_timeout=CONVERSATION_TIMEOUT,
        name="expense_conversation",
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_link))

    return app

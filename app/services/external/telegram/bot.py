"""
Telegram bot lifecycle management.

Handles bot initialization, long-polling startup/shutdown, and
thread-safe notification delivery from the polling loop.
"""

import asyncio
from concurrent.futures import Future
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_IDS
from app.services.common.logger import get_logger
from app.services.external.telegram.handlers.admin_handlers import (
    cmd_start, cmd_help, cmd_reviews, cmd_stats,
)
from app.services.external.telegram.handlers.review_handlers import handle_manage, handle_callback
from app.services.external.telegram.handlers.edit_handlers import (
    handle_edit_start, handle_edit_text, handle_post_edit,
    handle_edit_cancel_confirm, handle_edit_cancel,
    WAITING_FOR_EDIT, CONFIRM_EDIT,
)

logger = get_logger(__name__)

# Global bot application reference
_app: Optional[Application] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None


async def start_bot(creds):
    """
    Initialize and start the Telegram bot.

    Called from the FastAPI lifespan startup.
    Runs in the same event loop as FastAPI.

    Args:
        creds: Google API credentials (stored in bot_data for callback handlers)
    """
    global _app, _main_loop

    logger.info("Starting Telegram bot")

    _app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Store credentials in bot_data for handlers
    _app.bot_data["creds"] = creds

    # Register command handlers
    _app.add_handler(CommandHandler("start", cmd_start))
    _app.add_handler(CommandHandler("help", cmd_help))
    _app.add_handler(CommandHandler("reviews", cmd_reviews))
    _app.add_handler(CommandHandler("stats", cmd_stats))

    # Register edit conversation handler (must come before the flat CallbackQueryHandler)
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_edit_start, pattern=r"^edit:")],
        states={
            WAITING_FOR_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_text),
                CommandHandler("cancel", handle_edit_cancel),
            ],
            CONFIRM_EDIT: [
                CallbackQueryHandler(handle_post_edit, pattern=r"^post_edit$"),
                CallbackQueryHandler(handle_edit_cancel_confirm, pattern=r"^cancel_edit$"),
                CommandHandler("cancel", handle_edit_cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_edit_cancel)],
    )
    _app.add_handler(edit_conv)

    # Register manage callback (must come before the flat CallbackQueryHandler)
    _app.add_handler(CallbackQueryHandler(handle_manage, pattern=r"^manage:"))

    # Register callback handler for approve/reject inline buttons
    _app.add_handler(CallbackQueryHandler(handle_callback))

    await _app.initialize()
    await _app.updater.start_polling(drop_pending_updates=True)
    await _app.start()

    _main_loop = asyncio.get_event_loop()

    logger.info("Telegram bot started (polling mode)")


async def stop_bot():
    """
    Stop the Telegram bot.

    Called from the FastAPI lifespan shutdown.
    """
    global _app

    if _app is None:
        return

    logger.info("Stopping Telegram bot")
    await _app.updater.stop()
    await _app.stop()
    await _app.shutdown()
    logger.info("Telegram bot stopped")


def send_review_notification(review_id: str, location_title: str, reviewer_name: str,
                              star_rating: int, review_text: str, draft_reply: str) -> Optional[Future]:
    """
    Send a notification about a new bad review to the owner via Telegram.

    Called from the polling loop (thread pool). Returns a Future the caller
    can block on to confirm delivery before marking the review as seen.

    Returns None if the bot is not yet initialised.
    """
    if _app is None or _main_loop is None:
        logger.warning("Bot not initialised — cannot send notification for review %s", review_id)
        return None

    coro = _send_notification_async(review_id, location_title, reviewer_name,
                                     star_rating, review_text, draft_reply)
    return asyncio.run_coroutine_threadsafe(coro, _main_loop)


async def _send_notification_async(review_id: str, location_title: str, reviewer_name: str,
                                    star_rating: int, review_text: str, draft_reply: str):
    """Async version of sending notification message.

    Exceptions are NOT caught here so they propagate through the Future
    returned by send_review_notification — letting the polling loop decide
    whether to mark the review as seen.
    """
    stars = "⭐" * star_rating
    message = (
        f"{stars} BAD REVIEW — {location_title} ({star_rating}★)\n"
        f"From: {reviewer_name}\n\n"
        f'"{review_text}"\n\n'
        f"Draft response:\n"
        f'"{draft_reply}"'
    )

    # Store review_id and use short key in callback_data (Telegram limit: 64 bytes)
    store = _app.bot_data.setdefault("review_id_map", {})
    short_key = None
    for k, v in store.items():
        if v == review_id:
            short_key = k
            break
    if short_key is None:
        short_key = len(store)
        store[short_key] = review_id

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Post", callback_data=f"approve:{short_key}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{short_key}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{short_key}"),
        ]
    ])

    for chat_id in TELEGRAM_OWNER_CHAT_IDS:
        await _app.bot.send_message(chat_id=chat_id, text=message, reply_markup=keyboard)

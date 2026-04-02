"""
Telegram bot using python-telegram-bot v20+

Integrated into FastAPI's event loop (no separate thread).
Supports long-polling mode for local development.
"""

import asyncio
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID
from app.services.database import (
    get_all_pending_replies, get_stats, get_pending_reply, mark_posted, mark_rejected
)
from app.services.google_api import post_reply


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

    print("   Starting Telegram bot...")

    # Build the application
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

    # Register callback handler for inline buttons
    _app.add_handler(CallbackQueryHandler(handle_callback))

    # Initialize the application
    await _app.initialize()

    # Start polling
    await _app.updater.start_polling(drop_pending_updates=True)

    # Start the application
    await _app.start()

    # Store the current event loop for use in send_review_notification
    _main_loop = asyncio.get_event_loop()

    print("   ✅ Telegram bot started (polling mode)")


async def stop_bot():
    """
    Stop the Telegram bot.

    Called from the FastAPI lifespan shutdown.
    """
    global _app

    if _app is None:
        return

    print("   Stopping Telegram bot...")
    await _app.updater.stop()
    await _app.stop()
    await _app.shutdown()
    print("   ✅ Telegram bot stopped")


def send_review_notification(review_id: str, location_title: str, reviewer_name: str,
                            star_rating: int, review_text: str, draft_reply: str):
    """
    Send a notification about a new bad review to the owner via Telegram.

    This function is called from the polling loop (running in a thread pool).
    It bridges from sync code to the async bot using asyncio.run_coroutine_threadsafe.

    Args:
        review_id: Review ID for callback data
        location_title: Location name
        reviewer_name: Name of reviewer
        star_rating: Star rating (1-5)
        review_text: The review text
        draft_reply: AI-generated draft response
    """
    if _app is None or _main_loop is None:
        return

    # Schedule the async send on the main event loop
    coro = _send_notification_async(review_id, location_title, reviewer_name,
                                    star_rating, review_text, draft_reply)
    asyncio.run_coroutine_threadsafe(coro, _main_loop)


async def _send_notification_async(review_id: str, location_title: str, reviewer_name: str,
                                   star_rating: int, review_text: str, draft_reply: str):
    """Async version of sending notification message."""
    try:
        # Format the notification message
        stars = "⭐" * star_rating
        message = (
            f"{stars} BAD REVIEW — {location_title} ({star_rating}★)\n"
            f"From: {reviewer_name}\n\n"
            f'"{review_text}"\n\n'
            f"Draft response:\n"
            f'"{draft_reply}"'
        )

        # Create inline keyboard for approve/reject
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Post", callback_data=f"approve:{review_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{review_id}"),
            ]
        ])

        # Send to owner
        await _app.bot.send_message(
            chat_id=int(TELEGRAM_OWNER_CHAT_ID),
            text=message,
            reply_markup=keyboard,
        )
    except Exception as e:
        print(f"⚠️  Failed to send Telegram notification: {e}")


# ============================================================================
# Command Handlers
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    # Owner check
    if str(update.effective_chat.id) != str(TELEGRAM_OWNER_CHAT_ID):
        await update.message.reply_text("🚫 Unauthorized. This bot is for the owner only.")
        return

    await update.message.reply_text(
        "👋 Welcome to the Google Reviews Bot!\n\n"
        "I'll notify you about bad reviews (≤3 stars) and let you approve or reject responses.\n\n"
        "Commands:\n"
        "/help — Show all commands\n"
        "/reviews — List pending drafts\n"
        "/stats — Database statistics"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    # Owner check
    if str(update.effective_chat.id) != str(TELEGRAM_OWNER_CHAT_ID):
        await update.message.reply_text("🚫 Unauthorized.")
        return

    await update.message.reply_text(
        "📋 Available commands:\n\n"
        "/start — Greet and show intro\n"
        "/reviews — List all pending drafts waiting for approval\n"
        "/stats — Show database statistics\n\n"
        "When you receive a review notification:\n"
        "• Tap [✅ Post] to approve and post to Google\n"
        "• Tap [❌ Reject] to discard the draft"
    )


async def cmd_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reviews command — list pending drafts."""
    # Owner check
    if str(update.effective_chat.id) != str(TELEGRAM_OWNER_CHAT_ID):
        await update.message.reply_text("🚫 Unauthorized.")
        return

    pending = get_all_pending_replies("pending")

    if not pending:
        await update.message.reply_text("✅ No pending reviews!")
        return

    message = f"📋 Pending Reviews ({len(pending)}):\n\n"
    for i, review in enumerate(pending, 1):
        message += (
            f"{i}. {review['location_name']} ({review['star_rating']}★)\n"
            f"   From: {review['reviewer_name']}\n"
            f'   "{review["review_text"][:80]}..."\n'
            f"   Draft: {review['draft_reply'][:80]}...\n\n"
        )

    await update.message.reply_text(message)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command — show database statistics."""
    # Owner check
    if str(update.effective_chat.id) != str(TELEGRAM_OWNER_CHAT_ID):
        await update.message.reply_text("🚫 Unauthorized.")
        return

    stats = get_stats()

    message = (
        f"📊 Database Statistics:\n\n"
        f"Total reviews seen: {stats['total_seen']}\n"
        f"Pending approvals: {stats['pending_approvals']}\n"
        f"Posted replies: {stats['total_posted']}"
    )

    await update.message.reply_text(message)


# ============================================================================
# Callback Handler (for inline button presses)
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks (approve/reject)."""
    query = update.callback_query
    await query.answer()  # Dismiss the loading state

    # Parse callback data
    try:
        action, review_id = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid callback data")
        return

    # Fetch draft from database
    draft = get_pending_reply(review_id)
    if not draft:
        await query.edit_message_text("❌ Draft not found")
        return

    creds = context.bot_data.get("creds")
    if not creds:
        await query.edit_message_text("❌ Credentials not available")
        return

    if action == "approve":
        # Post the reply to Google My Business
        location_name = draft["location_name"]
        reply_text = draft["draft_reply"]

        result = post_reply(creds, location_name, review_id, reply_text)
        if result:
            # Mark as posted in database
            mark_posted(review_id, reply_text)
            await query.edit_message_text("✅ Posted to Google My Business")
            print(f"✅ Review {review_id} approved and posted")
        else:
            await query.edit_message_text("❌ Failed to post to Google — check logs")
            print(f"❌ Failed to post review {review_id}")

    elif action == "reject":
        # Mark as rejected in database
        mark_rejected(review_id)
        await query.edit_message_text("❌ Draft rejected")
        print(f"✅ Review {review_id} rejected")

    else:
        await query.edit_message_text(f"❌ Unknown action: {action}")

"""
Admin command handlers for the Telegram bot.

Handles /start, /help, /reviews, /stats commands.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.config import TELEGRAM_OWNER_CHAT_IDS
from app.services.persistence.repositories.draft_repository import get_all_pending_replies, get_stats
from app.services.external.telegram.utils import _store_review_id
from app.services.common.logger import get_logger

logger = get_logger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if update.effective_chat.id not in TELEGRAM_OWNER_CHAT_IDS:
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
    if update.effective_chat.id not in TELEGRAM_OWNER_CHAT_IDS:
        await update.message.reply_text("🚫 Unauthorized.")
        return

    await update.message.reply_text(
        "📋 Available commands:\n\n"
        "/start — Greet and show intro\n"
        "/reviews — List all pending drafts waiting for approval\n"
        "/stats — Show database statistics\n\n"
        "When you receive a review notification:\n"
        "• Tap [✅ Post] to approve and post to Google\n"
        "• Tap [✏️ Edit] to revise the draft before posting\n"
        "• Tap [❌ Reject] to discard the draft\n\n"
        "During editing, send /cancel to abort"
    )


async def cmd_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reviews command — list pending drafts with Manage buttons."""
    if update.effective_chat.id not in TELEGRAM_OWNER_CHAT_IDS:
        await update.message.reply_text("🚫 Unauthorized.")
        return

    pending = get_all_pending_replies("pending")

    if not pending:
        await update.message.reply_text("✅ No pending reviews!")
        return

    await update.message.reply_text(f"📋 {len(pending)} pending review(s):")

    for review in pending:
        stars = "⭐" * review["star_rating"]
        review_text = review["review_text"] or "No text"
        message = (
            f"{stars} {review['location_name']} ({review['star_rating']}★)\n"
            f"From: {review['reviewer_name']}\n"
            f'"{review_text[:120]}{"..." if len(review_text) > 120 else ""}"'
        )
        short_key = _store_review_id(context, review["review_id"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔧 Manage", callback_data=f"manage:{short_key}")
        ]])
        await update.message.reply_text(message, reply_markup=keyboard)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command — show database statistics."""
    if update.effective_chat.id not in TELEGRAM_OWNER_CHAT_IDS:
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

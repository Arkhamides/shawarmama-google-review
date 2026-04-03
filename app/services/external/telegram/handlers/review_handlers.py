"""
Review action handlers for the Telegram bot.

Handles [🔧 Manage], [✅ Post], and [❌ Reject] callbacks.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.config import DRY_RUN
from app.services.persistence.repositories.draft_repository import get_pending_reply, mark_posted, mark_rejected
from app.services.external.google.posting import post_reply
from app.services.external.telegram.utils import _store_review_id, _resolve_review_id
from app.services.common.logger import get_logger

logger = get_logger(__name__)


async def handle_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner tapped [🔧 Manage] — show full review + draft + action buttons."""
    query = update.callback_query
    await query.answer()

    _, short_key = query.data.split(":", 1)
    review_id = _resolve_review_id(context, short_key)
    if not review_id:
        await query.edit_message_text("❌ Session expired — use /reviews again")
        return

    draft = get_pending_reply(review_id)
    if not draft:
        await query.edit_message_text("❌ Draft not found")
        return

    stars = "⭐" * draft["star_rating"]
    review_text = draft["review_text"] or "No text"
    draft_reply = draft["draft_reply"] or "No draft"

    message = (
        f"{stars} {draft['location_name']} ({draft['star_rating']}★)\n"
        f"From: {draft['reviewer_name']}\n\n"
        f'"{review_text}"\n\n'
        f"Draft response:\n"
        f'"{draft_reply}"'
    )

    short_key = _store_review_id(context, review_id)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Post", callback_data=f"approve:{short_key}"),
        InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{short_key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:{short_key}"),
    ]])

    await query.edit_message_text(message, reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks (approve/reject)."""
    query = update.callback_query
    await query.answer()

    try:
        action, short_key = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid callback data")
        return

    review_id = _resolve_review_id(context, short_key)
    if not review_id:
        await query.edit_message_text("❌ Session expired — use /reviews again")
        return

    draft = get_pending_reply(review_id)
    if not draft:
        await query.edit_message_text("❌ Draft not found")
        return

    creds = context.bot_data.get("creds")
    if not creds:
        await query.edit_message_text("❌ Credentials not available")
        return

    if action == "approve":
        reply_text = draft["draft_reply"]

        if DRY_RUN:
            await query.edit_message_text(
                f"⚠️ Dry run — not posted to Google.\n\nWould have posted:\n\"{reply_text}\""
            )
            logger.info("[DRY RUN] Would post reply for review %s", review_id)
        else:
            result = post_reply(creds, draft["location_name"], review_id, reply_text)
            if result:
                mark_posted(review_id, reply_text)
                await query.edit_message_text("✅ Posted to Google My Business")
                logger.info("Review %s approved and posted", review_id)
            else:
                await query.edit_message_text("❌ Failed to post to Google — check logs")
                logger.error("Failed to post reply for review %s", review_id)

    elif action == "reject":
        mark_rejected(review_id)
        await query.edit_message_text("❌ Draft rejected")
        logger.info("Review %s rejected", review_id)

    else:
        await query.edit_message_text(f"❌ Unknown action: {action}")

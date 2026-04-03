"""
Edit conversation handlers for the Telegram bot.

Manages the multi-step draft editing flow:
  [✏️ Edit] → send new text → confirm → post or cancel
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from app.config import DRY_RUN
from app.services.persistence.repositories.draft_repository import get_pending_reply, mark_posted
from app.services.external.google.posting import post_reply
from app.services.external.telegram.utils import _resolve_review_id
from app.services.common.logger import get_logger

logger = get_logger(__name__)

# ConversationHandler states
WAITING_FOR_EDIT, CONFIRM_EDIT = range(2)


async def handle_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: owner tapped [✏️ Edit] on a notification."""
    query = update.callback_query
    await query.answer()

    _, short_key = query.data.split(":", 1)
    review_id = _resolve_review_id(context, short_key)
    if not review_id:
        await query.edit_message_text("❌ Session expired — use /reviews again")
        return ConversationHandler.END

    draft = get_pending_reply(review_id)
    if not draft:
        await query.edit_message_text("❌ Draft not found")
        return ConversationHandler.END

    context.user_data["editing_review_id"] = review_id

    await query.edit_message_text(
        f"✏️ Editing draft for {draft['location_name']} ({draft['star_rating']}★)\n\n"
        f"Current draft:\n\"{draft['draft_reply']}\"\n\n"
        "Send your revised response, or /cancel to abort:"
    )
    return WAITING_FOR_EDIT


async def handle_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner sent revised text — ask for confirmation."""
    new_text = update.message.text
    context.user_data["edit_text"] = new_text

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Post", callback_data="post_edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_edit"),
        ]
    ])

    await update.message.reply_text(
        f"New response:\n\"{new_text}\"\n\nPost this to Google?",
        reply_markup=keyboard,
    )
    return CONFIRM_EDIT


async def handle_post_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner confirmed edited text — post it to Google."""
    query = update.callback_query
    await query.answer()

    review_id = context.user_data.get("editing_review_id")
    new_text = context.user_data.get("edit_text")

    draft = get_pending_reply(review_id)
    creds = context.bot_data.get("creds")

    if not draft or not creds:
        await query.edit_message_text("❌ Could not retrieve draft or credentials")
        context.user_data.clear()
        return ConversationHandler.END

    if DRY_RUN:
        await query.edit_message_text(
            f"⚠️ Dry run — not posted to Google.\n\nWould have posted:\n\"{new_text}\""
        )
        logger.info("[DRY RUN] Would post edited reply for review %s", review_id)
    else:
        result = post_reply(creds, draft["location_name"], review_id, new_text)
        if result:
            mark_posted(review_id, new_text)
            await query.edit_message_text(f"✅ Posted to Google My Business:\n\"{new_text}\"")
            logger.info("Review %s posted with edited reply", review_id)
        else:
            await query.edit_message_text("❌ Failed to post to Google — check logs")
            logger.error("Failed to post edited reply for review %s", review_id)

    context.user_data.clear()
    return ConversationHandler.END


async def handle_edit_cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner cancelled from the confirmation step."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Edit cancelled")
    context.user_data.clear()
    return ConversationHandler.END


async def handle_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner sent /cancel during the edit flow."""
    await update.message.reply_text("❌ Edit cancelled")
    context.user_data.clear()
    return ConversationHandler.END

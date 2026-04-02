"""
Telegram bot using python-telegram-bot v20+

Integrated into FastAPI's event loop (no separate thread).
Supports long-polling mode for local development.
"""

import asyncio
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_IDS
from app.services.database import (
    get_all_pending_replies, get_stats, get_pending_reply, mark_posted, mark_rejected
)
from app.services.google_api import post_reply


# Global bot application reference
_app: Optional[Application] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# Short-key lookup: maps int key → full review_id (avoids Telegram's 64-byte callback_data limit)
# Keys are stored in bot_data["review_id_map"] so they persist across handlers.

def _store_review_id(context, review_id: str) -> int:
    """Store a full review_id in bot_data and return a short integer key."""
    store = context.bot_data.setdefault("review_id_map", {})
    # Reuse existing key if already stored
    for key, val in store.items():
        if val == review_id:
            return key
    new_key = len(store)
    store[new_key] = review_id
    return new_key


def _resolve_review_id(context, short_key: str) -> Optional[str]:
    """Resolve a short integer key back to the full review_id."""
    store = context.bot_data.get("review_id_map", {})
    return store.get(int(short_key))

# Safety flag: set to False when ready to post to Google in production
DRY_RUN = True

# ConversationHandler states
WAITING_FOR_EDIT, CONFIRM_EDIT = range(2)


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


def send_good_review_notification(location_title: str, reviewer_name: str,
                                  star_rating: int, review_text: str):
    """
    Send a simple notification about a new good review (>3 stars).

    No action buttons — just informational.
    """
    if _app is None or _main_loop is None:
        return

    coro = _send_good_notification_async(location_title, reviewer_name, star_rating, review_text)
    asyncio.run_coroutine_threadsafe(coro, _main_loop)


async def _send_good_notification_async(location_title: str, reviewer_name: str,
                                        star_rating: int, review_text: str):
    """Async version of sending a good review notification."""
    try:
        stars = "⭐" * star_rating
        message = (
            f"{stars} NEW REVIEW — {location_title} ({star_rating}★)\n"
            f"From: {reviewer_name}\n\n"
            f'"{review_text}"'
        )
        for chat_id in TELEGRAM_OWNER_CHAT_IDS:
            await _app.bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"⚠️  Failed to send good review notification: {e}")


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

        # Create inline keyboard for approve/edit/reject
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Post", callback_data=f"approve:{short_key}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{short_key}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{short_key}"),
            ]
        ])

        # Send to all owners
        for chat_id in TELEGRAM_OWNER_CHAT_IDS:
            await _app.bot.send_message(chat_id=chat_id, text=message, reply_markup=keyboard)
    except Exception as e:
        print(f"⚠️  Failed to send Telegram notification: {e}")


# ============================================================================
# Command Handlers
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    # Owner check
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
    # Owner check
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
    # Owner check
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
    # Owner check
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


# ============================================================================
# Manage Callback Handler
# ============================================================================

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


# ============================================================================
# Edit Conversation Handler
# ============================================================================

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
        print(f"[DRY RUN] Would post edited reply for review {review_id}")
    else:
        result = post_reply(creds, draft["location_name"], review_id, new_text)
        if result:
            mark_posted(review_id, new_text)
            await query.edit_message_text(f"✅ Posted to Google My Business:\n\"{new_text}\"")
            print(f"✅ Review {review_id} posted with edited reply")
        else:
            await query.edit_message_text("❌ Failed to post to Google — check logs")
            print(f"❌ Failed to post edited reply for review {review_id}")

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


# ============================================================================
# Callback Handler (for inline button presses)
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks (approve/reject)."""
    query = update.callback_query
    await query.answer()  # Dismiss the loading state

    # Parse callback data
    try:
        action, short_key = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid callback data")
        return

    review_id = _resolve_review_id(context, short_key)
    if not review_id:
        await query.edit_message_text("❌ Session expired — use /reviews again")
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
        reply_text = draft["draft_reply"]

        if DRY_RUN:
            await query.edit_message_text(
                f"⚠️ Dry run — not posted to Google.\n\nWould have posted:\n\"{reply_text}\""
            )
            print(f"[DRY RUN] Would post reply for review {review_id}")
        else:
            result = post_reply(creds, draft["location_name"], review_id, reply_text)
            if result:
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

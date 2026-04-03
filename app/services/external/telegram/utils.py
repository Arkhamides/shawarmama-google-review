"""
Telegram bot utility helpers.

Short-key lookup: maps integer key → full review_id to work around
Telegram's 64-byte callback_data limit.
"""

from typing import Optional


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

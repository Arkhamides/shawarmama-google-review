# Development Roadmap

Build a production-grade system for restaurant owners to monitor Google My Business reviews in real-time, with Telegram notifications, AI-generated draft responses, and owner approval workflow.

## Overview

The system enables Shawar'Mama (5 locations across Paris) to:
- **Receive instant notifications** when bad reviews (≤3 stars) are posted (✅ Phase 4 complete)
- **Approve or reject** responses via Telegram inline buttons (✅ Phase 4 complete)
- **Get AI-drafted responses** via OpenAI, tailored to each review (🔄 Phase 5 in progress)
- **Edit and refine** responses before posting them on Google (Phase 6 planned)
- **Browse all reviews** across locations via Telegram commands (✅ Phase 4 complete)

### Architecture

```
Cloud Run app (main.py)
  │
  ├─ Every 5-10 minutes:
  │  └─ Polling loop fetches reviews
  │     via Google My Business API
  │
  ├─ Detects new bad reviews (≤3 stars)
  │  └─ Generates draft via OpenAI
  │     Saves to database
  │
  ├─ Sends Telegram message to owner
  │  with [✅ Post] [✏️ Edit] buttons
  │
  └─ Owner approves/edits → posts reply
```

**Infrastructure:**
- **Google Cloud Run** — serverless container host (free tier available, scales to zero)
- **Polling loop** — checks for reviews every 5-10 minutes (simple, no webhooks needed)
- **Google My Business API v4** — fetch reviews and post owner responses
- **Telegram Bot API** — webhook mode for owner interactions
- **OpenAI API** — ChatGPT for generating draft responses
- **SQLite** — local DB to track seen reviews and pending approvals

**Why polling?** See `NOTIFICATION_STRATEGIES.md` for comparison of polling vs webhooks vs Pub/Sub. For 5 locations, polling is simpler with acceptable 5-10 min delay.

---

## Implementation Phases

### Phase 1: Refactor Google API into a reusable module
**Status:** ✅ **COMPLETE**

**Completed Tasks:**
- ✅ Created `google_api.py` with core functions:
  - `authenticate()` — OAuth 2.0 flow with configurable token path via `GOOGLE_TOKEN_PATH` env var
  - `get_all_accounts(creds)` — list all GMB accounts
  - `get_locations_for_account(service, account_id)` — list locations per account
  - `get_all_locations(creds)` — convenience wrapper for all locations across all accounts
  - `get_reviews(creds, location_name)` — fetch reviews for a location
  - `post_reply(creds, location_name, review_id, reply_text)` — post a response to a review via `PUT /reviews/{reviewId}/reply`
- ✅ Refactored `google_reviews.py` to be a thin CLI wrapper that imports from `google_api.py`
- ✅ Updated `requirements.txt`: added `requests==2.31.0`, `python-dotenv==1.0.0`
- ✅ Updated `CLAUDE.md` with new architecture documentation

**Verification (Completed):**
```bash
✅ python google_reviews.py           # Works as before, displays all 6 locations
✅ python google_reviews.py --debug   # Debug mode works
✅ from google_api import *           # All functions importable
```

---

### Phase 2: Create review polling loop
**Goal:** Detect new reviews by polling the API every 5-10 minutes.

**Approach:** Simple polling (not Pub/Sub webhooks)
- Why: 5 locations, simple to implement, no Google Cloud setup needed
- Trade-off: 5-10 minute delay (acceptable for reviews)
- See `NOTIFICATION_STRATEGIES.md` for detailed comparison of polling vs webhooks vs Pub/Sub

**Tasks:**
- Create `main.py` with a background polling loop:
  - Every 5-10 minutes, fetch all reviews via `get_all_reviews(creds, location_name)`
  - Compare against `seen_reviews` table in database
  - For new reviews: check if bad (≤3 stars)
  - If bad: generate AI response → save to `pending_replies` → send Telegram notification
  - Mark review as seen to avoid duplicate notifications
- Create web server (`Flask` or `FastAPI`) for:
  - `GET /health` — health check
  - `POST /telegram` — Telegram webhook (Phase 4)
- Update `requirements.txt`: add `flask` or `fastapi`, `apscheduler` (for scheduling the polling loop)

**Verification:**
- Run `main.py` locally
- Check logs to confirm polling loop runs every 5-10 minutes
- Post a test bad review on Google My Business
- Verify notification arrives within 5-10 minutes

---

### Phase 3: SQLite database for state
**Goal:** Track which reviews we've seen and which are pending owner approval.

**Tasks:**
- Create `database.py` with:
  - `init_db()` — create tables on startup
  - `has_seen_review(review_id: str) -> bool` — deduplication
  - `mark_seen(review_id, location, rating, timestamp)`
  - `save_pending_reply(review_id, location, draft_text, owner_chat_id)`
  - `get_pending_reply(review_id)` — fetch a draft waiting for approval
  - `mark_posted(review_id)` — after owner posts, mark it sent
- Tables:
  ```sql
  CREATE TABLE seen_reviews (
    review_id TEXT PRIMARY KEY,
    location TEXT,
    star_rating INT,
    reviewer_name TEXT,
    review_text TEXT,
    seen_at TIMESTAMP
  );
  
  CREATE TABLE pending_replies (
    review_id TEXT PRIMARY KEY,
    location TEXT,
    draft_text TEXT,
    status TEXT,  -- "pending", "posted", "edited"
    created_at TIMESTAMP
  );
  ```

**Verification:**
- Create `reviews.db` locally
- Run `python -c "from database import init_db; init_db()"`
- Check `reviews.db` with SQLite CLI

---

### Phase 4: Telegram bot notifications + approval workflow
**Status:** ✅ **COMPLETE**

**Completed Tasks:**
- ✅ Migrated from Flask + background thread to FastAPI with proper event loop
- ✅ Created `bot.py` with `python-telegram-bot` v21.10 (async, Application pattern):
  - `/start` — greet owner, show welcome message with available commands
  - `/help` — detailed command reference
  - `/reviews` — list all pending draft replies awaiting approval
  - `/stats` — database statistics (total reviews, pending approvals, posted replies)
  - Inline keyboard handler for `[✅ Post]` and `[❌ Reject]` buttons on notification messages
  - Owner-only access via `TELEGRAM_OWNER_CHAT_ID` check
- ✅ Integrated bot into FastAPI lifespan context manager (same event loop)
- ✅ Telegram bot runs in long-polling mode (suitable for local development)
- ✅ `send_review_notification()` bridges sync polling thread to async bot using `asyncio.run_coroutine_threadsafe()`
- ✅ Verified bot receives notifications when bad reviews detected
- ✅ Verified owner can approve/reject via inline buttons

**Architecture:** 
- Uvicorn ASGI server owns the main event loop
- FastAPI app uses lifespan context manager to initialize bot, polling scheduler, and routes
- All three components (web routes, Telegram bot, polling) share the same event loop
- No thread race conditions or globals (unlike previous Flask implementation)

**Future Enhancement (Phase 5+):**
- Add `ConversationHandler` for draft editing workflow
- Support webhook mode for Cloud Run production deployment

---

### Phase 5: AI response generation (Next)
**Goal:** Automatically draft empathetic, professional responses to bad reviews using OpenAI.

**Tasks:**
- Create `ai_responder.py` with OpenAI SDK:
  - Function: `generate_response(location_name: str, reviewer_name: str, star_rating: int, review_text: str) -> str`
  - System prompt (customize as needed):
    ```
    You are a professional restaurant manager for {location_name}.
    A customer left a {star_rating}-star review. Your job is to draft a brief, empathetic response.
    - Acknowledge their concern
    - Offer to resolve the issue (if applicable)
    - Thank them for the feedback
    - Keep it 2-4 sentences, professional tone
    - Match the language of the original review
    ```
  - Call OpenAI API with GPT-4 or GPT-3.5-turbo
  - Handle language detection (French/English/etc.)
- Add `openai` to `requirements.txt`

**Verification:**
```python
from ai_responder import generate_response
draft = generate_response(
  location_name="Shawar'Mama - Paris 16",
  reviewer_name="Alice",
  star_rating=2,
  review_text="Food was cold"
)
print(draft)
```

---

### Phase 6: Advanced features & webhook mode
**Goal:** Add draft editing workflow and prepare webhook mode for production.

**Tasks:**
- ✏️ Add `ConversationHandler` for draft editing:
  1. Owner taps `[✏️ Edit]` on a notification (future enhancement)
  2. Bot asks: "Send your revised response (or /cancel):"
  3. Owner sends new text
  4. Bot asks: "Confirm? [✅ Yes] [❌ Cancel]"
  5. If yes → post to Google + mark as done
- 🔄 Implement webhook mode for production (instead of long-polling)
  - Switch to `POST /telegram` webhook endpoint
  - Register webhook with Telegram API
- 📊 Add analytics: per-location statistics, response time metrics
- 🌍 Support for multi-language prompts

---

### Phase 7: Production deployment
**Goal:** Deploy to Google Cloud Run with monitoring and scaling.

**Tasks:**
- 🔧 Create `Dockerfile` for containerization
- 🔐 Store secrets securely (OAuth tokens, API keys) via Google Secret Manager
- 🚀 Deploy to Cloud Run with auto-scaling
- 📊 Set up monitoring and logging via Cloud Logging
- 🔄 Configure webhook mode for Telegram (instead of long-polling)
- 📈 Add uptime monitoring and alerting

---

## Success Criteria

✅ A new 2-star review is posted on Google  
✅ Within seconds, you receive a Telegram notification with:
  - Review content
  - AI-drafted response
  - `[✅ Post] [✏️ Edit]` buttons
✅ You tap `[✏️ Edit]`, refine the text, and confirm  
✅ The response appears on Google My Business within seconds  
✅ The bot remembers it and won't notify twice

---

## Tech Stack Summary

| Component | Tech | Why |
|-----------|------|-----|
| **Bot Framework** | `python-telegram-bot` v20+ | Async, webhook support, conversation handler |
| **Web Framework** | Flask or FastAPI | Lightweight HTTP server for webhooks |
| **AI Responses** | OpenAI API (ChatGPT) | High quality, multilingual, easy API |
| **Database** | SQLite | Simple, no server needed, fast |
| **Container** | Docker + Cloud Run | Serverless, auto-scales, cheap |
| **Notifications** | Google Cloud Pub/Sub | Native GMB integration, no polling |
| **Authentication** | Google OAuth 2.0 | Already working in existing code |

---

## Next Steps

1. **Start with Phase 1** — refactor `google_api.py` and test locally
2. **Test locally** with `--debug` to confirm all API calls work
3. **Phase 2-3** — SQLite + database, test data insertion
4. **Phase 4** — Bot locally with fake Pub/Sub messages
5. **Phase 5** — Integrate OpenAI and test drafts
6. **Phase 6-7** — Deploy to Cloud Run

---

## Questions?

- Where should responses be posted? (Google My Business review replies only, or elsewhere?)
- Do you want notifications for good reviews (4-5 stars) too?
- Should the owner be able to browse review history in the bot?

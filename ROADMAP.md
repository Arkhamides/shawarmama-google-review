# Development Roadmap

Build a production-grade system for restaurant owners to monitor Google My Business reviews in real-time, with Telegram notifications, AI-generated draft responses, and owner approval workflow.

## Overview

The system enables Shawar'Mama (6 locations across Paris) to:
- **Receive instant notifications** when bad reviews (≤3 stars) are posted (✅ complete)
- **Approve or reject** responses via Telegram inline buttons (✅ complete)
- **Get AI-drafted responses** via Claude, tailored to each review (✅ complete)
- **Edit and refine** responses before posting them on Google (🔄 Phase 6 in progress)
- **Browse all reviews** across locations via Telegram commands (✅ complete)

### Architecture

```
Cloud Run app (main.py)
  │
  ├─ Every 5-10 minutes:
  │  └─ Polling loop fetches reviews
  │     via Google My Business API
  │
  ├─ Detects new bad reviews (≤3 stars)
  │  └─ Generates draft via Claude AI
  │     Saves to database
  │
  ├─ Sends Telegram message to owner
  │  with [✅ Post] [✏️ Edit] [❌ Reject] buttons
  │
  └─ Owner approves/edits → posts reply
```

---

## Completed Phases

- **Phase 1** ✅ Refactored Google API into reusable module (`google_api.py`)
- **Phase 2** ✅ Background polling loop + SQLite database persistence
- **Phase 3** ✅ FastAPI routes for draft approval (HTTP API)
- **Phase 4** ✅ Telegram bot with inline approval buttons (python-telegram-bot v21, AsyncIOScheduler, unified event loop)
- **Phase 5** ✅ Claude AI response generation (`ai_responder.py`, falls back to templates)
- **Phase 6.1** ✅ Draft editing workflow (ConversationHandler in `bot.py`, full edit → confirm → post flow)
- **Good review notifications** ✅ Good reviews (>3★) send an informational Telegram message with no action buttons

---

## Implementation Phases

### Phase 6: Advanced features & webhook mode

#### 6.1 Draft editing workflow (✅ complete)
**Goal:** Let the owner edit AI-generated drafts before posting.

**Tasks:**
- [x] Add `[✏️ Edit]` button to Telegram notification keyboard
- [x] Add `ConversationHandler` in `bot.py`:
  1. Owner taps `[✏️ Edit]` → bot shows current draft, asks for revised text
  2. Owner sends new text → bot previews it with `[✅ Post]` / `[❌ Cancel]` buttons
  3. Confirm → post edited text to Google, mark as posted
  4. Cancel → return to pending state
- [x] `/reviews` command shows pending drafts with `[🔧 Manage]` button
- [x] `[🔧 Manage]` opens full review + draft with action buttons

**Files:** `app/services/bot.py`

#### 6.2 Webhook mode for Cloud Run
**Goal:** Switch from long-polling to webhook mode for serverless deployment.

**Tasks:**
- Activate `POST /telegram` webhook endpoint in `routes.py`
- Register webhook URL with Telegram API on startup
- Remove long-polling from `start_bot()`

#### 6.3 Per-location analytics
**Goal:** Extend `/stats` with per-location breakdown and response time metrics.

---

### Phase 7: Production deployment
**Goal:** Deploy to Google Cloud Run with monitoring and scaling.

**Tasks:**
- 🔧 Create `Dockerfile` for containerization
- 🔐 Store secrets via Google Secret Manager (OAuth tokens, API keys)
- 🚀 Deploy to Cloud Run with auto-scaling
- 📊 Cloud Logging integration
- 📈 Uptime monitoring and alerting

---

## Success Criteria

✅ A new 2-star review is posted on Google
✅ Within minutes, owner receives a Telegram notification with:
  - Review content
  - AI-drafted response
  - `[✅ Post] [✏️ Edit] [❌ Reject]` buttons
✅ Owner taps `[✏️ Edit]`, refines the text, and confirms
✅ The response appears on Google My Business
✅ The bot remembers it and won't notify twice

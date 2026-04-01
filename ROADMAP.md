# Telegram Bot Roadmap

Build a Telegram bot for restaurant owners to monitor Google My Business reviews in real-time, with AI-generated draft responses and owner approval workflow.

## Overview

The bot will enable Shawar'Mama (5 locations across Paris) to:
- **Receive instant notifications** when bad reviews (≤3 stars) are posted
- **Get AI-drafted responses** via OpenAI, tailored to each review
- **Approve or edit** responses before posting them on Google
- **Browse all reviews** across locations via Telegram commands

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

### Phase 4: Telegram bot (webhook mode)
**Goal:** Enable the owner to receive notifications and approve/edit responses.

**Tasks:**
- Create `bot.py` with `python-telegram-bot` v20+ (async):
  - `/start` — greet owner, confirm authenticated
  - `/reviews` — show latest reviews across all locations (with pagination)
  - `/locations` — list all 5 Shawar'Mama locations
  - Inline keyboard handler for `[✅ Post]` / `[✏️ Edit]` buttons on draft messages
  - `ConversationHandler` for the edit flow:
    1. Owner taps `[✏️ Edit]`
    2. Bot asks: "Send your revised response (or /cancel):"
    3. Owner sends new text
    4. Bot asks: "Confirm this text? [✅ Yes] [❌ Cancel]"
    5. If yes → post to Google + mark as done
- Restrict bot to a single owner via `TELEGRAM_OWNER_CHAT_ID` (reject all other users)
- Use webhook mode (not polling) for Cloud Run

**Verification:**
```bash
# Local testing with long-polling
python -c "from bot import create_app; create_app().run_polling()"
# Then manually message the bot
```

---

### Phase 5: AI response generation
**Goal:** Automatically draft empathetic, professional responses to bad reviews.

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

### Phase 6: Wire it all together
**Goal:** Create the main Cloud Run app that ties all components together.

**Tasks:**
- Create `main.py` (Flask or FastAPI):
  - `POST /pubsub` — Pub/Sub webhook endpoint:
    1. Decode incoming message
    2. Parse review (extract ID, location, rating, text, reviewer name)
    3. `has_seen_review(id)` → skip if seen
    4. `mark_seen(id, ...)`
    5. If `rating ≤ 3` (bad review):
       - `generate_response(...)` → draft
       - `save_pending_reply(...)`
       - Send Telegram message with review + draft + `[✅ Post] [✏️ Edit]` buttons
    6. Return 200 OK to acknowledge the message
  - `POST /telegram` — Telegram webhook endpoint (pass to bot handler)
  - `GET /health` — health check for Cloud Run
- Create `Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install -r requirements.txt
  COPY . .
  CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "main:app"]
  ```

**Verification:**
- Run locally: `python main.py`
- Test `/health` endpoint: `curl http://localhost:8080/health`
- Send a test Pub/Sub message (via Google Cloud console)
- Check Telegram for notifications

---

### Phase 7: Configuration & deployment
**Goal:** Make the system production-ready on Google Cloud.

**Tasks:**
- Create `.env.example`:
  ```
  # Telegram
  TELEGRAM_BOT_TOKEN=your_telegram_token_here
  TELEGRAM_OWNER_CHAT_ID=your_chat_id_here

  # OpenAI
  OPENAI_API_KEY=sk-...

  # Google Cloud
  GOOGLE_PROJECT_ID=your-gcp-project
  GOOGLE_TOKEN_PATH=/secrets/token.pickle
  PUBSUB_TOPIC=projects/your-gcp-project/topics/gmb-reviews

  # Settings
  BAD_REVIEW_THRESHOLD=3
  FLASK_PORT=8080
  ```

- Deploy to Google Cloud Run:
  1. **Pre-generate `token.pickle` locally:**
     ```bash
     python -c "from google_api import authenticate; authenticate()"
     # Browser will pop up for OAuth consent
     # token.pickle will be saved
     ```
  2. **Store token as a secret:**
     ```bash
     gcloud secrets create gmb-token --data-file=token.pickle
     ```
  3. **Deploy:**
     ```bash
     gcloud run deploy gmb-bot \
       --source . \
       --platform managed \
       --region us-central1 \
       --set-env-vars GOOGLE_PROJECT_ID=... \
       --secrets GOOGLE_TOKEN_PATH=gmb-token:latest
     ```
  4. **Register Telegram webhook:**
     ```bash
     curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
       -H "Content-Type: application/json" \
       -d '{"url":"https://<cloud-run-url>/telegram"}'
     ```
  5. **Register GMB Pub/Sub notifications:**
     - Use the deployed Cloud Run URL as the Pub/Sub push endpoint
     - Register with Google My Business API as shown in Phase 2

**Monitoring:**
- Cloud Run logs: `gcloud run logs read gmb-bot --limit 50`
- Pub/Sub messages: Google Cloud console → Pub/Sub → topic
- Telegram updates: your DMs with the bot

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

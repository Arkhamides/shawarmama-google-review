# Architecture

## Overview

A FastAPI application that polls Google My Business for reviews, detects bad ones (≤3 stars), generates AI draft responses via Claude, and notifies the owner via Telegram for approval.

## File Structure

```
app/
├── main.py                  # FastAPI app creation + include_router
├── lifespan.py              # Startup/shutdown orchestration (extracted from main.py)
├── config.py                # Environment variables (single source of truth)
├── logger.py                # Shim — re-exports from services/common/logger.py
├── routes.py                # HTTP API endpoints (APIRouter)
└── services/
    ├── common/              # Shared utilities (no intra-app dependencies except config)
    │   ├── logger.py        # Structured JSON logging — get_logger()
    │   ├── constants.py     # STAR_RATING_MAP
    │   ├── validators.py    # convert_rating_to_int()
    │   ├── exceptions.py    # (stub — future use)
    │   └── decorators.py    # (stub — future use)
    │
    ├── external/            # Third-party integrations
    │   ├── google/
    │   │   ├── client.py    # SCOPES, TOKEN_PATH, _TRANSIENT_CODES, _TransientGoogleError
    │   │   ├── auth.py      # authenticate() — OAuth2 token management
    │   │   ├── reviews.py   # get_all_accounts(), get_locations_for_account(), get_all_locations(), get_reviews()
    │   │   └── posting.py   # post_reply()
    │   ├── telegram/
    │   │   ├── bot.py       # start_bot(), stop_bot(), send_review_notification() + _app/_main_loop globals
    │   │   ├── utils.py     # _store_review_id(), _resolve_review_id() (short-key lookup)
    │   │   └── handlers/
    │   │       ├── admin_handlers.py   # cmd_start, cmd_help, cmd_reviews, cmd_stats
    │   │       ├── review_handlers.py  # handle_manage(), handle_callback() (approve/reject)
    │   │       └── edit_handlers.py    # handle_edit_*, WAITING_FOR_EDIT, CONFIRM_EDIT
    │   └── ai/
    │       ├── prompts.py             # SYSTEM_PROMPT constant
    │       ├── claude.py              # generate_ai_response() — Anthropic API client
    │       └── response_generator.py  # generate_draft_response() — AI with template fallback
    │
    ├── domain/              # Business logic / entities (stubs — future typed layer)
    │   ├── review.py        # Review entity placeholder
    │   ├── draft.py         # Draft entity placeholder
    │   ├── location.py      # Location entity placeholder
    │   └── workflows.py     # Complex workflow orchestration placeholder
    │
    ├── persistence/         # Database layer
    │   ├── database.py      # _connect(), init_db() — connection + Alembic migrations
    │   └── repositories/
    │       ├── review_repository.py  # has_seen_review(), mark_seen()
    │       └── draft_repository.py   # save_pending_reply(), get_pending_reply(), get_all_pending_replies(),
    │                                 # mark_approved(), mark_posted(), mark_rejected(), get_stats()
    │
    └── jobs/                # Background tasks
        ├── scheduler.py               # AsyncIOScheduler, start_polling(), stop_polling()
        └── polling/
            └── review_poller.py       # polling_loop()

db/
├── models.py                # SQLAlchemy Core table definitions (Alembic source)
└── migrations/              # Alembic migration history
    └── versions/

alembic.ini                  # Alembic config
run.py                       # Entry point: init_db() → uvicorn
scripts/
└── google_reviews.py        # CLI tool for manual review fetching
```

## Dependency Graph

The layered architecture enforces a strict dependency direction — each layer only imports from layers below it:

```
routes.py, lifespan.py
    ↓
services/external/telegram/bot.py (+ handlers/)
services/external/google/
services/external/ai/
services/jobs/
    ↓
services/persistence/repositories/
    ↓
services/persistence/database.py
    ↓
services/common/
    ↓
app/config.py   (no intra-app imports)
```

**Circular import rule:** Handler files (`external/telegram/handlers/`) NEVER import from `external/telegram/bot.py`. Only `bot.py` imports the handlers.

## Event Loop Model

All components share **one asyncio event loop** owned by Uvicorn:

```
Uvicorn (owns event loop)
  ├── FastAPI app (lifespan context manager in lifespan.py)
  ├── AsyncIOScheduler → runs polling_loop() in thread pool
  │     └── send_review_notification() bridges back via
  │         asyncio.run_coroutine_threadsafe()
  └── python-telegram-bot Application (long-polling)
```

This avoids thread-safety issues. The only cross-thread boundary is the polling thread calling `send_review_notification()`, which schedules the async bot message on the main loop.

## Startup Sequence

```
run.py:
  init_db()                      # alembic upgrade head (sync, before event loop starts)
  uvicorn.run(app.main:app)

app/main.py:
  import app.services.common.logger  # configures root logger (side-effect import)

app/lifespan.py lifespan():
  authenticate() → get_all_locations()
  → start_bot(creds)             # registers handlers, starts long-polling
  → start_polling(creds, locations)  # schedules polling_loop() every N min via APScheduler
```

`init_db()` runs synchronously in `run.py` before uvicorn to avoid SQLAlchemy thread-pool conflicts with asyncio. `polling_loop()` is never called directly from the async lifespan — APScheduler executes it in a thread pool.

State (`creds`, `locations`) is stored in `app.state` for use by HTTP route handlers.

## Review Lifecycle

```
polling_loop()  [jobs/polling/review_poller.py]
  └── get_reviews(creds, location)       # external/google/reviews.py
        for each review:
          has_seen_review(review_id)?    # persistence/repositories/review_repository.py
            yes → skip
            no  → if star_rating ≤ BAD_REVIEW_THRESHOLD:
                    generate_draft_response()    # external/ai/response_generator.py
                    save_pending_reply()         # persistence/repositories/draft_repository.py
                    send_review_notification()   # external/telegram/bot.py (bridges to async loop)
                    mark_seen()
                  else:
                    mark_seen()

Owner action (Telegram inline button):  [external/telegram/handlers/]
  approve → post_reply() → mark_posted()
  edit    → ConversationHandler → post_reply(edited_text) → mark_posted()
  reject  → mark_rejected()
```

## Database Schema

PostgreSQL (Cloud SQL in production, Docker postgres:16 locally). Schema managed by Alembic — see [DATABASE.md](DATABASE.md) for migration workflow.

**`seen_reviews`** — deduplication table, every fetched review goes here

| Column | Type | Notes |
|--------|------|-------|
| review_id | TEXT PK | Google review ID |
| location_id | TEXT | GMB location resource name |
| location_name | TEXT | Human-readable location title |
| reviewer_name | TEXT | |
| star_rating | INT | 1–5 |
| review_text | TEXT | |
| seen_at | TIMESTAMP | |

**`pending_replies`** — draft responses awaiting owner action

| Column | Type | Notes |
|--------|------|-------|
| review_id | TEXT PK | |
| location_id | TEXT | |
| location_name | TEXT | |
| reviewer_name | TEXT | |
| star_rating | INT | |
| review_text | TEXT | |
| draft_reply | TEXT | AI-generated or template |
| status | TEXT | `pending` → `posted` or `rejected` |
| created_at | TIMESTAMP | |
| approved_at | TIMESTAMP | |
| posted_at | TIMESTAMP | |

**`posted_replies`** — history of posted responses

| Column | Type | Notes |
|--------|------|-------|
| review_id | TEXT PK | |
| location_id | TEXT | |
| location_name | TEXT | |
| reply_text | TEXT | Final text that was posted |
| posted_at | TIMESTAMP | |

## HTTP API (`routes.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Cloud Run health check |
| GET | `/stats` | DB statistics |
| GET | `/reviews` | All pending drafts |
| POST | `/poll` | Manually trigger polling |
| POST | `/drafts/{review_id}/approve` | Approve draft → post to Google |
| POST | `/drafts/{review_id}/reject` | Reject draft |
| POST | `/drafts/{review_id}/edit` | Edit draft → post to Google |
| POST | `/telegram` | Webhook endpoint (unused; polling mode active) |

## Telegram Bot (`external/telegram/`)

**Commands** (`admin_handlers.py`):
- `/start` — welcome message
- `/help` — command reference
- `/reviews` — list pending drafts, each with a `[🔧 Manage]` button
- `/stats` — DB statistics

**Inline keyboard on bad-review notifications:**
- `[✅ Post]` → `approve:{key}` → posts immediately
- `[✏️ Edit]` → `edit:{key}` → enters `ConversationHandler`
- `[❌ Reject]` → `reject:{key}` → marks rejected

**`[🔧 Manage]` button (from `/reviews`)** (`review_handlers.py`):
Expands to show the full review text + draft reply with the same `[✅ Post] [✏️ Edit] [❌ Reject]` keyboard.

**Edit conversation flow** (`edit_handlers.py`, `ConversationHandler`):
```
edit:{key} (entry)
  → WAITING_FOR_EDIT: owner sends revised text
  → CONFIRM_EDIT: [✅ Post] / [❌ Cancel] inline buttons
  → post or cancel → END
```

**Short-key lookup** (`utils.py`):
Telegram limits `callback_data` to 64 bytes. Review IDs can be longer, so a `review_id_map` dict (stored in `bot_data`) maps short integer keys → full review IDs. All callback data uses these keys (e.g. `approve:0`, `edit:1`).

All commands and callbacks are gated to `TELEGRAM_OWNER_CHAT_ID` only (supports comma-separated list of IDs).

## AI Response Generation (`external/ai/`)

`generate_draft_response()` in `response_generator.py` orchestrates:
1. If `ANTHROPIC_API_KEY` is set → call `generate_ai_response()` in `claude.py` (Claude Haiku)
2. If not set or API call fails → return a rating-based template response

The system prompt in `prompts.py` instructs Claude to match the review's language (French/English), be 2–4 sentences, and acknowledge the specific concern.

## Google API (`external/google/`)

- **Auth** (`auth.py`): OAuth 2.0 via `InstalledAppFlow`, credentials cached in `token.pickle`
- **Reviews** (`reviews.py`): `get_all_accounts()`, `get_all_locations()`, `get_reviews()` via REST — retry on 429/500/503
- **Posting** (`posting.py`): `post_reply()` via REST — retry on 429/500/503
- **Shared** (`client.py`): `SCOPES`, `TOKEN_PATH`, `_TRANSIENT_CODES`, `_TransientGoogleError`

Star ratings come back as strings (`FIVE`, `FOUR`, etc.); `convert_rating_to_int()` in `common/validators.py` maps them to integers via `STAR_RATING_MAP` in `common/constants.py`.

## Configuration (`config.py`)

All settings loaded from `.env` via `python-dotenv`. Missing required vars raise `ValueError` at import time (fail-fast).

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_TOKEN_PATH` | `token.pickle` | Cached OAuth token |
| `GOOGLE_PROJECT_ID` | — | Required. GCP project ID |
| `TELEGRAM_BOT_TOKEN` | — | Required. Bot API token |
| `TELEGRAM_OWNER_CHAT_ID` | — | Required. Owner's Telegram chat ID |
| `DATABASE_URL` | — | Required. PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | — | Claude API key (optional) |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model |
| `BAD_REVIEW_THRESHOLD` | `3` | Reviews ≤ this are "bad" |
| `POLL_INTERVAL_MINUTES` | `5` | Polling frequency |
| `PORT` | `8080` | Web server port |
| `DRY_RUN` | `false` | Skip posting to Google when `true` |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

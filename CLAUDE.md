# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python application for Shawar'Mama (6 Paris locations) that polls Google My Business for bad reviews (≤3 stars), generates Claude AI draft responses, and notifies the owner via Telegram for approval/edit/reject via inline buttons.

**Current status:** Phase 8 complete (service architecture refactor). Next: Phase 6.2 (webhook mode) or Phase 7 (production deployment).

- Full architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Database reference: [DATABASE.md](DATABASE.md)
- Roadmap & next steps: [ROADMAP.md](ROADMAP.md)
- Setup instructions: [SETUP.md](SETUP.md)

## File Structure

```
app/
├── main.py              # FastAPI app creation + include_router
├── lifespan.py          # Startup/shutdown orchestration (extracted from main.py)
├── config.py            # All env vars — single source of truth
├── logger.py            # Shim — re-exports from services/common/logger.py
├── routes.py            # HTTP API endpoints
└── services/
    ├── common/          # Shared utilities (logger, constants, validators)
    ├── external/
    │   ├── google/      # auth.py, client.py, reviews.py, posting.py
    │   ├── telegram/    # bot.py, utils.py, handlers/{admin,review,edit}_handlers.py
    │   └── ai/          # prompts.py, claude.py, response_generator.py
    ├── domain/          # Stub entities: review.py, draft.py, location.py, workflows.py
    ├── persistence/     # database.py + repositories/{review,draft}_repository.py
    └── jobs/            # scheduler.py + polling/review_poller.py

db/
├── models.py            # SQLAlchemy Core table definitions (Alembic autogenerate source)
└── migrations/          # Alembic migration files
    └── versions/        # One file per schema change

scripts/
└── google_reviews.py    # CLI tool for manual review fetching (python -m scripts.google_reviews)

alembic.ini              # Alembic config (reads DATABASE_URL from env)
run.py                   # Entry point: runs migrations then starts uvicorn
```

## Running the Application

```bash
# Create and activate virtual environment (first time only)
python3.13 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Start local PostgreSQL (Docker) — skip if already running
docker run --name reviews-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=reviews -p 5432:5432 -d postgres:16
# or if container already exists: docker start reviews-pg

python run.py
```

Migrations run automatically on startup. `DATABASE_URL` and all other required vars must be set in `.env`.

## Environment Variables

All in `.env` (see `.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `GOOGLE_TOKEN_PATH` | `token.pickle` | Cached OAuth token |
| `GOOGLE_PROJECT_ID` | — | Required. GCP project ID |
| `TELEGRAM_BOT_TOKEN` | — | Required. Bot API token |
| `TELEGRAM_OWNER_CHAT_ID` | — | Required. Owner's chat ID |
| `DATABASE_URL` | — | Required. PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | — | Optional; falls back to templates if unset |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model for draft generation |
| `BAD_REVIEW_THRESHOLD` | `3` | Reviews ≤ this trigger notifications |
| `POLL_INTERVAL_MINUTES` | `5` | Polling frequency |
| `PORT` | `8080` | Web server port |
| `DRY_RUN` | `false` | Set `true` to skip posting to Google |
| `LOG_LEVEL` | `INFO` | Logging verbosity |


## Notes for Development

- Venv at `./venv/`
- Sensitive files (`credentials.json`, `token.pickle`, `.env`, `*.db`) are gitignored
- All components share one asyncio event loop (Uvicorn → FastAPI → APScheduler → Telegram bot)
- Polling runs in a thread pool; `send_review_notification()` bridges back via `asyncio.run_coroutine_threadsafe()`
- `ConversationHandler` for edit flow must be registered before the flat `CallbackQueryHandler` in `external/telegram/bot.py`
- Database migrations run synchronously in `run.py` before uvicorn starts — avoids SQLAlchemy thread-pool conflicts with asyncio
- Do NOT call `polling_loop()` directly from the async lifespan — it blocks the event loop. Let APScheduler run it in a thread pool via `jobs/scheduler.py`
- Handler files in `external/telegram/handlers/` NEVER import from `external/telegram/bot.py` — only `bot.py` imports handlers (enforces no circular imports)
- The root logger is configured by importing `app.services.common.logger` as a side-effect in `main.py`; `app/logger.py` is a backward-compat shim
- See [DATABASE.md](DATABASE.md) for schema changes and migration workflow

# Google My Business Reviews Manager

Python application for Shawar'Mama (6 Paris locations) that polls Google My Business for bad reviews (≤3 stars), generates AI draft responses via Claude, and notifies the owner via Telegram for approval, editing, or rejection.

## Quick Start

```bash
# 1. Create and activate virtual environment
python3.13 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up Google Cloud credentials (see SETUP.md)

# 4. Start PostgreSQL (Docker)
docker run --name reviews-pg \
  -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=reviews \
  -p 5432:5432 -d postgres:16

# 5. Configure environment
cp .env.example .env
# Edit .env — add DATABASE_URL and all required vars

# 6. Run
python run.py
```

On startup the app will:
- Apply any pending database migrations (Alembic)
- Authenticate with Google (browser prompt on first run, cached after)
- Load all 6 verified business locations
- Start the Telegram bot (long-polling mode)
- Start the background polling loop (every 5 minutes by default)
- Start the FastAPI server on port 8080

## How It Works

```
Every N minutes (AsyncIOScheduler):
  └── Fetch reviews from Google My Business API
        For each unseen review:
          ≤3★ → generate Claude AI draft
                save to PostgreSQL
                send Telegram notification → [✅ Post] [✏️ Edit] [❌ Reject]
                mark as seen (only after successful delivery)
          >3★ → send informational Telegram message, mark as seen
```

**Owner actions via Telegram:**
- `[✅ Post]` — posts the AI draft directly to Google My Business
- `[✏️ Edit]` — prompts for revised text → preview → confirm before posting
- `[❌ Reject]` — discards the draft
- `/reviews` — lists all pending drafts with a `[🔧 Manage]` button for each

## Configuration

All settings go in `.env`:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot API token |
| `TELEGRAM_OWNER_CHAT_ID` | Yes | — | Owner's chat ID (comma-separated for multiple) |
| `GOOGLE_PROJECT_ID` | Yes | — | GCP project ID |
| `ANTHROPIC_API_KEY` | No | — | Falls back to template responses if unset |
| `ANTHROPIC_MODEL` | No | `claude-haiku-4-5-20251001` | Claude model for draft generation |
| `GOOGLE_TOKEN_PATH` | No | `token.pickle` | Cached OAuth token path |
| `BAD_REVIEW_THRESHOLD` | No | `3` | Reviews ≤ this trigger notifications |
| `POLL_INTERVAL_MINUTES` | No | `5` | Polling frequency |
| `PORT` | No | `8080` | Web server port |
| `DRY_RUN` | No | `false` | Set `true` to skip posting to Google |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` for verbose output |

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (authenticated, locations loaded) |
| GET | `/stats` | DB counts (seen, pending, posted) |
| GET | `/reviews` | All pending drafts |
| POST | `/poll` | Manually trigger a poll cycle |
| POST | `/drafts/{id}/approve` | Approve draft → post to Google |
| POST | `/drafts/{id}/reject` | Reject draft |

## File Structure

```
app/
├── main.py              # FastAPI app + lifespan (startup/shutdown)
├── config.py            # All env vars — single source of truth
├── routes.py            # HTTP API endpoints
├── logger.py            # JSON-formatted logging
└── services/
    ├── google_api.py    # Google My Business API (auth, locations, reviews, post reply)
    ├── polling.py       # Background polling loop (AsyncIOScheduler)
    ├── bot.py           # Telegram bot (commands, inline buttons, edit ConversationHandler)
    ├── database.py      # PostgreSQL layer via psycopg2
    ├── ai_responder.py  # Claude AI draft generation
    └── utils.py         # Rating conversion + draft orchestration

db/
├── models.py            # SQLAlchemy Core table definitions (Alembic source)
└── migrations/          # Alembic migration history

cli/
└── google_reviews.py    # CLI tool for manual review fetching

alembic.ini              # Alembic config
run.py                   # Entry point: migrations → uvicorn
```

## Development Notes

- **Re-authenticate:** Delete `token.pickle` and restart to use a different Google account
- **Reset database:** `docker exec reviews-pg psql -U postgres -d reviews -c "TRUNCATE seen_reviews, pending_replies, posted_replies;"`
- **Inspect DB:** `docker exec reviews-pg psql -U postgres -d reviews -c "\dt"`
- **Schema changes:** Edit `db/models.py`, then run `alembic revision --autogenerate -m "description"` — see [DATABASE.md](DATABASE.md)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Missing required environment variables` | Check `.env` has all required vars — `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`, `GOOGLE_PROJECT_ID` |
| `No locations found` | Verify business at [business.google.com](https://business.google.com) — `verificationState` must be `VERIFIED` |
| `credentials.json not found` | Download OAuth credentials (Desktop Application type) from Google Cloud Console — see [SETUP.md](SETUP.md) |
| `403` from Google API | Enable the required APIs in Google Cloud Console and wait a few minutes |
| DB connection error | Ensure PostgreSQL is running: `docker start reviews-pg` |

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — event loop model, review lifecycle, full component breakdown
- [DATABASE.md](DATABASE.md) — schema, migration workflow, Cloud SQL setup
- [ROADMAP.md](ROADMAP.md) — completed phases and what's next
- [SETUP.md](SETUP.md) — Google OAuth credential setup

# Google My Business Reviews Manager

A Python application for managing Google My Business reviews with **real-time polling**, **bad review detection**, and **draft response generation**. Fetches reviews across all restaurant locations, automatically detects bad reviews (≤3 stars), generates draft responses, and saves them for owner approval via a Flask web interface. Future phases will add Telegram bot notifications and AI-powered response generation.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up Google Cloud credentials (see SETUP.md)

# 3. Create .env file (see .env.example)
cp .env.example .env

# 4. Run the server
python run.py
```

**On first run**, the application will:
- Authenticate with Google using your browser
- Cache credentials locally for future runs
- Fetch all verified business locations
- Initialize SQLite database (`db/reviews.db`)
- Start background polling loop (every 5 minutes by default)
- Start Flask web server on port 8080

The application runs continuously in the background:
- 🔄 **Polls for new reviews** every 5 minutes (configurable)
- 🚨 **Detects bad reviews** (≤3 stars, configurable)
- 📝 **Generates draft responses** automatically
- 💾 **Saves drafts** to database for owner approval
- (Phase 4+) **Sends Telegram notifications** when bad reviews detected

## How It Works

### Review Polling Loop
The application continuously monitors your Google My Business reviews:

1. **Fetch Reviews** — Every 5 minutes, polls Google My Business API for new reviews
2. **Detect Bad Reviews** — Identifies reviews with ≤3 stars as "bad"
3. **Generate Draft** — Creates a templated response (Phase 5 will use AI)
4. **Store for Approval** — Saves draft to SQLite database for owner review
5. **Prevent Duplicates** — Marks reviews as seen to avoid reprocessing

All pending drafts can be viewed and approved via the Flask web interface.

### Architecture
```
┌─────────────────────────────────────────┐
│ Flask Web Server (port 8080)            │
│  • View pending approvals               │
│  • Approve/reject drafts                │
│  • View review history                  │
└─────────────────────────────────────────┘
                    ▲
                    │
┌─────────────────────────────────────────┐
│ Background Polling Loop (APScheduler)   │
│  • Runs every 5 minutes                 │
│  • Fetches from Google My Business API  │
│  • Detects bad reviews                  │
│  • Generates drafts                     │
│  • Saves to database                    │
└─────────────────────────────────────────┘
                    ▲
                    │
┌─────────────────────────────────────────┐
│ SQLite Database (db/reviews.db)         │
│  • seen_reviews (deduplication)         │
│  • pending_replies (drafts waiting)     │
│  • posted_replies (history)             │
└─────────────────────────────────────────┘
```

## Using as a Python Module

The core API can be imported by other applications:

```python
from app.services.google_api import authenticate, get_all_locations, get_reviews, post_reply
from app.services.database import get_all_pending_replies, mark_approved

# Authenticate with Google
creds = authenticate()

# Get all locations
locations = get_all_locations(creds)

# View pending review drafts
pending = get_all_pending_replies(status='pending')
for draft in pending:
    print(f"Bad review from {draft['reviewer_name']}: {draft['star_rating']}★")
    print(f"Draft: {draft['draft_reply']}")
    
    # Approve and post the reply
    mark_approved(draft['review_id'])
    post_reply(creds, draft['location_name'], draft['review_id'], draft['draft_reply'])
```

See [CLAUDE.md](CLAUDE.md) for detailed API documentation and architecture.



## What the Application Does

1. **Authenticates** with Google My Business using OAuth 2.0
2. **Fetches** all verified business locations associated with your account
3. **Polls continuously** for new reviews every N minutes
4. **Detects bad reviews** (configurable threshold, default ≤3 stars)
5. **Generates draft responses** to bad reviews automatically
6. **Stores drafts** in SQLite database for owner approval
7. **Provides web interface** for viewing and approving pending replies
8. *(Phase 4+)* **Sends Telegram notifications** when bad reviews detected
9. *(Phase 5+)* **Uses AI** (OpenAI) to generate intelligent responses

## Requirements

- Python 3.7+
- Google account with a verified Google My Business location
- Google Cloud project with My Business APIs enabled

See [requirements.txt](requirements.txt) for Python package dependencies.

## Configuration

All settings are in `.env` file (see `.env.example`):

```bash
# Google Cloud
GOOGLE_TOKEN_PATH=token.pickle          # Where to cache OAuth token
GOOGLE_PROJECT_ID=your-gcp-project-id

# Application settings
BAD_REVIEW_THRESHOLD=3                  # Reviews ≤3 stars are "bad"
POLL_INTERVAL_MINUTES=5                 # Check for new reviews every N minutes
FLASK_PORT=8080                         # Web server port

# Telegram (Phase 4+, optional)
TELEGRAM_BOT_TOKEN=                     # Telegram bot API token
TELEGRAM_OWNER_CHAT_ID=                 # Your chat ID for notifications

# OpenAI (Phase 5+, optional)
OPENAI_API_KEY=                         # OpenAI API key for AI responses
```

## Troubleshooting

**"No locations found"**
- Verify your business is [verified on Google My Business](https://business.google.com)
- Use the same Google account for both the business and the OAuth credentials

**"credentials.json not found"**
- Download OAuth credentials from Google Cloud Console and save as `credentials.json`
- See [SETUP.md](SETUP.md) for detailed instructions

**Polling not starting / "database locked" errors**
- Check that `db/` directory is writable
- Ensure SQLite isn't being accessed by multiple processes
- Check Flask logs for detailed error messages

**API errors (403, 404)**
- Check that the required APIs are enabled in your Google Cloud project
- See [SETUP.md](SETUP.md) troubleshooting section
- Make sure your Google My Business account is VERIFIED

**Web server not accessible**
- Check `FLASK_PORT` in `.env` (default 8080)
- Verify firewall allows port 8080
- Check Flask logs for startup errors

## Development Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development plan:

- **Phase 1** ✅ — Core API refactored into reusable module
- **Phase 2** ✅ — Review polling loop + database persistence
- **Phase 3** (Next) — Flask web interface for viewing/approving pending drafts
- **Phase 4** — Telegram bot notifications + mobile approval workflow
- **Phase 5** — OpenAI integration for intelligent response generation
- **Phase 6** — Advanced features (analytics, scheduling, multi-language)
- **Phase 7** — Production deployment (Cloud Run, monitoring, scaling)

**Architecture decision:** Using simple polling instead of Pub/Sub webhooks for simplicity and faster deployment. See [NOTIFICATION_STRATEGIES.md](NOTIFICATION_STRATEGIES.md) for detailed comparison.

## File Structure

```
.
├── app/                         # Flask application
│   ├── main.py                 # App factory + initialization
│   ├── config.py               # Environment configuration
│   ├── routes.py               # Web endpoints
│   └── services/               # Core business logic
│       ├── google_api.py        # Google My Business API wrapper
│       ├── polling.py           # Background polling loop
│       ├── database.py          # SQLite database layer
│       └── utils.py             # Helper functions
├── db/                          # SQLite database directory
│   └── reviews.db              # (auto-created) Reviews database
├── run.py                       # Application entry point
├── .env.example                # Environment variables template
├── ROADMAP.md                  # Development plan (7 phases)
├── CLAUDE.md                   # Architecture documentation
├── SETUP.md                    # Setup instructions
├── NOTIFICATION_STRATEGIES.md  # Polling vs webhooks comparison
├── CHANGELOG.md                # Version history
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── credentials.json            # (created by you) OAuth credentials
├── token.pickle                # (auto-generated) Cached auth token
└── venv/                       # Virtual environment
```

## Development Notes

- **Re-authenticate:** Delete `token.pickle` and run `python run.py` again to use a different Google account
- **Reset database:** Delete `db/reviews.db` to clear all history and pending approvals
- **Modify polling interval:** Change `POLL_INTERVAL_MINUTES` in `.env` (requires restart)
- **Change bad review threshold:** Modify `BAD_REVIEW_THRESHOLD` in `.env` (default 3 = ≤3 stars)

See [CLAUDE.md](CLAUDE.md) for detailed API documentation and architecture notes.

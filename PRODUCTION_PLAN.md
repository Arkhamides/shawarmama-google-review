# Production Plan

Execution plan to bring the google-reviews app to production on **Google Cloud Run** with **PostgreSQL (Cloud SQL)**.

---

## Completed

| Phase | Summary |
|-------|---------|
| **P1** | DRY_RUN & config hardening — fail-fast on missing env vars, `PORT`, `ANTHROPIC_MODEL` |
| **P2** | Structured JSON logging via `app/logger.py`, `LOG_LEVEL` env var |
| **P3** | Typed exceptions, tenacity retry/backoff on Google API, polling race condition fixed |
| **P4** | PostgreSQL via psycopg2, Alembic migrations, `DATABASE_URL` env var |
| **P5** | HTTP API key auth (`X-Api-Key` header), `API_SECRET` env var, `POST /drafts/{id}/edit` endpoint |

---

## Phase P6 — Secrets Management (Google Secret Manager)

**Goal:** Remove all secrets from `.env` / plaintext env vars; use Secret Manager for Cloud Run.

**Files:** `app/config.py`, `app/services/google_api.py`, GCP config

### Tasks

- [ ] Enable Secret Manager API in GCP project
- [ ] Create secrets for:
  - `TELEGRAM_BOT_TOKEN`
  - `ANTHROPIC_API_KEY`
  - `GOOGLE_OAUTH_TOKEN` (replaces `token.pickle`)
  - `API_SECRET`
  - `DATABASE_URL`
- [ ] In `google_api.py` — replace `token.pickle` file with Secret Manager read/write:
  - On startup: fetch token JSON from Secret Manager, deserialize into `Credentials`
  - On token refresh: serialize and write back to Secret Manager
- [ ] Add `google-cloud-secret-manager` to `requirements.txt`
- [ ] Update Cloud Run service to mount secrets as env vars (`--set-secrets` flag)
- [ ] Keep `.env` file approach working for local dev (Secret Manager only when `GOOGLE_CLOUD_PROJECT` env var is set)

### Verification

```bash
# On Cloud Run: secrets visible as env vars
# Locally: .env file still works
```

---

## Phase P7 — Dockerfile & Cloud Run Deployment

**Goal:** Containerize the app and deploy to Cloud Run.

**Files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `app/main.py`

### Tasks

- [ ] Create `.dockerignore` (exclude `.env`, `token.pickle`, `*.db`, `venv/`, `__pycache__/`)
- [ ] Create `Dockerfile`:
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  EXPOSE 8080
  CMD ["python", "run.py"]
  ```
- [ ] Create `docker-compose.yml` for local dev (app + postgres)
- [ ] In `app/main.py` — add graceful shutdown: flush pending DB writes, stop bot cleanly
- [ ] Set up Cloud SQL (PostgreSQL 16) instance in GCP
- [ ] Configure Cloud Run service:
  - Connect to Cloud SQL via unix socket
  - Mount all secrets from Secret Manager
  - Set `DRY_RUN=false`, `LOG_LEVEL=INFO`
  - Min instances: 1 (long-polling requires always-on; OR do P8 first for scale-to-zero)
- [ ] Set up Cloud Logging export (automatic with Cloud Run)

### Deploy command

```bash
gcloud run deploy google-reviews \
  --source . \
  --region europe-west9 \
  --set-secrets="TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,..." \
  --add-cloudsql-instances="PROJECT:REGION:INSTANCE" \
  --min-instances=1
```

### Verification

```bash
curl https://SERVICE_URL/health
# {"status": "healthy", ...}
```

---

## Phase P8 — Webhook Mode ✅ complete

**Goal:** Switch from long-polling to Telegram webhook so Cloud Run can use `min-instances=0`.

**Files:** `app/routes.py`, `app/services/external/telegram/bot.py`, `app/config.py`

### Tasks

- [x] Activate `POST /telegram` webhook endpoint in `routes.py`
- [x] On startup: if `WEBHOOK_URL` env var is set, register webhook with Telegram; otherwise fall back to long-polling
- [x] Skip `start_polling()` when in webhook mode; delete webhook on shutdown
- [x] Pass `WEBHOOK_URL=https://YOUR_CLOUD_RUN_URL` as env var on Cloud Run (no trailing slash, no `/telegram`)

---

## Phase P9 — Monitoring & Alerting

**Goal:** Know when something breaks before the owner does.

### Tasks

- [ ] Set up Cloud Monitoring uptime check on `/health`
- [ ] Create alerting policy: notify if `/health` returns non-200 for >5 minutes
- [ ] Structured error metrics via Cloud Logging (automatic for `severity=ERROR`)
- [ ] Optional: `/metrics` endpoint (Prometheus format)

---

## Dependency Order

```
P6 → P7 → P8 → P9
       ↑
  (P8 before P7 if you want scale-to-zero from day one)
```

## New Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `API_SECRET` | Yes | — | Shared secret for HTTP API |
| `DRY_RUN` | No | `false` | Set `true` for testing |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` for local dev |
| `ANTHROPIC_MODEL` | No | `claude-haiku-4-5-20251001` | Claude model to use |
| `PORT` | No | `8080` | Uvicorn listen port |
| `WEBHOOK_URL` | No | — | If set, enables Telegram webhook mode |

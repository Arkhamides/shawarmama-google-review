# Database Reference

PostgreSQL (Cloud SQL in production, Docker locally). Schema is managed by **Alembic** — never edit tables manually.

---

## Local Development

```bash
# Start PostgreSQL
docker run --name reviews-pg \
  -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=reviews \
  -p 5432:5432 -d postgres:16

# Run the app (migrations apply automatically)
DATABASE_URL=postgresql://postgres:dev@localhost:5432/reviews python run.py

# Inspect tables
docker exec reviews-pg psql -U postgres -d reviews -c "\dt"
docker exec reviews-pg psql -U postgres -d reviews -c "SELECT * FROM seen_reviews LIMIT 5;"
```

---

## Schema

### `seen_reviews` — deduplication, every fetched review lands here

| Column | Type | Notes |
|--------|------|-------|
| `review_id` | TEXT PK | Google review ID |
| `location_id` | TEXT NOT NULL | GMB location resource name |
| `location_name` | TEXT NOT NULL | Human-readable location title |
| `reviewer_name` | TEXT | |
| `star_rating` | INTEGER | 1–5 |
| `review_text` | TEXT | |
| `seen_at` | TIMESTAMP | Defaults to `now()` |

### `pending_replies` — draft responses awaiting owner action

| Column | Type | Notes |
|--------|------|-------|
| `review_id` | TEXT PK | |
| `location_id` | TEXT NOT NULL | |
| `location_name` | TEXT NOT NULL | |
| `reviewer_name` | TEXT | |
| `star_rating` | INTEGER | |
| `review_text` | TEXT | |
| `draft_reply` | TEXT NOT NULL | AI-generated or template |
| `status` | TEXT | `pending` → `posted` or `rejected` |
| `created_at` | TIMESTAMP | Defaults to `now()` |
| `approved_at` | TIMESTAMP | Set when owner approves |
| `posted_at` | TIMESTAMP | Set when posted to Google |

### `posted_replies` — history of responses posted to Google

| Column | Type | Notes |
|--------|------|-------|
| `review_id` | TEXT PK | |
| `location_id` | TEXT NOT NULL | |
| `location_name` | TEXT NOT NULL | |
| `reply_text` | TEXT NOT NULL | Final text that was posted |
| `posted_at` | TIMESTAMP | Defaults to `now()` |

### `alembic_version` — managed by Alembic, do not touch

---

## Migration Workflow

Schema is defined in [db/models.py](db/models.py) as SQLAlchemy Core `Table` objects. Alembic diffs these against the live database to generate migrations.

### Adding a column or table

```bash
# 1. Edit db/models.py — add the new Column or Table
# 2. Generate migration (autogenerate diffs models vs live DB)
DATABASE_URL=postgresql://... alembic revision --autogenerate -m "add_edited_reply_column"
# 3. Review the generated file in db/migrations/versions/
# 4. Apply
DATABASE_URL=postgresql://... alembic upgrade head
# 5. Commit the migration file alongside the code change
```

### Applying migrations manually

```bash
DATABASE_URL=postgresql://... alembic upgrade head     # apply all pending
DATABASE_URL=postgresql://... alembic downgrade -1     # roll back one
DATABASE_URL=postgresql://... alembic current          # show current revision
DATABASE_URL=postgresql://... alembic history          # show migration history
```

### On startup

`run.py` calls `init_db()` which runs `alembic upgrade head` synchronously before uvicorn starts. Cloud Run deployments auto-migrate on startup — safe because Alembic is idempotent.

---

## Production (Cloud SQL)

Cloud Run connects to Cloud SQL via a Unix socket (no public network exposure):

```
DATABASE_URL=postgresql://user:pass@/reviews?host=/cloudsql/PROJECT:REGION:INSTANCE
```

The `DATABASE_URL` is stored in Secret Manager (P6) and mounted as an env var via `--set-secrets` in the Cloud Run deploy command.

---

## Key Files

| File | Purpose |
|------|---------|
| [db/models.py](db/models.py) | SQLAlchemy Core table definitions — edit this to change schema |
| [db/migrations/versions/](db/migrations/versions/) | Alembic migration history — commit every file |
| [db/migrations/env.py](db/migrations/env.py) | Alembic runner config (reads `DATABASE_URL` from env) |
| [alembic.ini](alembic.ini) | Alembic project config |
| [app/services/database.py](app/services/database.py) | psycopg2 data access layer (10 public functions) |

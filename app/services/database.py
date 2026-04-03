"""
PostgreSQL Database Layer for Review Management

Tracks seen reviews and pending owner approvals.
Schema managed by Alembic — run `alembic upgrade head` or call init_db() on startup.
"""

import psycopg2
import psycopg2.extras
from alembic.config import Config
from alembic import command

from app.config import DATABASE_URL
from app.logger import get_logger

logger = get_logger(__name__)


def _connect():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Apply all pending Alembic migrations on startup (idempotent)."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied (alembic upgrade head)")


def has_seen_review(review_id):
    """Check if we've already seen this review."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM seen_reviews WHERE review_id = %s', (review_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def mark_seen(review_id, location_id, location_name, reviewer_name, star_rating, review_text):
    """Mark a review as seen."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO seen_reviews
                (review_id, location_id, location_name, reviewer_name, star_rating, review_text)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (review_id) DO NOTHING
            ''',
            (review_id, location_id, location_name, reviewer_name, star_rating, review_text),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error in mark_seen for %s: %s", review_id, e, exc_info=True)
        raise
    finally:
        conn.close()


def save_pending_reply(review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply):
    """Save a pending reply waiting for owner approval."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO pending_replies
                (review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (review_id) DO UPDATE
                SET draft_reply = EXCLUDED.draft_reply,
                    status = 'pending'
            ''',
            (review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error in save_pending_reply for %s: %s", review_id, e, exc_info=True)
        raise
    finally:
        conn.close()


def get_pending_reply(review_id):
    """Fetch a pending reply waiting for approval."""
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT * FROM pending_replies WHERE review_id = %s', (review_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_pending_replies(status='pending'):
    """Fetch all pending replies with a specific status."""
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT * FROM pending_replies WHERE status = %s', (status,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def mark_approved(review_id):
    """Mark a reply as approved by owner."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pending_replies SET status = 'approved', approved_at = NOW() WHERE review_id = %s",
            (review_id,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error in mark_approved for %s: %s", review_id, e, exc_info=True)
        raise
    finally:
        conn.close()


def mark_posted(review_id, reply_text):
    """Mark a reply as posted to Google My Business and record in history."""
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "UPDATE pending_replies SET status = 'posted', posted_at = NOW() WHERE review_id = %s",
            (review_id,),
        )

        cur.execute('SELECT location_id, location_name FROM pending_replies WHERE review_id = %s', (review_id,))
        row = cur.fetchone()
        if row:
            cur.execute(
                '''
                INSERT INTO posted_replies (review_id, location_id, location_name, reply_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (review_id) DO NOTHING
                ''',
                (review_id, row['location_id'], row['location_name'], reply_text),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error in mark_posted for %s: %s", review_id, e, exc_info=True)
        raise
    finally:
        conn.close()


def mark_rejected(review_id):
    """Mark a reply as rejected by owner."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pending_replies SET status = 'rejected' WHERE review_id = %s",
            (review_id,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("DB error in mark_rejected for %s: %s", review_id, e, exc_info=True)
        raise
    finally:
        conn.close()


def get_stats():
    """Get database statistics."""
    conn = _connect()
    try:
        cur = conn.cursor()

        cur.execute('SELECT COUNT(*) FROM seen_reviews')
        total_seen = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM pending_replies WHERE status = 'pending'")
        pending_approvals = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM posted_replies')
        total_posted = cur.fetchone()[0]

        return {
            'total_seen': total_seen,
            'pending_approvals': pending_approvals,
            'total_posted': total_posted,
        }
    finally:
        conn.close()

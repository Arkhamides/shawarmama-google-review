"""
Repository for seen_reviews — review deduplication tracking.
"""

from app.services.persistence.database import _connect
from app.services.common.logger import get_logger

logger = get_logger(__name__)


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

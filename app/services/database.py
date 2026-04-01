"""
SQLite Database Layer for Review Management

Tracks seen reviews and pending owner approvals.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = 'db/reviews.db'


def init_db():
    """Initialize database schema on startup."""
    # Ensure db directory exists
    Path('db').mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table: Track which reviews we've already seen (deduplication)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seen_reviews (
            review_id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL,
            location_name TEXT NOT NULL,
            reviewer_name TEXT,
            star_rating INTEGER,
            review_text TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Table: Pending replies waiting for owner approval
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_replies (
            review_id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL,
            location_name TEXT NOT NULL,
            reviewer_name TEXT,
            star_rating INTEGER,
            review_text TEXT,
            draft_reply TEXT NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, approved, posted, rejected
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            posted_at TIMESTAMP
        )
    ''')

    # Table: Posted replies (history)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posted_replies (
            review_id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL,
            location_name TEXT NOT NULL,
            reply_text TEXT NOT NULL,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")


def has_seen_review(review_id):
    """Check if we've already seen this review."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM seen_reviews WHERE review_id = ?', (review_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def mark_seen(review_id, location_id, location_name, reviewer_name, star_rating, review_text):
    """Mark a review as seen."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO seen_reviews
        (review_id, location_id, location_name, reviewer_name, star_rating, review_text)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (review_id, location_id, location_name, reviewer_name, star_rating, review_text))
    conn.commit()
    conn.close()


def save_pending_reply(review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply):
    """Save a pending reply waiting for owner approval."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO pending_replies
        (review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (review_id, location_id, location_name, reviewer_name, star_rating, review_text, draft_reply))
    conn.commit()
    conn.close()


def get_pending_reply(review_id):
    """Fetch a pending reply waiting for approval."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pending_replies WHERE review_id = ?', (review_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'review_id': row[0],
        'location_id': row[1],
        'location_name': row[2],
        'reviewer_name': row[3],
        'star_rating': row[4],
        'review_text': row[5],
        'draft_reply': row[6],
        'status': row[7],
        'created_at': row[8],
    }


def get_all_pending_replies(status='pending'):
    """Fetch all pending replies with a specific status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pending_replies WHERE status = ?', (status,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            'review_id': row[0],
            'location_id': row[1],
            'location_name': row[2],
            'reviewer_name': row[3],
            'star_rating': row[4],
            'review_text': row[5],
            'draft_reply': row[6],
            'status': row[7],
            'created_at': row[8],
        })
    return results


def mark_approved(review_id):
    """Mark a reply as approved by owner."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pending_replies
        SET status = 'approved', approved_at = CURRENT_TIMESTAMP
        WHERE review_id = ?
    ''', (review_id,))
    conn.commit()
    conn.close()


def mark_posted(review_id, reply_text):
    """Mark a reply as posted to Google My Business."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Update pending_replies
    cursor.execute('''
        UPDATE pending_replies
        SET status = 'posted', posted_at = CURRENT_TIMESTAMP
        WHERE review_id = ?
    ''', (review_id,))

    # Get the pending reply details
    cursor.execute('SELECT * FROM pending_replies WHERE review_id = ?', (review_id,))
    row = cursor.fetchone()

    if row:
        # Insert into posted_replies history
        cursor.execute('''
            INSERT INTO posted_replies
            (review_id, location_id, location_name, reply_text)
            VALUES (?, ?, ?, ?)
        ''', (review_id, row[1], row[2], reply_text))

    conn.commit()
    conn.close()


def mark_rejected(review_id):
    """Mark a reply as rejected by owner."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pending_replies
        SET status = 'rejected'
        WHERE review_id = ?
    ''', (review_id,))
    conn.commit()
    conn.close()


def get_stats():
    """Get database statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM seen_reviews')
    total_seen = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM pending_replies WHERE status = "pending"')
    pending_approvals = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM posted_replies')
    total_posted = cursor.fetchone()[0]

    conn.close()

    return {
        'total_seen': total_seen,
        'pending_approvals': pending_approvals,
        'total_posted': total_posted,
    }

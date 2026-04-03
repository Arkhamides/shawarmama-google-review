"""
SQLAlchemy Core table definitions — single source of truth for the schema.

Used by Alembic for autogenerate (alembic revision --autogenerate).
Not used at runtime — database.py talks directly via psycopg2.
"""

from sqlalchemy import (
    Column, Integer, MetaData, String, Table, Text, TIMESTAMP
)
from sqlalchemy.sql import func

metadata = MetaData()

seen_reviews = Table(
    'seen_reviews',
    metadata,
    Column('review_id', String, primary_key=True),
    Column('location_id', String, nullable=False),
    Column('location_name', String, nullable=False),
    Column('reviewer_name', String),
    Column('star_rating', Integer),
    Column('review_text', Text),
    Column('seen_at', TIMESTAMP, server_default=func.now()),
)

pending_replies = Table(
    'pending_replies',
    metadata,
    Column('review_id', String, primary_key=True),
    Column('location_id', String, nullable=False),
    Column('location_name', String, nullable=False),
    Column('reviewer_name', String),
    Column('star_rating', Integer),
    Column('review_text', Text),
    Column('draft_reply', Text, nullable=False),
    Column('status', String, server_default='pending'),  # pending, approved, posted, rejected
    Column('created_at', TIMESTAMP, server_default=func.now()),
    Column('approved_at', TIMESTAMP),
    Column('posted_at', TIMESTAMP),
)

posted_replies = Table(
    'posted_replies',
    metadata,
    Column('review_id', String, primary_key=True),
    Column('location_id', String, nullable=False),
    Column('location_name', String, nullable=False),
    Column('reply_text', Text, nullable=False),
    Column('posted_at', TIMESTAMP, server_default=func.now()),
)

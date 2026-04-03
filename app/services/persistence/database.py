"""
PostgreSQL connection management and migration runner.

Schema managed by Alembic — call init_db() on startup.
"""

import psycopg2
from alembic.config import Config
from alembic import command

from app.config import DATABASE_URL
from app.services.common.logger import get_logger

logger = get_logger(__name__)


def _connect():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Apply all pending Alembic migrations on startup (idempotent)."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied (alembic upgrade head)")

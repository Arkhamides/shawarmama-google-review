"""
Background job scheduler.

Manages the AsyncIOScheduler for periodic review polling.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import POLL_INTERVAL_MINUTES
from app.services.common.logger import get_logger
from app.services.jobs.polling.review_poller import polling_loop

logger = get_logger(__name__)

# Global scheduler instance
scheduler = None


def start_polling(creds, locations):
    """Initialize and start the async polling scheduler."""
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.warning("Polling scheduler already running")
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        polling_loop,
        'interval',
        minutes=POLL_INTERVAL_MINUTES,
        args=[creds, locations],
        id='review_polling'
    )
    scheduler.start()
    logger.info("Polling scheduler started (every %d minutes)", POLL_INTERVAL_MINUTES)


def stop_polling():
    """Stop the background polling scheduler."""
    global scheduler

    if scheduler is not None and scheduler.running:
        scheduler.shutdown()
        scheduler = None
        logger.info("Polling scheduler stopped")

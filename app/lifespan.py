"""
FastAPI lifespan context manager — startup and shutdown orchestration.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.services.common.logger import get_logger
from app.services.external.google.auth import authenticate
from app.services.external.google.reviews import get_all_locations
from app.services.external.telegram.bot import start_bot, stop_bot
from app.services.jobs.scheduler import start_polling, stop_polling

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager: startup and shutdown."""
    # Startup
    logger.info("Initializing application")

    try:
        logger.info("Authenticating with Google My Business")
        creds = authenticate()
        logger.info("Authenticated with Google My Business")

        logger.info("Fetching locations")
        locations = get_all_locations(creds)
        logger.info("Locations loaded", extra={"count": len(locations)})

        # Store creds and locations in app state for route handlers
        app.state.creds = creds
        app.state.locations = locations

        # Start Telegram bot in the same event loop
        await start_bot(creds)

        # Start polling scheduler (runs sync polling_loop in thread pool executor)
        start_polling(creds, locations)

        logger.info("Application initialized successfully")

    except Exception as e:
        logger.error("Initialization failed: %s", e, exc_info=True)
        raise

    # Application is running
    yield

    # Shutdown
    logger.info("Shutting down")
    await stop_bot()
    stop_polling()
    logger.info("Shutdown complete")

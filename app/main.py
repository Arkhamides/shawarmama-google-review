"""
Main application: FastAPI server with polling loop and Telegram bot

Polls Google My Business for reviews every N minutes.
When bad reviews (≤3 stars) are detected, generates draft and notifies owner.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

import app.logger  # noqa: F401 — configures root logger before any other import
from app.logger import get_logger
from app.services.google_api import authenticate, get_all_locations
from app.services.polling import start_polling, stop_polling
from app.services.bot import start_bot, stop_bot
from app.routes import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager: startup and shutdown."""
    # Startup
    logger.info("Initializing application")

    try:
        # Authenticate
        logger.info("Authenticating with Google My Business")
        creds = authenticate()
        logger.info("Authenticated with Google My Business")

        # Fetch locations
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


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Include routes
app.include_router(router)

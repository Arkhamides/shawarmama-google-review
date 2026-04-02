"""
Main application: FastAPI server with polling loop and Telegram bot

Polls Google My Business for reviews every N minutes.
When bad reviews (≤3 stars) are detected, generates draft and notifies owner.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import FLASK_PORT
from app.services.google_api import authenticate, get_all_locations
from app.services.database import init_db
from app.services.polling import start_polling, stop_polling
from app.services.bot import start_bot, stop_bot
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager: startup and shutdown."""
    # Startup
    print("🚀 Initializing application...")

    try:
        # Authenticate
        print("   Authenticating with Google My Business...")
        creds = authenticate()
        print("   ✅ Authenticated")

        # Fetch locations
        print("   Fetching locations...")
        locations = get_all_locations(creds)
        print(f"   ✅ Found {len(locations)} location(s)")

        # Initialize database
        init_db()

        # Store creds and locations in app state for route handlers
        app.state.creds = creds
        app.state.locations = locations

        # Start Telegram bot in the same event loop
        await start_bot(creds)

        # Start polling scheduler (runs sync polling_loop in thread pool executor)
        start_polling(creds, locations)

        print("✅ Application initialized successfully\n")

    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        raise

    # Application is running
    yield

    # Shutdown
    print("\n🛑 Shutting down...")
    await stop_bot()
    stop_polling()
    print("✅ Shutdown complete")


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Include routes
app.include_router(router)

"""
Main application: FastAPI server with polling loop and Telegram bot

Polls Google My Business for reviews every N minutes.
When bad reviews (≤3 stars) are detected, generates draft and notifies owner.
"""

import app.services.common.logger  # noqa: F401 — configures root logger before any other import
from fastapi import FastAPI

from app.lifespan import lifespan
from app.routes import router

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Include routes
app.include_router(router)

#!/usr/bin/env python3
"""
Application entry point for Google Reviews FastAPI server.

Run with: python run.py
"""

import uvicorn
from app.config import PORT
from app.services.database import init_db


if __name__ == '__main__':
    # Run Alembic migrations synchronously before the event loop starts.
    # This avoids SQLAlchemy thread-pool conflicts with asyncio.
    init_db()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )

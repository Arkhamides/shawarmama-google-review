#!/usr/bin/env python3
"""
Application entry point for Google Reviews FastAPI server.

Run with: python run.py
"""

import uvicorn
from app.config import FLASK_PORT


if __name__ == '__main__':
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=FLASK_PORT,
        reload=False
    )

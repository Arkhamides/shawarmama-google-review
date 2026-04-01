#!/usr/bin/env python3
"""
Application entry point for Google Reviews Flask server.

Run with: python run.py
"""

from app.main import create_app, initialize_app
from app.config import FLASK_PORT


if __name__ == '__main__':
    app = create_app()
    initialize_app(app)

    # Run Flask server
    print(f"🌐 Starting Flask server on port {FLASK_PORT}...")
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)

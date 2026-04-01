"""
Main application: Flask web server + background polling loop

Polls Google My Business for reviews every N minutes.
When bad reviews (≤3 stars) are detected, generates draft and notifies owner.
"""

from flask import Flask

from app.config import FLASK_PORT
from app.services.google_api import authenticate, get_all_locations
from app.services.database import init_db
from app.services.polling import start_polling
from app.routes import register_routes


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    return app


def initialize_app(app):
    """Initialize credentials, locations, and routes."""
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

        # Register Flask routes (they need access to creds and locations)
        register_routes(app, creds, locations)

        # Start polling
        start_polling(creds, locations)

        print("✅ Application initialized successfully\n")

        return creds, locations

    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        raise


if __name__ == '__main__':
    # Create and initialize app
    app = create_app()
    initialize_app(app)

    # Run Flask server
    print(f"🌐 Starting Flask server on port {FLASK_PORT}...")
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)

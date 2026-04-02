"""
Configuration management for the Google Reviews application.

Load environment variables from .env file and provide centralized config access.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Cloud & Authentication
GOOGLE_TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')
GOOGLE_PROJECT_ID = os.getenv('GOOGLE_PROJECT_ID', 'your-gcp-project-id')

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_OWNER_CHAT_ID = os.getenv('TELEGRAM_OWNER_CHAT_ID')
TELEGRAM_OWNER_CHAT_IDS = [
    int(id.strip()) for id in TELEGRAM_OWNER_CHAT_ID.split(',') if id.strip()
] if TELEGRAM_OWNER_CHAT_ID else []

# Anthropic Configuration (Phase 4-5)
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Application Settings
BAD_REVIEW_THRESHOLD = int(os.getenv('BAD_REVIEW_THRESHOLD', '3'))
POLL_INTERVAL_MINUTES = int(os.getenv('POLL_INTERVAL_MINUTES', '5'))
FLASK_PORT = int(os.getenv('FLASK_PORT', '8080'))

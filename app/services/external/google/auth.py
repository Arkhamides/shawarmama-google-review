"""
Google OAuth2 authentication.

Manages token loading, refresh, and caching via token.pickle.
"""

import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from app.services.external.google.client import SCOPES, TOKEN_PATH
from app.services.common.logger import get_logger

logger = get_logger(__name__)


def authenticate():
    """
    Authenticate with Google My Business API.

    Returns:
        google.oauth2.credentials.Credentials object

    On first run, opens a browser for OAuth consent. Subsequent runs load cached
    credentials from TOKEN_PATH. Automatically refreshes expired tokens.
    """
    creds = None

    # Load saved credentials
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    return creds

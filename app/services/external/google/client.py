"""
Google API client constants and shared internals.

Shared by auth, reviews, and posting modules.
"""

import os

SCOPES = ['https://www.googleapis.com/auth/business.manage']
TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')

# HTTP status codes that warrant a retry (rate-limit / server-side transient)
_TRANSIENT_CODES = {429, 500, 503}


class _TransientGoogleError(Exception):
    """Raised internally when a Google API call returns a transient HTTP error."""

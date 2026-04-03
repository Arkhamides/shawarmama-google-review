#!/usr/bin/env python3
"""
Google My Business API Module

Provides functions to authenticate, fetch locations, fetch reviews, and post replies
to Google My Business reviews. Can be imported by other applications (like a Telegram bot).

Requirements:
- Google Cloud project with My Business APIs enabled
- OAuth 2.0 Desktop Application credentials saved as credentials.json
- Token cache will be saved to token.pickle (or custom path via TOKEN_PATH env var)
"""

import logging
import os
import pickle
import requests
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from tenacity import (
    retry, retry_if_exception_type,
    stop_after_attempt, wait_exponential,
    before_sleep_log, RetryError,
)

from app.logger import get_logger

logger = get_logger(__name__)

SCOPES = ['https://www.googleapis.com/auth/business.manage']
TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')

# Status codes that warrant a retry (rate-limit / server-side transient)
_TRANSIENT_CODES = {429, 500, 503}


class _TransientGoogleError(Exception):
    """Raised internally when a Google API call returns a transient HTTP error."""


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


def get_all_accounts(creds):
    """
    Fetch all Google My Business accounts associated with the authenticated user.

    Args:
        creds: Google credentials object (from authenticate())

    Returns:
        List of account dicts, each with keys: name, accountName, type, verificationState, etc.
        Returns empty list on error.
    """
    try:
        # Refresh credentials if needed
        if creds.expired:
            creds.refresh(Request())

        access_token = creds.token
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Use REST API to list accounts
        url = 'https://mybusinessaccountmanagement.googleapis.com/v1/accounts'
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            result = response.json()
            accounts = result.get('accounts', [])
            return accounts
        else:
            logger.warning("Error fetching accounts: status %s — %s", response.status_code, response.text)
            return []
    except Exception as e:
        logger.error("Error fetching accounts: %s", e, exc_info=True)
        return []


def get_locations_for_account(service, account_id):
    """
    Fetch all locations for a specific Google My Business account.

    Args:
        service: mybusinessbusinessinformation v1 discovery client
        account_id: Account ID string (e.g., "accounts/123456")

    Returns:
        List of location dicts with keys: name, title
        Returns empty list on error.
    """
    try:
        result = service.accounts().locations().list(
            parent=account_id,
            readMask='name,title'
        ).execute()
        locations = result.get('locations', [])
        return locations
    except Exception as e:
        logger.error("Error fetching locations for %s: %s", account_id, e, exc_info=True)
        return []


@retry(
    retry=retry_if_exception_type(_TransientGoogleError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)
def _fetch_reviews_inner(headers: dict, url: str) -> list:
    """Inner call with retry; raises _TransientGoogleError on 429/500/503."""
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('reviews', [])
    if response.status_code in _TRANSIENT_CODES:
        raise _TransientGoogleError(f"HTTP {response.status_code}")
    logger.warning("Error fetching reviews: status %s", response.status_code)
    return []


def get_reviews(creds, location_name):
    """
    Fetch reviews for a specific location.

    Args:
        creds: Google credentials object
        location_name: Location resource name (e.g., "locations/123456")

    Returns:
        List of review dicts with keys: reviewer, starRating, comment, etc.
        Returns empty list on error.
    """
    try:
        if creds.expired:
            creds.refresh(Request())

        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json',
        }
        url = f'https://mybusiness.googleapis.com/v4/accounts/me/{location_name}/reviews'
        return _fetch_reviews_inner(headers, url)
    except RetryError:
        logger.warning("get_reviews exhausted retries for location %s", location_name)
        return []
    except Exception as e:
        logger.error("Error fetching reviews for %s: %s", location_name, e, exc_info=True)
        return []


@retry(
    retry=retry_if_exception_type(_TransientGoogleError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)
def _post_reply_inner(headers: dict, url: str, payload: dict):
    """Inner call with retry; raises _TransientGoogleError on 429/500/503.
    Does NOT retry on 403/404 — those are permanent errors."""
    response = requests.put(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    if response.status_code in _TRANSIENT_CODES:
        raise _TransientGoogleError(f"HTTP {response.status_code}")
    # 403, 404, etc. — permanent; log and return None
    logger.warning("Error posting reply: status %s — %s", response.status_code, response.text)
    return None


def post_reply(creds, location_name, review_id, reply_text):
    """
    Post a reply to a Google My Business review.

    Args:
        creds: Google credentials object
        location_name: Location resource name (e.g., "locations/123456")
        review_id: Review ID from the review object
        reply_text: The response text to post

    Returns:
        The reply object on success, or None on error.
    """
    try:
        if creds.expired:
            creds.refresh(Request())

        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json',
        }
        url = (
            f'https://mybusiness.googleapis.com/v4/accounts/me/'
            f'{location_name}/reviews/{review_id}/reply'
        )
        return _post_reply_inner(headers, url, {'comment': reply_text})
    except RetryError:
        logger.error("post_reply exhausted retries for review %s", review_id)
        return None
    except Exception as e:
        logger.error("Error posting reply for review %s: %s", review_id, e, exc_info=True)
        return None


def get_all_locations(creds):
    """
    Fetch all locations from all accounts associated with the authenticated user.

    This is a convenience function that combines get_all_accounts() and
    get_locations_for_account() to return all locations across all accounts.

    Args:
        creds: Google credentials object (from authenticate())

    Returns:
        List of location dicts (with name and title keys)
    """
    # Build the discovery service once
    service = build('mybusinessbusinessinformation', 'v1', credentials=creds)

    # Get all accounts
    accounts = get_all_accounts(creds)
    if not accounts:
        return []

    # Collect all locations from all accounts
    all_locations = []
    for account in accounts:
        account_id = account['name']
        locations = get_locations_for_account(service, account_id)
        all_locations.extend(locations)

    return all_locations

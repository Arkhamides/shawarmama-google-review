"""
Google My Business review fetching and location listing.
"""

import logging

import requests
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from tenacity import (
    retry, retry_if_exception_type,
    stop_after_attempt, wait_exponential,
    before_sleep_log, RetryError,
)

from app.services.external.google.client import _TransientGoogleError, _TRANSIENT_CODES
from app.services.common.logger import get_logger

logger = get_logger(__name__)


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
        if creds.expired:
            creds.refresh(Request())

        access_token = creds.token
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

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


def get_all_locations(creds):
    """
    Fetch all locations from all accounts associated with the authenticated user.

    Args:
        creds: Google credentials object (from authenticate())

    Returns:
        List of location dicts (with name and title keys)
    """
    service = build('mybusinessbusinessinformation', 'v1', credentials=creds)

    accounts = get_all_accounts(creds)
    if not accounts:
        return []

    all_locations = []
    for account in accounts:
        account_id = account['name']
        locations = get_locations_for_account(service, account_id)
        all_locations.extend(locations)

    return all_locations

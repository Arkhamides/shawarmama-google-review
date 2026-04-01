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

import os
import pickle
import requests
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/business.manage']
TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')


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
            print(f"Error fetching accounts: Status {response.status_code}")
            print(response.text)
            return []
    except Exception as e:
        print(f"Error fetching accounts: {e}")
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
        print(f"Error fetching locations for {account_id}: {e}")
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
        # Refresh credentials if needed
        if creds.expired:
            creds.refresh(Request())

        access_token = creds.token
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Use REST API to fetch reviews
        url = f'https://mybusiness.googleapis.com/v4/accounts/me/{location_name}/reviews'
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            result = response.json()
            reviews = result.get('reviews', [])
            return reviews
        else:
            print(f"Error fetching reviews: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching reviews: {e}")
        return []


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
        # Refresh credentials if needed
        if creds.expired:
            creds.refresh(Request())

        access_token = creds.token
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Use REST API to post a reply
        url = f'https://mybusiness.googleapis.com/v4/accounts/me/{location_name}/reviews/{review_id}/reply'
        payload = {
            'comment': reply_text
        }
        response = requests.put(url, headers=headers, json=payload)

        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print(f"Error posting reply: Status {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"Error posting reply: {e}")
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

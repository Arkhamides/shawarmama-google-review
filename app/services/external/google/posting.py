"""
Google My Business reply posting.
"""

import logging

import requests
from google.auth.transport.requests import Request
from tenacity import (
    retry, retry_if_exception_type,
    stop_after_attempt, wait_exponential,
    before_sleep_log, RetryError,
)

from app.services.external.google.client import _TransientGoogleError, _TRANSIENT_CODES
from app.services.common.logger import get_logger

logger = get_logger(__name__)


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

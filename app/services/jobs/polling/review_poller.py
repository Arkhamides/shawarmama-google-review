"""
Review polling loop — fetches new reviews from Google My Business
and triggers the bad-review workflow (draft + notification).
"""

from app.config import BAD_REVIEW_THRESHOLD
from app.services.common.logger import get_logger
from app.services.common.validators import convert_rating_to_int
from app.services.external.google.reviews import get_reviews
from app.services.external.ai.response_generator import generate_draft_response
from app.services.external.telegram.bot import send_review_notification
from app.services.persistence.repositories.review_repository import has_seen_review, mark_seen
from app.services.persistence.repositories.draft_repository import save_pending_reply

logger = get_logger(__name__)


def polling_loop(creds, locations):
    """
    Background polling loop: checks for new reviews every N minutes.

    1. Fetch all reviews from all locations
    2. For each new review, check if it's "bad" (≤3 stars)
    3. If bad: generate draft response, save to database, notify owner
    4. Mark review as seen
    """
    if not creds or not locations:
        logger.warning("Polling skipped: not authenticated yet")
        return

    logger.info("Polling for new reviews")

    bad_reviews_found = 0

    for location in locations:
        location_name = location['name']
        location_title = location.get('title', 'Unknown')

        try:
            reviews = get_reviews(creds, location_name)
        except Exception as e:
            logger.error("Failed to fetch reviews for %s: %s", location_title, e, exc_info=True)
            continue

        for review in reviews:
            review_id = review.get('reviewId')
            if not review_id:
                continue
            if has_seen_review(review_id):
                continue

            reviewer_name = review.get('reviewer', {}).get('displayName', 'Anonymous')
            star_rating = convert_rating_to_int(review.get('starRating', 'FIVE'))
            review_text = review.get('comment', 'No text')

            try:
                if star_rating <= BAD_REVIEW_THRESHOLD:
                    logger.info(
                        "Bad review detected: %s (%d★) at %s",
                        reviewer_name, star_rating, location_title,
                    )

                    draft_reply = generate_draft_response(
                        location_title, reviewer_name, star_rating, review_text
                    )
                    save_pending_reply(
                        review_id, location_name, location_title, reviewer_name,
                        star_rating, review_text, draft_reply
                    )

                    # Wait for the notification to reach Telegram before marking seen.
                    # If it fails, do NOT mark_seen so the next poll retries.
                    future = send_review_notification(
                        review_id=review_id,
                        location_title=location_title,
                        reviewer_name=reviewer_name,
                        star_rating=star_rating,
                        review_text=review_text,
                        draft_reply=draft_reply,
                    )
                    if future is not None:
                        future.result(timeout=30)  # raises on Telegram error

                    mark_seen(review_id, location_name, location_title,
                              reviewer_name, star_rating, review_text)
                    bad_reviews_found += 1
                    logger.debug("Draft saved and owner notified: %.50s…", draft_reply)

                else:
                    logger.info(
                        "Good review: %s (%d★) at %s — skipped",
                        reviewer_name, star_rating, location_title,
                    )
                    mark_seen(review_id, location_name, location_title,
                              reviewer_name, star_rating, review_text)

            except Exception as e:
                logger.error(
                    "Failed to process review %s (%s) — will retry next poll: %s",
                    review_id, reviewer_name, e, exc_info=True,
                )

    if bad_reviews_found > 0:
        logger.info("Found %d bad review(s) — owner notified via Telegram", bad_reviews_found)
    else:
        logger.info("No new bad reviews")

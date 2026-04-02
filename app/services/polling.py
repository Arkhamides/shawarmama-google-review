"""
Review polling loop for Google My Business reviews.

Periodically checks for new reviews, detects bad reviews (≤3 stars),
generates draft responses, and saves them for owner approval.
"""

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import BAD_REVIEW_THRESHOLD, POLL_INTERVAL_MINUTES
from app.services.google_api import get_all_locations, get_reviews
from app.services.database import has_seen_review, mark_seen, save_pending_reply
from app.services.utils import convert_rating_to_int, generate_draft_response
from app.services.bot import send_review_notification


# Global scheduler instance
scheduler = None


def polling_loop(creds, locations):
    """
    Background polling loop: checks for new reviews every N minutes.

    1. Fetch all reviews from all locations
    2. For each new review, check if it's "bad" (≤3 stars)
    3. If bad: generate draft response, save to database, notify owner
    4. Mark review as seen
    """
    if not creds or not locations:
        print("⚠️  Polling skipped: not authenticated yet")
        return

    print(f"\n🔄 Polling for new reviews... ({datetime.now().strftime('%H:%M:%S')})")

    bad_reviews_found = 0

    try:
        for location in locations:
            location_name = location['name']
            location_title = location.get('title', 'Unknown')

            # Fetch reviews for this location
            reviews = get_reviews(creds, location_name)

            if not reviews:
                continue

            # Check each review
            for review in reviews:
                review_id = review.get('reviewId')  # Note: Google uses 'reviewId', not 'id'
                if not review_id:
                    continue

                # Skip if we've already seen this review
                if has_seen_review(review_id):
                    continue

                # Extract review details
                reviewer_name = review.get('reviewer', {}).get('displayName', 'Anonymous')
                star_rating = convert_rating_to_int(review.get('starRating', 'FIVE'))
                review_text = review.get('comment', 'No text')

                # Mark as seen
                mark_seen(review_id, location_name, location_title, reviewer_name, star_rating, review_text)

                # Check if it's a bad review
                if star_rating <= BAD_REVIEW_THRESHOLD:
                    print(f"⭐ BAD REVIEW detected: {reviewer_name} ({star_rating}★) - {location_title}")

                    # Generate draft response
                    draft_reply = generate_draft_response(location_title, reviewer_name, star_rating, review_text)

                    # Save to database
                    save_pending_reply(
                        review_id, location_name, location_title, reviewer_name,
                        star_rating, review_text, draft_reply
                    )

                    bad_reviews_found += 1

                    # Phase 4: Send Telegram notification to owner
                    send_review_notification(
                        review_id=review_id,
                        location_title=location_title,
                        reviewer_name=reviewer_name,
                        star_rating=star_rating,
                        review_text=review_text,
                        draft_reply=draft_reply
                    )

                    print(f"   📝 Draft saved: {draft_reply[:50]}...")

        if bad_reviews_found > 0:
            print(f"✅ Found {bad_reviews_found} bad review(s) — owner notified via Telegram")
        else:
            print("✅ No new bad reviews")

    except Exception as e:
        print(f"❌ Polling error: {e}")


def start_polling(creds, locations):
    """Initialize and start the async polling scheduler."""
    global scheduler

    if scheduler is not None and scheduler.running:
        print("⚠️  Polling scheduler already running")
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        polling_loop,
        'interval',
        minutes=POLL_INTERVAL_MINUTES,
        args=[creds, locations],
        id='review_polling'
    )
    scheduler.start()
    print(f"✅ Polling scheduler started (every {POLL_INTERVAL_MINUTES} minutes)")

    # Run once immediately
    polling_loop(creds, locations)


def stop_polling():
    """Stop the background polling scheduler."""
    global scheduler

    if scheduler is not None and scheduler.running:
        scheduler.shutdown()
        scheduler = None
        print("✅ Polling scheduler stopped")

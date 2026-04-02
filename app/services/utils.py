"""
Utility functions for the Google Reviews application.
"""

from app.config import ANTHROPIC_API_KEY
from app.services.ai_responder import generate_ai_response


def convert_rating_to_int(rating_str):
    """Convert Google's string ratings (FIVE, FOUR, etc.) to integers."""
    rating_map = {'FIVE': 5, 'FOUR': 4, 'THREE': 3, 'TWO': 2, 'ONE': 1}
    return rating_map.get(rating_str, 0)


def generate_draft_response(location_name, reviewer_name, star_rating, review_text):
    """
    Generate a draft response to a review.

    Uses Anthropic Claude AI if ANTHROPIC_API_KEY is set, falls back to templates.
    Phase 4 integrates Anthropic API. Template fallback ensures graceful degradation.
    """
    # Try AI-generated response first (Phase 4)
    if ANTHROPIC_API_KEY:
        ai_response = generate_ai_response(location_name, reviewer_name, star_rating, review_text)
        if ai_response:
            return ai_response

    # Fallback to template responses
    if star_rating <= 1:
        return f"Thank you for your feedback, {reviewer_name}. We're sorry to hear about your experience. Please contact us directly so we can make things right."
    elif star_rating == 2:
        return f"Hi {reviewer_name}, we appreciate your review. We'd like to understand your concerns better—please reach out to us."
    else:  # 3 stars
        return f"Thank you, {reviewer_name}, for taking the time to review us. We value your feedback and will work to improve."

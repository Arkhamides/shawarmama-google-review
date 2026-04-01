"""
Utility functions for the Google Reviews application.
"""


def convert_rating_to_int(rating_str):
    """Convert Google's string ratings (FIVE, FOUR, etc.) to integers."""
    rating_map = {'FIVE': 5, 'FOUR': 4, 'THREE': 3, 'TWO': 2, 'ONE': 1}
    return rating_map.get(rating_str, 0)


def generate_draft_response(location_name, reviewer_name, star_rating, review_text):
    """
    Generate a draft response to a review.

    For Phase 2, we return a simple template.
    Phase 5 will replace this with OpenAI integration.
    """
    # TODO: Phase 5 will integrate OpenAI API here
    # For now, return a template response

    if star_rating <= 1:
        template = f"Thank you for your feedback, {reviewer_name}. We're sorry to hear about your experience. Please contact us directly so we can make things right."
    elif star_rating == 2:
        template = f"Hi {reviewer_name}, we appreciate your review. We'd like to understand your concerns better—please reach out to us."
    else:  # 3 stars
        template = f"Thank you, {reviewer_name}, for taking the time to review us. We value your feedback and will work to improve."

    return template

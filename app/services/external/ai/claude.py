"""
Anthropic Claude API client for generating draft review responses.
"""

import anthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.services.external.ai.prompts import SYSTEM_PROMPT
from app.services.common.logger import get_logger

logger = get_logger(__name__)


def generate_ai_response(location_name: str, reviewer_name: str, star_rating: int, review_text: str) -> str:
    """
    Generate an AI-powered draft response to a review using Claude.

    Args:
        location_name: Restaurant location name (e.g., "Shawar'Mama Marais")
        reviewer_name: Name of the reviewer
        star_rating: Star rating (1-5)
        review_text: The review text

    Returns:
        A draft response text (2-4 sentences), or None if API call fails
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        user_message = f"{star_rating}-star review from {reviewer_name}:\n\n{review_text}"

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT.format(location_name=location_name),
            messages=[{"role": "user", "content": user_message}]
        )

        return response.content[0].text

    except anthropic.APIError as e:
        logger.warning("AI response generation failed: %s", e)
        return None

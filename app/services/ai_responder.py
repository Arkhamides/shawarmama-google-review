"""
Anthropic Claude AI responder for generating draft review responses.

Generates empathetic, professional responses to reviews using the Anthropic API.
Falls back gracefully if API key is not available.
"""

import anthropic
from app.config import ANTHROPIC_API_KEY


SYSTEM_PROMPT = """You are a professional restaurant manager for {location_name}, a shawarma restaurant in Paris.

A customer has left a review. Your task is to draft a brief, professional, and empathetic response.

Guidelines:
- Acknowledge the customer's specific concern or feedback
- Offer to resolve the issue if applicable, or thank them for positive feedback
- Be warm and professional in tone
- Keep the response to 2-4 sentences
- Match the language of the original review (French or English)
- Sign off with the restaurant name or "The team" — keep it simple
- Avoid generic filler phrases; be genuine and specific when possible"""


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

    Falls back to a simple template response if ANTHROPIC_API_KEY is not set.
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        user_message = f"{star_rating}-star review from {reviewer_name}:\n\n{review_text}"

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=SYSTEM_PROMPT.format(location_name=location_name),
            messages=[{"role": "user", "content": user_message}]
        )

        return response.content[0].text

    except Exception as e:
        print(f"⚠️  AI response generation failed: {e}")
        return None

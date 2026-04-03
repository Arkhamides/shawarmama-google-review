"""Input validators and converters."""

from app.services.common.constants import STAR_RATING_MAP


def convert_rating_to_int(rating_str):
    """Convert Google's string ratings (FIVE, FOUR, etc.) to integers."""
    return STAR_RATING_MAP.get(rating_str, 0)

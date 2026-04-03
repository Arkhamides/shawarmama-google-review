"""
Tests for app.services.common.validators

Pure function — no mocking, no DB, no API keys needed.
"""

import pytest
from app.services.common.validators import convert_rating_to_int


@pytest.mark.parametrize("rating_str, expected", [
    ("FIVE",  5),
    ("FOUR",  4),
    ("THREE", 3),
    ("TWO",   2),
    ("ONE",   1),
])
def test_known_ratings(rating_str, expected):
    assert convert_rating_to_int(rating_str) == expected


def test_unknown_rating_returns_zero():
    assert convert_rating_to_int("UNKNOWN") == 0


def test_empty_string_returns_zero():
    assert convert_rating_to_int("") == 0


def test_lowercase_returns_zero():
    # Google always sends uppercase — lowercase is not a valid input
    assert convert_rating_to_int("five") == 0

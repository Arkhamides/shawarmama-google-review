"""
Tests for app.services.external.ai.response_generator

Tests the template fallback path — no Anthropic API key required.
The AI path is tested via mocking so the suite stays offline.
"""

from unittest.mock import patch
import pytest
from app.services.external.ai.response_generator import generate_draft_response


# ---------------------------------------------------------------------------
# Template fallback (ANTHROPIC_API_KEY not set)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Ensure all tests in this file run without an API key by default."""
    monkeypatch.setattr("app.services.external.ai.response_generator.ANTHROPIC_API_KEY", None)


def test_one_star_mentions_reviewer():
    result = generate_draft_response("Shawar'Mama Marais", "Alice", 1, "Terrible food")
    assert "Alice" in result


def test_two_star_mentions_reviewer():
    result = generate_draft_response("Shawar'Mama Marais", "Bob", 2, "Not great")
    assert "Bob" in result


def test_three_star_mentions_reviewer():
    result = generate_draft_response("Shawar'Mama Marais", "Carol", 3, "It was okay")
    assert "Carol" in result


def test_returns_string():
    result = generate_draft_response("Shawar'Mama Marais", "Dave", 1, "Bad")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# AI path (mocked — keeps the suite offline)
# ---------------------------------------------------------------------------

def test_ai_response_used_when_available(monkeypatch):
    monkeypatch.setattr("app.services.external.ai.response_generator.ANTHROPIC_API_KEY", "fake-key")

    with patch("app.services.external.ai.response_generator.generate_ai_response") as mock_ai:
        mock_ai.return_value = "Merci pour votre avis."
        result = generate_draft_response("Shawar'Mama Marais", "Eve", 2, "Pas terrible")

    mock_ai.assert_called_once_with("Shawar'Mama Marais", "Eve", 2, "Pas terrible")
    assert result == "Merci pour votre avis."


def test_falls_back_to_template_when_ai_returns_none(monkeypatch):
    monkeypatch.setattr("app.services.external.ai.response_generator.ANTHROPIC_API_KEY", "fake-key")

    with patch("app.services.external.ai.response_generator.generate_ai_response") as mock_ai:
        mock_ai.return_value = None
        result = generate_draft_response("Shawar'Mama Marais", "Frank", 3, "Meh")

    assert "Frank" in result  # fell back to template

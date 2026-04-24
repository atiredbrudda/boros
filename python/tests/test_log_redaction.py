"""Tests for python/src/boros_brain/logging/redaction.py (INFRA-12 / T-01-06-02).

Verifies that the structlog processor redacts sensitive keys before JSONRenderer.

Test matrix:
  test_redaction_redacts_api_key             — api_key value becomes '***'
  test_redaction_case_insensitive            — Api-Key, TOKEN, Private_Key all redacted
  test_redaction_redacts_DOTENV_PRIVATE_KEY_vars — DOTENV_PRIVATE_KEY_PRODUCTION → '***'
  test_redaction_preserves_unrelated_keys    — run_id, market_id untouched
"""

from __future__ import annotations

from boros_brain.logging.redaction import redact_sensitive


class TestRedactionRedactsApiKey:
    def test_redaction_redacts_api_key(self) -> None:
        """api_key value is replaced with '***'; unrelated keys are untouched."""
        event_dict = {"api_key": "secret123", "market": "ETH"}
        result = redact_sensitive(None, None, event_dict)
        assert result["api_key"] == "***", f"Expected '***' but got {result['api_key']!r}"
        assert result["market"] == "ETH", "Unrelated key 'market' must not be modified"


class TestRedactionCaseInsensitive:
    def test_redaction_case_insensitive(self) -> None:
        """Redaction is case-insensitive: Api-Key, TOKEN, Private_Key all → '***'."""
        event_dict = {"Api-Key": "x", "TOKEN": "y", "Private_Key": "z"}
        result = redact_sensitive(None, None, event_dict)
        assert result["Api-Key"] == "***", f"Api-Key not redacted: {result['Api-Key']!r}"
        assert result["TOKEN"] == "***", f"TOKEN not redacted: {result['TOKEN']!r}"
        assert result["Private_Key"] == "***", f"Private_Key not redacted: {result['Private_Key']!r}"


class TestRedactionDotenvPrivateKey:
    def test_redaction_redacts_DOTENV_PRIVATE_KEY_vars(self) -> None:
        """DOTENV_PRIVATE_KEY_PRODUCTION (and any DOTENV_PRIVATE_KEY* variant) → '***'."""
        event_dict = {"DOTENV_PRIVATE_KEY_PRODUCTION": "ed25519abc123"}
        result = redact_sensitive(None, None, event_dict)
        assert (
            result["DOTENV_PRIVATE_KEY_PRODUCTION"] == "***"
        ), f"DOTENV_PRIVATE_KEY_PRODUCTION not redacted: {result['DOTENV_PRIVATE_KEY_PRODUCTION']!r}"


class TestRedactionPreservesUnrelated:
    def test_redaction_preserves_unrelated_keys(self) -> None:
        """run_id, market_id and other operational keys are untouched."""
        event_dict = {"run_id": "01JX...", "market_id": "ETH", "event": "order_placed"}
        result = redact_sensitive(None, None, event_dict)
        assert result["run_id"] == "01JX...", "run_id must not be redacted"
        assert result["market_id"] == "ETH", "market_id must not be redacted"
        assert result["event"] == "order_placed", "event must not be redacted"

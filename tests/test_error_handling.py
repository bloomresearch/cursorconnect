"""Tests for SDK error handling and the ``map_http_error`` factory.

Covers:

- ``map_http_error()`` mapping for every documented HTTP status class.
- ``AuthenticationError`` raised for 401 / 403 responses.
- ``RateLimitError`` raised for 429 responses.
- ``ConfigurationError`` raised for 400 responses.
- ``UnknownAgentError`` raised for 500+ and unknown status codes (e.g. 409).
- ``CursorAgentError`` raised when no API key is resolvable.
- ``UnsupportedRunOperationError`` raised when cancelling a terminal ``Run``.
- Exception attribute contracts (``is_retryable``, ``code``, ``cause``).
- Live round-trip: a bad API key triggers ``AuthenticationError`` from the
  real Cursor API (``@pytest.mark.slow``).

Notes
-----
All non-slow tests are pure unit tests; they do not hit any network endpoints.
"""

from __future__ import annotations

import pytest

from cursorconnect.exceptions import (
    AuthenticationError,
    ConfigurationError,
    CursorAgentError,
    NetworkError,
    RateLimitError,
    UnknownAgentError,
    UnsupportedRunOperationError,
    map_http_error,
)


# ---------------------------------------------------------------------------
# map_http_error()
# ---------------------------------------------------------------------------


class TestMapHttpError:
    """Unit tests for the ``map_http_error`` factory function."""

    def test_401_returns_authentication_error(self) -> None:
        """HTTP 401 maps to ``AuthenticationError``."""
        err = map_http_error(401, "Unauthorized")
        assert isinstance(err, AuthenticationError)

    def test_403_returns_authentication_error(self) -> None:
        """HTTP 403 maps to ``AuthenticationError``."""
        err = map_http_error(403, "Forbidden")
        assert isinstance(err, AuthenticationError)

    def test_401_is_not_retryable(self) -> None:
        """Authentication errors are not retryable."""
        err = map_http_error(401, "Unauthorized")
        assert err.is_retryable is False

    def test_429_returns_rate_limit_error(self) -> None:
        """HTTP 429 maps to ``RateLimitError``."""
        err = map_http_error(429, "Too Many Requests")
        assert isinstance(err, RateLimitError)

    def test_429_is_retryable(self) -> None:
        """Rate-limit errors are retryable."""
        err = map_http_error(429, "Too Many Requests")
        assert err.is_retryable is True

    def test_400_returns_configuration_error(self) -> None:
        """HTTP 400 maps to ``ConfigurationError``."""
        err = map_http_error(400, "Bad Request")
        assert isinstance(err, ConfigurationError)

    def test_400_is_not_retryable(self) -> None:
        """Configuration errors are not retryable."""
        err = map_http_error(400, "Bad Request")
        assert err.is_retryable is False

    def test_500_returns_unknown_agent_error(self) -> None:
        """HTTP 500 maps to ``UnknownAgentError``."""
        err = map_http_error(500, "Internal Server Error")
        assert isinstance(err, UnknownAgentError)

    def test_500_is_retryable(self) -> None:
        """Server errors are retryable."""
        err = map_http_error(500, "Internal Server Error")
        assert err.is_retryable is True

    def test_503_returns_unknown_agent_error(self) -> None:
        """HTTP 503 also maps to ``UnknownAgentError``."""
        err = map_http_error(503, "Service Unavailable")
        assert isinstance(err, UnknownAgentError)

    def test_409_returns_unknown_agent_error(self) -> None:
        """HTTP 409 (Conflict) falls through to ``UnknownAgentError`` (non-retryable)."""
        err = map_http_error(409, "Conflict")
        assert isinstance(err, UnknownAgentError)
        assert err.is_retryable is False

    def test_409_message_includes_status_code(self) -> None:
        """The 409 error message includes the HTTP status code for diagnostics."""
        err = map_http_error(409, "Conflict")
        assert "409" in str(err)

    def test_404_returns_unknown_agent_error(self) -> None:
        """HTTP 404 falls through to ``UnknownAgentError`` (non-retryable)."""
        err = map_http_error(404, "Not Found")
        assert isinstance(err, UnknownAgentError)

    def test_custom_code_preserved(self) -> None:
        """A custom ``code`` keyword argument is surfaced on the returned error."""
        err = map_http_error(400, "Bad Request", code="my_custom_code")
        assert err.code == "my_custom_code"

    def test_cause_preserved(self) -> None:
        """The ``cause`` keyword is preserved on the returned exception."""
        original = ValueError("original")
        err = map_http_error(500, "Server error", cause=original)
        assert err.cause is original

    def test_all_errors_inherit_cursor_agent_error(self) -> None:
        """Every variant of ``map_http_error`` returns a ``CursorAgentError`` subclass."""
        codes = [400, 401, 403, 404, 409, 429, 500, 503]
        for code in codes:
            err = map_http_error(code, "error")
            assert isinstance(err, CursorAgentError), f"HTTP {code} did not produce a CursorAgentError"


# ---------------------------------------------------------------------------
# Exception class contracts
# ---------------------------------------------------------------------------


class TestExceptionContracts:
    """Unit tests verifying attribute contracts on exception subclasses."""

    def test_cursor_agent_error_message(self) -> None:
        """``CursorAgentError.message`` stores the message string."""
        err = CursorAgentError("base error")
        assert err.message == "base error"

    def test_cursor_agent_error_is_retryable_default_false(self) -> None:
        """``CursorAgentError`` defaults to ``is_retryable=False``."""
        assert CursorAgentError("x").is_retryable is False

    def test_cursor_agent_error_code_default_none(self) -> None:
        """``CursorAgentError.code`` defaults to ``None``."""
        assert CursorAgentError("x").code is None

    def test_cursor_agent_error_cause_default_none(self) -> None:
        """``CursorAgentError.cause`` defaults to ``None``."""
        assert CursorAgentError("x").cause is None

    def test_cursor_agent_error_is_exception(self) -> None:
        """``CursorAgentError`` is a proper ``Exception`` subclass."""
        with pytest.raises(CursorAgentError):
            raise CursorAgentError("boom")

    def test_authentication_error_inherits(self) -> None:
        """``AuthenticationError`` is a ``CursorAgentError``."""
        assert issubclass(AuthenticationError, CursorAgentError)

    def test_rate_limit_error_default_retryable(self) -> None:
        """``RateLimitError`` defaults to ``is_retryable=True``."""
        assert RateLimitError("rate").is_retryable is True

    def test_rate_limit_error_default_code(self) -> None:
        """``RateLimitError`` sets ``code='rate_limit_exceeded'`` by default."""
        assert RateLimitError("rate").code == "rate_limit_exceeded"

    def test_network_error_default_retryable(self) -> None:
        """``NetworkError`` defaults to ``is_retryable=True``."""
        assert NetworkError("net").is_retryable is True

    def test_unsupported_run_operation_error_operation_attribute(self) -> None:
        """``UnsupportedRunOperationError`` exposes the attempted operation name."""
        err = UnsupportedRunOperationError("msg", operation="cancel")
        assert err.operation == "cancel"

    def test_unsupported_run_operation_error_not_retryable(self) -> None:
        """``UnsupportedRunOperationError`` is not retryable by default."""
        assert UnsupportedRunOperationError("msg", operation="cancel").is_retryable is False


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------


class TestMissingApiKey:
    """Tests for the 'no API key available' error path."""

    def test_agent_create_no_key_raises_cursor_agent_error(self, monkeypatch) -> None:
        """``Agent.create()`` raises ``CursorAgentError`` when key is absent from env."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        from cursorconnect import Agent

        with pytest.raises(CursorAgentError):
            Agent.create(api_key=None, prompt="test")  # type: ignore[arg-type]

    def test_cursor_me_no_key_raises(self, monkeypatch) -> None:
        """``Cursor.me()`` raises ``CursorAgentError`` when key is absent."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        from cursorconnect import Cursor

        with pytest.raises(CursorAgentError):
            Cursor.me(api_key=None)

    def test_cursor_client_empty_key_raises_value_error(self) -> None:
        """``CursorClient("")`` raises ``ValueError`` for an explicit empty string key."""
        import warnings

        from cursorconnect import CursorClient

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError):
                CursorClient("")


# ---------------------------------------------------------------------------
# Cancel on terminal run
# ---------------------------------------------------------------------------


class TestCancelTerminalRun:
    """Tests that cancelling a run in a terminal state raises correctly."""

    def test_cancel_finished_raises_unsupported(self, cursor_client) -> None:
        """Cancelling a ``FINISHED`` run raises ``UnsupportedRunOperationError``."""
        from cursorconnect import Run

        run = Run(cursor_client, "bc-test", {"id": "run-1", "status": "FINISHED"})
        run._status = "FINISHED"
        with pytest.raises(UnsupportedRunOperationError) as exc_info:
            run.cancel()
        assert exc_info.value.operation == "cancel"

    def test_cancel_expired_raises_unsupported(self, cursor_client) -> None:
        """Cancelling an ``EXPIRED`` run raises ``UnsupportedRunOperationError``."""
        from cursorconnect import Run

        run = Run(cursor_client, "bc-test", {"id": "run-1"})
        run._status = "EXPIRED"
        with pytest.raises(UnsupportedRunOperationError):
            run.cancel()


# ---------------------------------------------------------------------------
# HTTP error round-trip via CursorClient._request
# ---------------------------------------------------------------------------


class TestHttpErrorRoundTrip:
    """Tests that HTTP error responses propagate to the correct exception type."""

    def test_401_response_raises_authentication_error(
        self, mock_http, cursor_client
    ) -> None:
        """A 401 response from any endpoint raises ``AuthenticationError``."""
        mock_http(MockResponse({"error": "Unauthorized"}, status_code=401))
        with pytest.raises(AuthenticationError):
            cursor_client._get("/me")

    def test_429_response_raises_rate_limit_error(
        self, mock_http, cursor_client
    ) -> None:
        """A 429 response raises ``RateLimitError``."""
        mock_http(MockResponse({"error": "Too Many Requests"}, status_code=429))
        with pytest.raises(RateLimitError):
            cursor_client._get("/me")

    def test_400_response_raises_configuration_error(
        self, mock_http, cursor_client
    ) -> None:
        """A 400 response raises ``ConfigurationError``."""
        mock_http(MockResponse({"error": "Bad Request"}, status_code=400))
        with pytest.raises(ConfigurationError):
            cursor_client._post("/agents", json={"prompt": {}})

    def test_500_response_raises_unknown_agent_error(
        self, mock_http, cursor_client
    ) -> None:
        """A 500 response raises ``UnknownAgentError``."""
        mock_http(MockResponse({}, status_code=500))
        with pytest.raises(UnknownAgentError):
            cursor_client._get("/me")

    def test_409_response_raises_unknown_agent_error(
        self, mock_http, cursor_client
    ) -> None:
        """A 409 Conflict response raises ``UnknownAgentError`` (non-retryable)."""
        mock_http(MockResponse({"error": "Conflict"}, status_code=409))
        with pytest.raises(UnknownAgentError) as exc_info:
            cursor_client._post("/agents", json={})
        assert exc_info.value.is_retryable is False


# Import MockResponse for the HTTP round-trip tests above
from .conftest import MockResponse  # noqa: E402 (placed at end to avoid circular import issues)


# ---------------------------------------------------------------------------
# Live integration test
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bad_api_key_live_raises_authentication_error() -> None:
    """Live: a deliberately invalid API key causes the real API to return 401.

    Notes
    -----
    This test does not create an agent; it only calls ``Cursor.me()`` with a
    syntactically valid but incorrect key so the HTTP call reaches the server.
    """
    import warnings

    from cursorconnect import Cursor

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(AuthenticationError):
            Cursor.me(api_key="crsr_00000000000000000000000000000000000000000000000000000000000000000")

"""Shared pytest fixtures and helpers for the CursorConnect SDK test suite.

Notes
-----
This module is auto-discovered by pytest. It provides:

- `.env` loading at collection time (via ``python-dotenv`` when available, with
  a pure-Python fallback for environments that haven't installed the test extras).
- ``api_key``       – session-scoped; provides ``CURSOR_API_KEY``.  Skips the
  whole test when the variable is absent so the suite runs safely in bare CI.
- ``cursor_client`` – session-scoped authenticated ``CursorClient`` with the
  ``DeprecationWarning`` silenced.
- ``mock_http``     – function-scoped factory fixture; patches
  ``requests.Session.request`` to return caller-supplied ``MockResponse``
  objects in sequence.
- ``MockResponse``  – lightweight ``requests.Response`` stand-in exposed at
  module level so individual test modules can import it directly.
- ``suppress_deprecation``  – autouse fixture that silences the ``CursorClient``
  ``DeprecationWarning`` globally across the test run.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any, Dict, Iterator, List, Optional

import pytest


# ---------------------------------------------------------------------------
# Load .env before pytest collects anything
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, ".env")
    try:
        from dotenv import load_dotenv  # type: ignore[import]

        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        if not os.path.exists(env_path):
            return
        with open(env_path) as fh:
            for raw in fh:
                raw = raw.strip()
                if raw and not raw.startswith("#") and "=" in raw:
                    k, _, v = raw.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


# ---------------------------------------------------------------------------
# MockResponse helper
# ---------------------------------------------------------------------------
class MockResponse:
    """Lightweight stand-in for a ``requests.Response``.

    Parameters
    ----------
    json_data : dict, optional
        The JSON payload returned by ``.json()``.  Defaults to ``{}``.
    status_code : int, optional
        HTTP status code.  Defaults to ``200``.
    sse_lines : list of str, optional
        Raw SSE text lines returned by ``iter_lines()``.  Each blank string
        ``""`` acts as the SSE event-boundary separator.

    Attributes
    ----------
    status_code : int
    ok : bool
        ``True`` when ``status_code < 400``.
    content : bytes
        UTF-8 encoded JSON payload.
    text : str
        String-encoded JSON payload.
    """

    def __init__(
        self,
        json_data: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        sse_lines: Optional[List[str]] = None,
    ) -> None:
        self._json_data: Dict[str, Any] = json_data if json_data is not None else {}
        self.status_code = status_code
        self.ok = status_code < 400
        self.content = json.dumps(self._json_data).encode() if self._json_data else b""
        self.text = json.dumps(self._json_data) if self._json_data else ""
        self._sse_lines: List[str] = sse_lines if sse_lines is not None else []

    def json(self) -> Dict[str, Any]:  # noqa: D102
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise ``requests.HTTPError`` when ``status_code >= 400``."""
        if not self.ok:
            import requests

            raise requests.HTTPError(response=self)

    def iter_lines(self, decode_unicode: bool = False) -> Iterator[str]:  # noqa: D102, ARG002
        return iter(self._sse_lines)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_model() -> str:
    """Model ID used by live tests to avoid relying on the API's default."""
    return "gemini-3-flash"


@pytest.fixture(scope="session")
def api_key() -> str:
    """Provide ``CURSOR_API_KEY`` from the environment.

    Returns
    -------
    str
        The raw API-key string.

    Notes
    -----
    The entire dependent test is skipped automatically when the variable is
    absent, making it safe to run the fast unit tests in CI without any
    live credentials.
    """
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key:
        pytest.skip("CURSOR_API_KEY is not set; skipping live-credential test")
    return key


@pytest.fixture(scope="session")
def cursor_client(api_key: str):
    """Provide an authenticated ``CursorClient`` with ``DeprecationWarning`` muted.

    Parameters
    ----------
    api_key : str
        Injected by the ``api_key`` fixture.

    Returns
    -------
    CursorClient
        A ready-to-use (deprecated) shim client.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from cursorconnect import CursorClient

        return CursorClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def suppress_deprecation() -> Iterator[None]:
    """Autouse fixture that silences ``DeprecationWarning`` for all tests.

    ``Agent._make_client()`` internally creates a ``CursorClient``, which
    always emits a ``DeprecationWarning``.  Suppressing it globally keeps the
    test output clean while still allowing ``pytest.warns(DeprecationWarning)``
    calls to work in tests that explicitly opt in to capturing it (the
    ``catch_warnings`` context inside ``pytest.warns`` overrides this filter).

    Yields
    ------
    None
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


@pytest.fixture
def mock_http(monkeypatch):
    """Return a factory that patches ``requests.Session.request`` for unit tests.

    Usage
    -----
    >>> def test_something(mock_http, api_key):
    ...     mock_http(MockResponse({"email": "a@b.com"}))
    ...     user = Cursor.me(api_key=api_key)
    ...     assert user.email == "a@b.com"

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Injected by pytest.

    Returns
    -------
    Callable
        ``setup(*responses)`` — call with one or more ``MockResponse``
        objects; they are consumed in order for each outgoing HTTP request.
        After the sequence is exhausted, subsequent calls receive an empty
        ``200`` response.
    """

    def setup(*mock_responses: MockResponse) -> None:
        call_iter = iter(mock_responses)

        def _request(self_session, method: str, url: str, **kwargs: Any) -> MockResponse:  # noqa: ARG001
            try:
                return next(call_iter)
            except StopIteration:
                return MockResponse({}, 200)

        monkeypatch.setattr("requests.Session.request", _request)

    return setup

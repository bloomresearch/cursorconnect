"""Tests for the ``Cursor`` account-level namespace.

Covers ``Cursor.me()``, ``Cursor.models.list()``, and
``Cursor.repositories.list()``.  Unit tests mock the HTTP layer; integration
tests (``@pytest.mark.slow``) exercise the live Cursor API.

Notes
-----
All three methods internally construct a ``CursorClient``, which emits a
``DeprecationWarning``.  The ``suppress_deprecation`` autouse fixture in
``conftest.py`` keeps the output clean.
"""

from __future__ import annotations

import pytest

from cursorconnect import Cursor
from cursorconnect.exceptions import AuthenticationError, CursorAgentError
from cursorconnect.types import ModelListItem, SDKRepository, SDKUser

from .conftest import MockResponse


# ---------------------------------------------------------------------------
# Cursor.me()
# ---------------------------------------------------------------------------


class TestCursorMe:
    """Unit and integration tests for ``Cursor.me()``."""

    def test_me_returns_sdk_user_type(self, mock_http, api_key: str) -> None:
        """``Cursor.me()`` returns an ``SDKUser`` instance."""
        mock_http(MockResponse({"apiKeyName": "Test", "userEmail": "test@example.com", "createdAt": "2026-04-13T18:30:00.000Z"}))
        user = Cursor.me(api_key=api_key)
        assert isinstance(user, SDKUser)

    def test_me_api_key_name_populated(self, mock_http, api_key: str) -> None:
        """``SDKUser.api_key_name`` is correctly mapped from the API payload."""
        mock_http(MockResponse({"apiKeyName": "Production Key", "createdAt": "2026-04-13T18:30:00.000Z"}))
        user = Cursor.me(api_key=api_key)
        assert user.api_key_name == "Production Key"

    def test_me_created_at_populated(self, mock_http, api_key: str) -> None:
        """``SDKUser.created_at`` is correctly mapped from the API payload."""
        mock_http(MockResponse({"apiKeyName": "Test", "createdAt": "2026-04-13T18:30:00.000Z"}))
        user = Cursor.me(api_key=api_key)
        assert user.created_at == "2026-04-13T18:30:00.000Z"

    def test_me_user_email_populated(self, mock_http, api_key: str) -> None:
        """``SDKUser.user_email`` is mapped when present in the payload."""
        mock_http(MockResponse({"apiKeyName": "Test", "createdAt": "2026-04-13T18:30:00.000Z", "userEmail": "test@example.com"}))
        user = Cursor.me(api_key=api_key)
        assert user.user_email == "test@example.com"

    def test_me_optional_fields_default_to_none(self, mock_http, api_key: str) -> None:
        """``user_email`` defaults to ``None`` when absent from the payload."""
        mock_http(MockResponse({"apiKeyName": "Test", "createdAt": "2026-04-13T18:30:00.000Z"}))
        user = Cursor.me(api_key=api_key)
        assert user.user_email is None

    def test_me_missing_api_key_raises(self, monkeypatch) -> None:
        """``Cursor.me()`` raises ``CursorAgentError`` when no key is resolvable."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        with pytest.raises(CursorAgentError):
            Cursor.me(api_key=None)

    @pytest.mark.slow
    def test_me_live_returns_valid_fields(self, api_key: str) -> None:
        """Live: ``Cursor.me()`` returns a valid user for the real account."""
        user = Cursor.me(api_key=api_key)
        assert isinstance(user, SDKUser)
        assert user.api_key_name
        assert user.created_at


# ---------------------------------------------------------------------------
# Cursor.models.list()
# ---------------------------------------------------------------------------


class TestCursorModelsList:
    """Unit and integration tests for ``Cursor.models.list()``."""

    _MODELS_PAYLOAD = {
        "items": [
            {
                "id": "claude-sonnet-4-5",
                "displayName": "Claude Sonnet 4.5",
                "description": "Fast and capable",
                "parameters": [
                    {
                        "id": "thinking",
                        "displayName": "Thinking",
                        "values": [{"value": "enabled"}, {"value": "disabled"}],
                    }
                ],
                "variants": [
                    {"displayName": "Default", "isDefault": True}
                ],
            },
            {
                "id": "composer-2",
                "displayName": "Composer 2",
            },
        ]
    }

    def test_models_list_returns_list(self, mock_http, api_key: str) -> None:
        """``Cursor.models.list()`` returns a ``list``."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        result = Cursor.models.list(api_key=api_key)
        assert isinstance(result, list)

    def test_models_list_item_type(self, mock_http, api_key: str) -> None:
        """Each item in the list is a ``ModelListItem`` instance."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        items = Cursor.models.list(api_key=api_key)
        assert all(isinstance(m, ModelListItem) for m in items)

    def test_models_list_item_count(self, mock_http, api_key: str) -> None:
        """The list length matches the ``items`` array in the API response."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        items = Cursor.models.list(api_key=api_key)
        assert len(items) == 2

    def test_models_list_id_and_display_name(self, mock_http, api_key: str) -> None:
        """``ModelListItem.id`` and ``.displayName`` are populated correctly."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        items = Cursor.models.list(api_key=api_key)
        assert items[0].id == "claude-sonnet-4-5"
        assert items[0].displayName == "Claude Sonnet 4.5"

    def test_models_list_parameters_parsed(self, mock_http, api_key: str) -> None:
        """Parameter definitions are parsed into ``ModelParameterDefinition`` objects."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        items = Cursor.models.list(api_key=api_key)
        params = items[0].parameters
        assert params is not None and len(params) == 1
        assert params[0].id == "thinking"

    def test_models_list_variants_parsed(self, mock_http, api_key: str) -> None:
        """Variants are parsed into ``ModelVariant`` objects when present."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        items = Cursor.models.list(api_key=api_key)
        variants = items[0].variants
        assert variants is not None and len(variants) == 1
        assert variants[0].isDefault is True

    def test_models_list_empty_response(self, mock_http, api_key: str) -> None:
        """An empty ``items`` array produces an empty list without error."""
        mock_http(MockResponse({"items": []}))
        assert Cursor.models.list(api_key=api_key) == []

    def test_models_list_missing_api_key_raises(self, monkeypatch) -> None:
        """``Cursor.models.list()`` raises when no key can be resolved."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        with pytest.raises(CursorAgentError):
            Cursor.models.list(api_key=None)

    @pytest.mark.slow
    def test_models_list_live_non_empty(self, api_key: str) -> None:
        """Live: the models list is non-empty and all items have IDs."""
        items = Cursor.models.list(api_key=api_key)
        assert len(items) > 0
        assert all(m.id for m in items)


# ---------------------------------------------------------------------------
# Cursor.repositories.list()
# ---------------------------------------------------------------------------


class TestCursorRepositoriesList:
    """Unit and integration tests for ``Cursor.repositories.list()``.

    Notes
    -----
    The repositories endpoint is aggressively rate-limited (1 req/user/min,
    30 req/user/hr).  The live test is guarded by ``@pytest.mark.slow`` and
    should be run sparingly.
    """

    _REPOS_PAYLOAD = {
        "items": [
            {
                "url": "https://github.com/org/repo-a",
                "name": "org/repo-a",
                "description": "A demo repo",
                "isPrivate": False,
                "defaultBranch": "main",
            },
            {
                "url": "https://github.com/org/repo-b",
                "name": "org/repo-b",
                "isPrivate": True,
            },
        ]
    }

    def test_repositories_list_returns_list(self, mock_http, api_key: str) -> None:
        """``Cursor.repositories.list()`` returns a ``list``."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        result = Cursor.repositories.list(api_key=api_key)
        assert isinstance(result, list)

    def test_repositories_list_item_type(self, mock_http, api_key: str) -> None:
        """Each item is an ``SDKRepository`` instance."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        repos = Cursor.repositories.list(api_key=api_key)
        assert all(isinstance(r, SDKRepository) for r in repos)

    def test_repositories_list_url_populated(self, mock_http, api_key: str) -> None:
        """``SDKRepository.url`` is populated from the API payload."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        repos = Cursor.repositories.list(api_key=api_key)
        assert repos[0].url == "https://github.com/org/repo-a"

    def test_repositories_list_optional_fields(self, mock_http, api_key: str) -> None:
        """Optional fields (``name``, ``description``, etc.) map correctly."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        repos = Cursor.repositories.list(api_key=api_key)
        assert repos[0].name == "org/repo-a"
        assert repos[0].description == "A demo repo"
        assert repos[0].is_private is False
        assert repos[0].default_branch == "main"

    def test_repositories_list_absent_fields_are_none(self, mock_http, api_key: str) -> None:
        """Fields absent in the payload default to ``None``."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        repos = Cursor.repositories.list(api_key=api_key)
        assert repos[1].description is None
        assert repos[1].default_branch is None

    def test_repositories_list_empty_response(self, mock_http, api_key: str) -> None:
        """An empty ``items`` array produces an empty list without error."""
        mock_http(MockResponse({"items": []}))
        assert Cursor.repositories.list(api_key=api_key) == []

    def test_repositories_list_missing_api_key_raises(self, monkeypatch) -> None:
        """``Cursor.repositories.list()`` raises when no key can be resolved."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        with pytest.raises(CursorAgentError):
            Cursor.repositories.list(api_key=None)

    @pytest.mark.slow
    def test_repositories_list_live(self, api_key: str) -> None:
        """Live: repositories endpoint returns a list (may be empty for new accounts)."""
        repos = Cursor.repositories.list(api_key=api_key)
        assert isinstance(repos, list)
        for r in repos:
            assert isinstance(r, SDKRepository)
            assert r.url.startswith("https://")

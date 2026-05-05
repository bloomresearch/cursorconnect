"""Tests for the deprecated ``CursorClient`` compatibility shim.

Verifies that:

- Instantiating ``CursorClient`` always emits a ``DeprecationWarning``.
- ``CursorClient.list_models()`` returns a flat list of model ID strings.
- ``CursorClient.list_repositories()`` returns a flat list of URL strings.
- ``CursorClient.agents.create()`` returns an ``_AgentShimWrapper``.
- ``CursorClient.agents.get()`` returns an ``_AgentShimWrapper``.
- ``CursorClient.agents.list()`` returns a ``dict`` with ``items`` and
  ``nextCursor`` keys.
- The ``_AgentShimWrapper`` proxies ``agent_id``, ``status``, ``model``,
  ``name``, and ``delete()`` through to the underlying ``Agent``.
- ``_AgentShimWrapper.artifacts.list()`` delegates to ``Agent.list_artifacts()``.
- ``_AgentShimWrapper.runs.get()`` constructs a ``Run`` with the correct ID.

Notes
-----
``get_me()`` accesses ``user.api_key_name``, ``user.user_email``, and
``user.created_at`` on the returned ``SDKUser``, none of which are defined on
that dataclass.  This is a known shim implementation gap; the test documents
the failure mode explicitly.

All tests are unit tests unless decorated with ``@pytest.mark.slow``.
"""

from __future__ import annotations

import warnings

import pytest

from .conftest import MockResponse


# ---------------------------------------------------------------------------
# Helpers / shared payloads
# ---------------------------------------------------------------------------

_AGENT_PAYLOAD = {
    "agent": {
        "id": "bc-shim-001",
        "name": "shim-agent",
        "status": "ACTIVE",
        "model": {"id": "claude-sonnet-4-5"},
    },
    "latestRunId": "run-shim-001",
}

_AGENT_LIST_PAYLOAD = {
    "items": [
        {"id": "bc-shim-001", "name": "shim-agent", "status": "ACTIVE"},
    ],
    "nextCursor": None,
}


def _make_client(api_key: str):
    """Create a ``CursorClient`` with ``DeprecationWarning`` suppressed."""
    from cursorconnect import CursorClient

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return CursorClient(api_key=api_key)


# ---------------------------------------------------------------------------
# DeprecationWarning emission
# ---------------------------------------------------------------------------


class TestDeprecationWarning:
    """Verify that ``CursorClient.__init__`` always emits a ``DeprecationWarning``."""

    def test_init_emits_deprecation_warning(self, api_key: str) -> None:
        """Constructing ``CursorClient`` raises ``DeprecationWarning``."""
        from cursorconnect import CursorClient

        # pytest.warns overrides the autouse suppress_deprecation filter
        with pytest.warns(DeprecationWarning, match="CursorClient is deprecated"):
            CursorClient(api_key=api_key)

    def test_warning_mentions_agent_class(self, api_key: str) -> None:
        """The deprecation message recommends ``Agent`` as the replacement."""
        from cursorconnect import CursorClient

        with pytest.warns(DeprecationWarning, match="Agent"):
            CursorClient(api_key=api_key)

    def test_init_empty_key_raises_value_error(self) -> None:
        """An empty key string raises ``ValueError`` before the deprecation path."""
        from cursorconnect import CursorClient

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="API Key"):
                CursorClient("")


# ---------------------------------------------------------------------------
# CursorClient.list_models()
# ---------------------------------------------------------------------------


class TestListModels:
    """Unit tests for ``CursorClient.list_models()``."""

    _MODELS_PAYLOAD = {
        "items": [
            {"id": "claude-sonnet-4-5", "displayName": "Claude Sonnet 4.5"},
            {"id": "composer-2", "displayName": "Composer 2"},
        ]
    }

    def test_list_models_returns_list(self, mock_http, api_key: str) -> None:
        """``list_models()`` returns a ``list``."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_models()
        assert isinstance(result, list)

    def test_list_models_contains_strings(self, mock_http, api_key: str) -> None:
        """Each element in the returned list is a plain model-ID string."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_models()
        assert all(isinstance(m, str) for m in result)

    def test_list_models_ids_correct(self, mock_http, api_key: str) -> None:
        """The IDs match ``ModelListItem.id`` from the API payload."""
        mock_http(MockResponse(self._MODELS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_models()
        assert result == ["claude-sonnet-4-5", "composer-2"]

    def test_list_models_empty(self, mock_http, api_key: str) -> None:
        """An empty models list is returned without error."""
        mock_http(MockResponse({"items": []}))
        client = _make_client(api_key)
        assert client.list_models() == []

    @pytest.mark.slow
    def test_list_models_live(self, api_key: str) -> None:
        """Live: ``list_models()`` returns non-empty list of ID strings."""
        client = _make_client(api_key)
        models = client.list_models()
        assert len(models) > 0
        assert all(isinstance(m, str) for m in models)


# ---------------------------------------------------------------------------
# CursorClient.list_repositories()
# ---------------------------------------------------------------------------


class TestListRepositories:
    """Unit tests for ``CursorClient.list_repositories()``."""

    _REPOS_PAYLOAD = {
        "items": [
            {"url": "https://github.com/org/repo-a", "name": "org/repo-a"},
            {"url": "https://github.com/org/repo-b", "name": "org/repo-b"},
        ]
    }

    def test_list_repositories_returns_list(self, mock_http, api_key: str) -> None:
        """``list_repositories()`` returns a ``list``."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_repositories()
        assert isinstance(result, list)

    def test_list_repositories_contains_url_strings(self, mock_http, api_key: str) -> None:
        """Each element is a repository URL string."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_repositories()
        assert all(isinstance(u, str) for u in result)
        assert all(u.startswith("https://") for u in result)

    def test_list_repositories_urls_correct(self, mock_http, api_key: str) -> None:
        """The URL list matches the ``url`` fields in the API payload."""
        mock_http(MockResponse(self._REPOS_PAYLOAD))
        client = _make_client(api_key)
        result = client.list_repositories()
        assert result == [
            "https://github.com/org/repo-a",
            "https://github.com/org/repo-b",
        ]

    def test_list_repositories_empty(self, mock_http, api_key: str) -> None:
        """An empty repositories response returns an empty list."""
        mock_http(MockResponse({"items": []}))
        client = _make_client(api_key)
        assert client.list_repositories() == []


# ---------------------------------------------------------------------------
# CursorClient.get_me()
# ---------------------------------------------------------------------------


class TestGetMe:
    """Unit tests for ``CursorClient.get_me()``."""

    def test_get_me_returns_mapped_dict(
        self, mock_http, api_key: str
    ) -> None:
        """``get_me()`` returns a dictionary mapped correctly from the SDKUser fields."""
        mock_http(
            MockResponse({"apiKeyName": "Test Key", "userEmail": "test@example.com", "createdAt": "2026-04-13T18:30:00.000Z"})
        )
        client = _make_client(api_key)
        res = client.get_me()
        assert res["apiKeyName"] == "Test Key"
        assert res["userEmail"] == "test@example.com"
        assert res["createdAt"] == "2026-04-13T18:30:00.000Z"


# ---------------------------------------------------------------------------
# _AgentManagerShim.create()
# ---------------------------------------------------------------------------


class TestAgentManagerCreate:
    """Unit tests for ``CursorClient.agents.create()``."""

    def test_agents_create_returns_shim_wrapper(self, mock_http, api_key: str) -> None:
        """``agents.create()`` returns an ``_AgentShimWrapper``."""
        from cursorconnect.client import _AgentShimWrapper

        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.create(
            prompt_text="Hello",
            repo_url="https://github.com/org/repo",
        )
        assert isinstance(wrapper, _AgentShimWrapper)

    def test_agents_create_wrapper_has_agent_id(self, mock_http, api_key: str) -> None:
        """The returned wrapper exposes ``agent_id`` from the underlying ``Agent``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.create(
            prompt_text="Hello",
            repo_url="https://github.com/org/repo",
        )
        assert wrapper.agent_id == "bc-shim-001"

    def test_agents_create_with_model_id(self, mock_http, api_key: str) -> None:
        """``model_id`` is forwarded to ``Agent.create()`` as a ``ModelSelection``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.create(
            prompt_text="Hello",
            repo_url="https://github.com/org/repo",
            model_id="claude-sonnet-4-5",
        )
        assert wrapper.agent_id is not None


# ---------------------------------------------------------------------------
# _AgentManagerShim.get()
# ---------------------------------------------------------------------------


class TestAgentManagerGet:
    """Unit tests for ``CursorClient.agents.get()``."""

    def test_agents_get_returns_shim_wrapper(self, mock_http, api_key: str) -> None:
        """``agents.get(agent_id)`` returns an ``_AgentShimWrapper``."""
        from cursorconnect.client import _AgentShimWrapper

        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        assert isinstance(wrapper, _AgentShimWrapper)

    def test_agents_get_agent_id_matches(self, mock_http, api_key: str) -> None:
        """The wrapper's ``agent_id`` matches the one passed to ``get()``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        assert wrapper.agent_id == "bc-shim-001"


# ---------------------------------------------------------------------------
# _AgentManagerShim.list()
# ---------------------------------------------------------------------------


class TestAgentManagerList:
    """Unit tests for ``CursorClient.agents.list()``."""

    def test_agents_list_returns_dict(self, mock_http, api_key: str) -> None:
        """``agents.list()`` returns a ``dict`` with ``items`` and ``nextCursor`` keys."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        client = _make_client(api_key)
        result = client.agents.list()
        assert isinstance(result, dict)
        assert "items" in result
        assert "nextCursor" in result

    def test_agents_list_items_are_wrappers(self, mock_http, api_key: str) -> None:
        """Each entry in ``result['items']`` is an ``_AgentShimWrapper``."""
        from cursorconnect.client import _AgentShimWrapper

        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        client = _make_client(api_key)
        result = client.agents.list()
        assert all(isinstance(a, _AgentShimWrapper) for a in result["items"])

    def test_agents_list_item_count(self, mock_http, api_key: str) -> None:
        """The item count matches the API payload."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        client = _make_client(api_key)
        result = client.agents.list()
        assert len(result["items"]) == 1


# ---------------------------------------------------------------------------
# _AgentShimWrapper attribute proxy
# ---------------------------------------------------------------------------


class TestAgentShimWrapperProxy:
    """Unit tests verifying that ``_AgentShimWrapper`` proxies to the inner ``Agent``."""

    def test_wrapper_proxies_status(self, mock_http, api_key: str) -> None:
        """``wrapper.status`` returns the underlying agent's status."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        assert wrapper.status == "ACTIVE"

    def test_wrapper_proxies_name(self, mock_http, api_key: str) -> None:
        """``wrapper.name`` returns the underlying agent's name."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        assert wrapper.name == "shim-agent"

    def test_wrapper_delete_delegates(self, mock_http, api_key: str) -> None:
        """``wrapper.delete()`` calls the underlying ``Agent.delete()`` without error."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({}))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        wrapper.delete()  # should not raise

    def test_wrapper_artifacts_list_delegates(self, mock_http, api_key: str) -> None:
        """``wrapper.artifacts.list()`` delegates to ``Agent.list_artifacts()``."""
        artifacts_payload = {
            "items": [
                {"path": "out.py", "sizeBytes": 100, "updatedAt": "2024-01-01T00:00:00Z"}
            ]
        }
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(artifacts_payload))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        arts = wrapper.artifacts.list()
        assert isinstance(arts, list)
        assert len(arts) == 1

    def test_wrapper_runs_get_returns_run(self, mock_http, api_key: str) -> None:
        """``wrapper.runs.get(run_id)`` returns a ``RunProtocol`` with the correct ID."""
        from cursorconnect import RunProtocol

        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        run = wrapper.runs.get("run-shim-001")
        assert isinstance(run, RunProtocol)
        assert run.id == "run-shim-001"

    def test_wrapper_repr_delegates_to_agent(self, mock_http, api_key: str) -> None:
        """``repr(wrapper)`` returns the same string as ``repr(agent)``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        assert "bc-shim-001" in repr(wrapper)

    def test_wrapper_proxies_unknown_attribute_to_agent(
        self, mock_http, api_key: str
    ) -> None:
        """Attribute access for any agent field not overridden falls through to ``Agent``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        client = _make_client(api_key)
        wrapper = client.agents.get("bc-shim-001")
        # _latest_run_id is on Agent, not on the shim itself
        assert wrapper._latest_run_id == "run-shim-001"

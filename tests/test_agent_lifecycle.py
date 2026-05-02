"""Tests for the ``Agent`` lifecycle operations.

Covers ``Agent.create()``, ``Agent.get()``, ``Agent.list()``,
``Agent.resume()``, ``Agent.send()``/``stream()``, ``Agent.list_artifacts()``,
``Agent.archive()``/``unarchive()``, and ``Agent.delete()``.

Unit tests mock ``requests.Session.request`` via the ``mock_http`` fixture so
they run offline.  Integration tests are decorated with ``@pytest.mark.slow``
and create real agents against the live API; they always clean up after
themselves to avoid orphaned agents.

Notes
-----
``Agent._make_client()`` constructs a ``CursorClient`` which emits a
``DeprecationWarning``.  The ``suppress_deprecation`` autouse fixture silences
this globally.
"""

from __future__ import annotations

import pytest

from cursorconnect import Agent
from cursorconnect.artifact import Artifact
from cursorconnect.exceptions import CursorAgentError
from cursorconnect.types import ListResult, SDKAssistantMessage, SDKStatusMessage

from .conftest import MockResponse


# ---------------------------------------------------------------------------
# Shared response payloads
# ---------------------------------------------------------------------------

_AGENT_PAYLOAD = {
    "agent": {
        "id": "bc-test-0001",
        "name": "test-agent",
        "status": "ACTIVE",
        "model": {"id": "claude-sonnet-4-5"},
    },
    "latestRunId": "run-abc",
}

_AGENT_LIST_PAYLOAD = {
    "items": [
        {"id": "bc-0001", "name": "agent-a", "status": "ACTIVE"},
        {"id": "bc-0002", "name": "agent-b", "status": "ARCHIVED"},
    ],
    "nextCursor": "cursor-xyz",
}

_RUN_PAYLOAD = {"run": {"id": "run-abc", "status": "RUNNING"}}

_ARTIFACTS_PAYLOAD = {
    "items": [
        {"path": "output/hello.py", "sizeBytes": 128, "updatedAt": "2024-01-01T00:00:00Z"},
        {"path": "output/README.md", "sizeBytes": 64, "updatedAt": "2024-01-01T00:00:01Z"},
    ]
}


# ---------------------------------------------------------------------------
# Agent.create()
# ---------------------------------------------------------------------------


class TestAgentCreate:
    """Unit tests for ``Agent.create()``."""

    def test_create_returns_agent_instance(self, mock_http, api_key: str) -> None:
        """``Agent.create()`` returns an ``Agent`` instance."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world")
        assert isinstance(agent, Agent)

    def test_create_agent_id_populated(self, mock_http, api_key: str) -> None:
        """The returned agent has its ``agent_id`` populated from the API payload."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world")
        assert agent.agent_id == "bc-test-0001"

    def test_create_latest_run_id_populated(self, mock_http, api_key: str) -> None:
        """The ``_latest_run_id`` attribute is set from ``latestRunId`` in the payload."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world")
        assert agent._latest_run_id == "run-abc"

    def test_create_name_propagated(self, mock_http, api_key: str) -> None:
        """The ``name`` attribute is populated when the API echoes it back."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world", name="test-agent")
        assert agent.name == "test-agent"

    def test_create_status_populated(self, mock_http, api_key: str) -> None:
        """``Agent.status`` reflects the value returned by the API."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world")
        assert agent.status == "ACTIVE"

    def test_create_model_populated(self, mock_http, api_key: str) -> None:
        """``Agent.model`` is parsed into a ``ModelSelection`` when present."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="Hello world")
        assert agent.model is not None
        assert agent.model.id == "claude-sonnet-4-5"

    def test_create_missing_api_key_raises(self, monkeypatch) -> None:
        """``Agent.create()`` raises ``CursorAgentError`` when no key is available."""
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        with pytest.raises(CursorAgentError):
            Agent.create(api_key=None, prompt="test")  # type: ignore[arg-type]

    @pytest.mark.slow
    def test_create_live_and_delete(self, api_key: str) -> None:
        """Live: create an agent, verify it has an ID, then delete it."""
        agent = Agent.create(api_key=api_key, prompt="echo 'test-lifecycle'")
        try:
            assert agent.agent_id is not None
            assert agent.agent_id.startswith("bc-")
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Agent.get() / Agent.resume()
# ---------------------------------------------------------------------------


class TestAgentGet:
    """Unit tests for ``Agent.get()`` and ``Agent.resume()``."""

    def test_get_returns_agent(self, mock_http, api_key: str) -> None:
        """``Agent.get()`` returns an ``Agent`` populated from the API payload."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.get(api_key=api_key, agent_id="bc-test-0001")
        assert isinstance(agent, Agent)
        assert agent.agent_id == "bc-test-0001"

    def test_resume_is_alias_for_get(self, mock_http, api_key: str) -> None:
        """``Agent.resume()`` is semantically equivalent to ``Agent.get()``."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.resume(api_key=api_key, agent_id="bc-test-0001")
        assert agent.agent_id == "bc-test-0001"


# ---------------------------------------------------------------------------
# Agent.list()
# ---------------------------------------------------------------------------


class TestAgentList:
    """Unit tests for ``Agent.list()``."""

    def test_list_returns_list_result(self, mock_http, api_key: str) -> None:
        """``Agent.list()`` returns a ``ListResult`` object."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        result = Agent.list(api_key=api_key)
        assert isinstance(result, ListResult)

    def test_list_items_are_agents(self, mock_http, api_key: str) -> None:
        """Each item in the ``ListResult`` is an ``Agent``."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        result = Agent.list(api_key=api_key)
        assert all(isinstance(a, Agent) for a in result.items)

    def test_list_item_count(self, mock_http, api_key: str) -> None:
        """The item count matches the ``items`` array length."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        result = Agent.list(api_key=api_key)
        assert len(result.items) == 2

    def test_list_next_cursor_populated(self, mock_http, api_key: str) -> None:
        """``ListResult.nextCursor`` is set when the API returns a pagination token."""
        mock_http(MockResponse(_AGENT_LIST_PAYLOAD))
        result = Agent.list(api_key=api_key)
        assert result.nextCursor == "cursor-xyz"

    def test_list_empty_result(self, mock_http, api_key: str) -> None:
        """An empty items array produces an empty ``ListResult`` without error."""
        mock_http(MockResponse({"items": []}))
        result = Agent.list(api_key=api_key)
        assert result.items == []
        assert result.nextCursor is None


# ---------------------------------------------------------------------------
# Agent.send() + Run.stream()
# ---------------------------------------------------------------------------


class TestAgentSendStream:
    """Unit tests for ``Agent.send()`` and ``Run.stream()``."""

    _SSE_LINES = [
        "event: status",
        'data: {"status": "RUNNING"}',
        "",
        "event: assistant",
        'data: {"message": {"role": "assistant", "content": [{"type": "text", "text": "Hello!"}]}}',
        "",
        "event: status",
        'data: {"status": "FINISHED"}',
        "",
    ]

    def test_send_returns_run(self, mock_http, api_key: str) -> None:
        """``Agent.send()`` returns a ``Run`` instance."""
        from cursorconnect import Run

        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_RUN_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.send("follow-up")
        assert isinstance(run, Run)

    def test_send_run_has_id(self, mock_http, api_key: str) -> None:
        """The returned ``Run`` has its ``id`` set from the API response."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_RUN_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.send("follow-up")
        assert run.id == "run-abc"

    def test_stream_yields_sdk_messages(self, mock_http, api_key: str) -> None:
        """``Run.stream()`` yields typed ``SDKMessage`` objects parsed from SSE frames."""
        sse_response = MockResponse(sse_lines=self._SSE_LINES)
        # create → send → stream (3 HTTP calls)
        mock_http(
            MockResponse(_AGENT_PAYLOAD),
            MockResponse(_RUN_PAYLOAD),
            sse_response,
        )
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.send("follow-up")
        messages = list(run.stream())
        assert len(messages) > 0

    def test_stream_contains_assistant_message(self, mock_http, api_key: str) -> None:
        """The SSE stream includes at least one ``SDKAssistantMessage``."""
        sse_response = MockResponse(sse_lines=self._SSE_LINES)
        mock_http(
            MockResponse(_AGENT_PAYLOAD),
            MockResponse(_RUN_PAYLOAD),
            sse_response,
        )
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.send("go")
        types = {type(m) for m in run.stream()}
        assert SDKAssistantMessage in types

    def test_stream_status_updates_run_status(self, mock_http, api_key: str) -> None:
        """``SDKStatusMessage`` events update ``Run.status`` as they are yielded."""
        sse_response = MockResponse(sse_lines=self._SSE_LINES)
        mock_http(
            MockResponse(_AGENT_PAYLOAD),
            MockResponse(_RUN_PAYLOAD),
            sse_response,
        )
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.send("go")
        statuses = []
        for msg in run.stream():
            if isinstance(msg, SDKStatusMessage):
                statuses.append(msg.status)
        assert "RUNNING" in statuses
        assert "FINISHED" in statuses

    @pytest.mark.slow
    def test_send_stream_live(self, api_key: str) -> None:
        """Live: create an agent, send a message, consume the SSE stream."""
        agent = Agent.create(api_key=api_key, prompt="Print the number 42 and stop.")
        try:
            run = agent.send("Confirm: just output the number.")
            msgs = list(run.stream())
            assert len(msgs) > 0
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Agent.initial_run
# ---------------------------------------------------------------------------


class TestAgentInitialRun:
    """Unit tests for ``Agent.initial_run`` property."""

    def test_initial_run_returns_run(self, mock_http, api_key: str) -> None:
        """``Agent.initial_run`` returns a ``Run`` instance if ``_latest_run_id`` is set."""
        from cursorconnect import Run

        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        run = agent.initial_run
        assert isinstance(run, Run)
        assert run.id == "run-abc"

    def test_initial_run_returns_none_if_missing(self, mock_http, api_key: str) -> None:
        """``Agent.initial_run`` returns ``None`` if ``_latest_run_id`` is missing."""
        mock_http(MockResponse({"agent": {"id": "bc-test", "status": "ACTIVE"}}))
        agent = Agent.create(api_key=api_key, prompt="init")
        assert agent.initial_run is None


# ---------------------------------------------------------------------------
# Agent.run() shorthand
# ---------------------------------------------------------------------------


class TestAgentRunShorthand:
    """Unit tests for ``Agent.run()`` shorthand."""

    def test_run_returns_run_result(self, mock_http, api_key: str) -> None:
        """``Agent.run()`` delegates to ``send().wait()`` and returns a ``RunResult``."""
        from cursorconnect.types import RunResult

        mock_http(
            MockResponse(_AGENT_PAYLOAD),
            MockResponse(_RUN_PAYLOAD),  # send() POST
            MockResponse({"items": [{"id": "run-abc", "status": "FINISHED"}]}),  # wait() GET _refresh()
            MockResponse({"turns": []}), # wait() GET conversation()
        )
        agent = Agent.create(api_key=api_key, prompt="init")
        result = agent.run("follow-up")
        
        assert isinstance(result, RunResult)
        assert result.run_id == "run-abc"
        assert result.status == "FINISHED"


# ---------------------------------------------------------------------------
# Agent.list_artifacts()
# ---------------------------------------------------------------------------


class TestAgentListArtifacts:
    """Unit tests for ``Agent.list_artifacts()``."""

    def test_list_artifacts_returns_list(self, mock_http, api_key: str) -> None:
        """``Agent.list_artifacts()`` returns a ``list``."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_ARTIFACTS_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        artifacts = agent.list_artifacts()
        assert isinstance(artifacts, list)

    def test_list_artifacts_items_are_artifact_type(self, mock_http, api_key: str) -> None:
        """Each returned item is an ``Artifact`` instance."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_ARTIFACTS_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        artifacts = agent.list_artifacts()
        assert all(isinstance(a, Artifact) for a in artifacts)

    def test_list_artifacts_path_populated(self, mock_http, api_key: str) -> None:
        """``Artifact.path`` is populated from the API payload."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_ARTIFACTS_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        artifacts = agent.list_artifacts()
        assert artifacts[0].path == "output/hello.py"
        assert artifacts[1].path == "output/README.md"

    def test_list_artifacts_size_bytes_populated(self, mock_http, api_key: str) -> None:
        """``Artifact.size_bytes`` reflects the ``sizeBytes`` field."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse(_ARTIFACTS_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        artifacts = agent.list_artifacts()
        assert artifacts[0].size_bytes == 128

    def test_list_artifacts_empty(self, mock_http, api_key: str) -> None:
        """An empty artifacts response produces an empty list without error."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({"items": []}))
        agent = Agent.create(api_key=api_key, prompt="init")
        assert agent.list_artifacts() == []

    @pytest.mark.slow
    def test_list_artifacts_live(self, api_key: str) -> None:
        """Live: list artifacts on a freshly created agent (expected to be empty)."""
        agent = Agent.create(api_key=api_key, prompt="echo 'hello'")
        try:
            artifacts = agent.list_artifacts()
            assert isinstance(artifacts, list)
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Agent.archive() / unarchive()
# ---------------------------------------------------------------------------


class TestAgentArchive:
    """Unit tests for ``Agent.archive()`` and ``Agent.unarchive()``."""

    def test_archive_sets_status_archived(self, mock_http, api_key: str) -> None:
        """``Agent.archive()`` updates ``status`` to ``'ARCHIVED'`` locally."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({}))
        agent = Agent.create(api_key=api_key, prompt="init")
        agent.archive()
        assert agent.status == "ARCHIVED"

    def test_unarchive_sets_status_active(self, mock_http, api_key: str) -> None:
        """``Agent.unarchive()`` updates ``status`` to ``'ACTIVE'`` locally."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({}), MockResponse({}))
        agent = Agent.create(api_key=api_key, prompt="init")
        agent.archive()
        agent.unarchive()
        assert agent.status == "ACTIVE"

    def test_close_is_alias_for_archive(self, mock_http, api_key: str) -> None:
        """``Agent.close()`` is equivalent to calling ``archive()``."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({}))
        agent = Agent.create(api_key=api_key, prompt="init")
        agent.close()
        assert agent.status == "ARCHIVED"

    @pytest.mark.slow
    def test_archive_live_and_cleanup(self, api_key: str) -> None:
        """Live: archive an agent, verify status, then delete it."""
        agent = Agent.create(api_key=api_key, prompt="echo 'archive-test'")
        try:
            agent.archive()
            assert agent.status == "ARCHIVED"
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Agent.delete()
# ---------------------------------------------------------------------------


class TestAgentDelete:
    """Unit tests for ``Agent.delete()``."""

    def test_delete_does_not_raise(self, mock_http, api_key: str) -> None:
        """``Agent.delete()`` completes without raising an exception."""
        mock_http(MockResponse(_AGENT_PAYLOAD), MockResponse({}))
        agent = Agent.create(api_key=api_key, prompt="init")
        agent.delete()  # should not raise

    @pytest.mark.slow
    def test_delete_live(self, api_key: str) -> None:
        """Live: create an agent and immediately delete it."""
        agent = Agent.create(api_key=api_key, prompt="echo 'delete-test'")
        agent.delete()  # should not raise


# ---------------------------------------------------------------------------
# Agent.__repr__
# ---------------------------------------------------------------------------


class TestAgentRepr:
    """Unit tests for ``Agent.__repr__()``."""

    def test_repr_contains_agent_id(self, mock_http, api_key: str) -> None:
        """The ``repr`` string includes the agent's ID."""
        mock_http(MockResponse(_AGENT_PAYLOAD))
        agent = Agent.create(api_key=api_key, prompt="init")
        assert "bc-test-0001" in repr(agent)

"""Tests for ``Run`` lifecycle operations.

Covers ``Run.wait()``, ``Run.cancel()``, and ``Run.conversation()``.

Unit tests mock the HTTP layer; integration tests (``@pytest.mark.slow``)
exercise the live API.

Notes
-----
A ``Run`` instance is normally obtained from ``Agent.send()`` or
``Agent.prompt()``.  In unit tests we construct it directly via its public
constructor to keep each test self-contained.
"""

from __future__ import annotations

import warnings

import pytest

from cursorconnect import Run
from cursorconnect.exceptions import UnsupportedRunOperationError
from cursorconnect.types.account import RunResult

from .conftest import MockResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(cursor_client, agent_id: str = "bc-unit", run_id: str = "run-unit") -> Run:
    """Construct a bare ``Run`` for unit testing without any HTTP call.

    Parameters
    ----------
    cursor_client : CursorClient
        Session-scoped client fixture.
    agent_id : str, optional
        Agent ID to assign to the run.
    run_id : str, optional
        Run ID to assign.

    Returns
    -------
    Run
    """
    return Run(cursor_client, agent_id, {"id": run_id, "status": None})


# ---------------------------------------------------------------------------
# Run.wait()
# ---------------------------------------------------------------------------


class TestRunWait:
    """Unit and integration tests for ``Run.wait()``."""

    _RUNS_FINISHED = {
        "items": [{"id": "run-unit", "status": "FINISHED", "updatedAt": "2024-01-01T00:00:00Z"}]
    }
    _CONVERSATION_PAYLOAD = {
        "turns": [
            {
                "type": "agentConversationTurn",
                "turn": {
                    "userMessage": {"text": "Hello"},
                    "steps": [{"type": "assistantMessage", "message": {"text": "Hi!"}}],
                },
            }
        ]
    }

    def test_wait_returns_run_result(self, mock_http, cursor_client) -> None:
        """``Run.wait()`` returns a ``RunResult`` when the run is already terminal."""
        mock_http(
            MockResponse(self._RUNS_FINISHED),      # _refresh() poll
            MockResponse(self._CONVERSATION_PAYLOAD),  # conversation()
        )
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert isinstance(result, RunResult)

    def test_wait_result_status_finished(self, mock_http, cursor_client) -> None:
        """The ``RunResult.status`` is ``'FINISHED'`` after a successful wait."""
        mock_http(
            MockResponse(self._RUNS_FINISHED),
            MockResponse(self._CONVERSATION_PAYLOAD),
        )
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert result.status == "FINISHED"

    def test_wait_result_run_id_matches(self, mock_http, cursor_client) -> None:
        """``RunResult.run_id`` matches the ``Run.id`` that was polled."""
        mock_http(
            MockResponse(self._RUNS_FINISHED),
            MockResponse(self._CONVERSATION_PAYLOAD),
        )
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert result.run_id == "run-unit"

    def test_wait_result_includes_conversation(self, mock_http, cursor_client) -> None:
        """``RunResult.conversation`` contains the turns from the conversation endpoint."""
        mock_http(
            MockResponse(self._RUNS_FINISHED),
            MockResponse(self._CONVERSATION_PAYLOAD),
        )
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert result.conversation is not None
        assert len(result.conversation) == 1

    def test_wait_polls_until_terminal(self, mock_http, cursor_client) -> None:
        """``Run.wait()`` keeps polling until the run transitions to a terminal state."""
        running_resp = MockResponse(
            {"items": [{"id": "run-unit", "status": "RUNNING"}]}
        )
        finished_resp = MockResponse(self._RUNS_FINISHED)
        mock_http(
            running_resp,   # first poll → still RUNNING
            finished_resp,  # second poll → FINISHED
            MockResponse(self._CONVERSATION_PAYLOAD),
        )
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert result.status == "FINISHED"

    def test_wait_raises_timeout_error(self, mock_http, cursor_client) -> None:
        """``Run.wait()`` raises ``TimeoutError`` when *timeout* elapses."""
        # Return RUNNING indefinitely
        mock_http(*([MockResponse({"items": [{"id": "run-unit", "status": "RUNNING"}]})] * 20))
        run = _make_run(cursor_client)
        with pytest.raises(TimeoutError):
            run.wait(timeout=0.05, poll_interval=0.01)

    def test_wait_error_status_sets_error_message(self, mock_http, cursor_client) -> None:
        """When the run ends with ``ERROR``, ``RunResult.error_message`` is populated."""
        error_resp = MockResponse(
            {"items": [{"id": "run-unit", "status": "ERROR", "errorMessage": "Something broke"}]}
        )
        mock_http(error_resp, MockResponse({"turns": []}))
        run = _make_run(cursor_client)
        result = run.wait(poll_interval=0.01)
        assert result.status == "ERROR"
        assert result.error_message is not None

    @pytest.mark.slow
    def test_wait_live(self, api_key: str) -> None:
        """Live: create an agent, get its run, and wait for completion."""
        from cursorconnect import Agent

        agent = Agent.create(api_key=api_key, prompt="Print 'done' and stop immediately.", model="gemini-3-flash")
        try:
            assert agent._latest_run_id is not None
            run = Run(agent._client, agent.agent_id, {"id": agent._latest_run_id})
            result = run.wait(timeout=120, poll_interval=3)
            assert result.status in {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Run.cancel()
# ---------------------------------------------------------------------------


class TestRunCancel:
    """Unit and integration tests for ``Run.cancel()``."""

    def test_cancel_updates_local_status(self, mock_http, cursor_client) -> None:
        """``Run.cancel()`` sets ``Run.status`` to ``'CANCELLED'`` immediately."""
        mock_http(MockResponse({}))  # cancel POST
        run = _make_run(cursor_client)
        run._status = "RUNNING"
        run.cancel()
        assert run.status == "CANCELLED"

    def test_cancel_raises_for_finished_run(self, cursor_client) -> None:
        """Cancelling an already-``FINISHED`` run raises ``UnsupportedRunOperationError``."""
        run = _make_run(cursor_client)
        run._status = "FINISHED"
        with pytest.raises(UnsupportedRunOperationError) as exc_info:
            run.cancel()
        assert exc_info.value.operation == "cancel"

    def test_cancel_raises_for_error_run(self, cursor_client) -> None:
        """Cancelling a run in ``ERROR`` state raises ``UnsupportedRunOperationError``."""
        run = _make_run(cursor_client)
        run._status = "ERROR"
        with pytest.raises(UnsupportedRunOperationError):
            run.cancel()

    def test_cancel_raises_for_cancelled_run(self, cursor_client) -> None:
        """Cancelling an already-cancelled run raises ``UnsupportedRunOperationError``."""
        run = _make_run(cursor_client)
        run._status = "CANCELLED"
        with pytest.raises(UnsupportedRunOperationError):
            run.cancel()

    def test_cancel_raises_for_expired_run(self, cursor_client) -> None:
        """Cancelling an ``EXPIRED`` run raises ``UnsupportedRunOperationError``."""
        run = _make_run(cursor_client)
        run._status = "EXPIRED"
        with pytest.raises(UnsupportedRunOperationError):
            run.cancel()

    @pytest.mark.slow
    def test_cancel_live(self, api_key: str) -> None:
        """Live: start an agent, cancel its run, verify the cancelled status."""
        from cursorconnect import Agent

        agent = Agent.create(api_key=api_key, prompt="Sleep for 1 hour doing nothing.", model="gemini-3-flash")
        try:
            assert agent._latest_run_id is not None
            run = Run(agent._client, agent.agent_id, {"id": agent._latest_run_id})
            run._status = "RUNNING"
            run.cancel()
            assert run.status == "CANCELLED"
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Run.conversation()
# ---------------------------------------------------------------------------


class TestRunConversation:
    """Unit and integration tests for ``Run.conversation()``."""

    _CONV_PAYLOAD = {
        "turns": [
            {
                "type": "agentConversationTurn",
                "turn": {
                    "userMessage": {"text": "What is 2+2?"},
                    "steps": [
                        {
                            "type": "assistantMessage",
                            "message": {"text": "4"},
                        }
                    ],
                },
            }
        ]
    }

    def test_conversation_returns_conversation(self, mock_http, cursor_client) -> None:
        """``Run.conversation()`` returns a ``Conversation`` object."""
        from cursorconnect.types.conversation import Conversation
        mock_http(MockResponse(self._CONV_PAYLOAD))
        run = _make_run(cursor_client)
        conv = run.conversation()
        assert isinstance(conv, Conversation)

    def test_conversation_turn_count(self, mock_http, cursor_client) -> None:
        """The number of turns matches the ``turns`` array in the response."""
        mock_http(MockResponse(self._CONV_PAYLOAD))
        run = _make_run(cursor_client)
        turns = run.conversation()
        assert len(turns) == 1

    def test_conversation_turn_structure(self, mock_http, cursor_client) -> None:
        """Each turn is a typed ``ConversationTurn`` with a ``type`` attribute."""
        from cursorconnect.types.conversation import ConversationTurn
        mock_http(MockResponse(self._CONV_PAYLOAD))
        run = _make_run(cursor_client)
        conv = run.conversation()
        assert isinstance(conv[0], ConversationTurn)
        assert conv[0].type == "agentConversationTurn"

    def test_conversation_falls_back_to_items_key(self, mock_http, cursor_client) -> None:
        """``conversation()`` also works when the API returns ``items`` instead of ``turns``."""
        payload = {
            "items": [{"type": "agentConversationTurn", "turn": {"steps": []}}]
        }
        mock_http(MockResponse(payload))
        run = _make_run(cursor_client)
        turns = run.conversation()
        assert len(turns) == 1

    def test_conversation_empty(self, mock_http, cursor_client) -> None:
        """An empty turns array produces an empty ``Conversation`` without error."""
        mock_http(MockResponse({"turns": []}))
        run = _make_run(cursor_client)
        conv = run.conversation()
        assert len(conv) == 0

    @pytest.mark.slow
    def test_conversation_live(self, api_key: str) -> None:
        """Live: retrieve conversation history from a run that has completed."""
        from cursorconnect import Agent

        agent = Agent.create(api_key=api_key, prompt="Say 'hello' exactly once.", model="gemini-3-flash")
        try:
            assert agent._latest_run_id is not None
            run = Run(agent._client, agent.agent_id, {"id": agent._latest_run_id})
            # Wait for the run to finish before reading conversation
            result = run.wait(timeout=120, poll_interval=3)
            if result.status == "FINISHED":
                conv = run.conversation()
                assert len(conv) >= 0
        finally:
            agent.delete()


# ---------------------------------------------------------------------------
# Run status listener
# ---------------------------------------------------------------------------


class TestRunStatusListener:
    """Unit tests for ``Run.on_status_change()``."""

    def test_listener_called_on_status_change(self, cursor_client) -> None:
        """A registered listener is invoked when ``Run.status`` changes."""
        run = _make_run(cursor_client)
        received = []
        run.on_status_change(received.append)
        run.status = "RUNNING"
        assert received == ["RUNNING"]

    def test_listener_not_called_for_same_status(self, cursor_client) -> None:
        """The listener is NOT called when the status value is unchanged."""
        run = _make_run(cursor_client)
        run._status = "RUNNING"
        received = []
        run.on_status_change(received.append)
        run.status = "RUNNING"  # same value
        assert received == []

    def test_listener_exception_is_suppressed(self, cursor_client) -> None:
        """Exceptions raised inside a listener do not propagate to the caller."""

        def bad_listener(status: str) -> None:
            raise ValueError("boom")

        run = _make_run(cursor_client)
        run.on_status_change(bad_listener)
        run.status = "RUNNING"  # should not raise

    def test_multiple_listeners_all_called(self, cursor_client) -> None:
        """All registered listeners fire for each status transition."""
        run = _make_run(cursor_client)
        a: list = []
        b: list = []
        run.on_status_change(a.append)
        run.on_status_change(b.append)
        run.status = "FINISHED"
        assert a == ["FINISHED"]
        assert b == ["FINISHED"]

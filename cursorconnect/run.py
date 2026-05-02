"""Run object and SSE message parsing for the CursorConnect SDK.

:class:`Run` represents a single execution of a Cursor Cloud agent.  It
provides a typed SSE stream, a blocking ``wait()`` that polls until
completion, cancellation, conversation-history access, and a listener
registry for status changes.
"""

from __future__ import annotations

import json
import time
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    TYPE_CHECKING,
)

from .types import (
    Message,
    SystemMessage,
    UserMessageEvent,
    AssistantMessage,
    ThinkingMessage,
    ToolUseMessage,
    StatusMessage,
    TaskMessage,
    RequestMessage,
    ConversationTurn,
)
from .types.account import RunResult
from .exceptions import CursorAgentError, UnsupportedRunOperationError

if TYPE_CHECKING:
    from .client import CursorClient


_TERMINAL_STATES: frozenset = frozenset(
    {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}
)
_DEFAULT_POLL_INTERVAL: float = 1.5


def _parse_sdk_message(
    event_type: Optional[str],
    data: Dict[str, Any],
    agent_id: str,
    run_id: str,
) -> Optional[Message]:
    """
    Parse a raw SSE event into a typed :data:`~cursorconnect.types.Message`.

    Parameters
    ----------
    event_type : str or None
        The ``event:`` field from the SSE frame.
    data : dict
        The decoded JSON payload from the ``data:`` field.
    agent_id : str
        The agent ID from the enclosing :class:`Run` context, used as a
        fallback when the payload does not include ``agentId``.
    run_id : str
        The run ID from the enclosing :class:`Run` context.

    Returns
    -------
    Message or None
        A fully typed message object, or ``None`` when *event_type* is
        unrecognised and should be silently skipped.
    """
    aid = data.get("agentId") or agent_id
    rid = data.get("runId") or run_id

    if event_type == "system":
        return SystemMessage(
            agent_id=aid,
            run_id=rid,
            subtype=data.get("subtype"),
            model=data.get("model"),
            tools=data.get("tools"),
        )
    if event_type == "user":
        return UserMessageEvent(
            agent_id=aid,
            run_id=rid,
            message=data.get("message", {}),
        )
    if event_type == "assistant":
        return AssistantMessage(
            agent_id=aid,
            run_id=rid,
            message=data.get("message", {}),
        )
    if event_type == "thinking":
        return ThinkingMessage(
            agent_id=aid,
            run_id=rid,
            text=data.get("text", ""),
            thinking_duration_ms=data.get("thinkingDurationMs"),
        )
    if event_type == "tool_call":
        return ToolUseMessage(
            agent_id=aid,
            run_id=rid,
            call_id=data.get("callId", ""),
            name=data.get("name", ""),
            status=data.get("status", "running"),
            args=data.get("args"),
            result=data.get("result"),
            truncated=data.get("truncated"),
        )
    if event_type == "status":
        return StatusMessage(
            agent_id=aid,
            run_id=rid,
            status=data.get("status", "RUNNING"),
            message=data.get("message"),
        )
    if event_type == "task":
        return TaskMessage(
            agent_id=aid,
            run_id=rid,
            status=data.get("status"),
            text=data.get("text"),
        )
    if event_type == "request":
        return RequestMessage(
            agent_id=aid,
            run_id=rid,
            request_id=data.get("requestId", ""),
        )
    return None


class Run:
    """
    Represents a single execution run of a Cursor Cloud Agent.

    A ``Run`` is returned by :meth:`~cursorconnect.agent.Agent.send`,
    :meth:`~cursorconnect.agent.Agent.prompt`, or retrieved via the API.
    It provides typed SSE streaming, blocking until completion, cancellation,
    and conversation-history access.

    Parameters
    ----------
    client : CursorClient
        The authenticated HTTP client (shared with the parent ``Agent``).
    agent_id : str
        The ID of the agent that owns this run.
    data : dict
        Raw run payload from the Cursor API.

    Attributes
    ----------
    id : Optional[str]
        The run's unique identifier.
    agent_id : str
        The owning agent's identifier.
    created_at : Optional[str]
        ISO-8601 timestamp of run creation.
    updated_at : Optional[str]
        ISO-8601 timestamp of the last status update.
    """

    def __init__(
        self,
        client: "CursorClient",
        agent_id: str,
        data: Dict[str, Any],
    ) -> None:
        self._client = client
        self.agent_id = agent_id
        self.id: Optional[str] = data.get("id")
        self._status: Optional[str] = data.get("status")
        self.created_at: Optional[str] = data.get("createdAt")
        self.updated_at: Optional[str] = data.get("updatedAt")
        self._raw: Dict[str, Any] = dict(data)
        self._status_listeners: List[Callable[[Optional[str]], None]] = []

    # ------------------------------------------------------------------
    # Status property with listener support
    # ------------------------------------------------------------------

    @property
    def status(self) -> Optional[str]:
        """
        The current status of the run.

        Returns
        -------
        str or None
            One of ``"CREATING"``, ``"RUNNING"``, ``"FINISHED"``,
            ``"ERROR"``, ``"CANCELLED"``, ``"EXPIRED"``, or ``None``
            when not yet populated.
        """
        return self._status

    @status.setter
    def status(self, value: Optional[str]) -> None:
        if value != self._status:
            self._status = value
            for cb in self._status_listeners:
                try:
                    cb(value)
                except Exception:
                    pass

    def on_status_change(self, callback: Callable[[Optional[str]], None]) -> None:
        """
        Register a callback that fires whenever :attr:`status` changes.

        The callback receives the new status string as its sole argument.
        Exceptions raised inside callbacks are silently suppressed so that
        a misbehaving listener cannot interrupt the caller.

        Parameters
        ----------
        callback : Callable[[str], None]
            A function that accepts a single ``str`` (or ``None``) status
            argument.

        Examples
        --------
        >>> def on_change(new_status):
        ...     print(f"[run status → {new_status}]")
        >>> run.on_status_change(on_change)
        """
        self._status_listeners.append(callback)

    # ------------------------------------------------------------------
    # Typed SSE stream
    # ------------------------------------------------------------------

    def stream(self) -> Generator[Message, None, None]:
        """
        Stream Server-Sent Events for this run as typed
        :data:`~cursorconnect.types.Message` objects.

        Each SSE frame is parsed into the appropriate message subtype
        (``AssistantMessage``, ``StatusMessage``, etc.) and yielded in
        arrival order.  :class:`StatusMessage` events automatically update
        :attr:`status` and invoke any listeners registered via
        :meth:`on_status_change`.

        Yields
        ------
        Message
            A typed message.  Frames with unrecognised event types are
            silently skipped.

        Examples
        --------
        >>> run = agent.send("Add type hints to all public functions")
        >>> for msg in run.stream():
        ...     if isinstance(msg, AssistantMessage):
        ...         for block in msg.message.get("content", []):
        ...             if isinstance(block, dict) and block.get("type") == "text":
        ...                 print(block["text"], end="")
        ...     elif isinstance(msg, StatusMessage):
        ...         print(f"\\n[{msg.status}]")
        """
        url = f"/agents/{self.agent_id}/runs/{self.id}/stream"
        response = self._client._request(
            "GET", url, stream=True, headers={"Accept": "text/event-stream"}
        )

        event_type: Optional[str] = None
        event_id: Optional[str] = None
        data_lines: List[str] = []

        def _dispatch() -> Optional[Message]:
            nonlocal event_type, event_id, data_lines
            if not data_lines:
                return None
            data_str = "\n".join(data_lines)
            try:
                payload = (
                    json.loads(data_str)
                    if data_str.strip() not in ("", "{}")
                    else {}
                )
            except json.JSONDecodeError:
                payload = {}
            msg = _parse_sdk_message(
                event_type, payload, self.agent_id, self.id or ""
            )
            event_type = None
            event_id = None
            data_lines = []
            return msg

        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue

            if raw_line == "":
                # Blank line signals end of an SSE event block.
                msg = _dispatch()
                if msg is not None:
                    if isinstance(msg, StatusMessage):
                        self.status = msg.status
                    yield msg
                continue

            if raw_line.startswith("event:"):
                event_type = raw_line[6:].strip()
            elif raw_line.startswith("id:"):
                event_id = raw_line[3:].strip()
            elif raw_line.startswith("data:"):
                data_lines.append(raw_line[5:].strip())

        # Flush any remaining event if the stream ends without a trailing
        # blank line (non-standard but defensive).
        msg = _dispatch()
        if msg is not None:
            if isinstance(msg, StatusMessage):
                self.status = msg.status
            yield msg

    # ------------------------------------------------------------------
    # Blocking wait
    # ------------------------------------------------------------------

    def wait(
        self,
        timeout: Optional[float] = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> RunResult:
        """
        Block until this run reaches a terminal state and return a
        :class:`~cursorconnect.types.account.RunResult`.

        Internally polls the run-list endpoint at *poll_interval* seconds
        until ``status`` transitions to one of ``"FINISHED"``, ``"ERROR"``,
        ``"CANCELLED"``, or ``"EXPIRED"``.

        Parameters
        ----------
        timeout : float, optional
            Maximum seconds to wait before raising ``TimeoutError``, by
            default ``None`` (waits indefinitely).
        poll_interval : float, optional
            Seconds between status polls, by default 1.5.

        Returns
        -------
        RunResult
            Terminal result including final status, run ID, and conversation
            history.

        Raises
        ------
        TimeoutError
            If *timeout* elapses before a terminal state is reached.
        """
        start = time.monotonic()
        self._refresh()

        while self._status not in _TERMINAL_STATES:
            if timeout is not None and (time.monotonic() - start) >= timeout:
                raise TimeoutError(
                    f"Run {self.id!r} did not reach a terminal state within"
                    f" {timeout}s (current status: {self._status!r})."
                )
            time.sleep(poll_interval)
            self._refresh()

        try:
            turns = self.conversation()
        except Exception:
            turns = None

        error_msg: Optional[str] = None
        if self._status == "ERROR":
            error_msg = (
                self._raw.get("errorMessage")
                or self._raw.get("error")
                or "Run ended with status ERROR"
            )

        return RunResult(
            run_id=self.id or "",
            status=self._status or "",
            conversation=turns,
            error_message=error_msg,
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """
        Cancel the active run.

        Sends a cancellation request to the API and immediately updates the
        local :attr:`status` to ``"CANCELLED"``.

        Raises
        ------
        UnsupportedRunOperationError
            If the run is already in a terminal state and cannot be cancelled.
        """
        if self._status in _TERMINAL_STATES:
            raise UnsupportedRunOperationError(
                f"Cannot cancel a run that is already in terminal state"
                f" {self._status!r}.",
                operation="cancel",
            )
        self._client._post(f"/agents/{self.agent_id}/runs/{self.id}/cancel")
        self.status = "CANCELLED"

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def conversation(self) -> List[ConversationTurn]:
        """
        Retrieve the full conversation history for this run.

        Returns
        -------
        list of ConversationTurn
            Ordered list of conversation turns.  Each turn is a ``dict``
            with a ``type`` key (``"agentConversationTurn"`` or
            ``"shellConversationTurn"``) and a ``turn`` payload.
        """
        resp = self._client._get(
            f"/agents/{self.agent_id}/runs/{self.id}/conversation"
        )
        return resp.get("turns", resp.get("items", []))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Re-fetch run status from the API and update local state in-place."""
        try:
            resp = self._client._get(f"/agents/{self.agent_id}/runs")
            for item in resp.get("items", []):
                if item.get("id") == self.id:
                    new_status = item.get("status")
                    if new_status:
                        self.status = new_status
                    self.updated_at = item.get("updatedAt", self.updated_at)
                    self._raw.update(item)
                    return
        except Exception:
            pass

    def __repr__(self) -> str:
        return (
            f"<Run id={self.id!r} agent_id={self.agent_id!r}"
            f" status={self._status!r}>"
        )

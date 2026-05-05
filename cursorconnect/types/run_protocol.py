"""Structural protocol shared by cloud :class:`Run` and :class:`LocalRun`.

Defines the public interface that both run implementations satisfy, so
that callers and type checkers can work with either interchangeably.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Generator,
    Optional,
    runtime_checkable,
    Protocol,
)

from .account import RunResult
from .conversation import Conversation
from .messages import Message


@runtime_checkable
class RunProtocol(Protocol):
    """
    Structural protocol for agent run handles.

    Both :class:`~cursorconnect.run.Run` (cloud) and
    :class:`~cursorconnect._bridge.local_run.LocalRun` (local) satisfy
    this protocol, allowing callers to treat them identically regardless
    of the underlying runtime.

    Attributes
    ----------
    id : str or None
        The run's unique identifier.
    agent_id : str
        The owning agent's identifier.
    status : str or None
        Current run status (e.g. ``"RUNNING"``, ``"FINISHED"``).
    created_at : str or None
        ISO-8601 creation timestamp.
    updated_at : str or None
        ISO-8601 last-update timestamp.
    """

    id: Optional[str]
    agent_id: str
    created_at: Optional[str]
    updated_at: Optional[str]

    @property
    def status(self) -> Optional[str]: ...

    def stream(self) -> Generator[Message, None, None]:
        """Yield typed events as they arrive from the agent."""
        ...

    def wait(
        self,
        timeout: Optional[float] = None,
        poll_interval: float = 1.5,
    ) -> RunResult:
        """Block until the run reaches a terminal state."""
        ...

    def cancel(self) -> None:
        """Cancel the active run."""
        ...

    def conversation(self) -> Conversation:
        """Retrieve the typed conversation history."""
        ...

    def on_status_change(
        self, callback: Callable[[Optional[str]], None]
    ) -> None:
        """Register a listener for status transitions."""
        ...

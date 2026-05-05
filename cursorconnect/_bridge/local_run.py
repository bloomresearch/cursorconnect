"""Run adapter for local agents executed through the Node.js bridge.

Presents the same public interface as :class:`~cursorconnect.run.Run` so that
callers cannot distinguish between a cloud run and a local run.
"""

from __future__ import annotations

import asyncio
import queue as _queue
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional, TYPE_CHECKING

from ..types import (
    Message,
    StatusMessage,
    AssistantMessage,
    ThinkingMessage,
    ToolUseMessage,
    UserMessageEvent,
    SystemMessage,
    TaskMessage,
    RequestMessage,
)
from ..types.account import RunResult
from ..types.conversation import Conversation, parse_conversation
from ..exceptions import UnsupportedRunOperationError

if TYPE_CHECKING:
    from .manager import BridgeManager


_TERMINAL_STATES = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})

_EVENT_MAP = {
    "system": SystemMessage,
    "user": UserMessageEvent,
    "assistant": AssistantMessage,
    "thinking": ThinkingMessage,
    "tool_call": ToolUseMessage,
    "status": StatusMessage,
    "task": TaskMessage,
    "request": RequestMessage,
}


def _bridge_event_to_message(
    event: Dict[str, Any],
    agent_id: str,
    run_id: str,
) -> Optional[Message]:
    """Convert a raw bridge event dict into a typed Message."""
    update = event if "type" not in event or event.get("type") in _EVENT_MAP else event.get("update", event)

    if isinstance(update, dict) and "type" in update:
        etype = update.get("type")
    else:
        etype = event.get("type")

    data = update if isinstance(update, dict) else {}
    aid = data.get("agentId") or agent_id
    rid = data.get("runId") or run_id

    if etype == "system":
        return SystemMessage(agent_id=aid, run_id=rid, subtype=data.get("subtype"), model=data.get("model"), tools=data.get("tools"))
    if etype == "user":
        return UserMessageEvent(agent_id=aid, run_id=rid, message=data.get("message", {}))
    if etype == "assistant":
        return AssistantMessage(agent_id=aid, run_id=rid, message=data.get("message", {}))
    if etype == "thinking":
        return ThinkingMessage(agent_id=aid, run_id=rid, text=data.get("text", ""), thinking_duration_ms=data.get("thinkingDurationMs"))
    if etype == "tool_call":
        return ToolUseMessage(agent_id=aid, run_id=rid, call_id=data.get("callId", ""), name=data.get("name", ""), status=data.get("status", "running"), args=data.get("args"), result=data.get("result"), truncated=data.get("truncated"))
    if etype == "status":
        return StatusMessage(agent_id=aid, run_id=rid, status=data.get("status", "RUNNING"), message=data.get("message"))
    if etype == "task":
        return TaskMessage(agent_id=aid, run_id=rid, status=data.get("status"), text=data.get("text"))
    if etype == "request":
        return RequestMessage(agent_id=aid, run_id=rid, request_id=data.get("requestId", ""))
    return None


def _run_async(coro):
    """Run an async coroutine from synchronous code, handling event loop edge cases.

    Works correctly from the main thread, from ThreadPoolExecutor workers
    (which have no event loop), and when an event loop is already running.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        result_container: List[Any] = [None]
        exception_container: List[Optional[BaseException]] = [None]

        def _thread_target():
            new_loop = asyncio.new_event_loop()
            try:
                result_container[0] = new_loop.run_until_complete(coro)
            except BaseException as exc:
                exception_container[0] = exc
            finally:
                new_loop.close()

        t = threading.Thread(target=_thread_target)
        t.start()
        t.join()
        if exception_container[0] is not None:
            raise exception_container[0]
        return result_container[0]

    new_loop = asyncio.new_event_loop()
    try:
        return new_loop.run_until_complete(coro)
    finally:
        new_loop.close()


class LocalRun:
    """A run executed through the local Node.js bridge.

    Mirrors the public interface of :class:`~cursorconnect.run.Run`.
    """

    def __init__(
        self,
        bridge: "BridgeManager",
        bridge_agent_id: str,
        bridge_run_id: str,
        agent_id: str,
    ) -> None:
        self._bridge = bridge
        self._bridge_agent_id = bridge_agent_id
        self._bridge_run_id = bridge_run_id
        self.agent_id = agent_id
        self.id: Optional[str] = bridge_run_id
        self._status: Optional[str] = "RUNNING"
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None
        self._raw: Dict[str, Any] = {}
        self._status_listeners: List[Callable[[Optional[str]], None]] = []

    @property
    def status(self) -> Optional[str]:
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
        self._status_listeners.append(callback)

    def stream(self) -> Generator[Message, None, None]:
        """Stream typed events from the local agent run in real time.

        The bridge's ``stream_request`` is an async generator, but this
        ``stream()`` method is synchronous. To avoid the previous
        "collect-then-yield" anti-pattern (which made the caller wait for the
        whole run before seeing anything), we run the async iteration on a
        background thread with its own event loop and pump events through a
        thread-safe ``queue.Queue``. The synchronous generator pulls from that
        queue and yields each typed message as it arrives.

        A sentinel tuple ``("end", None)`` signals normal completion, and
        ``("error", exc)`` re-raises any exception from the pump thread on the
        consumer side. If the consumer breaks out of the loop early, the
        ``finally`` block cancels the pump task so we don't leak the
        background thread or stream queue.
        """
        out_q: "_queue.Queue[tuple]" = _queue.Queue()
        loop_holder: Dict[str, Any] = {}
        loop_ready = threading.Event()

        async def _pump() -> None:
            try:
                async for event in self._bridge.stream_request(
                    "run.stream", target=self._bridge_run_id
                ):
                    out_q.put(("event", event))
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                out_q.put(("error", exc))
            finally:
                out_q.put(("end", None))

        def _thread_target() -> None:
            new_loop = asyncio.new_event_loop()
            loop_holder["loop"] = new_loop
            asyncio.set_event_loop(new_loop)
            try:
                task = new_loop.create_task(_pump())
                loop_holder["task"] = task
                loop_ready.set()
                new_loop.run_until_complete(task)
            finally:
                loop_ready.set()
                try:
                    new_loop.close()
                except Exception:
                    pass

        pump_thread = threading.Thread(
            target=_thread_target,
            name=f"local-run-stream-{self._bridge_run_id}",
            daemon=True,
        )
        pump_thread.start()

        try:
            while True:
                kind, payload = out_q.get()
                if kind == "end":
                    break
                if kind == "error":
                    raise payload
                msg = _bridge_event_to_message(
                    payload, self.agent_id, self._bridge_run_id
                )
                if msg is None:
                    continue
                if isinstance(msg, StatusMessage):
                    self.status = msg.status
                yield msg
        finally:
            loop_ready.wait(timeout=1.0)
            loop = loop_holder.get("loop")
            task = loop_holder.get("task")
            if loop is not None and task is not None and not task.done():
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass
            pump_thread.join(timeout=2.0)

    def wait(
        self,
        timeout: Optional[float] = None,
        poll_interval: float = 1.5,
    ) -> RunResult:
        """Block until the local run reaches a terminal state."""
        result = _run_async(
            self._bridge.send_request("run.wait", target=self._bridge_run_id)
        )

        final_status = "FINISHED"
        error_msg = None
        result_text = None

        if isinstance(result, dict):
            final_status = result.get("status", "FINISHED")
            error_msg = result.get("errorMessage") or result.get("error")
            result_text = result.get("result")

        self.status = final_status

        conv = None
        try:
            conv = self.conversation()
        except Exception:
            pass

        return RunResult(
            run_id=self._bridge_run_id,
            status=final_status,
            conversation=conv,
            error_message=error_msg,
            result_text=result_text,
        )

    def cancel(self) -> None:
        if self._status in _TERMINAL_STATES:
            raise UnsupportedRunOperationError(
                f"Cannot cancel a run already in terminal state {self._status!r}.",
                operation="cancel",
            )
        _run_async(
            self._bridge.send_request("run.cancel", target=self._bridge_run_id)
        )
        self.status = "CANCELLED"

    def conversation(self) -> Conversation:
        """
        Retrieve the full conversation history for this run as typed objects.

        Returns
        -------
        Conversation
            A :class:`~cursorconnect.types.conversation.Conversation` that
            supports iteration, indexing, ``len()``, and ``print()``.
        """
        result = _run_async(
            self._bridge.send_request("run.conversation", target=self._bridge_run_id)
        )
        if isinstance(result, dict):
            raw_turns = result.get("turns", result.get("items", []))
        elif isinstance(result, list):
            raw_turns = result
        else:
            raw_turns = []
        return parse_conversation(raw_turns)

    def __repr__(self) -> str:
        return (
            f"<LocalRun id={self.id!r} agent_id={self.agent_id!r}"
            f" status={self._status!r}>"
        )

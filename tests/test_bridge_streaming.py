"""Tests for the Node.js bridge event-pipeline fixes.

This module exercises two related streaming bugs that previously caused
events to be either silently dropped or buffered until the run completed:

1. ``BridgeManager.send_request`` had no place to put ``type: "event"``
   messages that arrive alongside an in-flight request (e.g. ``agent.send``
   with ``streamEvents: true``). Those events are now routed to an optional
   per-request ``on_event`` callback.

2. ``LocalRun.stream()`` previously collected the full async-generator into a
   list before yielding anything. It now bridges async-to-sync via a
   background thread + ``queue.Queue`` so each event is yielded as it
   arrives.

These are unit tests — the Node.js bridge is replaced with a tiny fake so we
exercise only the Python plumbing.
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest

from cursorconnect._bridge.manager import BridgeManager
from cursorconnect._bridge.local_run import LocalRun
from cursorconnect.types import (
    AssistantMessage,
    StatusMessage,
    ThinkingMessage,
)


# ---------------------------------------------------------------------------
# Helpers: fake Node.js subprocess
# ---------------------------------------------------------------------------


class _FakeStdin:
    """Captures lines written by BridgeManager.send_request."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self._closed = False

    def write(self, data: str) -> None:
        if self._closed:
            raise BrokenPipeError("fake stdin closed")
        self.lines.append(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True


class _FakeProcess:
    """Minimal stand-in for ``subprocess.Popen`` used by BridgeManager."""

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = io.StringIO()
        self._returncode: Optional[int] = None

    def poll(self) -> Optional[int]:
        return self._returncode

    def terminate(self) -> None:
        self._returncode = 0


def _make_manager_with_fake_process() -> BridgeManager:
    """Return a BridgeManager wired up with a fake process so we can call
    ``send_request`` without spawning Node.js."""
    mgr = BridgeManager(bridge_path="<fake>", node_bin="<fake>")
    mgr._process = _FakeProcess()  # type: ignore[assignment]
    return mgr


def _last_request_id(mgr: BridgeManager) -> str:
    """Read back the request_id that send_request just wrote to fake stdin."""
    proc: _FakeProcess = mgr._process  # type: ignore[assignment]
    assert proc.stdin.lines, "expected a request to have been written"
    payload = json.loads(proc.stdin.lines[-1])
    return payload["id"]


# ---------------------------------------------------------------------------
# Bug 2: events during send_request must not be silently dropped.
# ---------------------------------------------------------------------------


def test_dispatch_message_routes_event_to_handler() -> None:
    """``_dispatch_message`` must invoke the per-request event handler for
    ``type: "event"`` messages, instead of dropping them on the floor."""
    mgr = BridgeManager(bridge_path="<fake>")
    captured: List[Any] = []
    mgr._request_event_handlers["req-1"] = captured.append

    mgr._dispatch_message({
        "id": "req-1",
        "type": "event",
        "data": {"type": "delta", "update": {"text": "hello"}},
    })
    mgr._dispatch_message({
        "id": "req-1",
        "type": "event",
        "data": {"type": "step", "step": {"index": 0}},
    })

    assert len(captured) == 2
    assert captured[0]["type"] == "delta"
    assert captured[1]["type"] == "step"


def test_dispatch_message_event_with_no_handler_does_not_raise(caplog) -> None:
    """An event with neither a handler nor a streaming queue should be
    survivable — we log it at DEBUG rather than crashing."""
    mgr = BridgeManager(bridge_path="<fake>")
    with caplog.at_level("DEBUG", logger="cursorconnect._bridge.manager"):
        mgr._dispatch_message({"id": "orphan", "type": "event", "data": {}})
    assert any("no registered handler" in rec.getMessage() for rec in caplog.records)


def test_send_request_captures_events_then_resolves() -> None:
    """End-to-end: ``send_request(on_event=...)`` must (a) deliver every
    ``type: "event"`` message to the callback in order, and (b) still resolve
    its return value with the final ``type: "success"`` payload. Previously
    only (b) worked; events between them were silently dropped."""
    mgr = _make_manager_with_fake_process()
    captured: List[Any] = []

    async def _drive() -> Any:
        send_task = asyncio.ensure_future(
            mgr.send_request(
                "agent.send",
                target="agent_1",
                args=["hi", {"streamEvents": True}],
                on_event=captured.append,
            )
        )
        # Wait until send_request has written the request to the fake stdin
        # so we know the req_id is registered.
        for _ in range(100):
            if mgr._process.stdin.lines:  # type: ignore[union-attr]
                break
            await asyncio.sleep(0.01)
        req_id = _last_request_id(mgr)

        mgr._dispatch_message({
            "id": req_id,
            "type": "event",
            "data": {"type": "delta", "update": {"text": "ping"}},
        })
        mgr._dispatch_message({
            "id": req_id,
            "type": "event",
            "data": {"type": "step", "step": {"index": 0}},
        })
        mgr._dispatch_message({
            "id": req_id,
            "type": "success",
            "data": {"runId": "run_1"},
        })
        return await send_task

    result = asyncio.new_event_loop().run_until_complete(_drive())

    assert result == {"runId": "run_1"}
    assert [c["type"] for c in captured] == ["delta", "step"]
    # The handler entry must be cleaned up after the request finishes so it
    # cannot leak into a future request that happens to reuse a uuid (it
    # never will, but cleanup matters for the in-flight registry as a whole).
    assert mgr._request_event_handlers == {}


def test_send_request_event_handler_exception_is_swallowed() -> None:
    """A buggy event handler must not poison the request future."""
    mgr = _make_manager_with_fake_process()

    def _bad_handler(_event: Any) -> None:
        raise RuntimeError("intentional")

    async def _drive() -> Any:
        task = asyncio.ensure_future(
            mgr.send_request("agent.send", target="agent_1", on_event=_bad_handler)
        )
        for _ in range(100):
            if mgr._process.stdin.lines:  # type: ignore[union-attr]
                break
            await asyncio.sleep(0.01)
        req_id = _last_request_id(mgr)

        mgr._dispatch_message({"id": req_id, "type": "event", "data": {}})
        mgr._dispatch_message({"id": req_id, "type": "success", "data": {"ok": True}})
        return await task

    result = asyncio.new_event_loop().run_until_complete(_drive())
    assert result == {"ok": True}


# ---------------------------------------------------------------------------
# Bug 1: LocalRun.stream() must yield events incrementally, not after the
# full run completes.
# ---------------------------------------------------------------------------


class _FakeBridge:
    """A minimal bridge that exposes only the async ``stream_request`` API
    that ``LocalRun.stream()`` consumes. Events are released one at a time
    by the test, so we can prove yielding is incremental rather than
    collect-then-flush."""

    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = events
        # One gate per event. Test code sets gate[i] to release event i.
        self.gates = [threading.Event() for _ in events]
        self.released_count = 0
        self.cancelled = False

    async def stream_request(
        self, action: str, target: Any = None, args: Any = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            for i, event in enumerate(self._events):
                # Wait for the test to release this event.
                while not self.gates[i].is_set():
                    await asyncio.sleep(0.01)
                self.released_count = i + 1
                yield event
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _make_local_run(bridge: _FakeBridge) -> LocalRun:
    return LocalRun(
        bridge=bridge,  # type: ignore[arg-type]
        bridge_agent_id="agent_1",
        bridge_run_id="run_1",
        agent_id="agent-public-1",
    )


def test_local_run_stream_yields_incrementally() -> None:
    """The crux of bug 1: each event must reach the consumer before the next
    one is even produced upstream. We gate the fake bridge so the second
    event cannot be produced until the first one has been observed."""
    events = [
        {"type": "assistant", "message": {"role": "assistant", "content": "first"}},
        {"type": "thinking", "text": "second"},
        {"type": "status", "status": "FINISHED"},
    ]
    bridge = _FakeBridge(events)
    run = _make_local_run(bridge)

    received: List[Any] = []
    bridge.gates[0].set()  # release the first event immediately.

    iterator = run.stream()
    msg1 = next(iterator)
    received.append(msg1)
    # At this point only event 0 should have been produced upstream.
    assert bridge.released_count == 1, (
        "stream() must yield event 0 before event 1 is produced; got "
        f"released_count={bridge.released_count}"
    )

    bridge.gates[1].set()
    msg2 = next(iterator)
    received.append(msg2)
    assert bridge.released_count == 2

    bridge.gates[2].set()
    msg3 = next(iterator)
    received.append(msg3)
    assert bridge.released_count == 3

    # Generator must terminate cleanly.
    with pytest.raises(StopIteration):
        next(iterator)

    assert isinstance(received[0], AssistantMessage)
    assert isinstance(received[1], ThinkingMessage)
    assert isinstance(received[2], StatusMessage)
    assert run.status == "FINISHED"


def test_local_run_stream_propagates_errors() -> None:
    """Exceptions from the async pump must surface on the consumer side."""

    class _BoomBridge:
        async def stream_request(self, *_a: Any, **_kw: Any) -> AsyncGenerator[Dict[str, Any], None]:
            yield {"type": "assistant", "message": {"role": "assistant", "content": "ok"}}
            raise RuntimeError("upstream failure")

    run = LocalRun(
        bridge=_BoomBridge(),  # type: ignore[arg-type]
        bridge_agent_id="agent_1",
        bridge_run_id="run_1",
        agent_id="agent-public-1",
    )

    iterator = run.stream()
    first = next(iterator)
    assert isinstance(first, AssistantMessage)
    with pytest.raises(RuntimeError, match="upstream failure"):
        next(iterator)


def test_local_run_stream_cancels_pump_on_early_break() -> None:
    """If the consumer breaks out of iteration early, the background pump
    task must be cancelled so we don't leak a thread/event-loop."""
    events = [
        {"type": "assistant", "message": {"role": "assistant", "content": "one"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "two"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "three"}},
    ]
    bridge = _FakeBridge(events)
    run = _make_local_run(bridge)
    bridge.gates[0].set()

    iterator = run.stream()
    first = next(iterator)
    assert isinstance(first, AssistantMessage)

    iterator.close()  # simulate consumer breaking out early.

    # Release the remaining gates so the pump can observe cancellation
    # promptly. Without cancellation the pump would block here forever.
    bridge.gates[1].set()
    bridge.gates[2].set()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not bridge.cancelled:
        time.sleep(0.05)
    assert bridge.cancelled, "pump task should have been cancelled on early break"

import sys
import json
import asyncio
import subprocess
import threading
import uuid
import logging
from typing import Callable, Dict, Any, AsyncGenerator, Optional, Tuple

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], None]

class BridgeManager:
    """
    Manages the Node.js subprocess that bridges Python to the Cursor TypeScript SDK.

    This manager spawns a Node.js process running `bridge.js`, communicates with it
    via newline-delimited JSON over stdin/stdout, and provides methods to send requests
    and receive streaming responses. It automatically restarts the process if it crashes.

    Parameters
    ----------
    bridge_path : str
        The path to the `bridge.js` script.
    node_bin : str, optional
        The path to the Node.js executable. Defaults to 'node'.
    """
    def __init__(self, bridge_path: str, node_bin: str = 'node', api_key: Optional[str] = None):
        self.bridge_path = bridge_path
        self.node_bin = node_bin
        self._api_key = api_key
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._streaming_queues: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}
        # Per-request side-channel handlers. Used to capture `type: "event"`
        # messages that arrive while a `send_request` future is in flight (e.g.
        # `agent.send` with `streamEvents: true` emits onDelta/onStep events
        # before resolving with `type: "success"`). Without this side-channel
        # those events would be silently dropped by `_dispatch_message`.
        self._request_event_handlers: Dict[str, EventHandler] = {}
        self._reader_thread: Optional[threading.Thread] = None

    def start(self):
        """
        Starts the Node.js bridge process and performs a health check.
        
        Raises
        ------
        RuntimeError
            If Node.js is not found or fails to start.
        """
        import os
        self._check_health()
        env = os.environ.copy()
        api_key = self._api_key or os.environ.get("CURSOR_API_KEY", "")
        if api_key:
            env["CURSOR_API_KEY"] = api_key
        self._process = subprocess.Popen(
            [self.node_bin, self.bridge_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
            env=env,
        )
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

    def _check_health(self):
        """Performs a health check to ensure node is available."""
        try:
            subprocess.run([self.node_bin, "--version"], check=True, capture_output=True)
        except FileNotFoundError:
            raise RuntimeError(f"Node.js not found at '{self.node_bin}'. Ensure it is installed and in your PATH.")

    def _read_stdout(self):
        """Background thread to read stdout from the Node.js process."""
        if not self._process or not self._process.stdout:
            return

        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self._dispatch_message(msg)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse bridge output: {line}")

        logger.warning("Node.js bridge process exited.")
        self._handle_crash()

    def _dispatch_message(self, msg: dict):
        """Dispatches an incoming message from Node.js to the appropriate future, queue, or event handler."""
        msg_id = msg.get("id")
        if not msg_id:
            logger.error(f"Received message without id: {msg}")
            return

        msg_type = msg.get("type")

        with self._lock:
            future = self._pending_requests.get(msg_id)
            queue_info = self._streaming_queues.get(msg_id)
            event_handler = self._request_event_handlers.get(msg_id)

        # Standard request/response future resolution.
        if future and not future.done() and msg_type in ("success", "error"):
            loop = future.get_loop()
            if msg_type == "success":
                loop.call_soon_threadsafe(future.set_result, msg.get("data"))
            else:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError(msg.get("error", "Unknown error")),
                )

            with self._lock:
                self._pending_requests.pop(msg_id, None)

        # Side-channel: route `type: "event"` messages to a per-request handler
        # when registered. This rescues mid-flight events (e.g. agent.send
        # streamEvents) that previously fell through to the silent-drop path
        # because `send_request` only owns a future, not a streaming queue.
        if msg_type == "event" and event_handler is not None:
            try:
                event_handler(msg.get("data"))
            except Exception:
                logger.exception("Per-request event handler raised; ignoring.")

        # Streaming updates (run.stream registers a queue).
        if queue_info:
            loop, queue = queue_info
            loop.call_soon_threadsafe(queue.put_nowait, msg)
            if msg_type in ("success", "error"):
                with self._lock:
                    self._streaming_queues.pop(msg_id, None)
            return

        # If we got here with an "event" message that has no destination at all
        # (no streaming queue and no event handler), surface it via debug log
        # rather than silently discarding it.
        if msg_type == "event" and event_handler is None:
            logger.debug(
                "Bridge emitted an event with no registered handler "
                "(req_id=%s); event will be dropped.",
                msg_id,
            )

    def _handle_crash(self):
        """Handles a crash by failing pending requests safely from another thread."""
        with self._lock:
            for future in self._pending_requests.values():
                if not future.done():
                    loop = future.get_loop()
                    loop.call_soon_threadsafe(future.set_exception, RuntimeError("Node.js bridge crashed or exited."))
            
            for loop, queue in self._streaming_queues.values():
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "error": "Node.js bridge crashed or exited."})
            
            self._pending_requests.clear()
            self._streaming_queues.clear()
            self._request_event_handlers.clear()
            self._process = None

    async def send_request(
        self,
        action: str,
        target: str = None,
        args: list = None,
        on_event: Optional[EventHandler] = None,
    ) -> Any:
        """
        Sends a single request to the Node.js bridge and waits for the response.

        Parameters
        ----------
        action : str
            The action to perform (e.g., 'Agent.create', 'run.wait').
        target : str, optional
            The target object ID (e.g., an agent ID or run ID).
        args : list, optional
            A list of arguments to pass to the action.
        on_event : callable, optional
            A callback invoked for any ``type: "event"`` messages that arrive
            while the request is in flight. This is how callers can capture the
            mid-flight events emitted by actions like ``agent.send`` with
            ``streamEvents: true``. Without this callback those events are
            still surfaced via debug logging rather than silently dropped, but
            registering a handler is the canonical way to consume them.

        Returns
        -------
        Any
            The result of the action.

        Raises
        ------
        RuntimeError
            If the bridge process crashes or returns an error.
        """
        if not self._process or self._process.poll() is not None:
            logger.info("Starting Node.js bridge process.")
            self.start()

        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        with self._lock:
            self._pending_requests[req_id] = future
            if on_event is not None:
                self._request_event_handlers[req_id] = on_event

        req = {
            "id": req_id,
            "action": action,
            "target": target,
            "args": args or [],
        }

        try:
            self._process.stdin.write(json.dumps(req) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, AttributeError):
            self._handle_crash()
            raise RuntimeError("Node.js bridge crashed while writing request.")

        try:
            return await future
        finally:
            with self._lock:
                self._request_event_handlers.pop(req_id, None)

    async def stream_request(self, action: str, target: str = None, args: list = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Sends a request to the Node.js bridge and yields streaming responses.

        Parameters
        ----------
        action : str
            The action to perform (e.g., 'run.stream').
        target : str, optional
            The target object ID (e.g., a run ID).
        args : list, optional
            A list of arguments to pass to the action.

        Yields
        ------
        Dict[str, Any]
            The yielded data fragments from the stream.

        Raises
        ------
        RuntimeError
            If the bridge process crashes or returns an error during streaming.
        """
        if not self._process or self._process.poll() is not None:
            logger.info("Starting Node.js bridge process.")
            self.start()

        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        with self._lock:
            self._streaming_queues[req_id] = (loop, queue)

        req = {
            "id": req_id,
            "action": action,
            "target": target,
            "args": args or []
        }

        try:
            self._process.stdin.write(json.dumps(req) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, AttributeError):
            self._handle_crash()
            raise RuntimeError("Node.js bridge crashed while writing stream request.")

        try:
            while True:
                msg = await queue.get()
                msg_type = msg.get("type")
                
                if msg_type == "error":
                    raise RuntimeError(msg.get("error", "Unknown stream error from Node.js bridge."))
                elif msg_type == "success":
                    break
                elif msg_type in ("event", "yield"):
                    yield msg.get("data")
        finally:
            with self._lock:
                self._streaming_queues.pop(req_id, None)
                
    def close(self):
        """Closes the bridge process gracefully."""
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            self._process.terminate()
            self._process = None

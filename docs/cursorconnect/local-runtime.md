# `cursorconnect._bridge`: Local runtime setup and operations

`cursorconnect._bridge` is the Python-to-Node adapter used when
`Agent.create(..., local=LocalOptions(...))` runs an agent on the caller's
machine. It hides the TypeScript `@cursor/sdk` subprocess behind the same
`RunProtocol` used by cloud runs.

This page is an operational runbook for setup, diagnostics, and common local
runtime failures.

## Module map

| Module | Responsibility |
| --- | --- |
| `cursorconnect._bridge.setup` | Detects Node.js, installs `@cursor/sdk` into package-local `node_modules`, and reports status. |
| `cursorconnect._bridge.manager` | Starts `bridge.js`, sends newline-delimited JSON requests, routes responses and streams. |
| `cursorconnect._bridge.bridge.js` | Calls the TypeScript `@cursor/sdk` and keeps in-memory maps of local agents and runs. |
| `cursorconnect._bridge.local_run` | Adapts local bridge runs to the synchronous `RunProtocol` interface. |
| `cursorconnect.cli` | Exposes setup and diagnostic commands as `cursorconnect setup-local` and `cursorconnect status`. |

## Setup lifecycle

Local runtime preparation is lazy. The first local agent creation calls
`ensure_local_runtime()` through `cursorconnect.agent._get_bridge()`.

1. `_find_node()` searches `PATH` for `node`.
2. Node.js must be version 18 or newer.
3. `_sdk_is_installed()` checks whether `@cursor/sdk` is resolvable from the
   bridge directory with `NODE_PATH` pointing at the package-local
   `node_modules`.
4. If missing, `_install_sdk()` runs:

   ```bash
   npm install --prefix cursorconnect/_bridge @cursor/sdk
   ```

5. `ensure_local_runtime()` returns `(node_binary, bridge_script_path)`.
6. `BridgeManager.start()` launches:

   ```bash
   node cursorconnect/_bridge/bridge.js
   ```

You can run the setup proactively:

```bash
cursorconnect setup-local
cursorconnect status
```

`setup-local` returns a non-zero exit code if Node.js or `@cursor/sdk`
preparation fails. `status` prints a diagnostic summary and returns zero even
when the runtime is not ready, so it can be used in support scripts without
failing the script immediately.

## Minimal local agent

```python
from cursorconnect import Agent
from cursorconnect.types import LocalOptions, AssistantMessage, StatusMessage

agent = Agent.create(
    prompt="Explain the purpose of this repository in two sentences.",
    local=LocalOptions(cwd="/path/to/repo", settingSources=["project", "user"]),
    model="gemini-3-flash",
)

run = agent.initial_run
if run is None:
    raise RuntimeError("local agent did not enqueue an initial run")

for event in run.stream():
    if event.type is AssistantMessage:
        print(event.message)
    elif event.type is StatusMessage:
        print(f"status={event.status}")

agent.close()
```

## Bridge protocol

The Python bridge manager writes JSON requests to the Node process over stdin:

```json
{"id": "uuid", "action": "agent.send", "target": "agent_1", "args": ["prompt", {"streamEvents": true}]}
```

The Node bridge writes newline-delimited JSON responses on stdout:

- `{"id": "...", "type": "success", "data": ...}` resolves a request.
- `{"id": "...", "type": "error", "error": "..."}` fails a request.
- `{"id": "...", "type": "event", "data": ...}` carries mid-flight
  `agent.send(..., streamEvents=True)` updates.
- `{"id": "...", "type": "yield", "data": ...}` carries `run.stream()`
  updates.

`BridgeManager` keeps separate registries for pending request futures, stream
queues, and per-request event handlers. This prevents events emitted before an
`agent.send` request resolves from being silently dropped.

## Streaming behavior

`LocalRun.stream()` is synchronous, but the bridge stream is asynchronous.
`LocalRun` starts a background daemon thread with its own asyncio event loop and
pumps events into a `queue.Queue`. The caller receives each typed message as
soon as it arrives; events are not collected until completion.

Important constraints:

- Breaking out of the generator early cancels the pump task and joins the
  background thread briefly.
- Upstream bridge exceptions are re-raised in the consumer's thread.
- `StatusMessage` events update `run.status` and notify callbacks registered
  through `run.on_status_change(...)`.
- Unknown event shapes are skipped if they cannot be converted to a typed
  `cursorconnect.types.Message`.

## Troubleshooting

### `Node.js is required for local agents but was not found on PATH`

Install Node.js 18+ and confirm:

```bash
node --version
npm --version
cursorconnect status
```

### `Node.js 18+ is required ... found vX`

Upgrade Node.js. The local bridge verifies the major version before attempting
to install or launch `@cursor/sdk`.

### `npm is required to install @cursor/sdk`

Install npm or use a Node.js distribution that includes it. CursorConnect uses
npm only for one-time installation of `@cursor/sdk`.

### `Failed to install @cursor/sdk via npm`

The setup helper includes npm stderr in the raised `LocalSetupError`. Common
causes are network restrictions, registry configuration, or write permissions
for the installed package directory.

Manual recovery:

```bash
cd cursorconnect/_bridge
npm install @cursor/sdk
cursorconnect status
```

### `Could not load @cursor/sdk`

The Node bridge could not resolve or load `@cursor/sdk`. Re-run:

```bash
cursorconnect setup-local
```

If the package is installed but still cannot load, remove the package-local
`node_modules` and install again from `cursorconnect/_bridge`.

### `Node.js bridge crashed or exited`

`BridgeManager` fails pending requests and clears stream queues when the
subprocess exits. A later request starts a new process automatically, but local
agent and run handles kept in `bridge.js` memory are lost. Create a new local
`Agent` after a bridge crash.

### Local-only unsupported operations

The following cloud operations raise `UnsupportedRunOperationError` for local
agents because the local runtime does not expose durable cloud metadata or
downloadable artifacts:

- `agent.archive()`
- `agent.unarchive()`
- `agent.delete()`
- `agent.reload()`
- `agent.list_artifacts()`
- `agent.download_artifact(path)`

Use `agent.close()` for local cleanup.

## CI and developer environment checks

For projects that depend on local agents, add a fast environment check before
running local integration tests:

```bash
cursorconnect status
python - <<'PY'
from cursorconnect._bridge.setup import get_status

status = get_status()
if not status["ready"]:
    raise SystemExit("CursorConnect local runtime is not ready")
PY
```

Run unit tests for bridge behavior without live Cursor credentials:

```bash
pytest tests/test_bridge_streaming.py
pytest -m "not slow"
```

The bridge streaming tests use fakes for the Node process and async stream, so
they validate Python event routing without invoking `@cursor/sdk`.

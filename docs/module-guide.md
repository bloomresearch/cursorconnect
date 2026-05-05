# CursorConnect Module Guide

This guide maps the public Python package structure to the workflows it
supports. It is intended for maintainers and SDK users who need to understand
where behavior lives before extending or debugging CursorConnect.

## Package map

| Module | Role | Public surface |
|---|---|---|
| `cursorconnect.agent` | Runtime-agnostic agent facade. Chooses cloud HTTP or local bridge execution and owns agent lifecycle operations. | `Agent` |
| `cursorconnect.run` | Cloud run control and SSE parsing. Polls for terminal status, streams typed events, cancels active runs, and loads conversation history. | `Run` |
| `cursorconnect._bridge` | Local runtime adapter around the Cursor TypeScript SDK. Spawns `bridge.js`, exchanges JSON-RPC over stdio, and adapts async TypeScript runs to synchronous Python methods. | Internal |
| `cursorconnect.mesh` | Parallel orchestration layer for multiple agents, optional cross-check broadcasts, and context-manager cleanup. | `Mesh` |
| `cursorconnect.cursor` | Account-level namespace for `/me`, `/models`, and `/repositories`. | `Cursor` |
| `cursorconnect.artifact` | Cloud artifact metadata and downloads through presigned URLs. | `Artifact` |
| `cursorconnect.client` | Deprecated compatibility shim plus low-level HTTP helper used internally by the facades. | `CursorClient` |
| `cursorconnect.types` | Dataclasses and protocols for options, messages, conversations, model selection, account objects, MCP config, and mesh results. | `CloudOptions`, `LocalOptions`, `RunProtocol`, message and result types |
| `cursorconnect.exceptions` | SDK exception hierarchy and HTTP-status mapping. | `CursorAgentError` and subclasses |

## Core workflow

### 1. Create an agent

`Agent.create()` is the main entry point. It enqueues the initial run and
returns an `Agent` instance whose `initial_run` property exposes that run.

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions, LocalOptions

cloud_agent = Agent.create(
    prompt="Run the test suite and fix one failing test.",
    cloud=CloudOptions(repos=[{"url": "https://github.com/org/repo"}]),
)

local_agent = Agent.create(
    prompt="Summarize this checkout.",
    local=LocalOptions(cwd="/path/to/repo"),
    model="composer-2",
)
```

Pass exactly one runtime option (`cloud` or `local`). The implementation raises
`ValueError` if both are provided. If neither is provided, CursorConnect uses
the cloud API path.

### 2. Observe or wait for a run

Both cloud `Run` and local `LocalRun` satisfy `RunProtocol`:

```python
run = cloud_agent.initial_run
if run is None:
    raise RuntimeError("Agent did not return an initial run id")

for event in run.stream():
    print(event.type.__name__)

result = run.wait(timeout=300)
print(result.status)
```

Cloud runs stream Server-Sent Events from `/agents/{agent_id}/runs/{run_id}/stream`.
Local runs stream through `BridgeManager.stream_request("run.stream", ...)`.
In both cases, `StatusMessage` events update `run.status` and notify callbacks
registered with `run.on_status_change(callback)`.

### 3. Read conversation history

`run.wait()` attempts to attach a parsed `Conversation` to the returned
`RunResult`. You can also call `run.conversation()` directly.

```python
conversation = result.conversation or run.conversation()
print(conversation.text)

for turn in conversation:
    print(turn.type, turn.text[:120])
```

The parser accepts the `turns` response shape and the `items` fallback shape
used by some API responses.

## Local runtime architecture

Local execution is implemented as a Python-to-Node bridge:

1. `Agent._create_local()` gets a shared, thread-safe `BridgeManager`.
2. `BridgeManager.start()` verifies `node --version`, starts
   `cursorconnect/_bridge/bridge.js`, and forwards `CURSOR_API_KEY` into the
   subprocess environment when available.
3. `bridge.js` imports `@cursor/sdk`, creates TypeScript SDK agents, and stores
   live agent/run handles in in-memory maps.
4. Python sends newline-delimited JSON requests such as `Agent.create`,
   `agent.send`, `run.wait`, `run.stream`, `run.cancel`, and
   `run.conversation`.
5. `LocalRun.stream()` converts the bridge's async stream into a synchronous
   Python generator with a background thread and `queue.Queue`, so consumers
   receive events incrementally rather than after the run completes.

### Local setup constraints

- Install Node.js 18+.
- Install `@cursor/sdk` where `bridge.js` can resolve it. In a source checkout,
  run `npm install` from the repository root.
- Set `CURSOR_API_KEY` or pass `api_key=` if the TypeScript SDK operation needs
  Cursor authentication.
- Local-only metadata operations are intentionally limited. `archive()`,
  `unarchive()`, `delete()`, `reload()`, and artifact listing raise
  `UnsupportedRunOperationError` for local agents.

## Mesh orchestration

`Mesh` coordinates multiple `MeshTask` objects through a thread pool.

```python
from cursorconnect import Mesh
from cursorconnect.types import CloudOptions, MeshTask

with Mesh(
    cloud=CloudOptions(repos=[{"url": "https://github.com/org/repo"}]),
    cross_check=True,
    cleanup="archive",
) as mesh:
    mesh + MeshTask("api", "Update the API layer only.")
    mesh + MeshTask("tests", "Add focused regression tests only.")
    results = mesh.run(timeout=600)
```

Important constraints:

- Task-level `cloud`, `local`, and `model` values override Mesh defaults.
- Results are returned in completion order, not registration order.
- `cross_check=True` sends a fire-and-forget follow-up message to still-running
  peers when a task finishes. A callable `cross_check` can format that message.
- Context-manager cleanup archives agents by default. Use `cleanup="delete"` for
  permanent cloud deletion or `cleanup=None` to leave agents untouched.
- Artifacts are collected only for cloud agents.

## Account and model discovery

Use the `Cursor` namespace for account-scoped reads:

```python
from cursorconnect import Cursor

user = Cursor.me()
models = Cursor.models.list()
repos = Cursor.repositories.list()
```

`Cursor.repositories.list()` is rate-limited by the Cursor API. The test suite
documents the expected limit as 1 request per user per minute and 30 per user
per hour, so cache repository lists in long-running services.

## Error handling contract

All SDK-specific exceptions inherit from `CursorAgentError` and expose:

- `message`: human-readable detail
- `is_retryable`: whether retrying is usually safe
- `code`: optional machine-readable error code
- `cause`: optional original exception

HTTP mapping is centralized in `map_http_error()`:

| HTTP status | Exception | Retryable |
|---|---|---|
| `400` | `ConfigurationError` | No |
| `401`, `403` | `AuthenticationError` | No |
| `429` | `RateLimitError` | Yes |
| `500+` | `UnknownAgentError` | Yes |
| Other statuses | `UnknownAgentError` | No |

Run-level failures are different from startup/API failures: a call can return a
`RunResult(status="ERROR", error_message=...)` without raising an exception.
Handle both paths explicitly in automation.

## Compatibility shim

`CursorClient` remains available for older integrations, but constructing it
emits a `DeprecationWarning`. New code should use:

- `Agent.create()`, `Agent.prompt()`, `Agent.get()`, and `Agent.list()` for
  agent lifecycle.
- `Cursor.me()`, `Cursor.models.list()`, and `Cursor.repositories.list()` for
  account metadata.

The shim adapts legacy methods to the modern facades where possible, including
`client.agents.create(...)`, `client.agents.get(...)`,
`client.agents.list(...)`, `client.list_models()`, and
`client.list_repositories()`.

## Testing and verification

Fast tests use mocked HTTP/bridge objects and do not require live credentials:

```bash
python -m pytest -m "not slow"
```

Live tests require `CURSOR_API_KEY` and are marked `slow`:

```bash
python -m pytest
```

When changing local execution, run the bridge-focused tests first:

```bash
python -m pytest tests/test_bridge_streaming.py
```

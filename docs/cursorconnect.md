# CursorConnect Developer Guide

This guide documents the Python package structure and operational behavior of
CursorConnect. It complements the user-facing examples in `README.md` with
source-level intent, constraints, and troubleshooting notes for maintainers.

## Module map

| Module | Responsibility | Public surface |
|---|---|---|
| `cursorconnect.__init__` | Package exports and quick-start docstring. | `Agent`, `Run`, `Cursor`, `Mesh`, `Artifact`, `CommonModels`, exceptions. |
| `cursorconnect.agent` | High-level agent facade. | Agent creation, listing, resumption, follow-up runs, artifacts, archival, deletion. |
| `cursorconnect.run` | Single-run lifecycle and SSE parsing. | Streaming, blocking wait, cancellation, conversation history, status listeners. |
| `cursorconnect.cursor` | Account-level namespace. | `Cursor.me()`, `Cursor.models.list()`, `Cursor.repositories.list()`. |
| `cursorconnect.mesh` | Multi-agent orchestration. | Concurrent task execution, optional peer cross-checking, context-manager cleanup. |
| `cursorconnect.artifact` | Artifact metadata and downloads. | Presigned URL retrieval and byte download helpers. |
| `cursorconnect.client` | Deprecated compatibility shim plus HTTP transport. | Legacy `CursorClient`; modern modules still use its `_get`, `_post`, and `_delete` helpers internally. |
| `cursorconnect.types` | Dataclass models for API payloads. | Options, models, messages, conversation turns, run results, repositories, MCP config. |
| `cursorconnect.exceptions` | Error hierarchy and HTTP status mapping. | `CursorAgentError` and specialized subclasses with `is_retryable` and `code`. |
| `cursorconnect.runtimes` | Runtime backend protocol and concrete backend implementations. | `RuntimeBackend`, `CloudRuntime`; the protocol explicitly anticipates cloud, local, and mock backends. |
| `cursorconnect._bridge` | Local Node.js bridge to `@cursor/sdk`. | Internal `BridgeManager` used by local-runtime experiments and tests; not exported as a stable public API. |

## Architecture

CursorConnect exposes a small Python API over Cursor agent operations. The
current public facade is synchronous for REST-backed cloud calls, while the
local integration path is represented by the TypeScript SDK bridge in
`cursorconnect._bridge` and by `LocalOptions` dataclasses that mirror the SDK
runtime contract.

1. `Agent.create()` builds a JSON payload from `CloudOptions`, model selection,
   and the initial prompt, then posts to `/agents`.
2. The create response is normalized into an `Agent` instance. If the API
   returns `latestRunId`, `agent.initial_run` constructs a `Run` for that first
   execution.
3. `Agent.send()` posts to `/agents/{agent_id}/runs` and returns a `Run`.
4. `Run.stream()` consumes Server-Sent Events from
   `/agents/{agent_id}/runs/{run_id}/stream` and yields typed message
   dataclasses.
5. `Run.wait()` polls `/agents/{agent_id}/runs` until a terminal status is
   observed, then attempts to fetch conversation history.

The package intentionally keeps the public model compact:

- `Agent` owns agent lifecycle and follow-up messages.
- `Run` owns execution lifecycle.
- `Cursor` owns account-level reads.
- `Mesh` coordinates multiple `Agent` instances for parallel work.
- `RuntimeBackend` defines the backend boundary for cloud, local, and test
  runtimes.

### Runtime selection and local integration

The codebase carries both cloud and local runtime concepts:

- `CloudOptions` configures Cursor Cloud execution by forwarding repository,
  environment, branch, and PR fields to the REST API.
- `LocalOptions` models local execution settings from the Cursor TypeScript SDK:
  `cwd`, `settingSources`, and `sandboxOptions`.
- `cursorconnect._bridge.manager.BridgeManager` starts `cursorconnect/_bridge/bridge.js`
  as a Node.js subprocess. The bridge loads `@cursor/sdk`, sends newline-delimited
  JSON requests over stdin, and streams responses back over stdout.
- `live_test_local.py` exercises that bridge by creating a local SDK agent,
  sending a prompt, streaming `run.stream()`, waiting with `run.wait()`, and
  closing the agent.
- `cursorconnect.runtimes.base.RuntimeBackend` is the structural contract for
  backend implementations, and `cursorconnect.runtimes.cloud.CloudRuntime`
  implements the cloud REST backend.

When documenting local behavior, keep the distinction precise: local execution
is set up through the SDK bridge and local option types, while the high-level
`Agent.create()` implementation in `cursorconnect.agent` currently serializes
cloud REST payload fields directly.

## Public workflows

### Create an agent and wait for the initial run

```python
import os

from cursorconnect import Agent
from cursorconnect.types import CloudOptions

agent = Agent.create(
    api_key=os.environ["CURSOR_API_KEY"],
    prompt="Run the unit tests and summarize failures.",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/org/repo", "startingRef": "main"}],
        autoCreatePR=False,
    ),
    name="test-runner",
)

run = agent.initial_run
if run is None:
    raise RuntimeError("Cursor API did not return latestRunId for the created agent")

result = run.wait(timeout=300)
print(result.status)
```

Constraints:

- `Agent.create()` and `Agent.prompt()` currently include `api_key` in their
  signatures. Internally, falsey values fall back to `CURSOR_API_KEY`, but
  examples should pass an explicit key for clarity.
- `LocalOptions` mirrors the local runtime contract from `@cursor/sdk`. Use it
  when documenting local execution settings (`cwd`, `settingSources`,
  `sandboxOptions`) and keep those settings distinct from REST-only cloud
  payload fields.
- `CloudOptions.repos` entries are forwarded as dictionaries. Keep field names
  in API wire format, for example `startingRef` and `prUrl`.

### Run a local SDK agent through the Node bridge

The local runtime path is exercised through `BridgeManager`, which wraps
`cursorconnect/_bridge/bridge.js` and delegates to `@cursor/sdk`. Use this path
when a workflow should run against a local checkout rather than a cloned cloud
repository.

```python
import asyncio
import os
from pathlib import Path

from cursorconnect._bridge.manager import BridgeManager


async def main() -> None:
    bridge_path = Path("cursorconnect/_bridge/bridge.js").resolve()
    manager = BridgeManager(bridge_path=str(bridge_path))

    try:
        created = await manager.send_request(
            "Agent.create",
            args=[{
                "apiKey": os.environ["CURSOR_API_KEY"],
                "model": {"id": "composer-2"},
                "local": {
                    "cwd": str(Path.cwd()),
                    "settingSources": [],
                    "sandboxOptions": {"enabled": True},
                },
            }],
        )
        agent_id = created["agentId"]

        run_created = await manager.send_request(
            "agent.send",
            target=agent_id,
            args=["Inspect this checkout and summarize the package layout."],
        )
        run_id = run_created["runId"]

        async for update in manager.stream_request("run.stream", target=run_id):
            print(update)

        result = await manager.send_request("run.wait", target=run_id)
        print(result)

        await manager.send_request("agent.close", target=agent_id)
    finally:
        manager.close()


asyncio.run(main())
```

Operational notes:

- Install JavaScript dependencies with `npm install` before using the bridge;
  `bridge.js` requires `@cursor/sdk`.
- `BridgeManager.start()` performs a `node --version` health check and raises
  `RuntimeError` when Node.js is unavailable.
- Requests and stream events are newline-delimited JSON on stdin/stdout. Bridge
  responses use in-process IDs such as `agent_1` and `run_2`; these are bridge
  handles, not cloud `bc-...` agent IDs.
- Always close both the SDK agent (`agent.close`) and the manager process to
  avoid leaked local executor resources.

### Stream typed run events

```python
from cursorconnect.types import AssistantMessage, StatusMessage, ToolUseMessage

run = agent.send("Add tests for the parser module.")

for event in run.stream():
    if event.type is AssistantMessage:
        for block in event.message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                print(block["text"], end="")
    elif event.type is ToolUseMessage:
        print(f"\nTool {event.name}: {event.status}")
    elif event.type is StatusMessage:
        print(f"\nRun status: {event.status}")
```

`Run.stream()` recognizes these SSE event names:

- `system`
- `user`
- `assistant`
- `thinking`
- `tool_call`
- `status`
- `task`
- `request`

Unknown SSE event names are skipped by `Run.stream()`. The lower-level
`cursorconnect.types.parse_message()` helper returns the raw dictionary for an
unknown `"type"` discriminator, which preserves forward compatibility for
callers that parse already-decoded payloads.

### Coordinate parallel agents with Mesh

```python
from cursorconnect import Mesh
from cursorconnect.types import CloudOptions, MeshTask

cloud = CloudOptions(repos=[{"url": "https://github.com/org/repo"}])

with Mesh(api_key=os.environ["CURSOR_API_KEY"], cloud=cloud, cross_check=True) as mesh:
    mesh + MeshTask(name="api", prompt="Implement the API changes.")
    mesh + MeshTask(name="tests", prompt="Add focused tests for the API changes.")

    results = mesh.run(timeout=600)

for result in results:
    print(result.name, result.run_result.status, len(result.artifacts))
```

Operational notes:

- `Mesh.run()` uses a `ThreadPoolExecutor`; `max_workers` defaults to the number
  of registered tasks.
- The context manager archives created agents on exit by default. Set
  `cleanup="delete"` for destructive cleanup or `cleanup=None` to leave agents
  untouched.
- `cross_check=True` sends a follow-up message to still-running peers when a
  task finishes. A callable can be supplied to customize the message.
- Cross-check sends are fire-and-forget; their returned runs are not waited on by
  the mesh worker.

## Setup and testing

Install the Python package in editable mode:

```bash
pip install -e ".[test]"
```

Run the offline test suite:

```bash
pytest -m "not slow"
```

Run live integration tests only when a Cursor API key is available:

```bash
export CURSOR_API_KEY="crsr_..."
pytest
```

The test suite mocks `requests.Session.request` for unit tests. Slow tests create
live agents and are expected to clean them up with `delete()`.

Local bridge smoke tests are separate from the mocked REST unit tests:

```bash
npm install
export CURSOR_API_KEY="crsr_..."
python3 live_test_local.py
```

`live_test_local.py` requires a working Node.js runtime and real Cursor SDK
credentials because it launches `@cursor/sdk` through the bridge.

## Troubleshooting

### Missing API key

`Agent` and `Cursor` helpers raise `CursorAgentError` with
`code="missing_api_key"` when no explicit key is supplied and
`CURSOR_API_KEY` is unset.

### Rate limits

HTTP 429 responses map to `RateLimitError` with `is_retryable=True`.
Repository listing has stricter limits than most account reads: 1 request per
user per minute and 30 requests per user per hour.

### Terminal run operations

`Run.cancel()` raises `UnsupportedRunOperationError` if the run is already in
`FINISHED`, `ERROR`, `CANCELLED`, or `EXPIRED`.

### Artifact downloads

`Artifact.get_download_url()` returns a temporary presigned URL. If no URL is
returned, `download_content()` raises `ValueError`; HTTP download failures raise
`requests` exceptions.

### Deprecated compatibility shim

Instantiating `CursorClient` emits a `DeprecationWarning`. New integrations
should use `Agent`, `Run`, and `Cursor` directly. The shim remains in place for
legacy code and for the shared HTTP transport used by the current public
facades.

### Local TypeScript SDK bridge

`cursorconnect._bridge` starts a Node.js subprocess that loads `@cursor/sdk` and
communicates over newline-delimited JSON. It requires:

- Node.js available on `PATH` or passed as `node_bin`.
- JavaScript dependencies installed from `package.json`.
- A CommonJS-compatible `@cursor/sdk` import path.

Bridge failures are surfaced as `RuntimeError` on pending requests or stream
consumers. For local workflows, verify Node.js, JavaScript dependencies, and the
SDK import before debugging Python call sites.

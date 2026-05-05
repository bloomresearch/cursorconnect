# Agent runtime contract

This page documents the public runtime contract implemented by
`cursorconnect.agent`, `cursorconnect.run`, and
`cursorconnect._bridge.local_run`.

Use it when you need to switch between Cursor Cloud agents and local agents
without changing orchestration code.

## Module map

| Module | Responsibility |
|---|---|
| `cursorconnect.agent` | Public `Agent` facade, runtime selection, cloud payload construction, local bridge delegation |
| `cursorconnect.run` | Cloud `Run` implementation: SSE streaming, polling, cancellation, conversation history |
| `cursorconnect._bridge.local_run` | Local `LocalRun` adapter with the same public methods as `Run` |
| `cursorconnect.types.run_protocol` | Structural `RunProtocol` shared by cloud and local run handles |
| `cursorconnect.types.options` | `CloudOptions`, `LocalOptions`, and per-send `SendOptions` dataclasses |

## Runtime selection

`Agent.create()` and `Agent.prompt()` select the runtime from keyword
arguments:

- Pass `cloud=CloudOptions(...)` for Cursor Cloud execution.
- Pass `local=LocalOptions(...)` for local execution through the Node.js
  bridge.
- Passing both `cloud` and `local` to `Agent.create()` raises `ValueError`.
- Passing neither uses the cloud path and requires an API key.

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions, LocalOptions

cloud_agent = Agent.create(
    api_key="crsr_...",
    prompt="Run the test suite and fix failures",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/org/project", "startingRef": "main"}],
        autoCreatePR=True,
    ),
)

local_agent = Agent.create(
    prompt="Inspect this checkout and summarize the package layout",
    local=LocalOptions(cwd="/path/to/project", settingSources=["project", "user"]),
)
```

## Shared run interface

Both runtimes return objects satisfying `RunProtocol`.

| Member | Behavior |
|---|---|
| `run.id` | Runtime-specific run identifier, or `None` before it is populated |
| `run.agent_id` | Owning agent identifier |
| `run.status` | Current status, updated by polling, streaming status events, or cancellation |
| `run.stream()` | Synchronous generator yielding typed message events |
| `run.wait(timeout=None, poll_interval=1.5)` | Blocks until a terminal status and returns `RunResult` |
| `run.cancel()` | Cancels an active run; terminal runs raise `UnsupportedRunOperationError` |
| `run.conversation()` | Returns typed conversation history |
| `run.on_status_change(callback)` | Registers a listener for status transitions |

Terminal statuses are `FINISHED`, `ERROR`, `CANCELLED`, and `EXPIRED`.

```python
from cursorconnect import Agent
from cursorconnect.types import AssistantMessage, StatusMessage
from cursorconnect.types import LocalOptions

run = Agent.prompt(
    message="Explain the migration plan and stop",
    local=LocalOptions(cwd="/path/to/project"),
)

for event in run.stream():
    if event.type is AssistantMessage:
        for block in event.message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                print(block.get("text", ""), end="")
    elif event.type is StatusMessage:
        print(f"\nstatus={event.status}")
```

## Cloud-only operations

The following `Agent` methods call Cursor Cloud API endpoints and are not
supported for local agents:

- `reload()`
- `archive()`
- `unarchive()`
- `delete()`
- `list_artifacts()`
- `download_artifact(path)`

Local agents support `close()`, which sends `agent.close` through the bridge
and marks the local facade as `CLOSED`. Cloud agents implement `close()` as an
alias for `archive()`.

## Payload constraints

`Agent.create()` only serializes option fields that are not `None`.

Cloud options:

- `repos`: list of repository dictionaries, usually including `url` and
  optionally `startingRef` or `prUrl`.
- `env`: cloud environment dictionary.
- `workOnCurrentBranch`, `autoCreatePR`, `skipReviewerRequest`: booleans passed
  through to the API when set.

Local options:

- `cwd`: string or list of strings for the local working directory context.
- `settingSources`: list containing values such as `project`, `user`, `team`,
  `mdm`, `plugins`, or `all`.
- `sandboxOptions`: dictionary passed through to the TypeScript SDK.

Model selection accepts either a raw model id string or `ModelSelection`. When
`ModelSelection.resolved_params` is populated, params are serialized as
`{"id": ..., "value": ...}` objects.

## Operational notes

- Cloud authentication resolves from `api_key=` or `CURSOR_API_KEY`.
- Local agent creation passes `apiKey` to the TypeScript SDK only when a key is
  available.
- `Run.wait()` fetches conversation history after a terminal status; if that
  retrieval fails, the returned `RunResult.conversation` is `None`.
- Status listener exceptions are suppressed so observers cannot interrupt run
  handling.
- `SendOptions` currently applies per-send `model` overrides. `mcpServers`,
  `onStep`, `onDelta`, and `local` are defined as dataclass fields but are not
  wired through by the Python `Agent.send()` implementation.

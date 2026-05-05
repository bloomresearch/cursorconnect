<p align="center">
  <h1 align="center">CursorConnect</h1>
  <p align="center">
    <strong>The Unofficial Python SDK for Cursor Agents</strong>
  </p>
  <p align="center">
    Orchestrate cloud and local AI coding agents from Python.<br />
    One import. Full control. Both runtimes.
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/cursorconnect/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/cursorconnect?color=blue"></a>
  <a href="https://pypi.org/project/cursorconnect/"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/cursorconnect"></a>
  <a href="https://github.com/bloomresearch/cursorconnect/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/github/license/bloomresearch/cursorconnect"></a>
  <a href="https://github.com/bloomresearch/cursorconnect/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/bloomresearch/cursorconnect?style=social"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#two-runtimes-one-interface">Runtimes</a> &middot;
  <a href="#design-philosophy">Design Philosophy</a> &middot;
  <a href="#examples">Examples</a> &middot;
  <a href="#api-reference">API Reference</a> &middot;
  <a href="#module-docs">Module Docs</a>
</p>

---

## What is CursorConnect?

CursorConnect is the Python interface to Cursor's agent infrastructure. It lets you **programmatically create, control, and orchestrate AI coding agents** from any Python script, notebook, or backend service, whether those agents run in Cursor's cloud or locally on your own machine.

With CursorConnect you can:

- **Spin up agents** that read your repos, write code, create PRs, and run commands
- **Choose your runtime**: cloud agents execute on Cursor's infrastructure; local agents run as a subprocess on your machine with direct filesystem access
- **Stream output** token-by-token as typed Python objects, including the agent's internal reasoning
- **Orchestrate in parallel** with the Mesh layer: dispatch multiple specialist agents, let them cross-check each other's work in real time, and collect structured results - **New! CursorConnect Only**
- **Send follow-up instructions** to refine work across multiple conversational turns
- **Manage your fleet**: list, archive, resume, or delete agents programmatically
- **Query your account**: see available models, connected repositories, and API key metadata

All of this through a clean, Pythonic interface that hides the underlying REST endpoints, SSE framing, Node.js bridge, and HTTP authentication behind three core concepts: `Agent`, `Run`, and `Mesh`.

---

## Installation

```bash
pip install cursorconnect
```

Or install from source:

```bash
git clone https://github.com/bloomresearch/cursorconnect.git
cd cursorconnect
pip install -e .
```

**Requirements:** Python 3.8+ and `requests>=2.28` (installed automatically).

**For local agents only:** Node.js 18+ must be installed on your system. The first time you create a local agent, CursorConnect automatically installs `@cursor/sdk` into a private `node_modules` inside the package -- no manual npm setup required. You can also run the setup proactively:

```bash
cursorconnect setup-local    # check Node.js and install @cursor/sdk
cursorconnect status         # show local runtime diagnostic info
```

Cloud agents have no additional requirements beyond Python and an API key.

---

## Two Runtimes, One Interface

CursorConnect supports two execution modes. The `Agent` API is the same regardless of which you choose, so you can develop locally and deploy to the cloud (or vice versa) without changing your orchestration code.

### Cloud Runtime

Cloud agents run on Cursor's managed infrastructure. You provide a GitHub repo URL, the agent clones it in a sandboxed environment, does its work, and can open a PR when it finishes. This is the zero-setup path: no local dependencies beyond Python and an API key.

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions

agent = Agent.create(
    api_key="crsr_...",
    prompt="Add comprehensive type hints to all public functions in src/utils.py",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/your-org/your-repo"}],
        autoCreatePR=True,
    ),
)
```

> See more examples in the [Examples](#examples) section, or browse the full [API Reference](#api-reference).

### Local Runtime

Local agents run as a subprocess on your machine via a Node.js bridge to the TypeScript `@cursor/sdk`. The agent operates directly on your local filesystem, which means it can access private files and integrate with local tooling, dev servers, and databases that aren't reachable from the cloud.

```python
from cursorconnect import Agent
from cursorconnect.types import LocalOptions

agent = Agent.create(
    prompt="Refactor the utils module to use pathlib instead of os.path",
    local=LocalOptions(cwd="/path/to/your/project"),
    model="claude-sonnet-4-6",
)

# agent.initial_run returns a RunProtocol (Run or LocalRun)
run = agent.initial_run
if run:
    result = run.wait()
    print(f"Done: {result.status}")
```

Same `Agent` class, same `Run` interface, same `stream()` and `wait()` methods. The SDK detects that you passed `local` instead of `cloud` and routes through the Node.js bridge automatically. Under the hood, the bridge communicates with the TypeScript SDK using newline-delimited JSON over stdin/stdout, handles streaming, and automatically restarts if the subprocess crashes.

For the module-level runtime contract and local bridge runbook, see
[`docs/cursorconnect/agent-runtime.md`](docs/cursorconnect/agent-runtime.md) and
[`docs/cursorconnect/local-runtime.md`](docs/cursorconnect/local-runtime.md).

### When to Use Which

| | Cloud | Local |
|---|---|---|
| **Setup** | API key only | Node.js + `@cursor/sdk` |
| **Filesystem** | Clones from GitHub | Direct access to local files |
| **Network** | Runs on Cursor's infra | Runs on your machine with access to local resources |
| **Best for** | CI/CD pipelines, batch operations across repos, PR automation | Interactive development, private codebases, local tool integration |

---

## Quick Start

### 1. Get your API key

Generate a Cursor API key from your [Cursor Settings](https://www.cursor.com/settings). Set it as an environment variable:

```bash
export CURSOR_API_KEY="crsr_your_key_here"
```

Or pass it directly to any method via the `api_key` parameter.

### 2. Fire-and-forget: one prompt, one result

The fastest path from idea to execution. `Agent.prompt()` creates an agent, sends your message, and hands you back a `Run` you can wait on:

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions

run = Agent.prompt(
    api_key="crsr_...",
    message="Add comprehensive type hints to all public functions in src/utils.py",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/your-org/your-repo"}],
        autoCreatePR=True,
    ),
)

result = run.wait()
print(f"Done: {result.status}")  # "FINISHED"

# See what the agent actually did
conv = result.conversation
print(conv.text)  # all assistant output as a single string
print(conv)       # full formatted conversation with turns and roles
```

That's it. The agent clones your repo, makes the changes, opens a PR, and you get a structured result object back. Every `RunResult` carries a `.conversation` property that gives you the complete, typed history of the run so you can inspect, log, or post-process what happened.

### 3. Multi-turn conversation

For iterative workflows, create a persistent agent and send multiple rounds of instructions:

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions

agent = Agent.create(
    api_key="crsr_...",
    prompt="Set up a FastAPI project with SQLAlchemy and Alembic",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/your-org/backend"}],
    ),
)

run1 = agent.send("Add JWT-based authentication with refresh tokens")
result1 = run1.wait()

run2 = agent.send("Now add role-based access control with admin and user roles")
result2 = run2.wait()

# Each result carries the conversation from that run
print(f"Round 1: {len(result1.conversation)} turns")
print(f"Round 2: {len(result2.conversation)} turns")
print(result2.conversation.text)

for artifact in agent.list_artifacts():
    print(f"  {artifact.path}  ({artifact.size_bytes} bytes)")
```

### 4. Parallel Agent Mesh

This is what the SDK unlocks that the Cursor UI can't do. In the app, you run one agent at a time. With CursorConnect, you can **decompose a feature into subtasks, dispatch parallel agents, and have them cross-check each other's work in real time as each one finishes**.

The Mesh is an orchestration layer that manages the full lifecycle: concurrent dispatch, optional peer-to-peer broadcasting, and automatic cleanup. As each agent completes, the Mesh sends a summary of what it built to the agents still running, so they can reconcile conflicts against their own output before they finish. The last agent to complete has seen everyone else's work.

```python
from cursorconnect import Mesh, CommonModels
from cursorconnect.types import CloudOptions, MeshTask

REPO = "https://github.com/your-org/saas-app"

auth_task = MeshTask(
    name="auth-agent",
    prompt=(
        "Implement a complete JWT authentication system: refresh tokens, "
        "middleware, login/register endpoints, and password hashing with bcrypt. "
        "Work only in src/auth/."
    )
)

billing_task = MeshTask(
    name="billing-agent",
    prompt=(
        "Integrate Stripe billing: subscription creation, webhook handlers, "
        "usage metering, and a customer portal redirect endpoint. "
        "Work only in src/billing/."
    )
)

rbac_task = MeshTask(
    name="rbac-agent",
    prompt=(
        "Build a role-based access control system with roles (admin, member, viewer), "
        "permission decorators, and a roles database migration. "
        "Work only in src/rbac/."
    )
)

with Mesh(
    cloud=CloudOptions(repos=[{"url": REPO}], autoCreatePR=True),
    model="claude-sonnet-4-6",
    cross_check=True,
) as mesh:

    mesh + auth_task + billing_task + rbac_task

    print("Dispatching 3 specialist agents in parallel...\n")

    for result in mesh():
        print(f"  {result.name}: {result.run_result.status} "
              f"({len(result.artifacts)} files produced)")
```

What happens at runtime:

1. All three agents start building simultaneously.
2. The **auth-agent** finishes first. The Mesh immediately sends a cross-check message to billing and RBAC: *"Peer task 'auth-agent' finished... Please review your own work for any conflicts."*
3. The **billing-agent** finishes next. The Mesh notifies the RBAC agent.
4. The **rbac-agent** finishes last, but by now it has already seen both other agents' summaries. Its final pass reconciles migration ordering, ensures its permission decorators compose correctly with the auth middleware, and avoids route collisions the billing agent introduced.
5. The context manager calls `agent.close()` on all created agents on exit, ensuring they are archived and resources are released.

The result: a complex multi-system feature built in parallel, where integration bugs are resolved during construction rather than discovered afterward.

---

## Design Philosophy

### Agents, Runs, and Messages

These three concepts form the backbone of the SDK:

- **Agent** is a persistent AI coding session. Think of it as a developer you've hired: it has context, memory, and a workspace. You create one, give it instructions, and it gets to work. An agent persists between messages and can handle multiple rounds of conversation.

- **Run** is a single unit of work within an agent. Every time you send a message, a new run is created (satisfying the `RunProtocol`). The run streams its progress as events, eventually reaching a terminal state (`FINISHED`, `ERROR`, `CANCELLED`, or `EXPIRED`). You can stream it, wait for it, or cancel it.

- **Messages** are the typed events that flow back from a run. Rather than giving you raw JSON, CursorConnect parses every event into a specific Python dataclass. When the agent is reasoning, you get a `ThinkingMessage`. When it speaks, an `AssistantMessage`. When it invokes a tool, a `ToolUseMessage`. Every event exposes a `type` property that returns its own class, enabling clean `event.type is AssistantMessage` checks instead of verbose `isinstance()` calls.

### Runtime-Agnostic by Design

The SDK is built around a structural `RunProtocol` that decouples the agent domain model from the transport layer. The cloud runtime speaks HTTP to Cursor's REST API. The local runtime bridges to the TypeScript SDK via a Node.js subprocess. Both present the same interface, so switching between them doesn't require rewriting your orchestration logic.

### Typed All the Way Down

Every API response is deserialized into a Python dataclass with explicit fields, not a nested dictionary you have to spelunk through. Model configurations, repository metadata, conversation turns, run results, and artifacts all have dedicated types with documented fields. This means fewer runtime surprises and full IDE autocompletion from day one.

### Minimal Dependencies, Maximum Clarity

The entire SDK depends only on `requests` for the cloud runtime. No async framework lock-in, no heavy abstractions, no magic. The `Agent` class is the entry point for agent work. The `Cursor` namespace handles account-level queries. The `Mesh` orchestrates parallel execution. The `Run` gives you full control over individual units of work. Four concepts, and you're productive.

### Errors That Tell You What to Do

Every HTTP error is mapped to a specific exception subclass with an `is_retryable` flag. A `RateLimitError` tells you to back off. An `AuthenticationError` tells you to check your key. A `ConfigurationError` tells you your request was malformed. You never have to parse status codes or guess what went wrong.

### Environment-First Authentication

Every method that needs an API key accepts an optional `api_key` parameter. If you omit it, the SDK automatically reads `CURSOR_API_KEY` from your environment. This means zero credential management in application code while still allowing explicit overrides for multi-tenant or testing scenarios.

---

## Examples

### Automated Code Review Bot

Build a bot that reviews PRs and posts feedback:

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions

def review_pr(repo_url: str, branch: str):
    """Spin up an agent to review code on a feature branch."""
    run = Agent.prompt(
        message=(
            f"Review the changes on branch '{branch}'. "
            "Focus on security vulnerabilities, performance issues, "
            "and deviation from the project's coding standards. "
            "Provide a summary with severity ratings."
        ),
        cloud=CloudOptions(
            repos=[{"url": repo_url, "startingRef": branch}],
        ),
    )
    result = run.wait(timeout=300)

    if result.status == "FINISHED" and result.conversation:
        print(f"Review complete ({len(result.conversation)} turns):\n")
        # .text gives you all assistant text concatenated across turns
        print(result.conversation.text)
    elif result.status == "ERROR":
        print(f"Review failed: {result.error_message}")

review_pr("https://github.com/your-org/app", "feature/user-auth")
```

### Batch Refactoring Across Multiple Repos

Apply a consistent change across your entire organization:

```python
from cursorconnect import Agent, CommonModels
from cursorconnect.types import CloudOptions

repos = [
    "https://github.com/your-org/service-a",
    "https://github.com/your-org/service-b",
    "https://github.com/your-org/service-c",
]

agents = []
for repo in repos:
    agent = Agent.create(
        prompt=(
            "Upgrade all Python logging to use structured logging with structlog. "
            "Replace print() calls with proper log levels. "
            "Add a structlog configuration module if one doesn't exist."
        ),
        cloud=CloudOptions(
            repos=[{"url": repo}],
            autoCreatePR=True,
        ),
        model="claude-sonnet-4-6",
        name=f"structlog-migration-{repo.split('/')[-1]}",
    )
    agents.append(agent)
    print(f"Started agent for {repo}: {agent.agent_id}")

for agent in agents:
    agent.reload()
    print(f"  {agent.name}: {agent.status}")
```

### Interactive Development Assistant

Build a REPL-style loop for conversational coding:

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions, AssistantMessage

agent = Agent.create(
    prompt="You are working on a Python CLI tool. The repo is ready.",
    cloud=CloudOptions(
        repos=[{"url": "https://github.com/your-org/cli-tool"}],
    ),
)
print(f"Agent ready: {agent.agent_id}\n")

while True:
    user_input = input("You: ").strip()
    if user_input.lower() in ("quit", "exit"):
        agent.close()
        print("Session closed.")
        break

    run = agent.send(user_input)
    print("Agent: ", end="")
    for event in run.stream():
        if event.type is AssistantMessage:
            content = event.message.get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    print(block.get("text", ""), end="")
    print("\n")
```

### Reading Conversation History

After a run completes, retrieve the full conversation as typed Python objects. The `Conversation` supports `print()`, `.text`, iteration, indexing, and `len()`:

```python
from cursorconnect import Agent
from cursorconnect.types import LocalOptions
from cursorconnect.types.conversation import AgentConversationTurn, AssistantContent

agent = Agent.create(
    prompt="Explain the observer pattern in three sentences.",
    local=LocalOptions(cwd="/path/to/project"),
    model="gemini-3-flash",
)

result = agent.initial_run.wait()
conv = result.conversation

# Quick: print the entire conversation
print(conv)

# Just the assistant's text across all turns
print(conv.text)

# Walk the structure for fine-grained access
for turn in conv:
    if isinstance(turn.turn, AgentConversationTurn):
        for step in turn.turn.steps:
            if isinstance(step.message, AssistantContent):
                print(f"Assistant said: {step.message.text[:80]}...")

agent.close()
```

### Downloading Build Artifacts

Retrieve files the agent produced during its run:

```python
from cursorconnect import Agent

agent = Agent.get(api_key="crsr_...", agent_id="bc-xxxxxxxx")

artifacts = agent.list_artifacts()
for artifact in artifacts:
    print(f"{artifact.path} ({artifact.size_bytes} bytes)")
    content = artifact.download_content()
    with open(f"./downloads/{artifact.path}", "wb") as f:
        f.write(content)
    print(f"  Saved to ./downloads/{artifact.path}")
```

### Monitoring with Status Callbacks

React to run state changes as they happen:

```python
from cursorconnect import Agent
from cursorconnect.types import CloudOptions
import time

    run = Agent.prompt(
        message="Run the full test suite and fix any failing tests",
        cloud=CloudOptions(
            repos=[{"url": "https://github.com/your-org/app"}],
        ),
        model="claude-sonnet-4-6",
    )

def on_status(new_status):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] Run status changed to: {new_status}")

run.on_status_change(on_status)

for event in run.stream():
    pass

print(f"Final status: {run.status}")
```

### Exploring Your Account

Discover what models and repositories are available:

```python
from cursorconnect import Cursor

user = Cursor.me()
print(f"API Key: {user.api_key_name}")
print(f"Email:   {user.user_email}")
print(f"Created: {user.created_at}")

models = Cursor.models.list()
for model in models:
    print(f"  {model.id}: {model.displayName}")
    if model.parameters:
        for param in model.parameters:
            print(f"    param: {param.id} = {param.values}")

repos = Cursor.repositories.list()
for repo in repos:
    visibility = "private" if repo.is_private else "public"
    print(f"  {repo.name} ({visibility}) - {repo.default_branch}")
```

### Agent Fleet Management

List, filter, and clean up your agents:

```python
from cursorconnect import Agent

result = Agent.list(api_key="crsr_...", limit=50, include_archived=False)
print(f"Active agents: {len(result.items)}")

for agent in result.items:
    print(f"  {agent.agent_id} | {agent.name} | {agent.status}")

for agent in result.items:
    if agent.status == "ACTIVE" and "migration" in (agent.name or ""):
        agent.archive()
        print(f"  Archived: {agent.name}")

page = Agent.list(api_key="crsr_...", limit=10)
all_agents = list(page.items)

while page.nextCursor:
    page = Agent.list(api_key="crsr_...", limit=10, cursor=page.nextCursor)
    all_agents.extend(page.items)

print(f"Total agents across all pages: {len(all_agents)}")
```

---

## API Reference

### `Agent` -- The Core Interface

| Method | Type | Returns | Description |
|---|---|---|---|
| `Agent.create(prompt, *, api_key, cloud, local, model, name)` | class | `Agent` | Create a new agent and enqueue its first run |
| `Agent.prompt(message, *, api_key, cloud, local, model, name)` | class | `RunProtocol` | One-shot: create agent and return the initial run |
| `Agent.get(api_key, agent_id)` | class | `Agent` | Retrieve an existing agent by ID |
| `Agent.resume(api_key, agent_id)` | class | `Agent` | Alias for `get` (semantic clarity for resumption) |
| `Agent.list(api_key, *, limit, cursor, pr_url, include_archived)` | class | `ListResult[Agent]` | Paginated listing of your agents |
| `agent.send(message, options)` | instance | `RunProtocol` | Send a follow-up message, get a new run |
| `agent.run(message, *, timeout, poll_interval)` | instance | `RunResult` | Send a message and block until completion |
| `agent.reload()` | instance | `Agent` | Refresh metadata from the API (Cloud only) |
| `agent.archive()` / `agent.unarchive()` | instance | `None` | Toggle archived state (Cloud only) |
| `agent.close()` | instance | `None` | Archive the agent (alias) |
| `agent.delete()` | instance | `None` | Permanently delete the agent (Cloud only) |
| `agent.list_artifacts()` | instance | `list[Artifact]` | List files produced by the agent (Cloud only) |
| `agent.download_artifact(path)` | instance | `str` | Get a presigned download URL (Cloud only) |
| `agent.initial_run` | property | `RunProtocol \| None` | The run created alongside the agent |

### `Run` -- Execution Control

| Method / Property | Returns | Description |
|---|---|---|
| `run.stream()` | `Generator[Message]` | Yield typed SSE events in real time |
| `run.wait(timeout, poll_interval)` | `RunResult` | Block until the run finishes |
| `run.cancel()` | `None` | Cancel an active run |
| `run.conversation()` | `Conversation` | Full conversation history for this run |
| `run.on_status_change(callback)` | `None` | Register a status-change listener |
| `run.status` | `str \| None` | Current status (reactive property) |
| `run.id` | `str \| None` | The run's unique identifier |

### `Mesh` -- Parallel Orchestration

| Method / Property | Returns | Description |
|---|---|---|
| `Mesh(*, cloud, model, cross_check, cleanup, ...)` | `Mesh` | Create an orchestrator with shared config |
| `mesh.add(task)` or `mesh + task` | `Mesh` | Register a `MeshTask` for execution |
| `mesh.run(timeout)` or `mesh()` | `list[MeshResult]` | Dispatch all tasks and collect results |
| `mesh.results` | `list[MeshResult]` | Access results after execution |

### `Cursor` -- Account Operations

| Method | Returns | Description |
|---|---|---|
| `Cursor.me(api_key)` | `User` | Your API key name, email, and creation date |
| `Cursor.models.list(api_key)` | `list[ModelListItem]` | Available models with parameters and variants |
| `Cursor.repositories.list(api_key)` | `list[Repository]` | Connected GitHub repositories |

### Local Runtime

Local agents use the same `Agent` class. Pass `local=LocalOptions(...)` instead of `cloud=CloudOptions(...)` and the SDK handles everything internally through the Node.js bridge to the TypeScript SDK. No additional imports or setup required.

For setup internals, diagnostics, and troubleshooting, see
[`docs/cursorconnect/local-runtime.md`](docs/cursorconnect/local-runtime.md).

### `Artifact` -- File Access

| Method / Property | Returns | Description |
|---|---|---|
| `artifact.path` | `str` | Relative file path |
| `artifact.size_bytes` | `int` | File size |
| `artifact.get_download_url()` | `str` | Presigned S3 URL (valid ~15 min) |
| `artifact.download_content()` | `bytes` | Raw file content |

---

## Module Docs

Focused, module-aligned documentation lives under `docs/cursorconnect/`:

- [`agent-runtime.md`](docs/cursorconnect/agent-runtime.md) documents the
  shared `Agent` / `RunProtocol` contract across cloud and local execution.
- [`local-runtime.md`](docs/cursorconnect/local-runtime.md) documents the
  `cursorconnect._bridge` setup lifecycle, bridge protocol, and local runtime
  troubleshooting.

---

## Streaming Event Types

Every event from `run.stream()` is a typed dataclass with a `type` property that returns its own class. This lets you identify events with clean `is` checks:

```python
if event.type is AssistantMessage:
    ...
```

| Type | What It Represents |
|---|---|
| `AssistantMessage` | The agent's written response (text, code, explanations) |
| `ThinkingMessage` | The agent's internal reasoning before acting |
| `ToolUseMessage` | A tool invocation (file edit, shell command, etc.) with status and result |
| `StatusMessage` | A lifecycle transition (RUNNING, FINISHED, ERROR, etc.) |
| `UserMessageEvent` | Echo of the user's original message |
| `SystemMessage` | System-level metadata (model info, available tools) |
| `TaskMessage` | Sub-task progress within the current run |
| `RequestMessage` | A request for additional input or confirmation |

All event types share `agent_id` and `run_id` fields, so you can always identify which agent and run produced them.

### Conversation & Structural Types

These are not streaming events but typed containers you work with after a run completes:

| Type | What It Represents |
|---|---|
| `Conversation` | Typed container for the full history of a run, returned by `run.conversation()` |
| `ConversationTurn` | A single turn wrapping either an `AgentConversationTurn` or `ShellConversationTurn` |
| `ConversationStep` | One step within an agent turn (assistant message, thinking, or tool call) |
| `AssistantContent` | The assistant's text output within a conversation step |
| `ThinkingContent` | The model's internal reasoning within a conversation step |
| `ToolCallContent` | A tool invocation recorded as a conversation step |
| `RunProtocol` | Structural protocol satisfied by both cloud `Run` and local `LocalRun` |
| `ModelParameters` | Ergonomic builder for model params (e.g. `ModelParameters(thinking="high")`) |

---

## Configuration Types

```python
from cursorconnect import CommonModels
from cursorconnect.types import (
    CloudOptions,
    LocalOptions,
    ModelSelection,
    ModelParameters,
    ModelParameterValue,
)

# Cloud: agent runs on Cursor's infrastructure with access to a GitHub repo
cloud = CloudOptions(
    repos=[{"url": "https://github.com/org/repo", "startingRef": "main"}],
    autoCreatePR=True,
    workOnCurrentBranch=False,
)

# Local: agent runs on your machine with direct filesystem access
local = LocalOptions(
    cwd="/path/to/your/project",
    settingSources=["project", "user"],
)

# Model selection: pass a string shorthand or a full ModelSelection
agent1 = Agent.create(
    prompt="Optimize the database queries",
    cloud=cloud,
    model="claude-sonnet-4-6",
)

# Use ModelSelection with thinking shorthand
model = ModelSelection("claude-sonnet-4-6", thinking="high")

# Or build parameters incrementally with ModelParameters
params = ModelParameters()
params.thinking = "high"
agent2 = Agent.create(
    prompt="Optimize the database queries",
    cloud=cloud,
    model=ModelSelection("claude-sonnet-4-6", params=params),
    name="query-optimizer",
)
```

---

## Error Handling

CursorConnect maps every API failure to a specific, actionable exception:

```python
from cursorconnect import Agent
from cursorconnect.exceptions import (
    AuthenticationError,
    RateLimitError,
    ConfigurationError,
    NetworkError,
    CursorAgentError,
)

try:
    agent = Agent.create(api_key="crsr_...", prompt="Hello")
except AuthenticationError:
    print("Bad API key. Check your credentials.")
except RateLimitError as e:
    print(f"Slow down! Retryable: {e.is_retryable}")
except ConfigurationError as e:
    print(f"Bad request: {e.message}")
except NetworkError:
    print("Network issue. Check your connection.")
except CursorAgentError as e:
    print(f"Unexpected error: {e.message} (retryable: {e.is_retryable})")
```

**Exception hierarchy:**

```
CursorAgentError             Base class for all SDK errors
  +-- AuthenticationError     HTTP 401 / 403 - invalid or expired credentials
  +-- RateLimitError          HTTP 429 - too many requests (is_retryable=True)
  +-- ConfigurationError      HTTP 400 - malformed request or missing params
  |     +-- IntegrationNotConnectedError   A required integration is not linked
  +-- NetworkError            Connection failures, timeouts (is_retryable=True)
  +-- UnsupportedRunOperationError   Invalid operation on a terminal run
  +-- UnknownAgentError       HTTP 5xx or unexpected errors (is_retryable=True)
```

Every exception carries `message`, `is_retryable`, `code`, and `cause` attributes so you can build robust retry logic without guessing.

---

## Testing

The test suite uses `pytest` and includes both fast unit tests (mocked HTTP) and slow integration tests (live API):

```bash
# Run fast unit tests only
pytest -m "not slow"

# Run everything (requires CURSOR_API_KEY in .env or environment)
pytest
```

To set up your test environment:

```bash
pip install -e ".[test]"
echo "CURSOR_API_KEY=crsr_your_key_here" > .env
```

---

## License

MIT License. See [LICENSE](https://github.com/bloomresearch/cursorconnect/blob/main/LICENSE) for details.

---

<p align="center">
  Built for developers who'd rather write Python than curl commands.
</p>

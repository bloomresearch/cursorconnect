<p align="center">
  <h1 align="center">CursorConnect</h1>
  <p align="center">
    <strong>The Python SDK for Cursor Cloud Agents</strong>
  </p>
  <p align="center">
    Create, orchestrate, and stream AI coding agents from Python.
    <br />
    One import. One API key. Full control.
  </p>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#design-philosophy">Design Philosophy</a> &middot;
  <a href="#examples">Examples</a> &middot;
  <a href="#api-reference">API Reference</a> &middot;
  <a href="#error-handling">Error Handling</a>
</p>

---

## What is CursorConnect?

CursorConnect lets you **programmatically control Cursor's Cloud Agents** from any Python script, notebook, or backend service. Think of it as your remote control for an AI developer that can read your repos, write code, create PRs, and stream its thought process back to you in real time.

With CursorConnect you can:

- **Spin up an agent** with a single function call and point it at any GitHub repo
- **Stream its output** token-by-token as typed Python objects
- **Send follow-up instructions** to refine its work across multiple turns
- **Wait for completion**, then inspect the conversation history and download artifacts
- **Manage your fleet** of agents: list, archive, resume, or delete them
- **Query your account**: see available models, connected repositories, and API key metadata

All of this through a clean, Pythonic interface that requires zero knowledge of REST endpoints, SSE framing, or HTTP authentication.

---

## Installation

```bash
pip install cursorconnect
```

Or install from source:

```bash
git clone https://github.com/your-org/cursorconnect.git
cd cursorconnect
pip install -e .
```

**Requirements:** Python 3.8+ and `requests>=2.28` (installed automatically).

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
```

That's it. The agent clones your repo, makes the changes, opens a PR, and you get a structured result object back.

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
run1.wait()

run2 = agent.send("Now add role-based access control with admin and user roles")
run2.wait()

for artifact in agent.list_artifacts():
    print(f"  {artifact.path}  ({artifact.size_bytes} bytes)")
```

### 4. Real-time streaming: Parallel Agent Mesh

This is what the SDK unlocks that the Cursor UI can't do. In the app, you run one agent at a time. With the SDK, you can **decompose a feature into subtasks, dispatch parallel agents, and have them cross-check each other's work in real time as each one finishes** — all from a single Python script.

The key insight: as each agent completes, the `Mesh` orchestrator automatically broadcasts a summary of what it built to the agents still working. Those agents receive the update as their next turn and immediately run a conflict check against their own output. The last agent to finish has seen *everyone* else's work, so integration issues are caught and resolved during the build — not after it.

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
    model=CommonModels.CLAUDE_4_6_SONNET,
    cross_check=True,  # Enable real-time peer broadcast
) as mesh:
    
    # You can add tasks using the .add() method or the + operator:
    mesh + auth_task + billing_task + rbac_task

    print("Dispatching 3 specialist agents in parallel...\n")
    
    # mesh() is a shorthand for mesh.run()
    for result in mesh():
        print(f"  {result.name}: {result.run_result.status} "
              f"({len(result.artifacts)} files produced)")
```

What happens at runtime:

1. All three agents start building simultaneously — auth, billing, and RBAC.
2. The **auth-agent** finishes first. The Mesh immediately sends a cross-check message to the billing and RBAC agents: *"Peer task 'auth-agent' finished... Please review your own work for any conflicts."*
3. The **billing-agent** finishes next. The Mesh notifies the RBAC agent (the only one still working).
4. The **rbac-agent** finishes last — but by now it has already seen both other agents' summaries. Its final pass automatically reconciles migration ordering, ensures its permission decorators compose correctly with the auth middleware, and avoids the route collisions the billing agent introduced.
5. Finally, the context manager `with Mesh(...)` safely archives all created agents, ensuring no orphaned agents are left behind.

The result: a complex multi-system feature built in parallel, where **integration bugs are resolved during construction, not discovered afterward**, all with practically zero boilerplate.

---

## Design Philosophy

CursorConnect is built around a few core principles that shape every API decision.

### Agents, Runs, and Messages

These three concepts form the backbone of the SDK:

- **Agent** is a persistent AI coding session. Think of it as a developer you've hired: it has context, memory, and a workspace (your repo). You create one, give it instructions, and it gets to work. An agent can handle multiple rounds of conversation and persists between messages.

- **Run** is a single unit of work within an agent. Every time you send a message, a new run is created. The run streams its progress as events, eventually reaching a terminal state (`FINISHED`, `ERROR`, `CANCELLED`, or `EXPIRED`). You can stream it, wait for it, or cancel it.

- **Messages** are the typed events that flow back from a run. Rather than giving you raw JSON blobs, CursorConnect parses every Server-Sent Event into a specific Python dataclass. When the agent is reasoning, you get a `ThinkingMessage`. When it speaks, you get an `AssistantMessage`. When it invokes a tool (editing a file, running a command), you get a `ToolUseMessage`. Every event exposes a `type` property that returns its own class, so you can identify events with clean `event.type is AssistantMessage` checks instead of verbose `isinstance()` calls.

### Typed All the Way Down

Every API response is deserialized into a Python dataclass with explicit fields, not a nested dictionary you have to spelunk through. Model configurations, repository metadata, conversation turns, run results, and artifacts all have dedicated types with documented fields. This means fewer runtime surprises and full IDE support from day one.

### Minimal Dependencies, Maximum Clarity

The entire SDK depends only on `requests`. No async framework lock-in, no heavy abstractions, no magic. The `Agent` class is the entry point for everything agent-related. The `Cursor` namespace handles account-level queries. The `Run` object gives you full control over execution. Three concepts, three classes, and you're productive.

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
        last_turn = result.conversation[-1]
        print("Review complete:")
        print(last_turn)
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
        model=CommonModels.CLAUDE_4_6_SONNET,
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
            for block in event.message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    print(block["text"], end="")
    print("\n")
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
)

def on_status(new_status):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] Run status changed to: {new_status}")

run.on_status_change(on_status)

for event in run.stream():
    pass  # Status callbacks fire as events arrive

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

### `Agent` — The Core Interface

| Method | Type | Returns | Description |
|---|---|---|---|
| `Agent.create(api_key, prompt, *, cloud, local, model, name)` | class | `Agent` | Create a new agent and enqueue its first run |
| `Agent.prompt(api_key, message, *, cloud, local, model, name)` | class | `Run` | One-shot: create agent and return the initial run |
| `Agent.get(api_key, agent_id)` | class | `Agent` | Retrieve an existing agent by ID |
| `Agent.resume(api_key, agent_id)` | class | `Agent` | Alias for `get` (semantic clarity for resumption) |
| `Agent.list(api_key, *, limit, cursor, pr_url, include_archived)` | class | `ListResult[Agent]` | Paginated listing of your agents |
| `agent.send(message, options)` | instance | `Run` | Send a follow-up message, get a new run |
| `agent.reload()` | instance | `Agent` | Refresh metadata from the API |
| `agent.archive()` / `agent.unarchive()` | instance | `None` | Toggle archived state |
| `agent.close()` | instance | `None` | Archive the agent (alias) |
| `agent.delete()` | instance | `None` | Permanently delete the agent |
| `agent.list_artifacts()` | instance | `list[Artifact]` | List files produced by the agent |
| `agent.download_artifact(path)` | instance | `str` | Get a presigned download URL |

### `Run` — Execution Control

| Method / Property | Returns | Description |
|---|---|---|
| `run.stream()` | `Generator[Message]` | Yield typed SSE events in real time |
| `run.wait(timeout, poll_interval)` | `RunResult` | Block until the run finishes |
| `run.cancel()` | `None` | Cancel an active run |
| `run.conversation()` | `list[ConversationTurn]` | Full conversation history for this run |
| `run.on_status_change(callback)` | `None` | Register a status-change listener |
| `run.status` | `str \| None` | Current status (reactive property) |
| `run.id` | `str \| None` | The run's unique identifier |

### `Cursor` — Account Operations

| Method | Returns | Description |
|---|---|---|
| `Cursor.me(api_key)` | `User` | Your API key name, email, and creation date |
| `Cursor.models.list(api_key)` | `list[ModelListItem]` | Available models with parameters and variants |
| `Cursor.repositories.list(api_key)` | `list[Repository]` | Connected GitHub repositories |

### `Artifact` — File Access

| Method / Property | Returns | Description |
|---|---|---|
| `artifact.path` | `str` | Relative file path |
| `artifact.size_bytes` | `int` | File size |
| `artifact.get_download_url()` | `str` | Presigned S3 URL (valid ~15 min) |
| `artifact.download_content()` | `bytes` | Raw file content |

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

## Configuration Types

Use these dataclasses and constants to configure agent creation and messaging:

```python
from cursorconnect import CommonModels
from cursorconnect.types import CloudOptions, ModelSelection, ModelParameterValue

cloud = CloudOptions(
    repos=[{"url": "https://github.com/org/repo", "startingRef": "main"}],
    autoCreatePR=True,
    workOnCurrentBranch=False,
)

# You can pass a raw string from CommonModels:
agent1 = Agent.create(
    prompt="Optimize the database queries",
    cloud=cloud,
    model=CommonModels.CLAUDE_4_6_SONNET,
)

# Or pass a full ModelSelection if you need custom parameters:
model = ModelSelection(
    id=CommonModels.CLAUDE_4_6_SONNET,
    params=[ModelParameterValue(id="thinking", value="enabled")],
)

agent2 = Agent.create(
    prompt="Optimize the database queries",
    cloud=cloud,
    model=model,
    name="query-optimizer",
)
```

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

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  Built for developers who'd rather write Python than curl commands.
</p>

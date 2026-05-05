"""CursorConnect Python SDK.

Quick-start
-----------
>>> from cursorconnect import Agent, Cursor
>>> from cursorconnect.types import CloudOptions, AssistantMessage

# One-shot: create agent, send prompt, stream the response
>>> run = Agent.prompt(
...     api_key="crsr_...",
...     message="Refactor src/utils.py to use pathlib",
...     cloud=CloudOptions(repos=[{"url": "https://github.com/org/repo"}]),
... )
>>> for event in run.stream():
...     if event.type is AssistantMessage:
...         ...
>>> result = run.wait()

# Persistent agent: create once, send many messages
>>> agent = Agent.create(api_key="crsr_...", prompt="Bootstrap a FastAPI project")
>>> run2 = agent.send("Now add JWT authentication")
>>> for msg in run2.stream():
...     ...

# Account-level reads
>>> user = Cursor.me(api_key="crsr_...")
>>> models = Cursor.models.list(api_key="crsr_...")
"""

from .agent import Agent
from .cursor import Cursor
from .run import Run
from .mesh import Mesh
from .artifact import Artifact
from .types import CommonModels, CloudOptions, LocalOptions, Conversation, RunProtocol
from .exceptions import (
    CursorAgentError,
    CursorAPIError,
    AuthenticationError,
    RateLimitError,
    ConfigurationError,
    NetworkError,
    UnsupportedRunOperationError,
    UnknownAgentError,
    map_http_error,
)
from .client import CursorClient

__all__ = [
    "Agent",
    "Cursor",
    "Run",
    "Mesh",
    "Artifact",
    "CommonModels",
    "CloudOptions",
    "LocalOptions",
    "Conversation",
    "RunProtocol",
    "CursorClient",
    "CursorAPIError",
    "CursorAgentError",
    "AuthenticationError",
    "RateLimitError",
    "ConfigurationError",
    "NetworkError",
    "UnsupportedRunOperationError",
    "UnknownAgentError",
    "map_http_error",
]

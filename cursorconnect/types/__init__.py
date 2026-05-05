"""
The types subpackage for the CursorConnect Python SDK.
This package contains dataclasses mapping the TypeScript SDK types to Python.
"""

from .account import (
    User,
    Repository,
    RunResult,
)
from .messages import (
    TextBlock,
    ToolUseBlock,
    SystemMessage,
    UserMessageEvent,
    AssistantMessage,
    ThinkingMessage,
    ToolUseMessage,
    StatusMessage,
    TaskMessage,
    RequestMessage,
    Message,
    parse_message,
    # Backward compatibility aliases
    SDKSystemMessage,
    SDKUserMessageEvent,
    SDKAssistantMessage,
    SDKThinkingMessage,
    SDKToolUseMessage,
    SDKStatusMessage,
    SDKTaskMessage,
    SDKRequestMessage,
    SDKMessage,
    parse_sdk_message,
)
from .updates import (
    TextDeltaUpdate,
    ThinkingDeltaUpdate,
    ThinkingCompletedUpdate,
    ToolCallStartedUpdate,
    PartialToolCallUpdate,
    ToolCallCompletedUpdate,
    TokenDeltaUpdate,
    StepStartedUpdate,
    StepCompletedUpdate,
    TurnEndedUpdate,
    UserMessageAppendedUpdate,
    SummaryUpdate,
    SummaryStartedUpdate,
    SummaryCompletedUpdate,
    ShellOutputDeltaUpdate,
    InteractionUpdate,
)
from .conversation import (
    AssistantContent,
    ThinkingContent,
    ToolCallContent,
    UserContent,
    ShellCommand,
    ShellOutput,
    ConversationStep,
    AgentConversationTurn,
    ShellConversationTurn,
    ConversationTurn,
    Conversation,
    parse_conversation,
)
from .models import (
    CommonModels,
    ModelParameterValue,
    ModelParameters,
    ModelSelection,
    ModelParameterDefinition,
    ModelVariant,
    ModelListItem,
)
from .mcp import (
    McpServerConfigStdio,
    McpServerConfigHttp,
    McpServerConfig,
    AgentDefinition,
)
from .options import (
    SettingSource,
    LocalOptions,
    CloudOptions,
    AgentOptions,
    SendOptions,
    ListResult,
)
from .mesh import (
    MeshTask,
    MeshResult,
)
from .run_protocol import RunProtocol

# Backward compatibility aliases for renamed account types
SDKUser = User
SDKRepository = Repository

__all__ = [
    # Account types (new names)
    "User",
    "Repository",
    "RunResult",
    # Account types (backward compat)
    "SDKUser",
    "SDKRepository",
    # Message event types (new names)
    "TextBlock",
    "ToolUseBlock",
    "SystemMessage",
    "UserMessageEvent",
    "AssistantMessage",
    "ThinkingMessage",
    "ToolUseMessage",
    "StatusMessage",
    "TaskMessage",
    "RequestMessage",
    "Message",
    "parse_message",
    # Message event types (backward compat)
    "SDKSystemMessage",
    "SDKUserMessageEvent",
    "SDKAssistantMessage",
    "SDKThinkingMessage",
    "SDKToolUseMessage",
    "SDKStatusMessage",
    "SDKTaskMessage",
    "SDKRequestMessage",
    "SDKMessage",
    "parse_sdk_message",
    # Updates
    "TextDeltaUpdate",
    "ThinkingDeltaUpdate",
    "ThinkingCompletedUpdate",
    "ToolCallStartedUpdate",
    "PartialToolCallUpdate",
    "ToolCallCompletedUpdate",
    "TokenDeltaUpdate",
    "StepStartedUpdate",
    "StepCompletedUpdate",
    "TurnEndedUpdate",
    "UserMessageAppendedUpdate",
    "SummaryUpdate",
    "SummaryStartedUpdate",
    "SummaryCompletedUpdate",
    "ShellOutputDeltaUpdate",
    "InteractionUpdate",
    # Conversation types
    "AssistantContent",
    "ThinkingContent",
    "ToolCallContent",
    "UserContent",
    "ShellCommand",
    "ShellOutput",
    "ConversationStep",
    "AgentConversationTurn",
    "ShellConversationTurn",
    "ConversationTurn",
    "Conversation",
    "parse_conversation",
    # Models
    "CommonModels",
    "ModelParameterValue",
    "ModelParameters",
    "ModelSelection",
    "ModelParameterDefinition",
    "ModelVariant",
    "ModelListItem",
    # MCP
    "McpServerConfigStdio",
    "McpServerConfigHttp",
    "McpServerConfig",
    "AgentDefinition",
    # Options
    "SettingSource",
    "LocalOptions",
    "CloudOptions",
    "AgentOptions",
    "SendOptions",
    "ListResult",
    # Mesh
    "MeshTask",
    "MeshResult",
    # Protocol
    "RunProtocol",
]

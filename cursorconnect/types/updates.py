from dataclasses import dataclass, field
from typing import Literal, Optional, Union, Any, Dict

@dataclass
class TextDeltaUpdate:
    """
    Represents a partial update to the assistant's text response.

    Parameters
    ----------
    type : Literal["text-delta"]
        The update type.
    text : str
        The newly generated text fragment.
    """
    type: Literal["text-delta"]
    text: str

@dataclass
class ThinkingDeltaUpdate:
    """
    Represents a partial update to the agent's internal reasoning text.

    Parameters
    ----------
    type : Literal["thinking-delta"]
        The update type.
    text : str
        The newly generated thinking fragment.
    """
    type: Literal["thinking-delta"]
    text: str

@dataclass
class ThinkingCompletedUpdate:
    """
    Indicates that the agent has finished its reasoning process for the current step.

    Parameters
    ----------
    type : Literal["thinking-completed"]
        The update type.
    thinkingDurationMs : int
        The total duration of the thinking process in milliseconds.
    """
    type: Literal["thinking-completed"]
    thinkingDurationMs: int

@dataclass
class ToolCallStartedUpdate:
    """
    Indicates that a tool invocation has started.

    Parameters
    ----------
    type : Literal["tool-call-started"]
        The update type.
    callId : str
        The unique ID of the tool call.
    toolCall : Any
        The tool call details.
    modelCallId : str
        The ID of the model call that triggered this tool.
    """
    type: Literal["tool-call-started"]
    callId: str
    toolCall: Any
    modelCallId: str

@dataclass
class PartialToolCallUpdate:
    """
    Represents a partial update to a tool call (e.g., streaming arguments).

    Parameters
    ----------
    type : Literal["partial-tool-call"]
        The update type.
    callId : str
        The unique ID of the tool call.
    toolCall : Any
        The partial tool call details.
    modelCallId : str
        The ID of the model call.
    """
    type: Literal["partial-tool-call"]
    callId: str
    toolCall: Any
    modelCallId: str

@dataclass
class ToolCallCompletedUpdate:
    """
    Indicates that a tool invocation has finished.

    Parameters
    ----------
    type : Literal["tool-call-completed"]
        The update type.
    callId : str
        The unique ID of the tool call.
    toolCall : Any
        The final tool call details including results.
    modelCallId : str
        The ID of the model call.
    """
    type: Literal["tool-call-completed"]
    callId: str
    toolCall: Any
    modelCallId: str

@dataclass
class TokenDeltaUpdate:
    """
    Reports the number of tokens processed in an update.

    Parameters
    ----------
    type : Literal["token-delta"]
        The update type.
    tokens : int
        The number of tokens in this delta.
    """
    type: Literal["token-delta"]
    tokens: int

@dataclass
class StepStartedUpdate:
    """
    Indicates that a new execution step has begun.

    Parameters
    ----------
    type : Literal["step-started"]
        The update type.
    stepId : int
        The unique ID of the step.
    """
    type: Literal["step-started"]
    stepId: int

@dataclass
class StepCompletedUpdate:
    """
    Indicates that an execution step has finished.

    Parameters
    ----------
    type : Literal["step-completed"]
        The update type.
    stepId : int
        The unique ID of the step.
    stepDurationMs : int
        The duration of the step in milliseconds.
    """
    type: Literal["step-completed"]
    stepId: int
    stepDurationMs: int

@dataclass
class TurnEndedUpdate:
    """
    Indicates that a conversation turn has concluded.

    Parameters
    ----------
    type : Literal["turn-ended"]
        The update type.
    usage : Optional[dict], optional
        Token usage statistics for the turn, by default None.
    """
    type: Literal["turn-ended"]
    usage: Optional[dict] = None # { inputTokens: number; outputTokens: number; cacheReadTokens: number; cacheWriteTokens: number; }

@dataclass
class UserMessageAppendedUpdate:
    """
    Indicates that a user message was added to the conversation.

    Parameters
    ----------
    type : Literal["user-message-appended"]
        The update type.
    userMessage : Any
        The user message that was appended.
    """
    type: Literal["user-message-appended"]
    userMessage: Any

@dataclass
class SummaryUpdate:
    """
    Provides a summary of the current state or progress.

    Parameters
    ----------
    type : Literal["summary"]
        The update type.
    summary : str
        The summary text.
    """
    type: Literal["summary"]
    summary: str

@dataclass
class SummaryStartedUpdate:
    """
    Indicates that a summary generation process has started.

    Parameters
    ----------
    type : Literal["summary-started"]
        The update type.
    """
    type: Literal["summary-started"]

@dataclass
class SummaryCompletedUpdate:
    """
    Indicates that a summary generation process has finished.

    Parameters
    ----------
    type : Literal["summary-completed"]
        The update type.
    """
    type: Literal["summary-completed"]

@dataclass
class ShellOutputDeltaUpdate:
    """
    Represents a partial update to shell command output.

    Parameters
    ----------
    type : Literal["shell-output-delta"]
        The update type.
    event : Dict[str, Any]
        The shell output event data.
    """
    type: Literal["shell-output-delta"]
    event: Dict[str, Any]

InteractionUpdate = Union[
    TextDeltaUpdate,
    ThinkingDeltaUpdate,
    ThinkingCompletedUpdate,
    ToolCallStartedUpdate,
    ToolCallCompletedUpdate,
    PartialToolCallUpdate,
    TokenDeltaUpdate,
    StepStartedUpdate,
    StepCompletedUpdate,
    TurnEndedUpdate,
    UserMessageAppendedUpdate,
    SummaryUpdate,
    SummaryStartedUpdate,
    SummaryCompletedUpdate,
    ShellOutputDeltaUpdate
]

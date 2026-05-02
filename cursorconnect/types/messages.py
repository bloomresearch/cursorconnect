from dataclasses import dataclass, field
from typing import Any, Dict, Literal, List, Optional, Union
from .models import ModelSelection


class _Typed:
    """Mixin that makes ``event.type`` return the concrete class.

    This enables clean identity checks like ``event.type is AssistantMessage``
    instead of verbose ``isinstance(event, AssistantMessage)`` calls.
    """

    @property
    def type(self):
        return self.__class__


@dataclass
class TextBlock:
    """
    Represents a block of text content in a message.

    Parameters
    ----------
    type : Literal["text"]
        The type of the block, always "text".
    text : str
        The actual text content.
    """
    type: Literal["text"]
    text: str

@dataclass
class ToolUseBlock:
    """
    Represents a request for a tool to be executed.

    Parameters
    ----------
    type : Literal["tool_use"]
        The type of the block, always "tool_use".
    id : str
        A unique identifier for this specific tool use instance.
    name : str
        The name of the tool to be invoked.
    input : Any
        The input arguments for the tool, typically a dictionary.
    """
    type: Literal["tool_use"]
    id: str
    name: str
    input: Any

@dataclass
class SystemMessage(_Typed):
    """
    A system message used for initialization or providing context to the agent.

    Parameters
    ----------
    agent_id : str
        The ID of the agent receiving the message.
    run_id : str
        The ID of the current execution run.
    subtype : Optional[Literal["init"]], optional
        The subtype of the system message, by default None.
    model : Optional[ModelSelection], optional
        The model configuration for this run, by default None.
    tools : Optional[List[str]], optional
        A list of tool names available to the agent, by default None.
    """
    agent_id: str
    run_id: str
    subtype: Optional[Literal["init"]] = None
    model: Optional[ModelSelection] = None
    tools: Optional[List[str]] = None

@dataclass
class UserMessageEvent(_Typed):
    """
    Represents a message sent by the user, echoed back during streaming.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    message : dict
        A dictionary containing the role ("user") and content (list of TextBlock).

    Examples
    --------
    >>> msg = UserMessageEvent(
    ...     agent_id="agent-1",
    ...     run_id="run-1",
    ...     message={"role": "user", "content": [TextBlock(type="text", text="Hello")]}
    ... )
    """
    agent_id: str
    run_id: str
    message: dict # { role: "user"; content: TextBlock[] }

@dataclass
class AssistantMessage(_Typed):
    """
    Represents a message sent by the assistant.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    message : dict
        A dictionary containing the role ("assistant") and content (list of TextBlock or ToolUseBlock).
    """
    agent_id: str
    run_id: str
    message: dict # { role: "assistant"; content: Array<TextBlock | ToolUseBlock> }

@dataclass
class ThinkingMessage(_Typed):
    """
    A message indicating the agent's internal reasoning process.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    text : str
        The content of the thinking process.
    thinking_duration_ms : Optional[int], optional
        How long the thinking took in milliseconds, by default None.
    """
    agent_id: str
    run_id: str
    text: str
    thinking_duration_ms: Optional[int] = None

@dataclass
class ToolUseMessage(_Typed):
    """
    A message describing the status or result of a tool invocation.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    call_id : str
        The unique ID of the tool call.
    name : str
        The name of the tool.
    status : Literal["running", "completed", "error"]
        The current status of the tool call.
    args : Optional[Any], optional
        The arguments passed to the tool, by default None.
    result : Optional[Any], optional
        The result returned by the tool, by default None.
    truncated : Optional[dict], optional
        Information about whether args or result were truncated, by default None.
    """
    agent_id: str
    run_id: str
    call_id: str
    name: str
    status: Literal["running", "completed", "error"]
    args: Optional[Any] = None
    result: Optional[Any] = None
    truncated: Optional[dict] = None # { args?: boolean; result?: boolean }

@dataclass
class StatusMessage(_Typed):
    """
    A message indicating a change in the overall status of the agent run.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    status : Literal["CREATING", "RUNNING", "FINISHED", "ERROR", "CANCELLED", "EXPIRED"]
        The new status of the run.
    message : Optional[str], optional
        An optional human-readable status message, by default None.
    """
    agent_id: str
    run_id: str
    status: Literal["CREATING", "RUNNING", "FINISHED", "ERROR", "CANCELLED", "EXPIRED"]
    message: Optional[str] = None

@dataclass
class TaskMessage(_Typed):
    """
    A message related to a specific task being performed by the agent.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    status : Optional[str], optional
        The status of the task, by default None.
    text : Optional[str], optional
        A description or update for the task, by default None.
    """
    agent_id: str
    run_id: str
    status: Optional[str] = None
    text: Optional[str] = None

@dataclass
class RequestMessage(_Typed):
    """
    A message representing a request for information or action.

    Parameters
    ----------
    agent_id : str
        The ID of the agent.
    run_id : str
        The ID of the run.
    request_id : str
        The unique identifier for the request.
    """
    agent_id: str
    run_id: str
    request_id: str

Message = Union[
    SystemMessage,
    UserMessageEvent,
    AssistantMessage,
    ThinkingMessage,
    ToolUseMessage,
    StatusMessage,
    TaskMessage,
    RequestMessage,
]


def parse_message(data: Dict[str, Any]) -> Message:
    """
    Deserialise an SSE event data dict into the appropriate Message subclass.

    Uses the ``"type"`` key of *data* as the discriminator.  Field names are
    normalised from camelCase (API wire format) to the snake_case used by the
    dataclass definitions.  Unknown types are passed through as raw dicts so
    that new server-side event types do not break existing consumers.

    Parameters
    ----------
    data : dict
        Parsed JSON payload from an SSE ``data:`` field.

    Returns
    -------
    Message
        A typed dataclass instance matching the event ``"type"``.  If the
        type is unrecognised, the original *data* dict is returned unchanged.

    Examples
    --------
    >>> msg = parse_message({
    ...     "type": "status",
    ...     "agentId": "a1",
    ...     "runId": "r1",
    ...     "status": "RUNNING",
    ... })
    >>> msg.type is StatusMessage
    True
    """
    msg_type = data.get("type", "")
    agent_id: str = data.get("agentId", "")
    run_id: str = data.get("runId", "")

    if msg_type == "system":
        return SystemMessage(
            agent_id=agent_id,
            run_id=run_id,
            subtype=data.get("subtype"),
            model=data.get("model"),
            tools=data.get("tools"),
        )
    if msg_type == "user":
        return UserMessageEvent(
            agent_id=agent_id,
            run_id=run_id,
            message=data.get("message", {}),
        )
    if msg_type == "assistant":
        return AssistantMessage(
            agent_id=agent_id,
            run_id=run_id,
            message=data.get("message", {}),
        )
    if msg_type == "thinking":
        return ThinkingMessage(
            agent_id=agent_id,
            run_id=run_id,
            text=data.get("text", ""),
            thinking_duration_ms=data.get("thinkingDurationMs"),
        )
    if msg_type == "tool_call":
        return ToolUseMessage(
            agent_id=agent_id,
            run_id=run_id,
            call_id=data.get("callId", ""),
            name=data.get("name", ""),
            status=data.get("status", "running"),
            args=data.get("args"),
            result=data.get("result"),
            truncated=data.get("truncated"),
        )
    if msg_type == "status":
        return StatusMessage(
            agent_id=agent_id,
            run_id=run_id,
            status=data.get("status", "RUNNING"),
            message=data.get("message"),
        )
    if msg_type == "task":
        return TaskMessage(
            agent_id=agent_id,
            run_id=run_id,
            status=data.get("status"),
            text=data.get("text"),
        )
    if msg_type == "request":
        return RequestMessage(
            agent_id=agent_id,
            run_id=run_id,
            request_id=data.get("requestId", ""),
        )
    return data  # type: ignore[return-value]


# Backward compatibility aliases
SDKSystemMessage = SystemMessage
SDKUserMessageEvent = UserMessageEvent
SDKAssistantMessage = AssistantMessage
SDKThinkingMessage = ThinkingMessage
SDKToolUseMessage = ToolUseMessage
SDKStatusMessage = StatusMessage
SDKTaskMessage = TaskMessage
SDKRequestMessage = RequestMessage
SDKMessage = Message
parse_sdk_message = parse_message

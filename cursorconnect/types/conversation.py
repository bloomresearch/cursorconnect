"""Typed conversation structures for the CursorConnect SDK.

Mirrors the TypeScript SDK's ``ConversationTurn`` discriminated union
and provides :func:`parse_conversation` to hydrate raw API/bridge
dicts into proper dataclass instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union, Any, Dict


# ---------------------------------------------------------------------------
# Leaf content types
# ---------------------------------------------------------------------------

@dataclass
class AssistantContent:
    """
    Text produced by the assistant during a conversation step.

    Parameters
    ----------
    text : str
        The assistant's output text.
    """
    text: str

    def __str__(self) -> str:
        return self.text


@dataclass
class ThinkingContent:
    """
    Internal reasoning produced by the model.

    Parameters
    ----------
    text : str
        The reasoning text.
    thinkingDurationMs : int, optional
        How long the model spent thinking, in milliseconds.
    """
    text: str
    thinkingDurationMs: Optional[int] = None

    def __str__(self) -> str:
        duration = f" ({self.thinkingDurationMs}ms)" if self.thinkingDurationMs else ""
        return f"[thinking{duration}] {self.text}"


@dataclass
class ToolCallContent:
    """
    A tool invocation recorded as a conversation step.

    The ``args`` and ``result`` payloads are tool-specific and should
    be treated as opaque.

    Parameters
    ----------
    name : str
        The tool name (e.g. ``"edit"``, ``"shell"``, ``"grep"``).
    args : Any, optional
        The arguments passed to the tool.
    result : Any, optional
        The tool's return value.
    status : str, optional
        One of ``"completed"``, ``"error"``, or ``"running"``.
    """
    name: str = ""
    args: Any = None
    result: Any = None
    status: Optional[str] = None

    def __str__(self) -> str:
        s = f"[tool: {self.name}]"
        if self.status:
            s += f" ({self.status})"
        return s


@dataclass
class UserContent:
    """
    A user message that initiated a conversation turn.

    Parameters
    ----------
    text : str
        The user's input text.
    """
    text: str

    def __str__(self) -> str:
        return self.text


# ---------------------------------------------------------------------------
# Conversation steps
# ---------------------------------------------------------------------------

@dataclass
class ConversationStep:
    """
    A single step within an agent conversation turn.

    Each step is one of: an assistant message, a thinking message,
    or a tool call.

    Parameters
    ----------
    type : str
        The step discriminator: ``"assistantMessage"``,
        ``"thinkingMessage"``, or ``"toolCall"``.
    message : AssistantContent, ThinkingContent, or ToolCallContent
        The typed content for this step.
    """
    type: str
    message: Union[AssistantContent, ThinkingContent, ToolCallContent]

    def __str__(self) -> str:
        return str(self.message)


@dataclass
class ShellCommand:
    """
    A command executed in a shell.

    Parameters
    ----------
    command : str
        The command string.
    workingDirectory : str, optional
        The directory the command ran in.
    """
    command: str
    workingDirectory: Optional[str] = None

    def __str__(self) -> str:
        prefix = f"[{self.workingDirectory}] " if self.workingDirectory else ""
        return f"{prefix}$ {self.command}"


@dataclass
class ShellOutput:
    """
    The output from a shell command execution.

    Parameters
    ----------
    stdout : str
        Standard output.
    stderr : str
        Standard error.
    exitCode : int
        The process exit code.
    """
    stdout: str
    stderr: str
    exitCode: int

    def __str__(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr] {self.stderr}")
        parts.append(f"[exit {self.exitCode}]")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Conversation turns
# ---------------------------------------------------------------------------

@dataclass
class AgentConversationTurn:
    """
    A single agent turn containing one or more steps.

    Parameters
    ----------
    steps : list of ConversationStep
        The ordered steps the agent took during this turn.
    userMessage : UserContent, optional
        The user message that initiated this turn.
    """
    steps: List[ConversationStep] = field(default_factory=list)
    userMessage: Optional[UserContent] = None

    @property
    def text(self) -> str:
        """Concatenated assistant text from all steps in this turn."""
        parts = []
        for step in self.steps:
            if step.type == "assistantMessage" and isinstance(step.message, AssistantContent):
                parts.append(step.message.text)
        return "\n\n".join(parts)

    def __str__(self) -> str:
        parts = []
        if self.userMessage:
            parts.append(f"User: {self.userMessage}")
        for step in self.steps:
            parts.append(str(step))
        return "\n".join(parts)


@dataclass
class ShellConversationTurn:
    """
    A shell turn recording a command and its output.

    Parameters
    ----------
    shellCommand : ShellCommand, optional
        The command that was executed.
    shellOutput : ShellOutput, optional
        The output produced.
    """
    shellCommand: Optional[ShellCommand] = None
    shellOutput: Optional[ShellOutput] = None

    def __str__(self) -> str:
        parts = []
        if self.shellCommand:
            parts.append(str(self.shellCommand))
        if self.shellOutput:
            parts.append(str(self.shellOutput))
        return "\n".join(parts)


@dataclass
class ConversationTurn:
    """
    A single turn in a conversation, wrapping either an agent turn
    or a shell turn.

    Parameters
    ----------
    type : str
        ``"agentConversationTurn"`` or ``"shellConversationTurn"``.
    turn : AgentConversationTurn or ShellConversationTurn
        The typed turn payload.
    """
    type: str
    turn: Union[AgentConversationTurn, ShellConversationTurn]

    @property
    def text(self) -> str:
        """Convenience accessor for the assistant text of an agent turn."""
        if isinstance(self.turn, AgentConversationTurn):
            return self.turn.text
        return str(self.turn)

    def __str__(self) -> str:
        return str(self.turn)


# ---------------------------------------------------------------------------
# Conversation (top-level container)
# ---------------------------------------------------------------------------

@dataclass
class Conversation:
    """
    The complete conversation history for a run, as a list of typed turns.

    Supports iteration, indexing, ``len()``, and ``print()``.
    """
    turns: List[ConversationTurn] = field(default_factory=list)

    @property
    def text(self) -> str:
        """All assistant text concatenated across all turns."""
        parts = []
        for turn in self.turns:
            t = turn.text
            if t:
                parts.append(t)
        return "\n\n".join(parts)

    def __str__(self) -> str:
        return "\n\n".join(str(t) for t in self.turns)

    def __len__(self) -> int:
        return len(self.turns)

    def __iter__(self):
        return iter(self.turns)

    def __getitem__(self, index):
        return self.turns[index]

    def __bool__(self) -> bool:
        return len(self.turns) > 0


# ---------------------------------------------------------------------------
# Parser: raw dicts -> typed dataclasses
# ---------------------------------------------------------------------------

def _parse_step(raw: Dict[str, Any]) -> ConversationStep:
    """Parse a single conversation step from a raw dict."""
    step_type = raw.get("type", "")
    raw_msg = raw.get("message", {})
    if not isinstance(raw_msg, dict):
        raw_msg = {}

    if step_type == "assistantMessage":
        message = AssistantContent(text=raw_msg.get("text", ""))
    elif step_type == "thinkingMessage":
        message = ThinkingContent(
            text=raw_msg.get("text", ""),
            thinkingDurationMs=raw_msg.get("thinkingDurationMs"),
        )
    elif step_type == "toolCall":
        message = ToolCallContent(
            name=raw_msg.get("name", ""),
            args=raw_msg.get("args") or raw_msg.get("input"),
            result=raw_msg.get("result"),
            status=raw_msg.get("status"),
        )
    else:
        message = AssistantContent(text=raw_msg.get("text", ""))

    return ConversationStep(type=step_type, message=message)


def _parse_agent_turn(raw: Dict[str, Any]) -> AgentConversationTurn:
    """Parse an agent conversation turn from a raw dict."""
    steps = [_parse_step(s) for s in raw.get("steps", []) if isinstance(s, dict)]

    user_msg = None
    raw_user = raw.get("userMessage")
    if isinstance(raw_user, dict):
        user_msg = UserContent(text=raw_user.get("text", ""))

    return AgentConversationTurn(steps=steps, userMessage=user_msg)


def _parse_shell_turn(raw: Dict[str, Any]) -> ShellConversationTurn:
    """Parse a shell conversation turn from a raw dict."""
    cmd = None
    raw_cmd = raw.get("shellCommand")
    if isinstance(raw_cmd, dict):
        cmd = ShellCommand(
            command=raw_cmd.get("command", ""),
            workingDirectory=raw_cmd.get("workingDirectory"),
        )

    output = None
    raw_out = raw.get("shellOutput")
    if isinstance(raw_out, dict):
        output = ShellOutput(
            stdout=raw_out.get("stdout", ""),
            stderr=raw_out.get("stderr", ""),
            exitCode=raw_out.get("exitCode", -1),
        )

    return ShellConversationTurn(shellCommand=cmd, shellOutput=output)


def parse_conversation(raw_turns: Any) -> Conversation:
    """
    Hydrate a list of raw conversation dicts into a typed
    :class:`Conversation`.

    Parameters
    ----------
    raw_turns : list of dict
        The raw ``turns`` list from the API or bridge response.

    Returns
    -------
    Conversation
        A fully typed conversation object that supports iteration,
        indexing, and ``print()``.
    """
    if not isinstance(raw_turns, list):
        return Conversation()

    turns: List[ConversationTurn] = []
    for raw in raw_turns:
        if not isinstance(raw, dict):
            continue

        turn_type = raw.get("type", "")
        raw_turn = raw.get("turn", {})
        if not isinstance(raw_turn, dict):
            raw_turn = {}

        if turn_type == "agentConversationTurn":
            turn = _parse_agent_turn(raw_turn)
        elif turn_type == "shellConversationTurn":
            turn = _parse_shell_turn(raw_turn)
        else:
            continue

        turns.append(ConversationTurn(type=turn_type, turn=turn))

    return Conversation(turns=turns)

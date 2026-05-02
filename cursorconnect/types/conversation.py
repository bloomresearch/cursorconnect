from dataclasses import dataclass, field
from typing import Literal, List, Optional, Union, Any

@dataclass
class AssistantContent:
    """
    A simple message from the assistant.

    Parameters
    ----------
    text : str
        The text content of the message.
    """
    text: str

@dataclass
class ThinkingContent:
    """
    Internal reasoning from the assistant.

    Parameters
    ----------
    text : str
        The reasoning text.
    thinkingDurationMs : Optional[int], optional
        The duration of the thinking in milliseconds, by default None.
    """
    text: str
    thinkingDurationMs: Optional[int] = None

@dataclass
class UserContent:
    """
    A simple message from the user.

    Parameters
    ----------
    text : str
        The text content of the message.
    """
    text: str

@dataclass
class ShellCommand:
    """
    A command executed in a shell.

    Parameters
    ----------
    command : str
        The command string.
    workingDirectory : Optional[str], optional
        The directory in which the command was run, by default None.
    """
    command: str
    workingDirectory: Optional[str] = None

@dataclass
class ShellOutput:
    """
    The output from a shell command.

    Parameters
    ----------
    stdout : str
        The standard output.
    stderr : str
        The standard error.
    exitCode : int
        The exit code of the command.
    """
    stdout: str
    stderr: str
    exitCode: int

ConversationStep = Union[
    dict, # { type: "assistantMessage"; message: AssistantContent }
    dict, # { type: "toolCall"; message: unknown }
    dict  # { type: "thinkingMessage"; message: ThinkingContent }
]

@dataclass
class AgentConversationTurn:
    """
    A single turn in a conversation involving an agent.

    Parameters
    ----------
    steps : List[dict]
        A list of steps taken during the turn.
    userMessage : Optional[UserMessage], optional
        The user message that initiated the turn, by default None.
    """
    steps: List[dict]
    userMessage: Optional[UserContent] = None

@dataclass
class ShellConversationTurn:
    """
    A single turn in a conversation involving a shell command.

    Parameters
    ----------
    shellCommand : Optional[ShellCommand], optional
        The command that was run, by default None.
    shellOutput : Optional[ShellOutput], optional
        The output of the command, by default None.
    """
    shellCommand: Optional[ShellCommand] = None
    shellOutput: Optional[ShellOutput] = None

ConversationTurn = Union[
    dict, # { type: "agentConversationTurn"; turn: AgentConversationTurn }
    dict  # { type: "shellConversationTurn"; turn: ShellConversationTurn }
]

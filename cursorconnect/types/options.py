from dataclasses import dataclass, field
from typing import Literal, List, Optional, Union, Dict, Any, TypeVar, Generic
from .models import ModelSelection
from .mcp import McpServerConfig, AgentDefinition

T = TypeVar("T")

SettingSource = Literal["project", "user", "team", "mdm", "plugins", "all"]

@dataclass
class LocalOptions:
    """
    Options for local execution of an agent.

    Parameters
    ----------
    cwd : Optional[Union[str, List[str]]], optional
        The current working directory or directories to use, by default None.
    settingSources : Optional[List[SettingSource]], optional
        The sources from which to load settings, by default None.
    sandboxOptions : Optional[dict], optional
        Options for the execution sandbox, by default None.
    """
    cwd: Optional[Union[str, List[str]]] = None
    settingSources: Optional[List[SettingSource]] = None
    sandboxOptions: Optional[dict] = None # { enabled: boolean; }

@dataclass
class CloudOptions:
    """
    Options for cloud-based execution of an agent.

    Parameters
    ----------
    env : Optional[dict], optional
        The cloud environment configuration, by default None.
    repos : Optional[List[dict]], optional
        A list of repositories to make available, by default None.
    workOnCurrentBranch : Optional[bool], optional
        Whether to work on the current branch, by default None.
    autoCreatePR : Optional[bool], optional
        Whether to automatically create a pull request, by default None.
    skipReviewerRequest : Optional[bool], optional
        Whether to skip requesting reviewers for PRs, by default None.
    """
    env: Optional[dict] = None # { type: "cloud" | "pool" | "machine"; name?: string; }
    repos: Optional[List[dict]] = None # Array<{ url: string; startingRef?: string; prUrl?: string; }>
    workOnCurrentBranch: Optional[bool] = None
    autoCreatePR: Optional[bool] = None
    skipReviewerRequest: Optional[bool] = None

@dataclass
class AgentOptions:
    """
    Configuration options for creating or interacting with an agent.

    Parameters
    ----------
    model : Optional[Union[str, ModelSelection]], optional
        The model to use, by default None.
    apiKey : Optional[str], optional
        The API key for authentication, by default None.
    name : Optional[str], optional
        A name for the agent instance, by default None.
    local : Optional[LocalOptions], optional
        Options for local execution, by default None.
    cloud : Optional[CloudOptions], optional
        Options for cloud execution, by default None.
    mcpServers : Optional[Dict[str, McpServerConfig]], optional
        MCP servers to make available to the agent, by default None.
    agents : Optional[Dict[str, AgentDefinition]], optional
        Definitions for sub-agents, by default None.
    agentId : Optional[str], optional
        The ID of an existing agent to use, by default None.
    """
    model: Optional[Union[str, ModelSelection]] = None
    apiKey: Optional[str] = None
    name: Optional[str] = None
    local: Optional[LocalOptions] = None
    cloud: Optional[CloudOptions] = None
    mcpServers: Optional[Dict[str, McpServerConfig]] = None
    agents: Optional[Dict[str, AgentDefinition]] = None
    agentId: Optional[str] = None

@dataclass
class SendOptions:
    """
    Options for sending a message or starting a run.

    Parameters
    ----------
    model : Optional[Union[str, ModelSelection]], optional
        The model to use for this specific send, by default None.
    mcpServers : Optional[Dict[str, McpServerConfig]], optional
        Additional MCP servers for this run, by default None.
    onStep : Optional[Any], optional
        A callback for step updates, by default None.
    onDelta : Optional[Any], optional
        A callback for delta/update events, by default None.
    local : Optional[LocalOptions], optional
        Options for local execution, by default None.
    """
    model: Optional[Union[str, ModelSelection]] = None
    mcpServers: Optional[Dict[str, McpServerConfig]] = None
    onStep: Optional[Any] = None # (args: { step: unknown }) => void
    onDelta: Optional[Any] = None # (args: { update: InteractionUpdate }) => void
    local: Optional[LocalOptions] = None

@dataclass
class ListResult(Generic[T]):
    """
    A paginated list of items.

    Parameters
    ----------
    items : List[T]
        The items in the current page.
    nextCursor : Optional[str], optional
        A cursor for fetching the next page of results, by default None.
    """
    items: List[T]
    nextCursor: Optional[str] = None

from dataclasses import dataclass, field
from typing import Literal, List, Optional, Union, Dict, Any
from .models import ModelSelection

@dataclass
class McpServerConfigStdio:
    """
    Configuration for an MCP server using stdio transport.

    Parameters
    ----------
    command : str
        The command to execute to start the server.
    type : Literal["stdio"], optional
        The transport type, by default "stdio".
    args : Optional[List[str]], optional
        Arguments to pass to the command, by default None.
    env : Optional[Dict[str, str]], optional
        Environment variables for the server process, by default None.
    cwd : Optional[str], optional
        The working directory for the server process, by default None.
    """
    command: str
    type: Literal["stdio"] = "stdio"
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None

@dataclass
class McpServerConfigHttp:
    """
    Configuration for an MCP server using HTTP or SSE transport.

    Parameters
    ----------
    url : str
        The URL of the MCP server.
    type : Literal["http", "sse"], optional
        The transport type, by default "http".
    headers : Optional[Dict[str, str]], optional
        HTTP headers to include in requests, by default None.
    auth : Optional[dict], optional
        Authentication configuration, by default None.
    """
    url: str
    type: Literal["http", "sse"] = "http"
    headers: Optional[Dict[str, str]] = None
    auth: Optional[dict] = None # { CLIENT_ID: string; CLIENT_SECRET?: string; scopes?: string[]; }

McpServerConfig = Union[McpServerConfigStdio, McpServerConfigHttp]

@dataclass
class AgentDefinition:
    """
    Defines the configuration and behavior of an agent.

    Parameters
    ----------
    description : str
        A description of the agent's purpose.
    prompt : str
        The system prompt that guides the agent's behavior.
    model : Union[ModelSelection, Literal["inherit"]]
        The model to use, or "inherit" to use the parent agent's model.
    mcpServers : List[Union[str, Dict[str, McpServerConfig]]]
        A list of MCP servers available to this agent.
    """
    description: str
    prompt: str
    model: Union[ModelSelection, Literal["inherit"]]
    mcpServers: List[Union[str, Dict[str, McpServerConfig]]]

"""
Defines the ``RuntimeBackend`` Protocol—the canonical interface that every
concrete backend (cloud, local, mock) must satisfy.

Any class that implements all methods below with matching signatures is
automatically considered a ``RuntimeBackend``; no explicit inheritance is
required.  This structural approach keeps the higher-level ``Agent`` / ``Run``
domain objects fully decoupled from transport concerns: switching backends is
a one-line change at construction time.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, Protocol, runtime_checkable

from cursorconnect.types.messages import Message


@runtime_checkable
class RuntimeBackend(Protocol):
    """
    Structural protocol defining the interface for all CursorConnect backends.

    Implementors do **not** need to inherit from this class.  Static type
    checkers and :func:`isinstance` (enabled by ``@runtime_checkable``) verify
    structural compatibility at development / runtime respectively.

    Methods
    -------
    create_agent
        Create a new Cloud Agent and enqueue its first run.
    send_message
        Send a follow-up prompt to an existing agent.
    stream_run
        Open an SSE stream for a run and yield typed messages.
    wait_run
        Block until a run reaches a terminal status.
    cancel_run
        Cancel an active run.
    get_conversation
        Retrieve the full conversation history for an agent.
    get_agent
        Fetch durable metadata for an agent.
    list_agents
        List agents for the authenticated user.
    archive_agent
        Archive an agent so it cannot accept new runs.
    delete_agent
        Permanently delete an agent.
    list_artifacts
        List file artifacts produced by an agent.
    download_artifact
        Obtain a presigned download URL for an artifact.
    close
        Release all transport resources.
    reload
        Reset and reinitialise internal transport state.
    """

    def create_agent(
        self,
        prompt_text: str,
        repo_url: str,
        starting_ref: str = "main",
        model_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Create a Cloud Agent and enqueue its initial run.

        Parameters
        ----------
        prompt_text : str
            The initial task description / prompt for the agent.
        repo_url : str
            GitHub repository URL the agent will operate on.
        starting_ref : str, optional
            Branch name or commit SHA to start from, by default ``"main"``.
        model_id : str, optional
            Explicit model identifier for this run, by default None.
        **kwargs : Any
            Extra payload fields forwarded verbatim to the API
            (e.g. ``autoCreatePR``, ``branchName``).

        Returns
        -------
        dict
            Raw API response containing ``{"agent": {...}, "latestRunId": "..."}``.
        """
        ...

    def send_message(
        self,
        agent_id: str,
        prompt_text: str,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a follow-up prompt to an existing active agent.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the target agent.
        prompt_text : str
            The follow-up message text.
        images : list of dict, optional
            Image attachments, each a dict with ``"url"`` and/or ``"base64"``
            keys, by default None.

        Returns
        -------
        dict
            Raw API response containing the newly created ``run`` object.
        """
        ...

    def stream_run(
        self,
        agent_id: str,
        run_id: str,
    ) -> Generator[Message, None, None]:
        """
        Open a Server-Sent Events stream for a run and yield typed messages.

        The generator yields one :class:`~cursorconnect.types.messages.Message`
        per complete SSE event.  It closes naturally when the server exhausts
        the stream (typically after a terminal status event).

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run to stream.

        Yields
        ------
        Message
            A typed message object deserialised from each SSE event payload.

        Raises
        ------
        NetworkError
            If the TCP connection is lost mid-stream.
        CursorAgentError
            On a non-2xx HTTP opening handshake.
        """
        ...

    def wait_run(
        self,
        agent_id: str,
        run_id: str,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Block until a run reaches a terminal status.

        Polls the run-status endpoint at a fixed interval until the status is
        one of ``FINISHED``, ``ERROR``, ``CANCELLED``, or ``EXPIRED``.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run.
        poll_interval : float, optional
            Seconds between consecutive status checks, by default ``2.0``.
        timeout : float, optional
            Maximum seconds to wait before raising :class:`TimeoutError`.
            ``None`` (default) means wait indefinitely.

        Returns
        -------
        dict
            The final run data object returned by the API.

        Raises
        ------
        TimeoutError
            If the run has not reached a terminal state within *timeout* seconds.
        """
        ...

    def cancel_run(self, agent_id: str, run_id: str) -> None:
        """
        Cancel an active run, transitioning it to ``CANCELLED``.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run to cancel.
        """
        ...

    def get_conversation(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve the full conversation history for an agent.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.

        Returns
        -------
        list of dict
            Ordered list of conversation turn objects as returned by the API.
        """
        ...

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        Retrieve durable metadata for an agent.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.

        Returns
        -------
        dict
            Raw agent metadata object as returned by the API.
        """
        ...

    def list_agents(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        pr_url: Optional[str] = None,
        include_archived: bool = True,
    ) -> Dict[str, Any]:
        """
        List agents for the authenticated user, newest first.

        Parameters
        ----------
        limit : int, optional
            Maximum number of results to return per page, by default ``20``.
        cursor : str, optional
            Opaque pagination cursor from a prior response, by default None.
        pr_url : str, optional
            Filter to agents associated with a specific PR URL, by default None.
        include_archived : bool, optional
            Include archived agents in results, by default ``True``.

        Returns
        -------
        dict
            Response dict with ``{"items": [...], "nextCursor": "..."}``.
        """
        ...

    def archive_agent(self, agent_id: str) -> None:
        """
        Archive an agent so it can no longer accept new runs.

        The agent remains readable but its status transitions to archived.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent to archive.
        """
        ...

    def delete_agent(self, agent_id: str) -> None:
        """
        Permanently delete an agent. This action is irreversible.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent to delete.
        """
        ...

    def list_artifacts(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        List file artifacts produced by an agent.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.

        Returns
        -------
        list of dict
            Artifact metadata objects, each with ``path``, ``sizeBytes``,
            and ``updatedAt`` fields.
        """
        ...

    def download_artifact(self, agent_id: str, path: str) -> str:
        """
        Retrieve a presigned S3 download URL for a specific artifact.

        The returned URL is valid for approximately 15 minutes after generation.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        path : str
            The artifact file path as returned by :meth:`list_artifacts`.

        Returns
        -------
        str
            A temporary presigned URL for direct artifact download.
        """
        ...

    def close(self) -> None:
        """
        Release all transport resources held by this backend.

        Safe to call multiple times; subsequent calls after the first are
        treated as no-ops.
        """
        ...

    def reload(self) -> None:
        """
        Reset and reinitialise the backend's internal transport state.

        Useful for clearing stale connection-pool state or picking up rotated
        credentials without constructing a brand-new backend instance.
        """
        ...

"""Unified Agent facade for the CursorConnect SDK.

This module exposes a single :class:`Agent` class that covers the complete
lifecycle of a Cursor Cloud agent: creation, resumption, messaging, artifact
retrieval, and termination.  Each class-method factory builds an internal
:class:`~cursorconnect.client.CursorClient` from the provided *api_key*, so
callers never need to instantiate a client directly.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .client import CursorClient
from .artifact import Artifact
from .types import (
    CloudOptions,
    LocalOptions,
    ModelSelection,
    SendOptions,
    ListResult,
    RunResult,
)
from .exceptions import CursorAgentError

if TYPE_CHECKING:
    from .run import Run


def _parse_model(raw: Any) -> Optional[ModelSelection]:
    """Coerce a raw API model payload into a :class:`ModelSelection`."""
    if isinstance(raw, dict):
        return ModelSelection(id=raw.get("id", ""), params=raw.get("params"))
    if isinstance(raw, ModelSelection):
        return raw
    return None


class Agent:
    """
    Unified facade for a Cursor Cloud Agent.

    This class provides both class-level factory operations (:meth:`create`,
    :meth:`resume`, :meth:`get`, :meth:`list`, :meth:`prompt`) and
    instance-level operations (:meth:`send`, :meth:`close`, :meth:`reload`,
    :meth:`archive`, :meth:`unarchive`, :meth:`delete`,
    :meth:`list_artifacts`, :meth:`download_artifact`).

    Instances should be obtained through one of the factory class methods
    rather than constructed directly.

    Parameters
    ----------
    _client : CursorClient
        The authenticated HTTP client used for all API calls.
    _data : dict
        The raw agent payload returned by the Cursor API.
    _api_key : str
        The API key associated with this agent session.

    Attributes
    ----------
    agent_id : Optional[str]
        The unique identifier of the agent (e.g. ``"bc-xxxxxxxx"``).
    model : Optional[ModelSelection]
        The model configuration last used for this agent.
    name : Optional[str]
        Human-readable name for the agent.
    status : Optional[str]
        Current lifecycle status (e.g. ``"ACTIVE"``, ``"ARCHIVED"``).
    """

    def __init__(
        self,
        _client: CursorClient,
        _data: Dict[str, Any],
        _api_key: str,
    ) -> None:
        self._client = _client
        self._api_key = _api_key

        # Normalise: creation wraps data in {"agent": {...}, "latestRunId": "..."}
        agent_data = _data.get("agent", _data)

        self.agent_id: Optional[str] = agent_data.get("id")
        self.name: Optional[str] = agent_data.get("name")
        self.status: Optional[str] = agent_data.get("status")
        self.model: Optional[ModelSelection] = _parse_model(agent_data.get("model"))
        self._latest_run_id: Optional[str] = _data.get("latestRunId")
        self._raw: Dict[str, Any] = agent_data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _make_client(cls, api_key: Optional[str]) -> CursorClient:
        """Resolve *api_key* from the argument or ``CURSOR_API_KEY`` env var."""
        key = api_key or os.environ.get("CURSOR_API_KEY")
        if not key:
            raise CursorAgentError(
                "No API key provided.  Pass api_key= or set CURSOR_API_KEY.",
                code="missing_api_key",
            )
        return CursorClient(key)

    @classmethod
    def _from_response(
        cls,
        client: CursorClient,
        resp: Dict[str, Any],
        api_key: str,
    ) -> "Agent":
        """Construct an ``Agent`` from a raw API response dict."""
        return cls(client, resp, api_key)

    # ------------------------------------------------------------------
    # Class-method factories
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        api_key: str,
        prompt: str,
        *,
        cloud: Optional[CloudOptions] = None,
        local: Optional[LocalOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "Agent":
        """
        Create a new Cursor Cloud Agent and enqueue its first run.

        Parameters
        ----------
        api_key : str
            Cursor API key used for authentication.
        prompt : str
            The initial user message / task description for the agent.
        cloud : CloudOptions, optional
            Cloud-execution options (repos, environment, PR settings).
        local : LocalOptions, optional
            Local-execution options (cwd, setting sources).  Accepted for
            forward compatibility; currently unused by the Cloud backend.
        model : Union[str, ModelSelection], optional
            Model to use for this agent. Can be a raw string ID or a 
            ``ModelSelection`` object. Defaults to the account's configured 
            default model when omitted.
        name : str, optional
            A human-readable name for the agent.

        Returns
        -------
        Agent
            A fully initialised ``Agent`` instance with ``agent_id`` and
            ``_latest_run_id`` populated.

        Raises
        ------
        CursorAgentError
            If *api_key* is missing or the API request fails.

        Examples
        --------
        >>> from cursorconnect import Agent
        >>> from cursorconnect.types import CloudOptions, ModelSelection
        >>> agent = Agent.create(
        ...     api_key="sk-...",
        ...     prompt="Refactor src/utils.py to use pathlib",
        ...     cloud=CloudOptions(
        ...         repos=[{"url": "https://github.com/org/repo"}],
        ...         autoCreatePR=True,
        ...     ),
        ...     model=ModelSelection(id="claude-sonnet-4-5"),
        ... )
        >>> print(agent.agent_id)
        bc-xxxxxxxx
        """
        client = cls._make_client(api_key)
        payload: Dict[str, Any] = {"prompt": {"text": prompt}}

        if model is not None:
            if isinstance(model, str):
                payload["model"] = {"id": model}
            else:
                model_payload: Dict[str, Any] = {"id": model.id}
                if model.params:
                    model_payload["params"] = [
                        {"id": p.id, "value": p.value} for p in model.params
                    ]
                payload["model"] = model_payload

        if name is not None:
            payload["name"] = name

        if cloud is not None:
            if cloud.repos:
                payload["repos"] = cloud.repos
            if cloud.env is not None:
                payload["env"] = cloud.env
            if cloud.workOnCurrentBranch is not None:
                payload["workOnCurrentBranch"] = cloud.workOnCurrentBranch
            if cloud.autoCreatePR is not None:
                payload["autoCreatePR"] = cloud.autoCreatePR
            if cloud.skipReviewerRequest is not None:
                payload["skipReviewerRequest"] = cloud.skipReviewerRequest

        resp = client._post("/agents", json=payload)
        return cls._from_response(client, resp, api_key)

    @classmethod
    def prompt(
        cls,
        api_key: str,
        message: str,
        *,
        cloud: Optional[CloudOptions] = None,
        local: Optional[LocalOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "Run":
        """
        One-shot helper: create an agent, send *message*, and return the
        initial :class:`~cursorconnect.run.Run` immediately.

        This is the ergonomic entry point for fire-and-forget workloads where
        you only need the run handle—not a persistent ``Agent`` reference.
        Pair with :meth:`~cursorconnect.run.Run.stream` or
        :meth:`~cursorconnect.run.Run.wait` to consume the output.

        Parameters
        ----------
        api_key : str
            Cursor API key used for authentication.
        message : str
            The user prompt to submit.
        cloud : CloudOptions, optional
            Cloud-execution options.
        local : LocalOptions, optional
            Local-execution options (forward-compatible, currently unused).
        model : ModelSelection, optional
            Model to use.
        name : str, optional
            Human-readable name for the agent.

        Returns
        -------
        Run
            The :class:`~cursorconnect.run.Run` created by the initial message.

        Raises
        ------
        CursorAgentError
            If the agent was created but no initial run ID was returned by
            the API.

        Examples
        --------
        >>> from cursorconnect import Agent
        >>> from cursorconnect.types import CloudOptions, SDKAssistantMessage
        >>> run = Agent.prompt(
        ...     api_key="sk-...",
        ...     message="Write unit tests for src/parser.py",
        ...     cloud=CloudOptions(repos=[{"url": "https://github.com/org/repo"}]),
        ... )
        >>> for event in run.stream():
        ...     if isinstance(event, SDKAssistantMessage):
        ...         content = event.message.get("content", [])
        ...         for block in content:
        ...             if isinstance(block, dict) and block.get("type") == "text":
        ...                 print(block["text"], end="")
        """
        from .run import Run

        agent = cls.create(
            api_key, message, cloud=cloud, local=local, model=model, name=name
        )
        if not agent._latest_run_id:
            raise CursorAgentError(
                "Agent.create did not return a latestRunId; cannot return a Run.",
                code="missing_run_id",
            )
        return Run(
            agent._client,
            agent.agent_id,  # type: ignore[arg-type]
            {"id": agent._latest_run_id},
        )

    @classmethod
    def resume(cls, api_key: str, agent_id: str) -> "Agent":
        """
        Resume an existing agent by its ID.

        A semantic alias for :meth:`get` that makes intent explicit when
        re-attaching to an in-progress or paused agent session.

        Parameters
        ----------
        api_key : str
            Cursor API key used for authentication.
        agent_id : str
            The agent's unique identifier (e.g. ``"bc-xxxxxxxx"``).

        Returns
        -------
        Agent
            The hydrated ``Agent`` instance.
        """
        return cls.get(api_key, agent_id)

    @classmethod
    def get(cls, api_key: str, agent_id: str) -> "Agent":
        """
        Retrieve durable metadata for an existing agent.

        Parameters
        ----------
        api_key : str
            Cursor API key used for authentication.
        agent_id : str
            The agent's unique identifier.

        Returns
        -------
        Agent
            The ``Agent`` instance populated with the latest server-side state.
        """
        client = cls._make_client(api_key)
        resp = client._get(f"/agents/{agent_id}")
        return cls._from_response(client, resp, api_key)

    @classmethod
    def list(
        cls,
        api_key: str,
        *,
        limit: int = 20,
        cursor: Optional[str] = None,
        pr_url: Optional[str] = None,
        include_archived: bool = True,
    ) -> "ListResult[Agent]":
        """
        List agents for the authenticated user, newest first.

        Parameters
        ----------
        api_key : str
            Cursor API key used for authentication.
        limit : int, optional
            Maximum number of agents to return, by default 20.
        cursor : str, optional
            Pagination cursor from a previous :class:`~cursorconnect.types.ListResult`,
            by default ``None``.
        pr_url : str, optional
            Filter agents by associated pull-request URL, by default ``None``.
        include_archived : bool, optional
            Whether to include archived agents in results, by default ``True``.

        Returns
        -------
        ListResult[Agent]
            A paginated result containing :class:`Agent` instances and an
            optional ``nextCursor`` for the following page.
        """
        client = cls._make_client(api_key)
        params: Dict[str, Any] = {
            "limit": limit,
            "includeArchived": str(include_archived).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        if pr_url:
            params["prUrl"] = pr_url

        resp = client._get("/agents", params=params)
        agents = [
            cls._from_response(client, item, api_key)
            for item in resp.get("items", [])
        ]
        return ListResult(items=agents, nextCursor=resp.get("nextCursor"))

    # ------------------------------------------------------------------
    # Instance operations
    # ------------------------------------------------------------------

    def send(
        self,
        message: str,
        options: Optional[SendOptions] = None,
    ) -> "Run":
        """
        Send a follow-up prompt to this agent and return the resulting
        :class:`~cursorconnect.run.Run`.

        Parameters
        ----------
        message : str
            The user message to submit.
        options : SendOptions, optional
            Per-send overrides for model, MCP servers, and callbacks.

        Returns
        -------
        Run
            The newly created run, ready for streaming or blocking.
        """
        from .run import Run

        payload: Dict[str, Any] = {"prompt": {"text": message}}
        if options is not None and options.model is not None:
            if isinstance(options.model, str):
                payload["model"] = {"id": options.model}
            else:
                payload["model"] = {"id": options.model.id}

        resp = self._client._post(f"/agents/{self.agent_id}/runs", json=payload)
        run_data = resp.get("run", resp)
        return Run(self._client, self.agent_id, run_data)  # type: ignore[arg-type]

    def run(
        self,
        message: str,
        *,
        timeout: Optional[float] = None,
        poll_interval: float = 1.5,
    ) -> "RunResult":
        """
        Send a message and block until the run completes.

        This is a convenience shorthand for ``self.send(message).wait(...)``.

        Parameters
        ----------
        message : str
            The user message to submit.
        timeout : Optional[float], optional
            Maximum seconds to wait before raising TimeoutError, by default None.
        poll_interval : float, optional
            Seconds to sleep between status checks, by default 1.5.

        Returns
        -------
        RunResult
            The terminal run result.
        """
        return self.send(message).wait(timeout=timeout, poll_interval=poll_interval)

    @property
    def initial_run(self) -> Optional["Run"]:
        """
        The initial run created alongside this agent.

        When an agent is created via :meth:`create`, a run is immediately
        enqueued. This property returns that initial run, allowing you to
        stream or wait for it without sending a new message.

        Returns
        -------
        Optional[Run]
            The initial :class:`~cursorconnect.run.Run` object, or ``None``
            if no initial run ID was returned by the API.
        """
        if not self._latest_run_id:
            return None
        
        from .run import Run
        return Run(
            self._client,
            self.agent_id,  # type: ignore[arg-type]
            {"id": self._latest_run_id},
        )

    def archive(self) -> None:
        """
        Archive the agent.

        An archived agent remains readable but cannot accept new runs.
        Use :meth:`unarchive` to restore it.
        """
        self._client._post(f"/agents/{self.agent_id}/archive")
        self.status = "ARCHIVED"

    def unarchive(self) -> None:
        """
        Unarchive the agent so it can accept new runs again.
        """
        self._client._post(f"/agents/{self.agent_id}/unarchive")
        self.status = "ACTIVE"

    def delete(self) -> None:
        """
        Permanently delete the agent.

        .. warning::
            This action is irreversible.  All associated runs and artifacts
            are permanently removed.
        """
        self._client._delete(f"/agents/{self.agent_id}")

    def close(self) -> None:
        """
        Close this agent session by archiving it.

        Equivalent to calling :meth:`archive`.  Use this when you are done
        with an agent and want to prevent further runs without permanently
        deleting it.
        """
        self.archive()

    def reload(self) -> "Agent":
        """
        Refresh this agent's metadata from the API in-place.

        Returns
        -------
        Agent
            *self*, with ``name``, ``status``, and ``model`` updated to
            reflect the current server-side state.
        """
        resp = self._client._get(f"/agents/{self.agent_id}")
        agent_data = resp.get("agent", resp)
        self.name = agent_data.get("name", self.name)
        self.status = agent_data.get("status", self.status)
        self.model = _parse_model(agent_data.get("model")) or self.model
        self._raw = agent_data
        return self

    def list_artifacts(self) -> List[Artifact]:
        """
        List file artifacts produced by this agent.

        Returns
        -------
        list of Artifact
            All artifacts available for download, in server-returned order.
        """
        resp = self._client._get(f"/agents/{self.agent_id}/artifacts")
        return [
            Artifact(self._client, self.agent_id, item)
            for item in resp.get("items", [])
        ]

    def download_artifact(self, path: str) -> str:
        """
        Retrieve a presigned download URL for the artifact at *path*.

        The returned URL is valid for approximately 15 minutes and points
        directly to the artifact file in S3.

        Parameters
        ----------
        path : str
            The relative artifact path as returned by :meth:`list_artifacts`.

        Returns
        -------
        str
            A temporary presigned S3 URL for direct download.
        """
        resp = self._client._get(
            f"/agents/{self.agent_id}/artifacts/download",
            params={"path": path},
        )
        return resp.get("url", "")

    def __repr__(self) -> str:
        return (
            f"<Agent agent_id={self.agent_id!r} status={self.status!r}"
            f" name={self.name!r}>"
        )

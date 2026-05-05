"""Unified Agent facade for the CursorConnect SDK.

This module exposes a single :class:`Agent` class that covers the complete
lifecycle of both cloud and local Cursor agents: creation, resumption,
messaging, artifact retrieval, and termination.  Pass ``cloud=CloudOptions``
for cloud execution or ``local=LocalOptions`` for local execution via the
Node.js bridge—the same ``Agent`` / ``Run`` interface applies to both.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

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
    from ._bridge.manager import BridgeManager
    from ._bridge.local_run import LocalRun
    from .types.run_protocol import RunProtocol


def _parse_model(raw: Any) -> Optional[ModelSelection]:
    """Coerce a raw API model payload into a :class:`ModelSelection`."""
    if isinstance(raw, dict):
        return ModelSelection(id=raw.get("id", ""), params=raw.get("params"))
    if isinstance(raw, ModelSelection):
        return raw
    return None


def _resolve_model_payload(model: Optional[Union[str, ModelSelection]]) -> Optional[Dict[str, Any]]:
    """
    Convert a model selection into the dictionary payload expected by the API.

    Handles resolving shorthand IDs, ``ModelParameters``, and the ``thinking=``
    parameter into the canonical JSON structure.
    """
    if model is None:
        return None
    if isinstance(model, str):
        return {"id": model}
    payload: Dict[str, Any] = {"id": model.id}
    resolved = model.resolved_params
    if resolved:
        payload["params"] = [{"id": p.id, "value": p.value} for p in resolved]
    return payload


import threading as _threading

_bridge_lock = _threading.Lock()


def _get_bridge(api_key: Optional[str] = None) -> "BridgeManager":
    """Lazily import and return a shared BridgeManager singleton.

    Thread-safe: the bridge is started exactly once even when multiple
    threads request it concurrently (e.g. from a Mesh).
    """
    from ._bridge.manager import BridgeManager

    with _bridge_lock:
        if not hasattr(_get_bridge, "_instance"):
            bridge_js = os.path.join(
                os.path.dirname(__file__), "_bridge", "bridge.js"
            )
            bridge = BridgeManager(bridge_js, api_key=api_key)
            bridge.start()
            _get_bridge._instance = bridge
    return _get_bridge._instance


class Agent:
    """
    Unified facade for Cursor Agents (cloud and local).

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
        _client: Optional[CursorClient],
        _data: Dict[str, Any],
        _api_key: str,
        *,
        _bridge: Optional["BridgeManager"] = None,
        _bridge_agent_id: Optional[str] = None,
        _local: Optional[LocalOptions] = None,
    ) -> None:
        self._client = _client
        self._api_key = _api_key
        self._bridge = _bridge
        self._bridge_agent_id = _bridge_agent_id
        self._local = _local
        self._is_local = _bridge is not None

        # Normalise: creation wraps data in {"agent": {...}, "latestRunId": "..."}
        agent_data = _data.get("agent", _data)

        self.agent_id: Optional[str] = agent_data.get("id") or _bridge_agent_id
        self.name: Optional[str] = agent_data.get("name")
        self.status: Optional[str] = agent_data.get("status", "ACTIVE" if self._is_local else None)
        self.model: Optional[ModelSelection] = _parse_model(agent_data.get("model"))
        self._latest_run_id: Optional[str] = _data.get("latestRunId") or _data.get("runId")
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
        prompt: str,
        *,
        api_key: Optional[str] = None,
        cloud: Optional[CloudOptions] = None,
        local: Optional[LocalOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "Agent":
        """
        Create a new Cursor Agent and enqueue its first run.

        Automatically selects the runtime based on which options are provided:
        pass ``cloud`` for cloud execution, or ``local`` for local execution
        via the Node.js bridge to the TypeScript SDK.

        Parameters
        ----------
        prompt : str
            The initial user message / task description for the agent.
        api_key : str, optional
            Cursor API key. Required for cloud agents. Falls back to the
            ``CURSOR_API_KEY`` environment variable when omitted.
        cloud : CloudOptions, optional
            Cloud-execution options (repos, environment, PR settings).
        local : LocalOptions, optional
            Local-execution options (cwd, setting sources). When provided
            (and ``cloud`` is not), the agent runs locally via the Node.js
            bridge.
        model : Union[str, ModelSelection], optional
            Model to use. Supports ``ModelParameters`` and the ``thinking=`` shorthand. Can be a raw string ID or a ``ModelSelection``
            object. Supports ``ModelParameters`` and the ``thinking=`` shorthand.
            Defaults to the account's configured default when omitted.
        name : str, optional
            A human-readable name for the agent.

        Returns
        -------
        Agent
            A fully initialised ``Agent`` instance.

        Raises
        ------
        CursorAgentError
            If required arguments are missing or the request fails.
        """
        if local is not None and cloud is not None:
            raise ValueError("Cannot specify both 'local' and 'cloud' options. Choose one runtime.")

        if local is not None and cloud is None:
            return cls._create_local(prompt, local=local, api_key=api_key, model=model, name=name)

        return cls._create_cloud(prompt, api_key=api_key, cloud=cloud, model=model, name=name)

    @classmethod
    def _create_cloud(
        cls,
        prompt: str,
        *,
        api_key: Optional[str] = None,
        cloud: Optional[CloudOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "Agent":
        client = cls._make_client(api_key)
        key = api_key or os.environ.get("CURSOR_API_KEY", "")
        payload: Dict[str, Any] = {"prompt": {"text": prompt}}

        model_payload = _resolve_model_payload(model)
        if model_payload is not None:
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
        return cls._from_response(client, resp, key)

    @classmethod
    def _create_local(
        cls,
        prompt: str,
        *,
        local: LocalOptions,
        api_key: Optional[str] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "Agent":
        from ._bridge.local_run import _run_async

        key = api_key or os.environ.get("CURSOR_API_KEY", "")
        bridge = _get_bridge(api_key=key)

        options: Dict[str, Any] = {}
        if key:
            options["apiKey"] = key

        local_opts: Dict[str, Any] = {}
        if local.cwd is not None:
            local_opts["cwd"] = local.cwd
        if local.settingSources is not None:
            local_opts["settingSources"] = local.settingSources
        if local.sandboxOptions is not None:
            local_opts["sandboxOptions"] = local.sandboxOptions
        if local_opts:
            options["local"] = local_opts

        model_payload = _resolve_model_payload(model)
        if model_payload is not None:
            options["model"] = model_payload

        if name is not None:
            options["name"] = name

        resp = _run_async(bridge.send_request("Agent.create", args=[options]))
        if not isinstance(resp, dict):
            raise CursorAgentError(f"Bridge returned unexpected response type: {type(resp).__name__}")
        if "agentId" not in resp:
            raise CursorAgentError("Bridge response missing required key 'agentId'")
        bridge_agent_id = resp["agentId"]

        send_resp = _run_async(bridge.send_request(
            "agent.send",
            target=bridge_agent_id,
            args=[prompt, {"streamEvents": True}],
        ))
        if not isinstance(send_resp, dict):
            raise CursorAgentError(f"Bridge returned unexpected response type: {type(send_resp).__name__}")
        if "runId" not in send_resp:
            raise CursorAgentError("Bridge response missing required key 'runId'")
        bridge_run_id = send_resp["runId"]

        data: Dict[str, Any] = {
            "id": bridge_agent_id,
            "name": name,
            "status": "ACTIVE",
            "runId": bridge_run_id,
        }

        return cls(
            None, data, key,
            _bridge=bridge,
            _bridge_agent_id=bridge_agent_id,
            _local=local,
        )

    @classmethod
    def prompt(
        cls,
        message: str,
        *,
        api_key: Optional[str] = None,
        cloud: Optional[CloudOptions] = None,
        local: Optional[LocalOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        name: Optional[str] = None,
    ) -> "RunProtocol":
        """
        One-shot helper: create an agent, send *message*, and return the
        initial run immediately.

        This is the ergonomic entry point for fire-and-forget workloads where
        you only need the run handle. Works with both cloud and local execution.

        Parameters
        ----------
        message : str
            The user prompt to submit.
        api_key : str, optional
            Cursor API key. Falls back to ``CURSOR_API_KEY`` env var.
        cloud : CloudOptions, optional
            Cloud-execution options.
        local : LocalOptions, optional
            Local-execution options.
        model : Union[str, ModelSelection], optional
            Model to use.
        name : str, optional
            Human-readable name for the agent.

        Returns
        -------
        RunProtocol
            The run created by the initial message. This object implements
            the ``RunProtocol`` interface (``stream()``, ``wait()``, ``cancel()``).
        """
        agent = cls.create(
            message, api_key=api_key, cloud=cloud, local=local, model=model, name=name
        )
        if agent._is_local:
            return agent._make_local_run()

        from .run import Run
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
    ) -> "RunProtocol":
        """
        Send a follow-up prompt to this agent and return the resulting run.

        Parameters
        ----------
        message : str
            The user message to submit.
        options : SendOptions, optional
            Per-send overrides for model, MCP servers, and callbacks.

        Returns
        -------
        RunProtocol
            The newly created run, ready for streaming or blocking.
        """
        if self._is_local:
            return self._send_local(message, options)

        from .run import Run

        payload: Dict[str, Any] = {"prompt": {"text": message}}
        if options is not None and options.model is not None:
            model_payload = _resolve_model_payload(options.model)
            if model_payload is not None:
                payload["model"] = model_payload

        resp = self._client._post(f"/agents/{self.agent_id}/runs", json=payload)
        run_data = resp.get("run", resp)
        return Run(self._client, self.agent_id, run_data)  # type: ignore[arg-type]

    def _send_local(self, message: str, options: Optional[SendOptions] = None) -> "LocalRun":
        from ._bridge.local_run import LocalRun, _run_async

        send_opts: Dict[str, Any] = {"streamEvents": True}
        if options is not None and options.model is not None:
            model_payload = _resolve_model_payload(options.model)
            if model_payload is not None:
                send_opts["model"] = model_payload

        resp = _run_async(self._bridge.send_request(
            "agent.send",
            target=self._bridge_agent_id,
            args=[message, send_opts],
        ))

        bridge_run_id = ""
        if isinstance(resp, dict):
            bridge_run_id = resp.get("runId", "")

        return LocalRun(
            self._bridge,
            self._bridge_agent_id or "",
            bridge_run_id,
            self.agent_id or "",
        )

    def _make_local_run(self) -> "LocalRun":
        from ._bridge.local_run import LocalRun
        return LocalRun(
            self._bridge,
            self._bridge_agent_id or "",
            self._latest_run_id or "",
            self.agent_id or "",
        )

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
    def initial_run(self) -> Optional["RunProtocol"]:
        """
        The initial run created alongside this agent.

        When an agent is created via :meth:`create`, a run is immediately
        enqueued. This property returns that initial run, allowing you to
        stream or wait for it without sending a new message.

        Returns
        -------
        Optional[RunProtocol]
            The initial run object, or ``None`` if no initial run ID was
            returned.
        """
        if not self._latest_run_id:
            return None

        if self._is_local:
            return self._make_local_run()

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

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("archive() is not supported for local agents.", operation="archive")
        self._client._post(f"/agents/{self.agent_id}/archive")
        self.status = "ARCHIVED"

    def unarchive(self) -> None:
        """
        Unarchive the agent so it can accept new runs again.

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("unarchive() is not supported for local agents.", operation="unarchive")
        self._client._post(f"/agents/{self.agent_id}/unarchive")
        self.status = "ACTIVE"

    def delete(self) -> None:
        """
        Permanently delete the agent.

        .. warning::
            This action is irreversible.  All associated runs and artifacts
            are permanently removed.

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("delete() is not supported for local agents.", operation="delete")
        self._client._delete(f"/agents/{self.agent_id}")

    def close(self) -> None:
        """
        Close this agent session.

        For cloud agents, this archives the agent. For local agents, this
        sends a close command through the bridge.
        """
        if self._is_local:
            from ._bridge.local_run import _run_async
            try:
                _run_async(self._bridge.send_request(
                    "agent.close", target=self._bridge_agent_id
                ))
            except Exception:
                pass
            self.status = "CLOSED"
            return
        self.archive()

    def reload(self) -> "Agent":
        """
        Refresh this agent's metadata from the API in-place.

        Returns
        -------
        Agent
            *self*, with ``name``, ``status``, and ``model`` updated to
            reflect the current server-side state.

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("reload() is not supported for local agents.", operation="reload")
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

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("list_artifacts() is not supported for local agents.", operation="list_artifacts")
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

        Raises
        ------
        UnsupportedRunOperationError
            If the agent is a local agent.
        """
        if self._is_local:
            raise UnsupportedRunOperationError("download_artifact() is not supported for local agents.", operation="download_artifact")
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

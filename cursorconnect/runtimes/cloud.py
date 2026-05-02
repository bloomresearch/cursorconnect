"""
Cloud runtime backend – wraps the Cursor REST API over HTTPS.

All HTTP errors are translated into the appropriate
:mod:`cursorconnect.exceptions` subclass via
:func:`~cursorconnect.exceptions.map_http_error`, and network-level failures
(timeouts, connection errors) are normalised to
:class:`~cursorconnect.exceptions.NetworkError`.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Generator, List, Optional

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from cursorconnect.exceptions import NetworkError, map_http_error
from cursorconnect.types.messages import Message, parse_message

_BASE_URL = "https://api.cursor.com/v1"

# Statuses that indicate a run has stopped progressing.
_TERMINAL_STATES: frozenset[str] = frozenset(
    {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}
)


class CloudRuntime:
    """
    ``RuntimeBackend`` implementation that communicates with the Cursor REST API.

    Credentials are attached via HTTP Basic Auth using the ``api_key:`` format
    documented in the Cursor API reference.  A single :class:`requests.Session`
    is reused across all calls to benefit from connection pooling.

    Parameters
    ----------
    api_key : str
        A valid Cursor API key.
    base_url : str, optional
        Override the API base URL.  Primarily useful for testing against a
        local mock server.  Defaults to ``"https://api.cursor.com/v1"``.

    Attributes
    ----------
    api_key : str
        The API key provided at construction time.
    base_url : str
        The base URL prefix prepended to every request path.

    Examples
    --------
    >>> rt = CloudRuntime(api_key="sk-…")
    >>> agent_data = rt.create_agent("Fix the null-pointer bug",
    ...                               repo_url="https://github.com/org/repo")
    >>> rt.close()

    Using as a context manager ensures the session is always closed::

        with CloudRuntime(api_key="sk-…") as rt:
            rt.list_agents()
    """

    def __init__(self, api_key: str, base_url: str = _BASE_URL) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session: requests.Session = self._build_session()

    # ------------------------------------------------------------------
    # Internal transport helpers
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """
        Construct a new ``requests.Session`` pre-configured for the Cursor API.

        Returns
        -------
        requests.Session
            A session with Basic Auth attached using ``(api_key, "")``.
        """
        session = requests.Session()
        session.auth = (self.api_key, "")
        return session

    def _request(
        self,
        method: str,
        path: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """
        Dispatch a single HTTP request and normalise errors to typed exceptions.

        Parameters
        ----------
        method : str
            HTTP verb (``"GET"``, ``"POST"``, ``"DELETE"``, …).
        path : str
            API path relative to :attr:`base_url` (must start with ``"/"``).
        stream : bool, optional
            When ``True``, return the raw :class:`requests.Response` for
            SSE / chunked-transfer consumption without reading the body,
            by default ``False``.
        **kwargs : Any
            Forwarded verbatim to :meth:`requests.Session.request`.

        Returns
        -------
        dict or requests.Response
            Parsed JSON body for non-streaming calls; the raw
            :class:`requests.Response` object for streaming calls.

        Raises
        ------
        NetworkError
            On transport-level failures (timeout, connection refused, DNS).
        CursorAgentError
            Any subclass mapped by :func:`map_http_error` for non-2xx responses.
        """
        url = f"{self.base_url}{path}"
        try:
            response = self._session.request(method, url, stream=stream, **kwargs)
        except (RequestsConnectionError, RequestsTimeout) as exc:
            raise NetworkError(
                f"Network error while calling {method} {url}: {exc}",
                cause=exc,
            ) from exc

        if stream:
            response.raise_for_status()
            return response

        if not response.ok:
            self._raise_for_response(response)

        return response.json() if response.content else {}

    def _raise_for_response(self, response: requests.Response) -> None:
        """
        Parse a non-2xx response body and raise the appropriate typed exception.

        The API error envelope is expected to follow the shape
        ``{"error": {"message": "…", "code": "…", "provider": "…", "helpUrl": "…"}}``.
        Falls back to raw response text when the body is not valid JSON.

        Parameters
        ----------
        response : requests.Response
            A response with a non-2xx status code.

        Raises
        ------
        CursorAgentError
            The most specific subclass that matches the status code and error body.
        """
        try:
            body = response.json()
        except ValueError:
            body = {}

        error_obj = body.get("error", {}) if isinstance(body, dict) else {}
        if isinstance(error_obj, dict):
            message: str = error_obj.get("message", response.text)
            code: Optional[str] = error_obj.get("code")
            provider: Optional[str] = error_obj.get("provider")
            help_url: Optional[str] = error_obj.get("helpUrl")
        else:
            message = response.text
            code = None
            provider = None
            help_url = None

        extra: Dict[str, Any] = {}
        if provider:
            extra["provider"] = provider
        if help_url:
            extra["help_url"] = help_url

        raise map_http_error(response.status_code, message, code=code, **extra)

    def _get(self, path: str, **kwargs: Any) -> Any:
        """Issue a GET request.  See :meth:`_request` for full parameter docs."""
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs: Any) -> Any:
        """Issue a POST request.  See :meth:`_request` for full parameter docs."""
        return self._request("POST", path, **kwargs)

    def _delete(self, path: str, **kwargs: Any) -> Any:
        """Issue a DELETE request.  See :meth:`_request` for full parameter docs."""
        return self._request("DELETE", path, **kwargs)

    # ------------------------------------------------------------------
    # RuntimeBackend implementation
    # ------------------------------------------------------------------

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
        payload: Dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "repos": [{"url": repo_url, "startingRef": starting_ref}],
        }
        if model_id:
            payload["model"] = {"id": model_id}
        payload.update(kwargs)
        return self._post("/agents", json=payload)

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
            Image attachments, each with ``"url"`` and/or ``"base64"`` keys,
            by default None.

        Returns
        -------
        dict
            Raw API response containing the newly created ``run`` object.
        """
        payload: Dict[str, Any] = {"prompt": {"text": prompt_text}}
        if images:
            payload["prompt"]["images"] = images
        return self._post(f"/agents/{agent_id}/runs", json=payload)

    def stream_run(
        self,
        agent_id: str,
        run_id: str,
    ) -> Generator[Message, None, None]:
        """
        Open a Server-Sent Events stream for a run and yield typed messages.

        Connects to ``GET /agents/{agent_id}/runs/{run_id}/stream`` and parses
        the SSE byte stream line-by-line.  Each complete event is handed to
        :func:`~cursorconnect.types.messages.parse_message` before being
        yielded.  The generator closes naturally once the server exhausts the
        stream (typically after the terminal ``status`` event).

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run to stream.

        Yields
        ------
        Message
            One typed message object per complete SSE event received.

        Raises
        ------
        NetworkError
            If the TCP connection is lost mid-stream.
        CursorAgentError
            On a non-2xx HTTP opening handshake.
        """
        path = f"/agents/{agent_id}/runs/{run_id}/stream"
        response = self._request(
            "GET",
            path,
            stream=True,
            headers={"Accept": "text/event-stream"},
        )

        event_type: Optional[str] = None
        event_id: Optional[str] = None

        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    # Empty line signals end of one SSE event block; reset state.
                    event_type = None
                    event_id = None
                    continue

                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("id: "):
                    event_id = line[4:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:].strip()
                    if not data_str or data_str == "{}":
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    yield parse_message(data)
        except (RequestsConnectionError, RequestsTimeout) as exc:
            raise NetworkError(
                f"Stream interrupted for run {run_id}: {exc}",
                cause=exc,
            ) from exc
        finally:
            response.close()

    def _fetch_run(self, agent_id: str, run_id: str) -> Dict[str, Any]:
        """
        Retrieve the current state of a single run.

        Normalises both the direct-object response shape and the
        ``{"items": [...]}`` envelope that some API versions return for
        the single-run endpoint.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run.

        Returns
        -------
        dict
            The run data object with at minimum a ``"status"`` key.
        """
        res = self._get(f"/agents/{agent_id}/runs/{run_id}")
        if isinstance(res, dict) and "items" in res:
            items: List[Dict[str, Any]] = res.get("items", [])
            return items[0] if items else res
        return res

    def wait_run(
        self,
        agent_id: str,
        run_id: str,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Block until a run reaches a terminal status, polling via REST.

        Polls :meth:`_fetch_run` every *poll_interval* seconds.  Terminal
        statuses are ``FINISHED``, ``ERROR``, ``CANCELLED``, and ``EXPIRED``.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent.
        run_id : str
            The unique identifier of the run to wait for.
        poll_interval : float, optional
            Seconds between consecutive status polls, by default ``2.0``.
        timeout : float, optional
            Maximum seconds to wait before raising :class:`TimeoutError`.
            ``None`` (default) means wait indefinitely.

        Returns
        -------
        dict
            The final run data object returned by the API once a terminal
            status has been reached.

        Raises
        ------
        TimeoutError
            If the run has not completed within *timeout* seconds.
        """
        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            run_data = self._fetch_run(agent_id, run_id)
            status: str = run_data.get("status", "")

            if status in _TERMINAL_STATES:
                return run_data

            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Run {run_id!r} did not reach a terminal state within "
                    f"{timeout}s (current status: {status!r})."
                )

            time.sleep(poll_interval)

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
        self._post(f"/agents/{agent_id}/runs/{run_id}/cancel")

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
        res = self._get(f"/agents/{agent_id}/conversation")
        if isinstance(res, dict):
            return res.get("items", [res])
        return res

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
            Raw agent metadata as returned by ``GET /agents/{agent_id}``.
        """
        return self._get(f"/agents/{agent_id}")

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
            Response with ``{"items": [...], "nextCursor": "..."}``.
        """
        params: Dict[str, Any] = {
            "limit": limit,
            "includeArchived": str(include_archived).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        if pr_url:
            params["prUrl"] = pr_url
        return self._get("/agents", params=params)

    def archive_agent(self, agent_id: str) -> None:
        """
        Archive an agent so it can no longer accept new runs.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent to archive.
        """
        self._post(f"/agents/{agent_id}/archive")

    def delete_agent(self, agent_id: str) -> None:
        """
        Permanently delete an agent. This action is irreversible.

        Parameters
        ----------
        agent_id : str
            The unique identifier of the agent to delete.
        """
        self._delete(f"/agents/{agent_id}")

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
            Artifact metadata objects with ``path``, ``sizeBytes``, and
            ``updatedAt`` fields.
        """
        res = self._get(f"/agents/{agent_id}/artifacts")
        return res.get("items", [])

    def download_artifact(self, agent_id: str, path: str) -> str:
        """
        Retrieve a presigned S3 download URL for a specific artifact.

        The URL is valid for approximately 15 minutes after generation.

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
        res = self._get(
            f"/agents/{agent_id}/artifacts/download",
            params={"path": path},
        )
        return res.get("url", "")

    def close(self) -> None:
        """
        Close the underlying HTTP session and release all pooled connections.

        Safe to call multiple times; subsequent calls are silently ignored.
        """
        try:
            self._session.close()
        except Exception:
            pass

    def reload(self) -> None:
        """
        Close the current HTTP session and open a fresh one.

        Useful for clearing stale connection-pool entries or picking up newly
        rotated credentials without constructing a brand-new ``CloudRuntime``.
        """
        self.close()
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "CloudRuntime":
        """Return self to support ``with CloudRuntime(…) as rt:`` usage."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Ensure the session is closed when leaving a ``with`` block."""
        self.close()

    def __repr__(self) -> str:
        masked = f"{self.api_key[:6]}…" if len(self.api_key) > 6 else "***"
        return f"<CloudRuntime base_url={self.base_url!r} api_key={masked!r}>"

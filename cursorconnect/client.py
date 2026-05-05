import warnings
import requests
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .exceptions import CursorAgentError, map_http_error
from .types import CloudOptions, ModelSelection

if TYPE_CHECKING:
    from .agent import Agent
    from .run import Run

class _ArtifactsShim:
    def __init__(self, agent: 'Agent'):
        self._agent = agent

    def list(self) -> List[Any]:
        return self._agent.list_artifacts()

class _RunsShim:
    def __init__(self, agent: 'Agent'):
        self._agent = agent

    def get(self, run_id: str) -> 'Run':
        from .run import Run
        return Run(self._agent._client, self._agent.agent_id, {"id": run_id})

class _AgentShimWrapper:
    def __init__(self, agent: 'Agent'):
        self._agent = agent
        self.runs = _RunsShim(agent)
        self.artifacts = _ArtifactsShim(agent)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def delete(self) -> None:
        self._agent.delete()

    def __repr__(self) -> str:
        return repr(self._agent)

class _AgentManagerShim:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def create(self, prompt_text: str, repo_url: Optional[str] = None,
               starting_ref: str = "main",
               model_id: Optional[str] = None, **kwargs) -> _AgentShimWrapper:
        from .agent import Agent

        create_kwargs = dict(kwargs)

        if "cloud" not in create_kwargs and "local" not in create_kwargs and repo_url:
            cloud_opts = CloudOptions(repos=[{"url": repo_url, "startingRef": starting_ref}])
            if "autoCreatePR" in create_kwargs:
                cloud_opts.autoCreatePR = create_kwargs.pop("autoCreatePR")
            if "workOnCurrentBranch" in create_kwargs:
                cloud_opts.workOnCurrentBranch = create_kwargs.pop("workOnCurrentBranch")
            create_kwargs["cloud"] = cloud_opts

        model = ModelSelection(id=model_id) if model_id else create_kwargs.pop("model", None)

        agent = Agent.create(
            prompt_text,
            api_key=self._api_key,
            model=model,
            **create_kwargs,
        )
        return _AgentShimWrapper(agent)

    def get(self, agent_id: str) -> _AgentShimWrapper:
        from .agent import Agent
        agent = Agent.get(self._api_key, agent_id)
        return _AgentShimWrapper(agent)

    def list(self, limit: int = 20, cursor: Optional[str] = None, 
             pr_url: Optional[str] = None, include_archived: bool = True) -> Dict[str, Any]:
        from .agent import Agent
        result = Agent.list(
            self._api_key, 
            limit=limit, 
            cursor=cursor, 
            pr_url=pr_url, 
            include_archived=include_archived
        )
        items = [_AgentShimWrapper(a) for a in result.items]
        return {"items": items, "nextCursor": result.nextCursor}

class CursorClient:
    """
    Deprecated compatibility shim for the Cursor API.

    This class is preserved for backward compatibility. New code should use the
    high-level :class:`~cursorconnect.agent.Agent` and :class:`~cursorconnect.cursor.Cursor` 
    facades instead.

    Parameters
    ----------
    api_key : str
        The Cursor API key used for authentication.

    Attributes
    ----------
    api_key : str
        The provided API key.
    session : requests.Session
        The authenticated HTTP session.
    agents : _AgentManagerShim
        The legacy agent manager facade.

    Examples
    --------
    >>> import warnings
    >>> warnings.simplefilter("ignore", DeprecationWarning)
    >>> client = CursorClient(api_key="sk-...")
    >>> agent = client.agents.create(prompt_text="Hello", repo_url="...")
    """
    BASE_URL = "https://api.cursor.com/v1"

    def __init__(self, api_key: str):
        warnings.warn(
            "CursorClient is deprecated. Use Agent.create(), Agent.prompt(), or the Cursor namespace directly.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not api_key:
            raise ValueError("API Key must be provided.")
        self.api_key = api_key
        
        self.session = requests.Session()
        self.session.auth = (self.api_key, "")
        
        self.agents = _AgentManagerShim(self.api_key)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.BASE_URL}{path}"
        stream = kwargs.pop("stream", False)
        
        response = self.session.request(method, url, stream=stream, **kwargs)
        
        if stream:
            response.raise_for_status()
            return response

        if not response.ok:
            raise map_http_error(response.status_code, response.text)

        if response.content:
            return response.json()
        return {}

    def _get(self, path: str, **kwargs): return self._request("GET", path, **kwargs)
    def _post(self, path: str, **kwargs): return self._request("POST", path, **kwargs)
    def _delete(self, path: str, **kwargs): return self._request("DELETE", path, **kwargs)

    def get_me(self) -> Dict[str, Any]:
        """
        Retrieve information about the API key being used.

        Returns
        -------
        dict
            A dictionary containing ``apiKeyName``, ``userEmail``, and ``createdAt``.

        See Also
        --------
        cursorconnect.cursor.Cursor.me : The modern equivalent.
        """
        from .cursor import Cursor
        user = Cursor.me(self.api_key)
        return {
            "apiKeyName": user.api_key_name,
            "userEmail": user.user_email,
            "createdAt": user.created_at,
        }

    def list_models(self) -> List[str]:
        """
        Returns a recommended set of explicit model IDs you can pass to the API.

        Returns
        -------
        list of str
            A list of model ID strings.

        See Also
        --------
        cursorconnect.cursor.Cursor.models.list : The modern equivalent.
        """
        from .cursor import Cursor
        models = Cursor.models.list(self.api_key)
        return [m.id for m in models]

    def list_repositories(self) -> List[str]:
        """
        List GitHub repositories accessible to the user.

        .. warning::
            This endpoint has a strict limit of 1/user/minute and 30/user/hour.

        Returns
        -------
        list of str
            A list of repository URLs.

        See Also
        --------
        cursorconnect.cursor.Cursor.repositories.list : The modern equivalent.
        """
        from .cursor import Cursor
        repos = Cursor.repositories.list(self.api_key)
        return [r.url for r in repos]

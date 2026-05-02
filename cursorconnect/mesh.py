"""
Orchestration layer for executing parallel agents with peer-to-peer cross-checking.
"""

from __future__ import annotations

import threading
import concurrent.futures
from typing import Callable, Dict, List, Literal, Optional, Union, Any

from .agent import Agent
from .types import CloudOptions, ModelSelection
from .types.mesh import MeshTask, MeshResult

CleanupStrategy = Literal["archive", "delete"]


class Mesh:
    """
    Orchestrator for managing parallel agent tasks.

    The Mesh handles the concurrent execution of multiple agents, optionally
    broadcasting the results of finished agents to still-running peers
    (cross-checking), and ensuring all created agents are cleaned up.

    Parameters
    ----------
    api_key : Optional[str], optional
        The Cursor API key to use for all agents, by default None (reads from env).
    cloud : Optional[CloudOptions], optional
        Default cloud options for all tasks, by default None.
    model : Optional[Union[str, ModelSelection]], optional
        Default model selection for all tasks, by default None.
    max_workers : Optional[int], optional
        Maximum number of concurrent agent threads. Defaults to the number of tasks.
    cross_check : Union[bool, Callable[[MeshResult, List[Agent]], str]], optional
        If True, broadcasts a default summary of completed tasks to running peers.
        If a callable, it must accept a `MeshResult` and a list of running `Agent`
        objects, and return a string to send to the peers. By default False.
    cleanup : Optional[CleanupStrategy], optional
        How to clean up agents when the context manager exits. One of "archive",
        "delete", or None. By default "archive".
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        cloud: Optional[CloudOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        max_workers: Optional[int] = None,
        cross_check: Union[bool, Callable[[MeshResult, List[Agent]], str]] = False,
        cleanup: Optional[CleanupStrategy] = "archive",
    ) -> None:
        self.api_key = api_key
        self.cloud = cloud
        self.model = model
        self.max_workers = max_workers
        self.cross_check = cross_check
        self.cleanup = cleanup

        self._tasks: List[MeshTask] = []
        self._results: List[MeshResult] = []
        self._agents: List[Agent] = []
        
        # Thread-safe tracking of live agents for cross-checking
        self._lock = threading.Lock()
        self._live_agents: Dict[str, Agent] = {}

    def add(
        self,
        name_or_task: Union[str, MeshTask],
        prompt: Optional[str] = None,
        *,
        cloud: Optional[CloudOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
    ) -> "Mesh":
        """
        Register a new task to be executed.

        Parameters
        ----------
        name_or_task : Union[str, MeshTask]
            Either a unique identifier string for a new task, or a pre-configured
            ``MeshTask`` instance.
        prompt : Optional[str]
            The instruction for the agent. Required if ``name_or_task`` is a string.
        cloud : Optional[CloudOptions], optional
            Task-specific cloud options (overrides Mesh defaults), by default None.
        model : Optional[Union[str, ModelSelection]], optional
            Task-specific model selection (overrides Mesh defaults), by default None.

        Returns
        -------
        Mesh
            Returns ``self`` to allow chaining (e.g., ``mesh.add(...).add(...)``).
        """
        if isinstance(name_or_task, MeshTask):
            # Apply mesh-level defaults if the task doesn't override them
            if name_or_task.cloud is None and self.cloud is not None:
                name_or_task.cloud = self.cloud
            if name_or_task.model is None and self.model is not None:
                name_or_task.model = self.model
            self._tasks.append(name_or_task)
        else:
            if prompt is None:
                raise ValueError("prompt is required when name_or_task is a string")
            self._tasks.append(
                MeshTask(
                    name=name_or_task,
                    prompt=prompt,
                    cloud=cloud or self.cloud,
                    model=model or self.model,
                )
            )
        return self

    def __add__(self, task: MeshTask) -> "Mesh":
        """
        Operator overload for ``+`` to register a task.
        
        Allows intuitive setup: ``mesh = mesh + task1 + task2`` or 
        inside a context manager: ``mesh + task1 + task2``.
        
        Returns
        -------
        Mesh
            Returns ``self`` (mutates in-place).
        """
        if not isinstance(task, MeshTask):
            return NotImplemented
        return self.add(task)

    def __iadd__(self, task: MeshTask) -> "Mesh":
        """
        Operator overload for ``+=`` to register a task.
        """
        if not isinstance(task, MeshTask):
            return NotImplemented
        return self.add(task)

    def run(self, timeout: Optional[float] = None) -> List[MeshResult]:
        """
        Execute all registered tasks concurrently.

        Parameters
        ----------
        timeout : Optional[float], optional
            Maximum seconds to wait for each task, by default None.

        Returns
        -------
        List[MeshResult]
            The collected results from all tasks.
        """
        max_workers = self.max_workers or max(1, len(self._tasks))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._execute_task, task, timeout): task
                for task in self._tasks
            }
            
            for future in concurrent.futures.as_completed(futures):
                # The _execute_task method handles its own exceptions and builds
                # a MeshResult, but if a raw exception bubbled up, we'd catch it here.
                # In this design, we let it bubble so the user sees the failure.
                result = future.result()
                self._results.append(result)
                
        return self._results

    def __call__(self, timeout: Optional[float] = None) -> List[MeshResult]:
        """
        Execute all registered tasks concurrently (alias for `run()`).
        """
        return self.run(timeout=timeout)

    def results(self) -> List[MeshResult]:
        """
        Return the collected results of all tasks that have completed so far.

        Returns
        -------
        List[MeshResult]
            The list of results.
        """
        return self._results

    def __enter__(self) -> "Mesh":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self.cleanup:
            return
            
        for agent in self._agents:
            try:
                if self.cleanup == "archive":
                    agent.archive()
                elif self.cleanup == "delete":
                    agent.delete()
            except Exception:
                # Swallow cleanup errors on exit so we don't mask original exceptions
                pass

    def _execute_task(self, task: MeshTask, timeout: Optional[float]) -> MeshResult:
        """Internal worker method to execute a single task."""
        kwargs: Dict[str, Any] = {
            "prompt": task.prompt,
            "name": task.name,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        # fallback to env var logic handles missing api_key in Agent.create if not explicitly provided
        elif "api_key" not in kwargs and self.api_key is None:
            # We don't provide api_key so Agent.create will use the env var
            kwargs["api_key"] = None # Will be caught by _make_client

        if task.cloud:
            kwargs["cloud"] = task.cloud
        if task.model:
            kwargs["model"] = task.model

        # 1. Create the agent
        # If kwargs["api_key"] is None, pop it so we pass either a string or nothing.
        # Actually, Agent.create takes api_key as a positional argument or kwarg without default.
        # We need to resolve api_key to pass to create, or pass None if allowed.
        # Agent.create requires api_key: str. Let's resolve it here if needed, or pass an empty string and let create handle it?
        # Actually Agent.create signature: create(cls, api_key: str, ...)
        
        # Let's resolve api_key properly.
        from cursorconnect.exceptions import CursorAgentError
        import os
        api_key = self.api_key or os.environ.get("CURSOR_API_KEY")
        if not api_key:
            raise CursorAgentError("No API key provided.", code="missing_api_key")
        
        # Remove api_key from kwargs if it's there so we don't pass it twice
        if "api_key" in kwargs:
            del kwargs["api_key"]

        agent = Agent.create(api_key=api_key, **kwargs)
        
        with self._lock:
            self._agents.append(agent)
            self._live_agents[task.name] = agent

        # 2. Wait for the initial run
        run_obj = agent.initial_run
        if not run_obj:
            raise CursorAgentError(f"Task {task.name} failed to enqueue an initial run.")
            
        run_result = run_obj.wait(timeout=timeout)
        
        # Enrich the run result with the agent_id
        run_result.agent_id = agent.agent_id
        
        # 3. Fetch artifacts
        artifacts = agent.list_artifacts()
        run_result.artifacts = artifacts
        
        mesh_result = MeshResult(
            name=task.name,
            agent=agent,
            run_result=run_result,
            artifacts=artifacts,
        )

        # 4. Remove from live agents and optionally cross-check
        with self._lock:
            if task.name in self._live_agents:
                del self._live_agents[task.name]
            peers = list(self._live_agents.values())

        if self.cross_check and peers:
            self._broadcast_cross_check(mesh_result, peers)

        return mesh_result

    def _broadcast_cross_check(self, finished: MeshResult, peers: List[Agent]) -> None:
        """Send a cross-check message to all currently running peers."""
        if callable(self.cross_check):
            message = self.cross_check(finished, peers)
        else:
            # Default cross-check message
            message = (
                f"CROSS-CHECK UPDATE: Peer task '{finished.name}' has finished "
                f"with status '{finished.run_result.status}'.\n\n"
                f"Please review your own work for any conflicts."
            )
            
        if not message:
            return

        # Send the message to all peers in parallel so we don't block this worker thread
        # on HTTP requests to add messages to other agents.
        def _notify(peer: Agent) -> None:
            try:
                peer.send(message)
            except Exception:
                pass
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(peers)) as executor:
            for peer in peers:
                executor.submit(_notify, peer)

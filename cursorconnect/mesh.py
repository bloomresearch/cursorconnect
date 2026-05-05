"""
Orchestration layer for executing parallel agents with peer-to-peer cross-checking.
"""

from __future__ import annotations

import threading
import concurrent.futures
from typing import Callable, Dict, List, Literal, Optional, Union, Any

from .agent import Agent
from .types import CloudOptions, LocalOptions, ModelSelection
from .types.mesh import MeshTask, MeshResult

CleanupStrategy = Literal["archive", "delete"]


class Mesh:
    """
    Orchestrator for managing parallel agent tasks.

    The Mesh handles the concurrent execution of multiple agents, optionally
    broadcasting the results of finished agents to still-running peers
    (cross-checking), and ensuring all created agents are cleaned up.

    Works with both cloud and local execution. Pass ``cloud`` for cloud
    agents, ``local`` for local agents, or mix both at the task level.

    Parameters
    ----------
    api_key : Optional[str], optional
        The Cursor API key to use for all agents, by default None (reads from env).
    cloud : Optional[CloudOptions], optional
        Default cloud options for all tasks, by default None.
    local : Optional[LocalOptions], optional
        Default local options for all tasks, by default None. When set (and
        ``cloud`` is not), tasks run locally unless overridden per-task.
    model : Optional[Union[str, ModelSelection]], optional
        Default model selection for all tasks, by default None. Supports
        ``ModelParameters`` and the ``thinking=`` shorthand.
    max_workers : Optional[int], optional
        Maximum number of concurrent agent threads. Defaults to the number of tasks.
    cross_check : Union[bool, Callable[[MeshResult, List[Agent]], str]], optional
        If True, broadcasts a default summary of completed tasks to running peers.
        If a callable, it must accept a `MeshResult` and a list of running `Agent`
        objects, and return a string to send to the peers. By default False.
    cleanup : Optional[CleanupStrategy], optional
        How to clean up agents when the context manager exits. One of "archive",
        "delete", or None. By default "archive". For local agents or cloud
        agents using "archive", this calls ``agent.close()``.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        cloud: Optional[CloudOptions] = None,
        local: Optional[LocalOptions] = None,
        model: Optional[Union[str, ModelSelection]] = None,
        max_workers: Optional[int] = None,
        cross_check: Union[bool, Callable[[MeshResult, List[Agent]], str]] = False,
        cleanup: Optional[CleanupStrategy] = "archive",
    ) -> None:
        self.api_key = api_key
        self.cloud = cloud
        self.local = local
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
        local: Optional[LocalOptions] = None,
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
        local : Optional[LocalOptions], optional
            Task-specific local options (overrides Mesh defaults), by default None.
        model : Optional[Union[str, ModelSelection]], optional
            Task-specific model selection (overrides Mesh defaults), by default None.

        Returns
        -------
        Mesh
            Returns ``self`` to allow chaining (e.g., ``mesh.add(...).add(...)``).
        """
        if isinstance(name_or_task, MeshTask):
            # Only apply mesh-level defaults if the task doesn't specify a runtime
            if name_or_task.cloud is None and name_or_task.local is None:
                name_or_task.cloud = self.cloud
                name_or_task.local = self.local
            
            if name_or_task.model is None and self.model is not None:
                name_or_task.model = self.model
            self._tasks.append(name_or_task)
        else:
            if prompt is None:
                raise ValueError("prompt is required when name_or_task is a string")
            
            # Task-level options take precedence over Mesh defaults
            task_cloud = cloud
            task_local = local
            if task_cloud is None and task_local is None:
                task_cloud = self.cloud
                task_local = self.local

            self._tasks.append(
                MeshTask(
                    name=name_or_task,
                    prompt=prompt,
                    cloud=task_cloud,
                    local=task_local,
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
                if self.cleanup == "delete":
                    agent.delete()
                else:
                    agent.close()
            except Exception:
                pass

    def _execute_task(self, task: MeshTask, timeout: Optional[float]) -> MeshResult:
        """Internal worker method to execute a single task."""
        from cursorconnect.exceptions import CursorAgentError

        kwargs: Dict[str, Any] = {
            "prompt": task.prompt,
            "name": task.name,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key

        if task.local:
            kwargs["local"] = task.local
        if task.cloud:
            kwargs["cloud"] = task.cloud

        # Defensive guard: local takes precedence if both somehow ended up here
        if "local" in kwargs and "cloud" in kwargs:
            kwargs.pop("cloud")

        if task.model:
            kwargs["model"] = task.model

        agent = Agent.create(**kwargs)

        with self._lock:
            self._agents.append(agent)
            self._live_agents[task.name] = agent

        run_obj = agent.initial_run
        if not run_obj:
            raise CursorAgentError(f"Task {task.name} failed to enqueue an initial run.")

        run_result = run_obj.wait(timeout=timeout)
        run_result.agent_id = agent.agent_id

        artifacts = []
        if not getattr(agent, "_is_local", False):
            try:
                artifacts = agent.list_artifacts()
                run_result.artifacts = artifacts
            except Exception:
                pass

        mesh_result = MeshResult(
            name=task.name,
            agent=agent,
            run_result=run_result,
            artifacts=artifacts,
        )

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

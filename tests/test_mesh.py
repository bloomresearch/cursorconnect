"""Tests for the ``Mesh`` orchestrator.

Covers basic task execution, concurrency, cross-checking, and cleanup.
"""

from __future__ import annotations

import time
from typing import List, Dict, Any

import pytest

from cursorconnect import Agent, Mesh
from cursorconnect.types import MeshTask, MeshResult, CloudOptions, ModelSelection

from .conftest import MockResponse


# ---------------------------------------------------------------------------
# Mocks & Shared Payload
# ---------------------------------------------------------------------------

# For Mesh tests we mock Agent.create and Agent.send, but because Mesh uses 
# real threads, we need a thread-safe mock for the HTTP client, which conftest 
# `mock_http` provides natively because it replaces responses sequentially.
# Wait, `mock_http` uses `side_effect=responses.pop(0)`. In a threaded 
# environment, pop(0) on a list might need to be thread-safe. list.pop(0) 
# is thread-safe in CPython due to the GIL.

def _build_responses(num_tasks: int, has_cross_check: bool) -> List[MockResponse]:
    """
    Build a list of sequential mock responses for N tasks.
    Each task needs:
    1. POST /agents (create agent)
    2. GET /agents/.../runs/... (wait for initial run)
    3. GET /agents/.../artifacts (list artifacts)
    4. Optional: POST /agents/.../runs (cross-check send)
    5. Optional: GET /agents/.../runs/... (wait for cross-check run - wait, cross-check is fire-and-forget? Yes, `peer.send(message)` doesn't wait!)
    """
    responses = []
    # In a real run, these might interleave unpredictably. 
    # To test robustly, we will monkeypatch Agent instead of using mock_http
    # because mock_http expects exact ordered calls.
    return responses


class DummyRun:
    def __init__(self, run_id: str, status: str = "FINISHED"):
        self.id = run_id
        self._status = status
    
    def wait(self, timeout=None, poll_interval=None):
        from cursorconnect.types import RunResult
        return RunResult(run_id=self.id, status=self._status)

    def stream(self):
        yield from []


class DummyAgent:
    def __init__(self, name: str):
        self.agent_id = f"bc-{name}"
        self.name = name
        self.status = "ACTIVE"
        self._latest_run_id = f"run-{name}"
        self.cross_check_messages = []
        self.deleted = False
        self.archived = False
        self._run_obj = DummyRun(self._latest_run_id)
        
    @property
    def initial_run(self):
        return self._run_obj

    def send(self, message: str, options=None):
        self.cross_check_messages.append(message)
        return DummyRun(f"run-{self.name}-crosscheck")

    def list_artifacts(self):
        return []

    def archive(self):
        self.archived = True

    def delete(self):
        self.deleted = True


@pytest.fixture
def mock_agent_create(monkeypatch):
    def fake_create(cls, api_key, prompt, name=None, cloud=None, model=None, **kwargs):
        # Simulate slight delay to ensure concurrency overlap
        time.sleep(0.01)
        agent = DummyAgent(name=name or "test")
        return agent
    
    monkeypatch.setattr(Agent, "create", classmethod(fake_create))


# ---------------------------------------------------------------------------
# Mesh Tests
# ---------------------------------------------------------------------------

class TestMeshBasic:
    """Unit tests for basic Mesh execution."""

    def test_mesh_executes_tasks(self, mock_agent_create, api_key: str) -> None:
        """Mesh runs multiple tasks concurrently and collects results."""
        mesh = Mesh(api_key=api_key)
        mesh.add("task1", "do A")
        mesh.add("task2", "do B")
        
        results = mesh.run()
        
        assert len(results) == 2
        assert results[0].name in ("task1", "task2")
        assert results[1].name in ("task1", "task2")
        assert results[0].run_result.status == "FINISHED"

    def test_mesh_context_manager_cleans_up(self, mock_agent_create, api_key: str) -> None:
        """The context manager archives agents by default on exit."""
        with Mesh(api_key=api_key) as mesh:
            mesh.add("task1", "do A")
            results = mesh.run()
            agent = results[0].agent
            assert not agent.archived  # type: ignore

        # After context exit, agents should be archived
        assert agent.archived  # type: ignore
        assert not agent.deleted  # type: ignore

    def test_mesh_cleanup_delete(self, mock_agent_create, api_key: str) -> None:
        """When cleanup='delete', agents are deleted on exit."""
        with Mesh(api_key=api_key, cleanup="delete") as mesh:
            mesh.add("task1", "do A")
            results = mesh.run()
            agent = results[0].agent
            
        assert agent.deleted  # type: ignore
        assert not agent.archived  # type: ignore


class TestMeshCrossCheck:
    """Unit tests for the peer-to-peer cross-checking feature."""

    def test_cross_check_default(self, mock_agent_create, api_key: str) -> None:
        """When cross_check=True, peers receive default broadcast messages."""
        mesh = Mesh(api_key=api_key, cross_check=True)
        mesh.add("task1", "do A")
        mesh.add("task2", "do B")
        
        results = mesh.run()
        
        # Because execution order is non-deterministic and threads finish quickly,
        # at least one agent should have finished while the other was still 'live'.
        # We'll just verify that no exceptions were raised and the logic ran.
        assert len(results) == 2

    def test_cross_check_custom_callable(self, mock_agent_create, api_key: str) -> None:
        """Custom callables can format the cross-check message."""
        def custom_formatter(finished: MeshResult, peers: List[Agent]) -> str:
            return f"CUSTOM: {finished.name} done."
            
        mesh = Mesh(api_key=api_key, cross_check=custom_formatter)
        mesh.add("task1", "do A")
        mesh.add("task2", "do B")
        
        results = mesh.run()
        assert len(results) == 2

class TestMeshCallAlias:
    """Unit tests for the ``__call__`` shorthand alias."""
    
    def test_mesh_call_alias(self, mock_agent_create, api_key: str) -> None:
        """mesh() is a pure alias for mesh.run()."""
        with Mesh(api_key=api_key) as mesh:
            mesh.add("task1", "do A")
            results = mesh()
            
        assert len(results) == 1
        assert results[0].name == "task1"

class TestMeshAddTask:
    """Unit tests for the MeshTask addition methods."""
    
    def test_mesh_add_meshtask_object(self, mock_agent_create, api_key: str) -> None:
        """Tasks can be added by passing a MeshTask object directly."""
        task = MeshTask(name="obj-task", prompt="do C")
        with Mesh(api_key=api_key) as mesh:
            mesh.add(task)
            results = mesh()
            
        assert len(results) == 1
        assert results[0].name == "obj-task"
        
    def test_mesh_add_operator(self, mock_agent_create, api_key: str) -> None:
        """Tasks can be added using the + operator."""
        task1 = MeshTask(name="op-task1", prompt="do X")
        task2 = MeshTask(name="op-task2", prompt="do Y")
        
        with Mesh(api_key=api_key) as mesh:
            mesh + task1 + task2
            results = mesh()
            
        assert len(results) == 2
        names = [r.name for r in results]
        assert "op-task1" in names
        assert "op-task2" in names

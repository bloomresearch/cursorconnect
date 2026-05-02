"""
The runtimes subpackage for the CursorConnect Python SDK.

This package exposes the :class:`RuntimeBackend` structural protocol and all
concrete backend implementations.  Import from here to avoid coupling callers
to deep internal paths.

Classes
-------
RuntimeBackend
    The typing Protocol that every backend must satisfy.
CloudRuntime
    HTTP backend delegating to the Cursor Cloud REST API.
"""

from .base import RuntimeBackend
from .cloud import CloudRuntime

__all__ = ["RuntimeBackend", "CloudRuntime"]

"""Auto-detection and installation of Node.js and @cursor/sdk.

This module is invoked lazily the first time a local agent is created.
It checks for Node.js availability, locates or installs @cursor/sdk into
a private ``node_modules`` directory inside the package, and returns the
paths the bridge manager needs to spawn its subprocess.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

_BRIDGE_DIR = Path(__file__).resolve().parent
_NODE_MODULES = _BRIDGE_DIR / "node_modules"
_SDK_PACKAGE = "@cursor/sdk"

_MIN_NODE_MAJOR = 18


class LocalSetupError(RuntimeError):
    """Raised when the local runtime environment cannot be prepared."""


def _find_node() -> str:
    """Locate the Node.js binary and verify the version meets the minimum.

    Returns
    -------
    str
        Absolute path (or bare command name) to a usable ``node`` binary.

    Raises
    ------
    LocalSetupError
        If Node.js is not found or the version is too old.
    """
    node = shutil.which("node")
    if node is None:
        raise LocalSetupError(
            f"Node.js is required for local agents but was not found on PATH. "
            f"Install Node.js {_MIN_NODE_MAJOR}+ from https://nodejs.org and try again."
        )

    try:
        raw = subprocess.check_output(
            [node, "--version"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (subprocess.CalledProcessError, OSError) as exc:
        raise LocalSetupError(f"Found node at {node} but could not determine its version: {exc}")

    version_str = raw.lstrip("v")
    try:
        major = int(version_str.split(".")[0])
    except (ValueError, IndexError):
        raise LocalSetupError(f"Could not parse Node.js version from '{raw}'.")

    if major < _MIN_NODE_MAJOR:
        raise LocalSetupError(
            f"Node.js {_MIN_NODE_MAJOR}+ is required for local agents, "
            f"but found v{version_str} at {node}. Please upgrade."
        )

    return node


def _sdk_is_installed() -> bool:
    """Check whether @cursor/sdk is resolvable from the bridge directory."""
    node = shutil.which("node")
    if node is None:
        return False

    check_script = (
        "try { require.resolve('@cursor/sdk'); process.exit(0); } "
        "catch(e) { process.exit(1); }"
    )
    try:
        result = subprocess.run(
            [node, "-e", check_script],
            cwd=str(_BRIDGE_DIR),
            env={**os.environ, "NODE_PATH": str(_NODE_MODULES)},
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _install_sdk(node: str) -> None:
    """Install @cursor/sdk into the package-local node_modules.

    Parameters
    ----------
    node : str
        Path to the Node.js binary (used to locate npm).
    """
    npm = shutil.which("npm")
    if npm is None:
        raise LocalSetupError(
            "npm is required to install @cursor/sdk but was not found on PATH. "
            "Install Node.js (which includes npm) from https://nodejs.org."
        )

    _NODE_MODULES.mkdir(parents=True, exist_ok=True)

    logger.info("Installing %s (this only happens once)...", _SDK_PACKAGE)
    print(
        f"[cursorconnect] Installing {_SDK_PACKAGE} for local agent support "
        f"(one-time setup)...",
        file=sys.stderr,
        flush=True,
    )

    try:
        subprocess.check_call(
            [npm, "install", "--prefix", str(_BRIDGE_DIR), _SDK_PACKAGE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        stderr_text = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise LocalSetupError(
            f"Failed to install {_SDK_PACKAGE} via npm (exit {exc.returncode}).\n"
            f"You can install it manually:\n"
            f"  cd {_BRIDGE_DIR}\n"
            f"  npm install {_SDK_PACKAGE}\n\n"
            f"npm stderr: {stderr_text}"
        )
    except subprocess.TimeoutExpired:
        raise LocalSetupError(
            f"npm install timed out after 120 seconds. Check your network connection "
            f"and try again, or install manually:\n"
            f"  cd {_BRIDGE_DIR}\n"
            f"  npm install {_SDK_PACKAGE}"
        )

    if not _sdk_is_installed():
        raise LocalSetupError(
            f"npm reported success but {_SDK_PACKAGE} is still not resolvable. "
            f"Try installing manually:\n"
            f"  cd {_BRIDGE_DIR}\n"
            f"  npm install {_SDK_PACKAGE}"
        )

    print(
        f"[cursorconnect] {_SDK_PACKAGE} installed successfully.",
        file=sys.stderr,
        flush=True,
    )


def ensure_local_runtime() -> Tuple[str, str]:
    """Ensure Node.js and @cursor/sdk are available, installing if needed.

    This is the main entry point called by the bridge manager before
    spawning the Node.js subprocess.

    Returns
    -------
    tuple of (str, str)
        ``(node_binary, bridge_script_path)`` ready for subprocess.Popen.

    Raises
    ------
    LocalSetupError
        If Node.js is missing, too old, or @cursor/sdk cannot be installed.
    """
    node = _find_node()

    if not _sdk_is_installed():
        _install_sdk(node)

    bridge_js = str(_BRIDGE_DIR / "bridge.js")
    return node, bridge_js


def get_status() -> dict:
    """Return a diagnostic dict describing the local runtime environment.

    Useful for the CLI ``setup-local`` command and debugging.

    Returns
    -------
    dict
        Keys: ``node_found``, ``node_path``, ``node_version``,
        ``npm_found``, ``sdk_installed``, ``sdk_location``, ``ready``.
    """
    status = {
        "node_found": False,
        "node_path": None,
        "node_version": None,
        "npm_found": False,
        "sdk_installed": False,
        "sdk_location": str(_NODE_MODULES),
        "ready": False,
    }

    node = shutil.which("node")
    if node:
        status["node_found"] = True
        status["node_path"] = node
        try:
            raw = subprocess.check_output(
                [node, "--version"], stderr=subprocess.DEVNULL, text=True
            ).strip()
            status["node_version"] = raw
        except Exception:
            pass

    status["npm_found"] = shutil.which("npm") is not None
    status["sdk_installed"] = _sdk_is_installed()
    status["ready"] = status["node_found"] and status["sdk_installed"]
    return status

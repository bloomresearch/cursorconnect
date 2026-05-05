"""CursorConnect CLI entry points.

Usage
-----
After installing cursorconnect, the ``cursorconnect`` command is available::

    cursorconnect setup-local     # check/install Node.js + @cursor/sdk
    cursorconnect status          # show local runtime diagnostic info
"""

import sys


def _setup_local() -> int:
    """Check for Node.js and @cursor/sdk, installing the SDK if missing."""
    from ._bridge.setup import ensure_local_runtime, LocalSetupError

    try:
        node, bridge = ensure_local_runtime()
        print(f"Local runtime is ready.")
        print(f"  Node.js:    {node}")
        print(f"  Bridge:     {bridge}")
        return 0
    except LocalSetupError as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1


def _status() -> int:
    """Print a diagnostic summary of the local runtime environment."""
    from ._bridge.setup import get_status

    info = get_status()
    ready = "YES" if info["ready"] else "NO"
    print(f"Local Runtime Ready: {ready}\n")
    print(f"  Node.js found:   {info['node_found']}")
    if info["node_path"]:
        print(f"  Node.js path:    {info['node_path']}")
    if info["node_version"]:
        print(f"  Node.js version: {info['node_version']}")
    print(f"  npm found:       {info['npm_found']}")
    print(f"  @cursor/sdk:     {'installed' if info['sdk_installed'] else 'not installed'}")
    print(f"  SDK location:    {info['sdk_location']}")

    if not info["ready"]:
        print(f"\nRun 'cursorconnect setup-local' to install missing dependencies.")

    return 0


_COMMANDS = {
    "setup-local": _setup_local,
    "status": _status,
}


def main() -> None:
    """CLI dispatcher for ``cursorconnect`` console script."""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: cursorconnect <command>\n")
        print("Commands:")
        print("  setup-local   Check for and install local runtime dependencies")
        print("  status        Show local runtime diagnostic information")
        sys.exit(0)

    command = sys.argv[1]
    handler = _COMMANDS.get(command)
    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(f"Available commands: {', '.join(_COMMANDS)}", file=sys.stderr)
        sys.exit(1)

    sys.exit(handler())


if __name__ == "__main__":
    main()

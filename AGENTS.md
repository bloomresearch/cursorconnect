# AGENTS.md

## Cursor Cloud specific instructions

### Product Overview

CursorConnect is a Python SDK (`cursorconnect`) for programmatically controlling Cursor's Cloud Agents via their REST API. It is a pip-installable library, not a web application or deployable service.

### Development Setup

- **Python**: Requires Python 3.8+. Install in editable mode: `pip install -e ".[test]"` and `pip install pytest`.
- **Node.js** (optional): Only needed for the local bridge runtime (`cursorconnect/_bridge/`). Install with `npm install` in the repo root. Not required for cloud-based operations or unit tests.

### Running Tests

- **Unit tests (no API key needed):** `pytest tests/ -m "not slow"` — 35 tests run with mocked HTTP; 111 live API tests are auto-skipped when `CURSOR_API_KEY` is absent.
- **Full test suite (requires API key):** `pytest tests/` — set `CURSOR_API_KEY` env var or create a `.env` file at the repo root.
- **Bridge manager test:** `python test_manager.py` — requires Node.js; tests the optional `BridgeManager` → `bridge.js` → `@cursor/sdk` pipeline with a mock script.
- The root-level `test_manager.py` is an async ad-hoc test (not part of the pytest suite); run it directly with `python test_manager.py`.

### Key Gotchas

- There is no linter configuration in the repository. No `ruff`, `flake8`, `pylint`, `mypy`, or `pyright` config exists.
- There is no CI/CD pipeline, Makefile, or devcontainer configuration.
- `api_key` is a **required positional argument** to `Agent.create()`, `Agent.prompt()`, `Agent.get()`, `Agent.list()`, and `Cursor.me()` — it does not auto-read from env in those call signatures (despite README examples suggesting optional). Tests that depend on live credentials use the `api_key` pytest fixture from `conftest.py`.
- The `package.json` at the repo root is for the optional Node.js bridge dependency (`@cursor/sdk`), not for the main Python SDK.
- Build the package with `python -m build` (after `pip install build`).

This is a CLI tool `ha-sync` that syncs Home Assistant UI configuration (dashboards, automations, helpers, etc.) to/from local YAML files.

It uses Python, Typer, Rich, Pydantic, and Logfire.
You should use uv, ruff, pyright, and pytest.

Key commands (all accept multiple paths, e.g., `automations/ scripts/`):
- `sync [PATHS...]`: Bidirectional sync - pulls remote, merges local changes, pushes. Recommended for users.
- `pull [PATHS...]`: Pull from HA. Auto-stashes in git repos, safe to run anytime.
- `push [PATHS...]`: Push to HA. Always asks confirmation.
- `diff [PATHS...]`: Show differences.
- `validate [PATHS...] [-t]`: Validate YAML. Use `-t` to also validate templates against HA.

Don't run `ha-sync` in the current directory, always use a temp dir if you want to test something. NEVER use destructive commands (e.g. `sync`, `push`, `--all`, or `--sync-deletions`) without verification.

Every command is instrumented and traces are sent to [Logfire](https://logfire.pydantic.dev/). The MCP server can help you see what happened in each run, including HTTP requests and responses.

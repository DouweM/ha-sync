This is a CLI tool `ha-sync` that syncs Home Assistant UI configuration (dashboards, automations, helpers, etc.) to/from local YAML files.

It uses Python, Typer, Rich, Pydantic, and Logfire.
You should use uv, ruff, pyright, and pytest.

Key commands:
- `sync`: Bidirectional sync - pulls remote, merges local changes, pushes. Recommended for users.
- `pull`: Pull from HA. Auto-stashes in git repos, safe to run anytime.
- `push`: Push to HA. Always asks confirmation.
- `diff`: Show differences.

Don't run `ha-sync` in the current directory, always use a temp dir if you want to test something. NEVER use `sync`, `push`, `--all`, or `--sync-deletions` without verification.

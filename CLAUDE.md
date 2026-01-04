This is a CLI tool `ha-sync` that syncs Home Assistant UI configuration (dashboards, automations, helpers, etc.) to/from local YAML files.

It uses Python, Typer, Rich, and Pydantic.
You should use uv, ruff, pyright, and pytest.

Don't run `ha-sync` in the current directory, always use a temp dir if you want to test something. NEVER use a real `push`, `--force`, or `--sync-deletions` without verification.

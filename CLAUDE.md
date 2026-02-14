This is a CLI tool `ha-sync` that syncs Home Assistant UI configuration (dashboards, automations, helpers, etc.) to/from local YAML files.

It uses Python, Typer, Rich, Pydantic, and Logfire.
You should use uv, ruff, pyright, and pytest.

Key commands (all accept multiple paths, e.g., `automations/ scripts/`):
- `sync [PATHS...]`: Bidirectional sync - pulls remote, merges local changes, pushes. Recommended for users.
- `pull [PATHS...]`: Pull from HA. Auto-stashes in git repos, safe to run anytime.
- `push [PATHS...]`: Push to HA. Always asks confirmation.
- `diff [PATHS...]`: Show differences.
- `validate [PATHS...] [-t]`: Validate YAML. Use `-t` to also validate templates against HA.
- `render <VIEW_PATH> [-u USER]`: Render a dashboard view as CLI text. Use when asked to "show" or "render" a dashboard. If icons are missing or display incorrectly, fix the `ICON_EMOJI` mapping in `src/ha_sync/render.py` first - don't assume the dashboard YAML needs icon specifications.

Don't run `ha-sync` in the current directory, always use a temp dir if you want to test something. NEVER use destructive commands (e.g. `sync`, `push`, `--all`, or `--sync-deletions`) without verification.

Every command is instrumented and traces are sent to [Logfire](https://logfire.pydantic.dev/). The MCP server can help you see what happened in each run, including HTTP requests and responses.

## Releasing

To release a new version:
1. Update `version` in `pyproject.toml`
2. Commit the version bump
3. Create and push a tag: `git tag v0.x.x && git push --tags`

The release workflow will run CI, build, create a GitHub release, and publish to PyPI.

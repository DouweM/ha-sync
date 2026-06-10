"""Dashboard sync implementation with view splitting."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import logfire
import yaml
from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import View
from ha_sync.utils import (
    dump_yaml,
    git_list_files,
    git_read_file,
    load_yaml,
    relative_path,
    slugify,
)

from .base import BaseSyncer, DiffItem, SyncResult
from .three_way import ThreeWayDiffItem, _compute_status

console = Console()

META_FILE = "_meta.yaml"
DASHBOARD_PREFIX = "dashboard-"

# Sentinel key used to represent the dashboard-level metadata unit (title, icon,
# hoisted config keys like swipe_nav/strategy) when splitting a dashboard into
# per-view units for three-way diffing.
META_UNIT = "_meta"


@dataclass
class DashboardViewDiff:
    """Result of a per-view three-way diff across all dashboards.

    Each item's ``entity_id`` is the dashboard's directory name (so existing
    pull/resolve plumbing that keys on dir name keeps working), while
    ``file_path`` points at the specific view file (or ``_meta.yaml``) that
    changed. ``merged_remote`` holds, per dashboard, the reassembled full
    ``{"meta": ..., "config": ...}`` to write on pull -- combining remote-only
    and unchanged views with local-only views so disjoint edits auto-merge.
    """

    local_only: list[ThreeWayDiffItem] = field(default_factory=list)
    remote_only: list[ThreeWayDiffItem] = field(default_factory=list)
    conflicts: list[ThreeWayDiffItem] = field(default_factory=list)
    merged_remote: dict[str, dict[str, Any]] = field(default_factory=dict)


def dir_name_from_url_path(url_path: str | None) -> str:
    """Convert HA url_path to clean directory name."""
    if url_path is None:
        return "lovelace"
    # Strip common prefix for cleaner names
    if url_path.startswith(DASHBOARD_PREFIX):
        return url_path[len(DASHBOARD_PREFIX) :]
    return url_path


def url_path_from_dir_name(dir_name: str, stored_url_path: str | None = None) -> str | None:
    """Convert directory name back to HA url_path."""
    if dir_name == "lovelace":
        return None
    # Use stored url_path if available (preserves original)
    if stored_url_path is not None:
        return stored_url_path
    # Otherwise reconstruct with prefix
    return f"{DASHBOARD_PREFIX}{dir_name}"


class DashboardSyncer(BaseSyncer):
    """Syncer for Home Assistant Lovelace dashboards."""

    entity_type = "dashboard"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.dashboards_path

    @logfire.instrument("Fetch remote dashboards")
    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all dashboards from Home Assistant.

        Returns dict keyed by clean directory name (without dashboard- prefix).
        """
        dashboards = await self.client.get_dashboards()
        result: dict[str, dict[str, Any]] = {}

        # Include the default dashboard if it has saved config
        # (instances using the auto-generated Overview return config_not_found)
        try:
            default_config = await self.client.get_dashboard_config(None)
        except Exception:
            default_config = None
        if default_config:
            result["lovelace"] = {
                "meta": {
                    "title": default_config.get("title", "Home"),
                    "url_path": None,
                },
                "config": default_config,
            }

        # Get other dashboards
        for dashboard in dashboards:
            url_path = dashboard.get("url_path")
            if url_path:
                try:
                    config = await self.client.get_dashboard_config(url_path)
                    if config:
                        # Use clean directory name as key
                        dir_name = dir_name_from_url_path(url_path)
                        result[dir_name] = {
                            "meta": {
                                "title": dashboard.get("title", url_path),
                                "icon": dashboard.get("icon"),
                                "show_in_sidebar": dashboard.get("show_in_sidebar", True),
                                "require_admin": dashboard.get("require_admin", False),
                                "url_path": url_path,  # Store original for push
                            },
                            "config": config,
                        }
                except Exception as e:
                    console.print(f"  [red]Error getting dashboard[/red] {url_path}: {e}")

        return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local dashboard directories.

        Returns dict keyed by directory name (clean, without dashboard- prefix).
        """
        result: dict[str, dict[str, Any]] = {}

        if not self.local_path.exists():
            return result

        for dashboard_dir in self.local_path.iterdir():
            if not dashboard_dir.is_dir():
                continue

            dir_name = dashboard_dir.name
            meta_file = dashboard_dir / META_FILE

            # Load metadata
            meta = load_yaml(meta_file) or {}

            # Build config from meta (extra keys like strategy, swipe_nav, etc.)
            config: dict[str, Any] = {}

            # Add extra config keys from meta (strategy, swipe_nav, etc.)
            for key in meta.get("_config_keys", []):
                if key in meta:
                    config[key] = meta[key]

            # Load views from individual files (if not a strategy-based dashboard)
            if "strategy" not in config:
                views: list[dict[str, Any]] = []
                for view_file in sorted(dashboard_dir.glob("*.yaml")):
                    if view_file.name == META_FILE:
                        continue
                    view_data = load_yaml(view_file)
                    if view_data:
                        views.append(view_data)
                config["views"] = views

            result[dir_name] = {
                "meta": meta,
                "config": config,
            }

        return result

    def get_base_entities(self) -> dict[str, dict[str, Any]]:
        """Get dashboard entities from git HEAD."""
        if not self._can_read_base():
            return {}

        result: dict[str, dict[str, Any]] = {}
        local_path_str = str(self.local_path)
        files = git_list_files(local_path_str)

        # Group files by dashboard directory
        dashboard_files: dict[str, list[tuple[str, str]]] = {}
        for file_path in files:
            if not file_path.endswith(".yaml"):
                continue
            # Extract dir_name from path: dashboards/<dir_name>/<file>.yaml
            if file_path.startswith(local_path_str):
                rel = file_path[len(local_path_str) + 1 :]
            else:
                rel = file_path
            parts = Path(rel).parts
            if len(parts) >= 2:
                dir_name = parts[-2] if len(parts) == 2 else parts[0]
                filename = parts[-1]
                content = git_read_file(file_path)
                if content:
                    dashboard_files.setdefault(dir_name, []).append((filename, content))

        for dir_name, file_list in dashboard_files.items():
            meta: dict[str, Any] = {}
            config: dict[str, Any] = {}

            for filename, content in file_list:
                data = yaml.safe_load(content)
                if not data:
                    continue

                if filename == META_FILE:
                    meta = data
                    # Extract config keys
                    for key in meta.get("_config_keys", []):
                        if key in meta:
                            config[key] = meta[key]

            # Build views from non-meta files (if not strategy-based)
            if "strategy" not in config:
                views: list[dict[str, Any]] = []
                for filename, content in sorted(file_list):
                    if filename == META_FILE:
                        continue
                    data = yaml.safe_load(content)
                    if data:
                        views.append(data)
                config["views"] = views

            result[dir_name] = {
                "meta": meta,
                "config": config,
            }

        return result

    def _save_dashboard_locally(
        self, dir_name: str, meta: dict[str, Any], config: dict[str, Any]
    ) -> None:
        """Save a dashboard to local files (split into views).

        Args:
            dir_name: Clean directory name (without dashboard- prefix)
            meta: Dashboard metadata including url_path
            config: Dashboard configuration
        """
        dashboard_dir = self.local_path / dir_name
        dashboard_dir.mkdir(parents=True, exist_ok=True)

        # Build metadata, including extra config keys
        meta_data: dict[str, Any] = {
            "title": meta.get("title", config.get("title", dir_name)),
            "icon": meta.get("icon"),
            "show_in_sidebar": meta.get("show_in_sidebar", True),
            "require_admin": meta.get("require_admin", False),
            "url_path": meta.get("url_path"),  # Store original url_path for push
        }

        # Track which extra config keys we're saving
        extra_config_keys: list[str] = []

        # Save extra config keys (like strategy, swipe_nav) to meta
        for key, value in config.items():
            if key not in ("views", "title"):
                meta_data[key] = value
                extra_config_keys.append(key)

        # Store the list of extra keys so we know what to restore
        if extra_config_keys:
            meta_data["_config_keys"] = extra_config_keys

        # Remove None values
        meta_data = {k: v for k, v in meta_data.items() if v is not None}

        # Save metadata
        meta_file = dashboard_dir / META_FILE
        dump_yaml(meta_data, meta_file)

        # Clear existing view files
        for view_file in dashboard_dir.glob("*.yaml"):
            if view_file.name != META_FILE:
                view_file.unlink()

        # Save each view to a separate file (only if views exist, not for strategy dashboards)
        # Prefix with index to preserve order (sorted alphabetically on load)
        views = config.get("views", [])
        for i, view in enumerate(views):
            # Add position field (1-indexed for user-friendliness)
            view_with_position = {"position": i + 1, **view}

            # Determine filename from view path or title, prefixed with index
            view_path = view.get("path")
            view_title = view.get("title")

            if view_path:
                filename = f"{i:02d}_{view_path}.yaml"
            elif view_title:
                filename = f"{i:02d}_{slugify(view_title)}.yaml"
            else:
                filename = f"{i:02d}_view.yaml"

            view_file = dashboard_dir / filename
            # Validate and order through Pydantic model
            dump_yaml(View.normalize(view_with_position), view_file)

    def _load_dashboard_locally(self, dir_name: str) -> dict[str, Any] | None:
        """Load a dashboard from local files."""
        dashboard_dir = self.local_path / dir_name
        if not dashboard_dir.exists():
            return None

        meta_file = dashboard_dir / META_FILE
        meta = load_yaml(meta_file) or {}

        # Build config, restoring extra keys from meta
        config: dict[str, Any] = {}

        # Restore extra config keys
        for key in meta.get("_config_keys", []):
            if key in meta:
                config[key] = meta[key]

        # Load views - only if not a strategy-based dashboard
        if "strategy" not in config:
            views_with_files: list[tuple[dict[str, Any], Path]] = []
            for view_file in sorted(dashboard_dir.glob("*.yaml")):
                if view_file.name == META_FILE:
                    continue
                view_data = load_yaml(view_file)
                if view_data:
                    views_with_files.append((view_data, view_file))

            # Sort by position field if present, otherwise by filename
            def sort_key(item: tuple[dict[str, Any], Path]) -> tuple[int, str]:
                view_data, view_file = item
                pos = view_data.get("position", 999)
                return (pos, view_file.name)

            views_with_files.sort(key=sort_key)

            # Build views list, removing position field (not part of HA config)
            views: list[dict[str, Any]] = []
            for view_data, _ in views_with_files:
                view_without_position = {k: v for k, v in view_data.items() if k != "position"}
                views.append(view_without_position)
            config["views"] = views

        return config

    @logfire.instrument("Pull dashboards")
    async def pull(
        self,
        sync_deletions: bool = False,
        dry_run: bool = False,
        remote: dict[str, Any] | None = None,
    ) -> SyncResult:
        """Pull dashboards from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        if not dry_run:
            self.local_path.mkdir(parents=True, exist_ok=True)
        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        for dir_name, data in remote.items():
            meta = data["meta"]
            config = data["config"]
            dashboard_dir = self.local_path / dir_name
            rel_dir_path = relative_path(dashboard_dir)

            try:
                if dir_name in local:
                    # Check if changed using normalized comparison
                    local_config = self._load_dashboard_locally(dir_name)
                    local_normalized = self._normalize_config(local_config or {})
                    remote_normalized = self._normalize_config(config)
                    if dump_yaml(remote_normalized) != dump_yaml(local_normalized):
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_dir_path}/")
                            self._print_all_files(dashboard_dir, "cyan", "Would update")
                        else:
                            self._save_dashboard_locally(dir_name, meta, config)
                            console.print(f"  [yellow]Updated[/yellow] {rel_dir_path}/")
                            self._print_all_files(dashboard_dir, "yellow", "Updated")
                        result.updated.append(dir_name)
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_dir_path}/")
                    else:
                        self._save_dashboard_locally(dir_name, meta, config)
                        console.print(f"  [green]Created[/green] {rel_dir_path}/")
                        self._print_all_files(dashboard_dir, "green", "Created")
                    result.created.append(dir_name)

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error[/red] {rel_dir_path}/: {e}")

        # Delete local directories that don't exist in remote
        if sync_deletions:
            import shutil

            for dir_name in local:
                if dir_name not in remote:
                    dashboard_dir = self.local_path / dir_name
                    if dashboard_dir.exists():
                        rel_dir_path = relative_path(dashboard_dir)
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {rel_dir_path}/")
                            self._print_all_files(dashboard_dir, "cyan", "Would delete")
                        else:
                            # Print files before deleting
                            console.print(f"  [red]Deleted[/red] {rel_dir_path}/")
                            self._print_all_files(dashboard_dir, "red", "Deleted")
                            shutil.rmtree(dashboard_dir)
                        result.deleted.append(dir_name)
        else:
            # Warn about local directories without remote counterpart
            orphaned = [d for d in local if d not in remote]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} local dashboard(s) not in HA "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    @logfire.instrument("Push dashboards")
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local dashboards to Home Assistant.

        Args:
            force: If True, push all local entities regardless of changes.
            sync_deletions: If True, delete remote dashboards not in local files.
            dry_run: If True, only show what would be done without making changes.
            diff_items: Pre-computed diff items. If provided (and force=False),
                       these are used directly without recomputing. This ensures
                       the actual push matches the diff that was shown to the user.
        """
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        local = self.get_local_entities()

        # Determine whether we need to fetch remote entities
        # We need remote for: force mode, no diff_items, or if diff_items has renames/deletions
        # (renames/deletions need url_path from remote metadata)
        has_renames = diff_items and any(item.status == "renamed" for item in diff_items)
        has_deletions = diff_items and any(item.status == "deleted" for item in diff_items)
        need_remote = force or diff_items is None or has_renames or has_deletions
        remote: dict[str, Any] | None = None
        if need_remote:
            remote = await self.get_remote_entities()

        # Determine what to process
        if force or diff_items is None:
            assert remote is not None  # Guaranteed by need_remote logic
            # Force mode or no pre-computed diff: compute fresh diff
            diff_items = await self.diff(remote=remote)
        # else: Use the provided diff_items directly (the key fix!)

        # Track processed items to avoid double-processing
        processed_dirs: set[str] = set()

        # Process url_path renames first (always, regardless of force)
        for item in diff_items:
            if item.status != "renamed" or not item.new_id:
                continue

            # remote is guaranteed to be fetched when there are renames (has_renames check)
            assert remote is not None

            dir_name = item.entity_id
            old_url_path = remote[dir_name]["meta"].get("url_path")
            new_url_path = item.new_id
            processed_dirs.add(dir_name)

            local_data = local[dir_name]
            meta = local_data["meta"]
            config = local_data["config"]
            dashboard_dir = self.local_path / dir_name
            rel_dir_path = relative_path(dashboard_dir)
            title = meta.get("title", dir_name)

            if dry_run:
                msg = f"({old_url_path} -> {new_url_path})"
                console.print(f"  [cyan]Would rename url_path[/cyan] {rel_dir_path}/ {msg}")
                result.renamed.append((old_url_path, new_url_path))
                continue

            try:
                # Create new dashboard with new url_path
                await self.client.create_dashboard(
                    url_path=new_url_path,
                    title=title,
                    icon=meta.get("icon"),
                    show_in_sidebar=meta.get("show_in_sidebar", True),
                    require_admin=meta.get("require_admin", False),
                )
                # Copy config to new dashboard
                await self.client.save_dashboard_config(config, new_url_path)
                # Delete old dashboard
                await self.client.delete_dashboard(old_url_path)

                result.renamed.append((old_url_path, new_url_path))
                console.print(
                    f"  [blue]Renamed[/blue] {rel_dir_path}/ ({old_url_path} -> {new_url_path})"
                )

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error renaming[/red] {rel_dir_path}/: {e}")

        # Build a map of diff_item status by entity_id for quick lookup
        diff_status_map = {item.entity_id: item.status for item in diff_items}

        # Determine items to create/update
        if force:
            # Force mode: all local items not already processed
            items_to_process = [
                (dir_name, local[dir_name]) for dir_name in local if dir_name not in processed_dirs
            ]
        else:
            # Normal mode: only items from diff (added or modified)
            items_to_process = [
                (item.entity_id, local[item.entity_id])
                for item in diff_items
                if item.status in ("added", "modified") and item.entity_id in local
            ]

        for dir_name, data in items_to_process:
            config = data["config"]
            meta = data["meta"]
            dashboard_dir = self.local_path / dir_name
            rel_dir_path = relative_path(dashboard_dir)
            title = meta.get("title", dir_name)

            try:
                # Get url_path from stored meta, or reconstruct from dir_name
                stored_url_path = meta.get("url_path")
                url_path = url_path_from_dir_name(dir_name, stored_url_path)

                # Determine if this is an update (existing in remote) or create (new)
                # Use diff_item status when remote is not fetched, otherwise check remote directly
                if remote is not None:
                    is_update = dir_name in remote
                else:
                    # Infer from diff_item status: "modified" means it exists in remote
                    is_update = diff_status_map.get(dir_name) == "modified"

                if is_update:
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {rel_dir_path}/")
                        result.updated.append(dir_name)
                        continue

                    await self.client.save_dashboard_config(config, url_path)
                    result.updated.append(dir_name)
                    console.print(f"  [yellow]Updated[/yellow] {rel_dir_path}/")
                else:
                    # Create new dashboard
                    if dir_name == "lovelace":
                        # Default dashboard doesn't need creation
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {rel_dir_path}/")
                            result.created.append(dir_name)
                            continue

                        await self.client.save_dashboard_config(config, None)
                        result.created.append(dir_name)
                        console.print(f"  [green]Created[/green] {rel_dir_path}/")
                    else:
                        # Create new dashboard first, then save config
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {rel_dir_path}/")
                            result.created.append(dir_name)
                            continue

                        # Create the dashboard entry
                        await self.client.create_dashboard(
                            url_path=url_path or f"dashboard-{dir_name}",
                            title=title,
                            icon=meta.get("icon"),
                            show_in_sidebar=meta.get("show_in_sidebar", True),
                            require_admin=meta.get("require_admin", False),
                        )
                        # Then save the config
                        await self.client.save_dashboard_config(config, url_path)
                        result.created.append(dir_name)
                        console.print(f"  [green]Created[/green] {rel_dir_path}/")

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error[/red] {rel_dir_path}/: {e}")

        # Process deletions
        if sync_deletions:
            if force:
                # Force mode: remote is guaranteed to be fetched
                assert remote is not None
                # Delete all remote items not in local
                items_to_delete = [
                    dir_name
                    for dir_name in remote
                    if dir_name not in local and dir_name not in processed_dirs
                ]
            else:
                # Normal mode: only items from diff
                items_to_delete = [
                    item.entity_id for item in diff_items if item.status == "deleted"
                ]

            for dir_name in items_to_delete:
                # remote is guaranteed to be fetched when there are deletions (has_deletions check)
                assert remote is not None
                url_path = remote[dir_name]["meta"].get("url_path")
                dashboard_dir = self.local_path / dir_name
                rel_dir_path = relative_path(dashboard_dir)

                try:
                    if dry_run:
                        console.print(f"  [cyan]Would delete[/cyan] {rel_dir_path}/")
                        result.deleted.append(dir_name)
                        continue

                    await self.client.delete_dashboard(url_path)
                    result.deleted.append(dir_name)
                    console.print(f"  [red]Deleted[/red] {rel_dir_path}/")
                except Exception as e:
                    result.errors.append((dir_name, str(e)))
                    console.print(f"  [red]Error deleting[/red] {rel_dir_path}/: {e}")
        else:
            # Warn about remote items without local counterpart
            # Only show if we have remote data (not when using pre-computed diff_items)
            if remote is not None:
                orphaned = [d for d in remote if d not in local and d not in processed_dirs]
                if orphaned:
                    console.print(
                        f"  [dim]{len(orphaned)} remote dashboard(s) not in local files "
                        "(use --sync-deletions to remove)[/dim]"
                    )

        # Auto-rename view files to match content (after successful push)
        if not dry_run:
            self._rename_view_files(local)

        return result

    def _rename_view_files(self, local: dict[str, dict[str, Any]]) -> None:
        """Rename view files to match their position and title/path after push."""
        for dir_name in local:
            dashboard_dir = self.local_path / dir_name
            if not dashboard_dir.exists():
                continue

            # Read all view files with their data
            views_with_files: list[tuple[dict[str, Any], Path]] = []
            for view_file in dashboard_dir.glob("*.yaml"):
                if view_file.name == META_FILE:
                    continue
                view_data = load_yaml(view_file)
                if view_data:
                    views_with_files.append((view_data, view_file))

            # Sort by position field if present, otherwise by filename
            def sort_key(item: tuple[dict[str, Any], Path]) -> tuple[int, str]:
                view_data, view_file = item
                pos = view_data.get("position", 999)
                return (pos, view_file.name)

            views_with_files.sort(key=sort_key)

            # Rename files to match new order, using temp names to avoid conflicts
            renames: list[tuple[Path, Path]] = []
            for i, (view_data, view_file) in enumerate(views_with_files):
                view_path = view_data.get("path")
                view_title = view_data.get("title")

                # Determine expected filename based on new index
                if view_path:
                    expected_name = f"{i:02d}_{view_path}.yaml"
                elif view_title:
                    expected_name = f"{i:02d}_{slugify(view_title)}.yaml"
                else:
                    expected_name = f"{i:02d}_view.yaml"

                if view_file.name != expected_name:
                    renames.append((view_file, dashboard_dir / expected_name))

            # Perform renames via temp files to avoid conflicts
            if renames:
                # First pass: rename to temp names
                temp_renames: list[tuple[Path, Path, Path]] = []
                for old_file, new_file in renames:
                    temp_file = old_file.with_suffix(".yaml.tmp")
                    old_file.rename(temp_file)
                    temp_renames.append((temp_file, new_file, old_file))

                # Second pass: rename to final names and update position in file
                for temp_file, new_file, old_file in temp_renames:
                    # Extract new index from filename
                    new_index = int(new_file.name.split("_")[0])
                    view_data = load_yaml(temp_file)
                    if view_data:
                        view_data["position"] = new_index + 1  # 1-indexed
                        dump_yaml(View.normalize(view_data), new_file)
                        temp_file.unlink()
                    else:
                        temp_file.rename(new_file)

                    old_rel = relative_path(old_file)
                    new_rel = relative_path(new_file)
                    console.print(f"  [blue]Renamed view[/blue] {old_rel} -> {new_rel}")

    def _print_views(self, dashboard_dir: Path, color: str, action: str) -> None:
        """Print view files under a dashboard (excludes _meta.yaml)."""
        for view_file in sorted(dashboard_dir.glob("*.yaml")):
            if view_file.name == META_FILE:
                continue
            rel_path = relative_path(view_file)
            console.print(f"    [{color}]{action}[/{color}] {rel_path}")

    def _print_all_files(self, dashboard_dir: Path, color: str, action: str) -> None:
        """Print all files under a dashboard (including _meta.yaml)."""
        for yaml_file in sorted(dashboard_dir.glob("*.yaml")):
            rel_path = relative_path(yaml_file)
            console.print(f"    [{color}]{action}[/{color}] {rel_path}")

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Normalize a dashboard config for comparison.

        This ensures consistent key ordering and removes title if empty.
        Also strips 'position' from views since it's a local-only field for ordering.
        """
        result: dict[str, Any] = {}

        # Copy non-view keys (like strategy, swipe_nav, etc.) as-is
        for key, value in config.items():
            if key == "views":
                # Normalize views through Pydantic, then strip 'position' (local-only)
                normalized_views = []
                for view in value:
                    normalized = View.normalize(view)
                    normalized.pop("position", None)
                    normalized_views.append(normalized)
                result["views"] = normalized_views
            elif key == "title" and not value:
                # Skip empty title
                continue
            else:
                result[key] = value

        return result

    def _view_key(self, view: dict[str, Any], index: int) -> str:
        """Stable identity for a view across base/local/remote sides.

        Prefer the view's ``path`` (the durable HA identifier). Fall back to a
        slug of its title, then to a positional key so views lacking both don't
        collide or crash.
        """
        path = view.get("path")
        if path:
            return f"path:{path}"
        title = view.get("title")
        if title:
            return f"title:{slugify(str(title))}"
        return f"index:{index}"

    def _meta_unit(self, meta: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Build a normalized comparable dict of dashboard-level metadata.

        Includes user-facing meta (title, icon, show_in_sidebar, require_admin)
        and hoisted config keys (swipe_nav, strategy, etc.) but excludes
        ``views`` (compared per-view) and ``url_path`` (rename handling lives
        elsewhere and would otherwise look like a meta change on every pull).
        """
        unit: dict[str, Any] = {}
        for key in ("title", "icon", "show_in_sidebar", "require_admin"):
            if meta.get(key) is not None:
                unit[key] = meta[key]
        for key, value in self._normalize_config(config).items():
            if key != "views":
                unit[key] = value
        return unit

    def _split_into_units(self, entity: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        """Split a dashboard ``{"meta", "config"}`` into per-view + meta units.

        Returns a dict keyed by ``_view_key`` (and ``META_UNIT``) mapping to
        normalized, position-stripped content suitable for three-way comparison.
        """
        if entity is None:
            return {}
        meta = entity.get("meta") or {}
        config = entity.get("config") or {}
        units: dict[str, dict[str, Any]] = {META_UNIT: self._meta_unit(meta, config)}
        for index, view in enumerate(config.get("views", [])):
            normalized = View.normalize(view)
            normalized.pop("position", None)
            units[self._view_key(view, index)] = normalized
        return units

    def _view_file_path(self, dir_name: str, view: dict[str, Any]) -> str:
        """Relative path of the view file for diff reporting and path filtering."""
        path = view.get("path")
        title = view.get("title")
        if path:
            stem = str(path)
        elif title:
            stem = slugify(str(title))
        else:
            stem = "view"
        # Saved view files carry a numeric ordering prefix (e.g. 00_oasis.yaml),
        # so prefer the actual on-disk file. Otherwise path filters like
        # `diff dashboards/welcome/00_oasis.yaml` never match the reported path
        # and the diff silently comes back empty.
        dashboard_dir = self.local_path / dir_name
        matches = sorted(dashboard_dir.glob(f"[0-9][0-9]_{stem}.yaml"))
        if matches:
            return relative_path(matches[0])
        return relative_path(dashboard_dir / f"{stem}.yaml")

    def compute_view_three_way(
        self,
        base: dict[str, dict[str, Any]],
        local: dict[str, dict[str, Any]],
        remote: dict[str, dict[str, Any]],
        conflict_resolution: str = "none",
    ) -> DashboardViewDiff:
        """Per-view three-way diff across all dashboards.

        Splits each dashboard into per-view units (plus a ``_meta`` unit) keyed
        by stable view identity, runs the standard three-way comparison per
        unit, and reassembles a merged config per dashboard so disjoint
        local/remote edits auto-merge. Same-unit divergence becomes a conflict
        reported against that unit's file (the view file or ``_meta.yaml``).

        Args:
            conflict_resolution: How to fold conflicted units into the merged
                config. ``"none"`` keeps the local side (conflicts are reported,
                not applied); ``"theirs"`` takes the remote side per conflicted
                unit; ``"ours"`` keeps the local side. With ``"theirs"``/``"ours"``
                the affected dashboard is added to ``merged_remote`` so callers
                can pull the per-view resolution without clobbering disjoint
                local edits in the same dashboard.
        """
        result = DashboardViewDiff()
        all_dirs = set(base) | set(local) | set(remote)

        for dir_name in sorted(all_dirs):
            base_entity = base.get(dir_name)
            local_entity = local.get(dir_name)
            remote_entity = remote.get(dir_name)

            base_units = self._split_into_units(base_entity)
            local_units = self._split_into_units(local_entity)
            remote_units = self._split_into_units(remote_entity)

            # Index raw (un-normalized) views by key on each side so we can
            # reassemble the merged config from whichever side won.
            local_views = self._index_raw_views(local_entity)
            remote_views = self._index_raw_views(remote_entity)
            base_views = self._index_raw_views(base_entity)

            dir_has_remote_change = False
            dir_has_conflict = False
            conflict_keys: set[str] = set()

            unit_keys = set(base_units) | set(local_units) | set(remote_units)

            for unit_key in sorted(unit_keys):
                b = base_units.get(unit_key)
                lo = local_units.get(unit_key)
                re_ = remote_units.get(unit_key)

                local_status = _compute_status(b, lo)
                remote_status = _compute_status(b, re_)

                if local_status is None and remote_status is None:
                    continue  # Unit unchanged on both sides.

                if unit_key == META_UNIT:
                    fp = relative_path(self.local_path / dir_name / META_FILE)
                else:
                    raw_for_path = (
                        remote_views.get(unit_key)
                        or local_views.get(unit_key)
                        or base_views.get(unit_key)
                        or {}
                    )
                    fp = self._view_file_path(dir_name, raw_for_path)

                if local_status is not None and remote_status is None:
                    result.local_only.append(
                        ThreeWayDiffItem(
                            entity_id=dir_name,
                            entity_type=self.entity_type,
                            change_location="local_only",
                            local_status=local_status,
                            remote_status=None,
                            base=b,
                            local=lo,
                            remote=re_,
                            file_path=fp,
                            has_conflict=False,
                        )
                    )
                elif local_status is None and remote_status is not None:
                    dir_has_remote_change = True
                    result.remote_only.append(
                        ThreeWayDiffItem(
                            entity_id=dir_name,
                            entity_type=self.entity_type,
                            change_location="remote_only",
                            local_status=None,
                            remote_status=remote_status,
                            base=b,
                            local=lo,
                            remote=re_,
                            file_path=fp,
                            has_conflict=False,
                        )
                    )
                else:
                    # Both sides changed.
                    if lo == re_:
                        continue  # Same change on both sides: no action.
                    conflict_keys.add(unit_key)
                    dir_has_conflict = True
                    result.conflicts.append(
                        ThreeWayDiffItem(
                            entity_id=dir_name,
                            entity_type=self.entity_type,
                            change_location="both",
                            local_status=local_status,
                            remote_status=remote_status,
                            base=b,
                            local=lo,
                            remote=re_,
                            file_path=fp,
                            has_conflict=True,
                        )
                    )

            # Reassemble a merged config for the pull side. For every view key,
            # pick the side that wins:
            #   - conflict + "theirs" -> remote view (or drop if remote deleted)
            #   - conflict + "ours"/"none" -> local view (or drop if local deleted)
            #   - remote changed it (no conflict) -> remote view
            #   - remote deleted it (no conflict) -> drop the view
            #   - otherwise -> local view (preserving local-only edits)
            merged_views: list[dict[str, Any]] = []
            for unit_key in self._ordered_view_keys(remote_entity, local_entity, base_entity):
                b = base_units.get(unit_key)
                remote_status = _compute_status(b, remote_units.get(unit_key))
                local_status = _compute_status(b, local_units.get(unit_key))
                in_conflict = unit_key in conflict_keys

                if in_conflict:
                    if conflict_resolution == "theirs":
                        if remote_status == "deleted":
                            continue
                        raw = remote_views.get(unit_key)
                    else:  # "ours" or "none": keep local
                        if local_status == "deleted":
                            continue
                        raw = local_views.get(unit_key)
                elif remote_status == "deleted":
                    continue
                elif remote_status is not None:
                    raw = remote_views.get(unit_key)
                else:
                    raw = local_views.get(unit_key) or remote_views.get(unit_key)

                if raw is not None:
                    merged_views.append(raw)

            # Merged meta: pick the winning side for the dashboard-level metadata.
            meta_remote_status = _compute_status(
                base_units.get(META_UNIT), remote_units.get(META_UNIT)
            )
            meta_in_conflict = META_UNIT in conflict_keys
            if meta_in_conflict:
                meta_from_remote = conflict_resolution == "theirs"
            else:
                meta_from_remote = meta_remote_status is not None and remote_entity is not None
            if meta_from_remote and remote_entity is not None:
                source_entity: dict[str, Any] = remote_entity
            else:
                source_entity = local_entity or remote_entity or {}
            merged_meta = source_entity.get("meta", {})

            merged_config: dict[str, Any] = {}
            for key, value in source_entity.get("config", {}).items():
                if key != "views":
                    merged_config[key] = value
            if "strategy" not in merged_config:
                merged_config["views"] = merged_views

            # Add to merged_remote when there's a remote change to pull, or when
            # we're resolving conflicts in a way that requires writing locally.
            needs_pull = dir_has_remote_change or (
                dir_has_conflict and conflict_resolution in ("theirs", "ours")
            )
            if needs_pull:
                result.merged_remote[dir_name] = {
                    "meta": merged_meta,
                    "config": merged_config,
                }

        return result

    def _index_raw_views(self, entity: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        """Map view key -> raw (un-normalized) view dict for an entity side."""
        if entity is None:
            return {}
        config = entity.get("config") or {}
        result: dict[str, dict[str, Any]] = {}
        for index, view in enumerate(config.get("views", [])):
            result[self._view_key(view, index)] = view
        return result

    def _ordered_view_keys(
        self,
        remote_entity: dict[str, Any] | None,
        local_entity: dict[str, Any] | None,
        base_entity: dict[str, Any] | None,
    ) -> list[str]:
        """Stable ordering of view keys: remote order first, then local-only adds."""
        ordered: list[str] = []
        seen: set[str] = set()
        for entity in (remote_entity, local_entity, base_entity):
            for key in self._index_raw_views(entity):
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        return ordered

    @logfire.instrument("Diff dashboards")
    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local dashboards with remote.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        items: list[DiffItem] = []

        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Detect url_path renames
        url_path_renames: set[str] = set()
        for dir_name, local_data in local.items():
            if dir_name in remote and dir_name != "lovelace":
                local_url_path = local_data["meta"].get("url_path")
                remote_url_path = remote[dir_name]["meta"].get("url_path")
                if local_url_path and remote_url_path and local_url_path != remote_url_path:
                    url_path_renames.add(dir_name)
                    meta_path = self.local_path / dir_name / META_FILE
                    rel_path = relative_path(meta_path)
                    items.append(
                        DiffItem(
                            entity_id=dir_name,
                            status="renamed",
                            local=local_data["config"],
                            remote=remote[dir_name]["config"],
                            new_id=local_url_path,
                            file_path=f"{rel_path} ({remote_url_path} -> {local_url_path})",
                        )
                    )

        for dir_name, local_data in local.items():
            if dir_name in url_path_renames:
                continue

            local_config = local_data["config"]
            # Use directory path (e.g., "dashboards/welcome/") since dashboards sync at dir level
            dir_path = self.local_path / dir_name
            rel_path = relative_path(dir_path)

            # Normalize local config for comparison and display
            local_normalized = self._normalize_config(local_config)

            if dir_name not in remote:
                items.append(
                    DiffItem(
                        entity_id=dir_name,
                        status="added",
                        local=local_normalized,
                        file_path=rel_path,
                    )
                )
            else:
                remote_config = remote[dir_name]["config"]
                # Normalize both configs for comparison and display
                remote_normalized = self._normalize_config(remote_config)

                if dump_yaml(local_normalized) != dump_yaml(remote_normalized):
                    items.append(
                        DiffItem(
                            entity_id=dir_name,
                            status="modified",
                            local=local_normalized,
                            remote=remote_normalized,
                            file_path=rel_path,
                        )
                    )

        for dir_name in remote:
            if dir_name not in local and dir_name not in url_path_renames:
                # Use directory path for consistency
                dir_path = self.local_path / dir_name
                rel_path = relative_path(dir_path)
                # Normalize for consistent display
                remote_normalized = self._normalize_config(remote[dir_name]["config"])
                items.append(
                    DiffItem(
                        entity_id=dir_name,
                        status="deleted",
                        remote=remote_normalized,
                        file_path=rel_path,
                    )
                )

        return items

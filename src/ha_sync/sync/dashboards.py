"""Dashboard sync implementation with view splitting."""

from pathlib import Path
from typing import Any

from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import View
from ha_sync.utils import (
    dump_yaml,
    load_yaml,
    slugify,
)

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()

META_FILE = "_meta.yaml"
DASHBOARD_PREFIX = "dashboard-"


def dir_name_from_url_path(url_path: str | None) -> str:
    """Convert HA url_path to clean directory name."""
    if url_path is None:
        return "lovelace"
    # Strip common prefix for cleaner names
    if url_path.startswith(DASHBOARD_PREFIX):
        return url_path[len(DASHBOARD_PREFIX):]
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

    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all dashboards from Home Assistant.

        Returns dict keyed by clean directory name (without dashboard- prefix).
        """
        dashboards = await self.client.get_dashboards()
        result: dict[str, dict[str, Any]] = {}

        # Always include the default dashboard
        default_config = await self.client.get_dashboard_config(None)
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
                view_without_position = {
                    k: v for k, v in view_data.items() if k != "position"
                }
                views.append(view_without_position)
            config["views"] = views

        return config

    async def pull(self, sync_deletions: bool = False) -> SyncResult:
        """Pull dashboards from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        self.local_path.mkdir(parents=True, exist_ok=True)
        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        for dir_name, data in remote.items():
            meta = data["meta"]
            config = data["config"]
            display_name = meta.get("title", dir_name)

            try:
                if dir_name in local:
                    # Check if changed using normalized comparison
                    local_config = self._load_dashboard_locally(dir_name)
                    local_normalized = self._normalize_config(local_config or {})
                    remote_normalized = self._normalize_config(config)
                    if dump_yaml(remote_normalized) != dump_yaml(local_normalized):
                        self._save_dashboard_locally(dir_name, meta, config)
                        result.updated.append(dir_name)
                        console.print(f"  [yellow]Updated[/yellow] {display_name}")
                else:
                    self._save_dashboard_locally(dir_name, meta, config)
                    result.created.append(dir_name)
                    console.print(f"  [green]Created[/green] {display_name}")

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error[/red] {display_name}: {e}")

        # Delete local directories that don't exist in remote
        if sync_deletions:
            import shutil

            for dir_name in local:
                if dir_name not in remote:
                    dashboard_dir = self.local_path / dir_name
                    if dashboard_dir.exists():
                        shutil.rmtree(dashboard_dir)
                        result.deleted.append(dir_name)
                        display_name = local[dir_name]["meta"].get("title", dir_name)
                        console.print(f"  [red]Deleted[/red] {display_name}")
        else:
            # Warn about local directories without remote counterpart
            orphaned = [d for d in local if d not in remote]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} local dashboard(s) not in HA "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Push local dashboards to Home Assistant."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Detect url_path renames: same dir_name but different url_path
        # Maps dir_name -> (old_url_path, new_url_path)
        url_path_renames: dict[str, tuple[str, str]] = {}
        for dir_name, local_data in local.items():
            if dir_name in remote and dir_name != "lovelace":
                local_url_path = local_data["meta"].get("url_path")
                remote_url_path = remote[dir_name]["meta"].get("url_path")
                if local_url_path and remote_url_path and local_url_path != remote_url_path:
                    url_path_renames[dir_name] = (remote_url_path, local_url_path)

        # Process url_path renames first
        for dir_name, (old_url_path, new_url_path) in url_path_renames.items():
            local_data = local[dir_name]
            meta = local_data["meta"]
            config = local_data["config"]
            display_name = meta.get("title", dir_name)

            if dry_run:
                console.print(
                    f"  [cyan]Would rename url_path[/cyan] {old_url_path} -> {new_url_path}"
                )
                result.renamed.append((old_url_path, new_url_path))
                continue

            try:
                # Create new dashboard with new url_path
                await self.client.create_dashboard(
                    url_path=new_url_path,
                    title=display_name,
                    icon=meta.get("icon"),
                    show_in_sidebar=meta.get("show_in_sidebar", True),
                    require_admin=meta.get("require_admin", False),
                )
                # Copy config to new dashboard
                await self.client.save_dashboard_config(config, new_url_path)
                # Delete old dashboard
                await self.client.delete_dashboard(old_url_path)

                result.renamed.append((old_url_path, new_url_path))
                console.print(f"  [blue]Renamed[/blue] {old_url_path} -> {new_url_path}")

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error renaming[/red] {display_name}: {e}")

        for dir_name, data in local.items():
            # Skip if already handled as rename
            if dir_name in url_path_renames:
                continue

            config = data["config"]
            meta = data["meta"]
            display_name = meta.get("title", dir_name)

            try:
                # Get url_path from stored meta, or reconstruct from dir_name
                stored_url_path = meta.get("url_path")
                url_path = url_path_from_dir_name(dir_name, stored_url_path)

                if dir_name in remote:
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {display_name}")
                        result.updated.append(dir_name)
                        continue

                    await self.client.save_dashboard_config(config, url_path)
                    result.updated.append(dir_name)
                    console.print(f"  [yellow]Updated[/yellow] {display_name}")
                else:
                    # Create new dashboard
                    if dir_name == "lovelace":
                        # Default dashboard doesn't need creation
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {display_name}")
                            result.created.append(dir_name)
                            continue

                        await self.client.save_dashboard_config(config, None)
                        result.created.append(dir_name)
                        console.print(f"  [green]Created[/green] {display_name}")
                    else:
                        # Create new dashboard first, then save config
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {display_name}")
                            result.created.append(dir_name)
                            continue

                        # Create the dashboard entry
                        await self.client.create_dashboard(
                            url_path=url_path or f"dashboard-{dir_name}",
                            title=display_name,
                            icon=meta.get("icon"),
                            show_in_sidebar=meta.get("show_in_sidebar", True),
                            require_admin=meta.get("require_admin", False),
                        )
                        # Then save the config
                        await self.client.save_dashboard_config(config, url_path)
                        result.created.append(dir_name)
                        console.print(f"  [green]Created[/green] {display_name}")

            except Exception as e:
                result.errors.append((dir_name, str(e)))
                console.print(f"  [red]Error[/red] {display_name}: {e}")

        # Auto-rename view files to match content (after successful push)
        if not dry_run:
            self._rename_view_files(local)

        # Warn about remote items without local counterpart
        if not sync_deletions:
            orphaned = [d for d in remote if d not in local and d not in url_path_renames]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} remote dashboard(s) not in local files "
                    "(use --sync-deletions to remove)[/dim]"
                )

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

                    console.print(
                        f"  [blue]Renamed view[/blue] {old_file.name} -> {new_file.name}"
                    )

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Normalize a dashboard config for comparison.

        This ensures consistent key ordering and removes title if empty.
        """
        result: dict[str, Any] = {}

        # Copy non-view keys (like strategy, swipe_nav, etc.) as-is
        for key, value in config.items():
            if key == "views":
                # Normalize views through Pydantic for consistent comparison
                result["views"] = [View.normalize(view) for view in value]
            elif key == "title" and not value:
                # Skip empty title
                continue
            else:
                result[key] = value

        return result

    async def diff(self) -> list[DiffItem]:
        """Compare local dashboards with remote."""
        items: list[DiffItem] = []

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
                    items.append(
                        DiffItem(
                            entity_id=dir_name,
                            status="renamed",
                            local=local_data["config"],
                            remote=remote[dir_name]["config"],
                            new_id=local_url_path,
                        )
                    )

        for dir_name, local_data in local.items():
            if dir_name in url_path_renames:
                continue

            local_config = local_data["config"]

            if dir_name not in remote:
                items.append(
                    DiffItem(
                        entity_id=dir_name,
                        status="added",
                        local=local_config,
                    )
                )
            else:
                remote_config = remote[dir_name]["config"]
                # Normalize both configs for comparison
                local_normalized = self._normalize_config(local_config)
                remote_normalized = self._normalize_config(remote_config)

                if dump_yaml(local_normalized) != dump_yaml(remote_normalized):
                    items.append(
                        DiffItem(
                            entity_id=dir_name,
                            status="modified",
                            local=local_config,
                            remote=remote_config,
                        )
                    )

        for dir_name in remote:
            if dir_name not in local and dir_name not in url_path_renames:
                items.append(
                    DiffItem(
                        entity_id=dir_name,
                        status="deleted",
                        remote=remote[dir_name]["config"],
                    )
                )

        return items

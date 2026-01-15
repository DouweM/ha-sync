"""Helper sync implementation for input_boolean, input_number, etc."""

from pathlib import Path
from typing import Any

import logfire
from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import HELPER_MODELS
from ha_sync.utils import (
    dump_yaml,
    filename_from_id,
    id_from_filename,
    load_yaml,
    relative_path,
)

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()

HELPER_TYPES = list(HELPER_MODELS.keys())


class HelperSyncer(BaseSyncer):
    """Syncer for Home Assistant input helpers."""

    entity_type = "helper"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path

    def _helper_path(self, helper_type: str) -> Path:
        """Get path for a specific helper type."""
        return self.local_path / helper_type

    async def _get_helpers_of_type(self, helper_type: str) -> list[dict[str, Any]]:
        """Get helpers of a specific type from HA."""
        method_name = f"get_{helper_type}s"
        method = getattr(self.client, method_name, None)
        if method:
            return await method()
        return []

    async def _create_helper(self, helper_type: str, config: dict[str, Any]) -> None:
        """Create a helper in HA."""
        method_name = f"create_{helper_type}"
        method = getattr(self.client, method_name, None)
        if method:
            await method(config)

    async def _update_helper(
        self, helper_type: str, helper_id: str, config: dict[str, Any]
    ) -> None:
        """Update a helper in HA."""
        method_name = f"update_{helper_type}"
        method = getattr(self.client, method_name, None)
        if method:
            await method(helper_id, config)

    async def _delete_helper(self, helper_type: str, helper_id: str) -> None:
        """Delete a helper in HA."""
        method_name = f"delete_{helper_type}"
        method = getattr(self.client, method_name, None)
        if method:
            await method(helper_id)

    @logfire.instrument("Fetch remote helpers")
    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all helpers from Home Assistant."""
        result: dict[str, dict[str, Any]] = {}

        for helper_type in HELPER_TYPES:
            helpers = await self._get_helpers_of_type(helper_type)
            for helper in helpers:
                helper_id = helper.get("id", helper.get("name", ""))
                if helper_id:
                    result[f"{helper_type}/{helper_id}"] = {
                        "type": helper_type,
                        **helper,
                    }

        return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local helper files."""
        result: dict[str, dict[str, Any]] = {}

        for helper_type in HELPER_TYPES:
            helper_path = self._helper_path(helper_type)
            if not helper_path.exists():
                continue

            for yaml_file in helper_path.glob("*.yaml"):
                data = load_yaml(yaml_file)
                if data and isinstance(data, dict):
                    helper_id = data.get("id", id_from_filename(yaml_file))
                    result[f"{helper_type}/{helper_id}"] = {
                        "type": helper_type,
                        **data,
                    }

        return result

    @logfire.instrument("Pull helpers")
    async def pull(
        self,
        sync_deletions: bool = False,
        dry_run: bool = False,
        remote: dict[str, Any] | None = None,
    ) -> SyncResult:
        """Pull helpers from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        # Ensure all helper directories exist
        if not dry_run:
            for helper_type in HELPER_TYPES:
                self._helper_path(helper_type).mkdir(parents=True, exist_ok=True)

        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        for full_id, data in remote.items():
            helper_type = data["type"]
            helper_id = data.get("id", full_id.split("/")[-1])

            # Remove type from data for storage
            config = {k: v for k, v in data.items() if k != "type"}

            # Ensure ID is in config
            if "id" not in config:
                config = {"id": helper_id, **config}

            # Validate and order through Pydantic model
            model_class = HELPER_MODELS.get(helper_type)
            if model_class:
                ordered = model_class.normalize(config)
            else:
                ordered = config

            file_path = self._helper_path(helper_type) / filename_from_id(helper_id)

            rel_path = relative_path(file_path)

            try:
                if full_id in local:
                    local_config = {k: v for k, v in local[full_id].items() if k != "type"}
                    if model_class:
                        local_normalized = model_class.normalize(local_config)
                    else:
                        local_normalized = local_config
                    if ordered != local_normalized:
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        else:
                            dump_yaml(ordered, file_path)
                            console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                        result.updated.append(full_id)
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                    else:
                        dump_yaml(ordered, file_path)
                        console.print(f"  [green]Created[/green] {rel_path}")
                    result.created.append(full_id)

            except Exception as e:
                result.errors.append((full_id, str(e)))
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        # Delete local files that don't exist in remote
        if sync_deletions:
            for full_id, local_data in local.items():
                if full_id not in remote:
                    helper_type = local_data["type"]
                    helper_id = full_id.split("/")[-1]
                    file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
                    if file_path.exists():
                        rel_path = relative_path(file_path)
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                        else:
                            file_path.unlink()
                            console.print(f"  [red]Deleted[/red] {rel_path}")
                        result.deleted.append(full_id)
        else:
            # Warn about local files without remote counterpart
            orphaned = [fid for fid in local if fid not in remote]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} local file(s) not in HA "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    @logfire.instrument("Push helpers")
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local helpers to Home Assistant.

        Args:
            force: If True, push all local entities regardless of changes.
            sync_deletions: If True, delete remote helpers not in local files.
            dry_run: If True, only show what would be done without making changes.
            diff_items: Pre-computed diff items. If provided (and force=False),
                       these are used directly without recomputing. This ensures
                       the actual push matches the diff that was shown to the user.
        """
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        local = self.get_local_entities()

        # Determine whether we need to fetch remote entities
        # We need remote for: force mode, no diff_items, or if diff_items has renames/deletions
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
        processed_ids: set[str] = set()

        # Build a map of diff_item status by entity_id for quick lookup
        diff_status_map = {item.entity_id: item.status for item in diff_items}

        # Process renames first (always, regardless of force)
        for item in diff_items:
            if item.status != "renamed" or not item.new_id:
                continue

            # remote is guaranteed to be fetched when there are renames (has_renames check)
            assert remote is not None

            old_full_id = item.entity_id
            new_full_id = item.new_id
            processed_ids.add(old_full_id)
            processed_ids.add(new_full_id)

            helper_type = old_full_id.split("/")[0]
            old_id = old_full_id.split("/")[1]
            new_id = new_full_id.split("/")[1]
            old_file = self._helper_path(helper_type) / filename_from_id(old_id)
            new_file = self._helper_path(helper_type) / filename_from_id(new_id)
            old_rel_path = relative_path(old_file)
            new_rel_path = relative_path(new_file)

            if dry_run:
                console.print(f"  [cyan]Would rename[/cyan] {old_rel_path} -> {new_rel_path}")
                result.renamed.append((old_full_id, new_full_id))
                continue

            try:
                config = load_yaml(old_file)
                if not config:
                    continue

                # Delete old and create new
                await self._delete_helper(helper_type, old_id)
                await self._create_helper(helper_type, config)

                # Rename local file
                old_file.rename(new_file)

                result.renamed.append((old_full_id, new_full_id))
                console.print(f"  [blue]Renamed[/blue] {old_rel_path} -> {new_rel_path}")

            except Exception as e:
                result.errors.append((old_full_id, str(e)))
                console.print(f"  [red]Error renaming[/red] {old_rel_path}: {e}")

        # Determine items to create/update
        if force:
            # Force mode: all local items not already processed
            items_to_process = [
                (full_id, local[full_id]) for full_id in local if full_id not in processed_ids
            ]
        else:
            # Normal mode: only items from diff (added or modified)
            items_to_process = [
                (item.entity_id, local[item.entity_id])
                for item in diff_items
                if item.status in ("added", "modified") and item.entity_id in local
            ]

        # Process creates and updates
        for full_id, data in items_to_process:
            helper_type = data["type"]
            helper_id = data.get("id", full_id.split("/")[-1])
            config = {k: v for k, v in data.items() if k != "type"}
            file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
            rel_path = relative_path(file_path)

            # Determine if this is an update (existing in remote) or create (new)
            # Use diff_item status when remote is not fetched, otherwise check remote directly
            if remote is not None:
                is_update = full_id in remote
            else:
                # Infer from diff_item status: "modified" means it exists in remote
                is_update = diff_status_map.get(full_id) == "modified"

            try:
                if dry_run:
                    action = "Would update" if is_update else "Would create"
                    console.print(f"  [cyan]{action}[/cyan] {rel_path}")
                    (result.updated if is_update else result.created).append(full_id)
                    continue

                if is_update:
                    await self._update_helper(helper_type, helper_id, config)
                    result.updated.append(full_id)
                    console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                else:
                    await self._create_helper(helper_type, config)
                    result.created.append(full_id)
                    console.print(f"  [green]Created[/green] {rel_path}")

            except Exception as e:
                result.errors.append((full_id, str(e)))
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        # Process deletions
        if sync_deletions:
            if force:
                # Force mode: remote is guaranteed to be fetched
                assert remote is not None
                # Delete all remote items not in local
                items_to_delete = [
                    full_id
                    for full_id in remote
                    if full_id not in local and full_id not in processed_ids
                ]
            else:
                # Normal mode: only items from diff
                items_to_delete = [
                    item.entity_id for item in diff_items if item.status == "deleted"
                ]

            for full_id in items_to_delete:
                helper_type = full_id.split("/")[0]
                helper_id = full_id.split("/")[1]
                file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
                rel_path = relative_path(file_path)

                try:
                    if dry_run:
                        console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                        result.deleted.append(full_id)
                        continue

                    await self._delete_helper(helper_type, helper_id)
                    result.deleted.append(full_id)
                    console.print(f"  [red]Deleted[/red] {rel_path}")
                except Exception as e:
                    result.errors.append((full_id, str(e)))
                    console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")
        else:
            # Warn about remote items without local counterpart
            # Only show if we have remote data (not when using pre-computed diff_items)
            if remote is not None:
                orphaned = [fid for fid in remote if fid not in local and fid not in processed_ids]
                if orphaned:
                    console.print(
                        f"  [dim]{len(orphaned)} remote item(s) not in local files "
                        "(use --sync-deletions to remove)[/dim]"
                    )

        # Reload helpers
        if not dry_run and result.has_changes:
            try:
                await self.client.reload_helpers()
                console.print("  [dim]Reloaded helpers[/dim]")
            except Exception as e:
                console.print(f"  [red]Error reloading[/red]: {e}")

        return result

    @logfire.instrument("Diff helpers")
    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local helpers with remote.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        items: list[DiffItem] = []

        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Find renames
        renames: set[str] = set()
        for helper_type in HELPER_TYPES:
            helper_path = self._helper_path(helper_type)
            if not helper_path.exists():
                continue

            for yaml_file in helper_path.glob("*.yaml"):
                filename_id = id_from_filename(yaml_file)
                data = load_yaml(yaml_file)
                if data and isinstance(data, dict):
                    content_id = data.get("id", filename_id)
                    old_full_id = f"{helper_type}/{filename_id}"
                    new_full_id = f"{helper_type}/{content_id}"
                    if content_id != filename_id and old_full_id in remote:
                        renames.add(old_full_id)
                        old_file = helper_path / filename_from_id(filename_id)
                        rel_path = relative_path(old_file)
                        items.append(
                            DiffItem(
                                entity_id=old_full_id,
                                status="renamed",
                                local=data,
                                remote=remote.get(old_full_id),
                                new_id=new_full_id,
                                file_path=rel_path,
                            )
                        )

        for full_id, local_data in local.items():
            if full_id in renames:
                continue

            helper_type = full_id.split("/")[0]
            helper_id = full_id.split("/")[-1]
            file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
            rel_path = relative_path(file_path)

            local_config = {k: v for k, v in local_data.items() if k != "type"}

            if full_id not in remote:
                items.append(
                    DiffItem(
                        entity_id=full_id,
                        status="added",
                        local=local_config,
                        file_path=rel_path,
                    )
                )
            else:
                remote_data = remote[full_id]
                remote_config = {k: v for k, v in remote_data.items() if k != "type"}
                # Add id to remote config for comparison (like pull does)
                if "id" not in remote_config:
                    remote_config = {"id": helper_id, **remote_config}

                # Normalize both through Pydantic for consistent comparison
                model_class = HELPER_MODELS.get(helper_type)
                if model_class:
                    local_normalized = model_class.normalize(local_config)
                    remote_normalized = model_class.normalize(remote_config)
                else:
                    local_normalized = local_config
                    remote_normalized = remote_config

                if local_normalized != remote_normalized:
                    items.append(
                        DiffItem(
                            entity_id=full_id,
                            status="modified",
                            local=local_normalized,
                            remote=remote_normalized,
                            file_path=rel_path,
                        )
                    )

        for full_id in remote:
            if full_id not in local and full_id not in renames:
                remote_data = remote[full_id]
                helper_type = full_id.split("/")[0]
                helper_id = full_id.split("/")[-1]
                file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
                rel_path = relative_path(file_path)
                remote_config = {k: v for k, v in remote_data.items() if k != "type"}
                items.append(
                    DiffItem(
                        entity_id=full_id,
                        status="deleted",
                        remote=remote_config,
                        file_path=rel_path,
                    )
                )

        return items

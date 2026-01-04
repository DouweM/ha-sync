"""Helper sync implementation for input_boolean, input_number, etc."""

from pathlib import Path
from typing import Any

from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import HELPER_MODELS
from ha_sync.utils import (
    dump_yaml,
    filename_from_id,
    id_from_filename,
    load_yaml,
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

    async def pull(self, sync_deletions: bool = False) -> SyncResult:
        """Pull helpers from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        # Ensure all helper directories exist
        for helper_type in HELPER_TYPES:
            self._helper_path(helper_type).mkdir(parents=True, exist_ok=True)

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

            try:
                if full_id in local:
                    local_config = {k: v for k, v in local[full_id].items() if k != "type"}
                    if model_class:
                        local_normalized = model_class.normalize(local_config)
                    else:
                        local_normalized = local_config
                    if ordered != local_normalized:
                        dump_yaml(ordered, file_path)
                        result.updated.append(full_id)
                        console.print(f"  [yellow]Updated[/yellow] {full_id}")
                else:
                    dump_yaml(ordered, file_path)
                    result.created.append(full_id)
                    console.print(f"  [green]Created[/green] {full_id}")

            except Exception as e:
                result.errors.append((full_id, str(e)))
                console.print(f"  [red]Error[/red] {full_id}: {e}")

        # Delete local files that don't exist in remote
        if sync_deletions:
            for full_id, local_data in local.items():
                if full_id not in remote:
                    helper_type = local_data["type"]
                    helper_id = full_id.split("/")[-1]
                    file_path = self._helper_path(helper_type) / filename_from_id(helper_id)
                    if file_path.exists():
                        file_path.unlink()
                        result.deleted.append(full_id)
                        console.print(f"  [red]Deleted[/red] {full_id}")
        else:
            # Warn about local files without remote counterpart
            orphaned = [fid for fid in local if fid not in remote]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} local file(s) not in HA "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Push local helpers to Home Assistant."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Handle renames
        renames: dict[str, str] = {}
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
                        renames[old_full_id] = new_full_id

        for old_full_id, new_full_id in renames.items():
            helper_type = old_full_id.split("/")[0]
            old_id = old_full_id.split("/")[1]
            new_id = new_full_id.split("/")[1]

            if dry_run:
                console.print(f"  [cyan]Would rename[/cyan] {old_full_id} -> {new_full_id}")
                result.renamed.append((old_full_id, new_full_id))
                continue

            try:
                yaml_file = self._helper_path(helper_type) / filename_from_id(old_id)
                config = load_yaml(yaml_file)
                if not config:
                    continue

                # Delete old and create new
                await self._delete_helper(helper_type, old_id)
                await self._create_helper(helper_type, config)

                # Rename local file
                new_file = self._helper_path(helper_type) / filename_from_id(new_id)
                yaml_file.rename(new_file)

                result.renamed.append((old_full_id, new_full_id))
                console.print(f"  [blue]Renamed[/blue] {old_full_id} -> {new_full_id}")

                remote.pop(old_full_id, None)
                local[new_full_id] = local.pop(old_full_id, {"type": helper_type, **config})

            except Exception as e:
                result.errors.append((old_full_id, str(e)))
                console.print(f"  [red]Error renaming[/red] {old_full_id}: {e}")

        # Process creates and updates
        for full_id, data in local.items():
            if full_id in [r[0] for r in renames.items()]:
                continue

            helper_type = data["type"]
            helper_id = data.get("id", full_id.split("/")[-1])
            config = {k: v for k, v in data.items() if k != "type"}

            try:
                if full_id in remote:
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {full_id}")
                        result.updated.append(full_id)
                        continue

                    await self._update_helper(helper_type, helper_id, config)
                    result.updated.append(full_id)
                    console.print(f"  [yellow]Updated[/yellow] {full_id}")
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {full_id}")
                        result.created.append(full_id)
                        continue

                    await self._create_helper(helper_type, config)
                    result.created.append(full_id)
                    console.print(f"  [green]Created[/green] {full_id}")

            except Exception as e:
                result.errors.append((full_id, str(e)))
                console.print(f"  [red]Error[/red] {full_id}: {e}")

        # Process deletions
        if sync_deletions:
            for full_id in remote:
                if full_id not in local and full_id not in renames:
                    helper_type = full_id.split("/")[0]
                    helper_id = full_id.split("/")[1]

                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {full_id}")
                            result.deleted.append(full_id)
                            continue

                        await self._delete_helper(helper_type, helper_id)
                        result.deleted.append(full_id)
                        console.print(f"  [red]Deleted[/red] {full_id}")
                    except Exception as e:
                        result.errors.append((full_id, str(e)))
                        console.print(f"  [red]Error deleting[/red] {full_id}: {e}")

        # Reload helpers
        if not dry_run and result.has_changes:
            try:
                await self.client.reload_helpers()
                console.print("  [dim]Reloaded helpers[/dim]")
            except Exception as e:
                console.print(f"  [red]Error reloading[/red]: {e}")

        # Warn about remote items without local counterpart
        if not sync_deletions:
            orphaned = [fid for fid in remote if fid not in local and fid not in renames]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} remote item(s) not in local files "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    async def diff(self) -> list[DiffItem]:
        """Compare local helpers with remote."""
        items: list[DiffItem] = []

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
                        items.append(
                            DiffItem(
                                entity_id=old_full_id,
                                status="renamed",
                                local=data,
                                remote=remote.get(old_full_id),
                                new_id=new_full_id,
                            )
                        )

        for full_id, local_data in local.items():
            if full_id in renames:
                continue

            local_config = {k: v for k, v in local_data.items() if k != "type"}

            if full_id not in remote:
                items.append(
                    DiffItem(
                        entity_id=full_id,
                        status="added",
                        local=local_config,
                    )
                )
            else:
                remote_data = remote[full_id]
                helper_type = full_id.split("/")[0]
                helper_id = full_id.split("/")[-1]
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
                        )
                    )

        for full_id in remote:
            if full_id not in local and full_id not in renames:
                remote_data = remote[full_id]
                remote_config = {k: v for k, v in remote_data.items() if k != "type"}
                items.append(
                    DiffItem(
                        entity_id=full_id,
                        status="deleted",
                        remote=remote_config,
                    )
                )

        return items

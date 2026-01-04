"""Template helper sync implementation (config entry-based helpers)."""

import logging
from pathlib import Path
from typing import Any

from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import TEMPLATE_ENTITY_TYPES, TEMPLATE_HELPER_MODELS
from ha_sync.utils import dump_yaml, filename_from_name, load_yaml, relative_path

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()
logger = logging.getLogger(__name__)

# Track warned types to avoid repeated warnings
_warned_template_types: set[str] = set()


class TemplateSyncer(BaseSyncer):
    """Syncer for template helpers (sensors, binary_sensors, switches).

    Template helpers are config entry-based, so they use a different API than
    traditional input_* helpers. Currently only pull is supported - push requires
    complex config flow interactions.
    """

    entity_type = "template"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path / "template"

    def _subtype_path(self, subtype: str) -> Path:
        """Get path for a specific subtype (sensor, binary_sensor, switch)."""
        return self.local_path / subtype

    def _get_model_for_subtype(self, subtype: str) -> type | None:
        """Get the Pydantic model for a subtype."""
        return TEMPLATE_HELPER_MODELS.get(subtype)

    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all template helpers from Home Assistant."""
        result: dict[str, dict[str, Any]] = {}

        templates = await self.client.get_template_helpers()
        for helper in templates:
            entry_id = helper.get("entry_id", "")
            step_id = helper.get("step_id", "unknown")
            if entry_id:
                # Warn about unknown template entity types
                if step_id not in TEMPLATE_ENTITY_TYPES and step_id not in _warned_template_types:
                    _warned_template_types.add(step_id)
                    logger.warning(
                        f"Unknown template entity type '{step_id}' - "
                        "Home Assistant may have added a new type. "
                        "Please report this at https://github.com/DouweM/ha-sync/issues"
                    )
                    console.print(
                        f"  [yellow]Warning:[/yellow] Unknown template type '{step_id}'"
                    )

                result[f"{step_id}/{entry_id}"] = {
                    "subtype": step_id,
                    **helper,
                }

        return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local template helper files."""
        result: dict[str, dict[str, Any]] = {}

        if not self.local_path.exists():
            return result

        for subtype_dir in self.local_path.iterdir():
            if not subtype_dir.is_dir():
                continue
            subtype = subtype_dir.name
            for yaml_file in subtype_dir.glob("*.yaml"):
                data = load_yaml(yaml_file)
                if data and isinstance(data, dict):
                    entry_id = data.get("entry_id")
                    if entry_id:
                        key = f"{subtype}/{entry_id}"
                    else:
                        # New file without entry_id - use filename as temporary key
                        key = f"{subtype}/_new/{yaml_file.stem}"
                    result[key] = {
                        "subtype": subtype,
                        "_filename": yaml_file.name,
                        **data,
                    }

        return result

    def _get_filename(
        self, name: str, entry_id: str, existing_filenames: set[str]
    ) -> str:
        """Get a unique filename for a helper, handling collisions."""
        filename = filename_from_name(name, entry_id)
        if filename not in existing_filenames:
            return filename
        # Handle collision by appending entry_id suffix
        base = filename.rsplit(".yaml", 1)[0]
        return f"{base}-{entry_id}.yaml"

    async def pull(self, sync_deletions: bool = False) -> SyncResult:
        """Pull template helpers from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        self.local_path.mkdir(parents=True, exist_ok=True)
        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Track used filenames per subtype to handle collisions
        used_filenames: dict[str, set[str]] = {}

        for full_id, data in remote.items():
            subtype = data["subtype"]
            entry_id = data.get("entry_id", full_id.split("/")[-1])
            name = data.get("name", entry_id)

            # Create subtype directory
            subtype_path = self._subtype_path(subtype)
            subtype_path.mkdir(parents=True, exist_ok=True)

            # Track filenames per subtype
            if subtype not in used_filenames:
                used_filenames[subtype] = set()

            # Remove subtype from data for storage
            config = {k: v for k, v in data.items() if k != "subtype"}

            # Ensure entry_id is in config
            if "entry_id" not in config:
                config = {"entry_id": entry_id, **config}

            # Validate and order through Pydantic model
            model_class = self._get_model_for_subtype(subtype)
            if model_class:
                try:
                    ordered = model_class.normalize(config)
                except Exception:
                    ordered = config
            else:
                ordered = config

            try:
                if full_id in local:
                    # Existing entry - check if name changed (needs rename)
                    local_data = local[full_id]
                    current_filename = local_data.get("_filename")
                    expected_filename = self._get_filename(
                        name, entry_id, used_filenames[subtype]
                    )
                    used_filenames[subtype].add(expected_filename)

                    # Remove metadata from comparison
                    local_config = {
                        k: v
                        for k, v in local_data.items()
                        if k not in ("subtype", "_filename")
                    }
                    if model_class:
                        try:
                            local_normalized = model_class.normalize(local_config)
                        except Exception:
                            local_normalized = local_config
                    else:
                        local_normalized = local_config

                    if current_filename and current_filename != expected_filename:
                        # Name changed - rename file
                        old_path = subtype_path / current_filename
                        new_path = subtype_path / expected_filename
                        if old_path.exists():
                            dump_yaml(ordered, new_path)
                            old_path.unlink()
                            result.renamed.append((full_id, full_id))
                            old_rel = relative_path(old_path)
                            new_rel = relative_path(new_path)
                            console.print(
                                f"  [blue]Renamed[/blue] {old_rel} -> {new_rel}"
                            )
                    elif ordered != local_normalized:
                        file_path = subtype_path / (current_filename or expected_filename)
                        dump_yaml(ordered, file_path)
                        result.updated.append(full_id)
                        rel_path = relative_path(file_path)
                        console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                else:
                    # New entry
                    filename = self._get_filename(name, entry_id, used_filenames[subtype])
                    used_filenames[subtype].add(filename)
                    file_path = subtype_path / filename
                    dump_yaml(ordered, file_path)
                    result.created.append(full_id)
                    rel_path = relative_path(file_path)
                    console.print(f"  [green]Created[/green] {rel_path}")

            except Exception as e:
                result.errors.append((full_id, str(e)))
                file_path = subtype_path / self._get_filename(name, entry_id, set())
                rel_path = relative_path(file_path)
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        # Delete local files that don't exist in remote
        if sync_deletions:
            for full_id, local_data in local.items():
                if full_id not in remote:
                    subtype = local_data["subtype"]
                    filename = local_data.get("_filename")
                    if filename:
                        file_path = self._subtype_path(subtype) / filename
                        if file_path.exists():
                            file_path.unlink()
                            result.deleted.append(full_id)
                            rel_path = relative_path(file_path)
                            console.print(f"  [red]Deleted[/red] {rel_path}")
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
        """Push local template helpers to Home Assistant."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        local = self.get_local_entities()
        remote = await self.get_remote_entities()

        # Get diff to determine what needs syncing
        diff_items = await self.diff()

        # Determine items to create/update
        if force:
            # Force mode: all local items
            items_to_process = list(local.items())
        else:
            # Normal mode: only items from diff (added or modified)
            items_to_process = [
                (item.entity_id, local[item.entity_id])
                for item in diff_items
                if item.status in ("added", "modified") and item.entity_id in local
            ]

        # Process creates and updates
        for full_id, data in items_to_process:
            subtype = data["subtype"]
            entry_id: str | None = data.get("entry_id")
            name = data.get("name", entry_id or full_id)
            current_filename = data.get("_filename")
            # Remove metadata before sending to HA
            config = {k: v for k, v in data.items() if k not in ("subtype", "_filename")}
            file_path = self._subtype_path(subtype) / (current_filename or filename_from_name(name, entry_id or "new"))
            rel_path = relative_path(file_path)

            is_update = full_id in remote and entry_id is not None

            try:
                if is_update:
                    # Update existing entry
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        result.updated.append(full_id)
                        continue

                    await self.client.update_template_helper(entry_id, config)  # type: ignore[arg-type]
                    result.updated.append(full_id)
                    console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                else:
                    # Create new entry
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                        result.created.append(full_id)
                        continue

                    new_entry_id = await self.client.create_template_helper(subtype, config)
                    result.created.append(full_id)
                    console.print(f"  [green]Created[/green] {rel_path}")

                    # Update local file with new entry_id
                    config["entry_id"] = new_entry_id
                    new_filename = filename_from_name(name, new_entry_id)
                    new_file_path = self._subtype_path(subtype) / new_filename

                    dump_yaml(config, new_file_path)

                    # Remove old file if filename changed
                    if current_filename and current_filename != new_filename:
                        old_path = self._subtype_path(subtype) / current_filename
                        if old_path.exists():
                            old_path.unlink()

            except Exception as e:
                result.errors.append((full_id, str(e)))
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        # Process deletions
        if sync_deletions:
            if force:
                # Force mode: delete all remote items not in local
                items_to_delete = [full_id for full_id in remote if full_id not in local]
            else:
                # Normal mode: only items from diff
                items_to_delete = [
                    item.entity_id
                    for item in diff_items
                    if item.status == "deleted"
                ]

            for full_id in items_to_delete:
                remote_data = remote[full_id]
                subtype = remote_data.get("subtype", full_id.split("/")[0])
                del_entry_id: str = remote_data.get("entry_id") or full_id.split("/")[-1]
                name = remote_data.get("name", del_entry_id)
                file_path = self._subtype_path(subtype) / filename_from_name(name, del_entry_id)
                rel_path = relative_path(file_path)
                try:
                    if dry_run:
                        console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                        result.deleted.append(full_id)
                        continue

                    await self.client.delete_template_helper(del_entry_id)
                    result.deleted.append(full_id)
                    console.print(f"  [red]Deleted[/red] {rel_path}")
                except Exception as e:
                    result.errors.append((full_id, str(e)))
                    console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")
        else:
            # Warn about remote items without local counterpart
            orphaned = [fid for fid in remote if fid not in local]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} remote item(s) not in local files "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    async def diff(self) -> list[DiffItem]:
        """Compare local template helpers with remote."""
        items: list[DiffItem] = []

        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        for full_id, local_data in local.items():
            subtype = local_data["subtype"]
            # Remove metadata from comparison
            local_config = {
                k: v for k, v in local_data.items() if k not in ("subtype", "_filename")
            }

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
                entry_id = full_id.split("/")[-1]
                remote_config = {k: v for k, v in remote_data.items() if k != "subtype"}

                # Ensure entry_id is in remote config for comparison
                if "entry_id" not in remote_config:
                    remote_config = {"entry_id": entry_id, **remote_config}

                # Normalize both through Pydantic for consistent comparison
                model_class = self._get_model_for_subtype(subtype)
                if model_class:
                    try:
                        local_normalized = model_class.normalize(local_config)
                        remote_normalized = model_class.normalize(remote_config)
                    except Exception:
                        local_normalized = local_config
                        remote_normalized = remote_config
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
            if full_id not in local:
                remote_data = remote[full_id]
                remote_config = {k: v for k, v in remote_data.items() if k != "subtype"}
                items.append(
                    DiffItem(
                        entity_id=full_id,
                        status="deleted",
                        remote=remote_config,
                    )
                )

        return items

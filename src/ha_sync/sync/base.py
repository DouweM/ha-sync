"""Base class for entity syncers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import logfire
from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import BaseEntityModel
from ha_sync.utils import dump_yaml, filename_from_id, id_from_filename, load_yaml, relative_path

console = Console()


@dataclass
class SyncResult:
    """Result of a sync operation."""

    created: list[str]
    updated: list[str]
    deleted: list[str]
    renamed: list[tuple[str, str]]  # (old_id, new_id)
    errors: list[tuple[str, str]]  # (entity_id, error message)

    @property
    def has_changes(self) -> bool:
        return bool(self.created or self.updated or self.deleted or self.renamed)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class DiffItem:
    """A single difference between local and remote."""

    entity_id: str
    status: str  # 'added', 'modified', 'deleted', 'renamed'
    entity_type: str = ""  # Type of entity (e.g., 'automation', 'script')
    local: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None
    new_id: str | None = None  # For renames
    file_path: str | None = None  # Relative file path for display


class BaseSyncer(ABC):
    """Base class for entity syncers."""

    entity_type: str = ""

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        self.client = client
        self.config = config

    @property
    @abstractmethod
    def local_path(self) -> Path:
        """Get the local path for this entity type."""
        ...

    @abstractmethod
    async def pull(
        self,
        sync_deletions: bool = False,
        dry_run: bool = False,
        remote: dict[str, Any] | None = None,
    ) -> SyncResult:
        """Pull entities from Home Assistant to local files.

        Args:
            sync_deletions: If True, delete local files that don't exist remotely.
            dry_run: If True, show what would be done without making changes.
            remote: Pre-fetched remote entities (skips API call if provided).
        """
        ...

    @abstractmethod
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local files to Home Assistant.

        Args:
            diff_items: Pre-computed diff items (skips API call if provided).
        """
        ...

    @abstractmethod
    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local files with remote state.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        ...

    @abstractmethod
    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all remote entities of this type."""
        ...

    @abstractmethod
    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local entities of this type."""
        ...


class SimpleEntitySyncer(BaseSyncer):
    """Base class for simple entity syncers (single YAML file per entity).

    Subclasses must set:
        - entity_type: str
        - model_class: type[BaseEntityModel]

    And implement:
        - local_path property
        - get_remote_entities()
        - save_remote()
        - delete_remote()
        - reload_remote()
    """

    model_class: ClassVar[type[BaseEntityModel]]

    def normalize(self, config: dict[str, Any]) -> dict[str, Any]:
        """Normalize config through Pydantic model."""
        return self.model_class.normalize(config)

    def get_display_name(self, entity_id: str, config: dict[str, Any]) -> str:
        """Get display name for logging. Override for custom display names."""
        return entity_id

    def get_filename(self, entity_id: str, config: dict[str, Any]) -> str:
        """Generate filename for entity. Override for custom filename logic."""
        return filename_from_id(entity_id)

    def clean_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Remove internal metadata from config."""
        return {k: v for k, v in config.items() if not k.startswith("_")}

    def ensure_id_in_config(self, entity_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Ensure ID is present in config."""
        if "id" not in config:
            return {"id": entity_id, **config}
        return config

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local entity files."""
        result: dict[str, dict[str, Any]] = {}

        if not self.local_path.exists():
            return result

        for yaml_file in self.local_path.glob("*.yaml"):
            data = load_yaml(yaml_file)
            if data and isinstance(data, dict):
                entity_id = data.get("id", id_from_filename(yaml_file))
                data["_filename"] = yaml_file.name
                result[entity_id] = data

        return result

    def detect_renames(self, remote: dict[str, dict[str, Any]]) -> dict[str, str]:
        """Detect renames by comparing filename ID to content ID.

        Returns:
            Dict mapping old_id (from filename) to new_id (from content).
        """
        renames: dict[str, str] = {}
        for yaml_file in self.local_path.glob("*.yaml"):
            filename_id = id_from_filename(yaml_file)
            data = load_yaml(yaml_file)
            if data and isinstance(data, dict):
                content_id = data.get("id", filename_id)
                if content_id != filename_id and filename_id in remote:
                    renames[filename_id] = content_id
        return renames

    @abstractmethod
    async def save_remote(self, entity_id: str, config: dict[str, Any]) -> None:
        """Save entity to Home Assistant."""
        ...

    @abstractmethod
    async def delete_remote(self, entity_id: str) -> None:
        """Delete entity from Home Assistant."""
        ...

    @abstractmethod
    async def reload_remote(self) -> None:
        """Reload entities in Home Assistant."""
        ...

    async def pull(
        self,
        sync_deletions: bool = False,
        dry_run: bool = False,
        remote: dict[str, Any] | None = None,
    ) -> SyncResult:
        """Pull entities from Home Assistant to local files."""
        with logfire.span("Pull {entity_type}s", entity_type=self.entity_type, dry_run=dry_run):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            if not dry_run:
                self.local_path.mkdir(parents=True, exist_ok=True)
            if remote is None:
                remote = await self.get_remote_entities()
            local = self.get_local_entities()

            for entity_id, config in remote.items():
                config = self.ensure_id_in_config(entity_id, config)
                ordered = self.normalize(config)
                file_path = self.local_path / self.get_filename(entity_id, config)
                rel_path = relative_path(file_path)

                if entity_id in local:
                    local_config = self.clean_config(local[entity_id])
                    local_normalized = self.normalize(local_config)
                    if ordered != local_normalized:
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        else:
                            dump_yaml(ordered, file_path)
                            console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                        result.updated.append(entity_id)
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                    else:
                        dump_yaml(ordered, file_path)
                        console.print(f"  [green]Created[/green] {rel_path}")
                    result.created.append(entity_id)

            if sync_deletions:
                for entity_id, local_data in local.items():
                    if entity_id not in remote:
                        filename = local_data.get(
                            "_filename", self.get_filename(entity_id, local_data)
                        )
                        file_path = self.local_path / filename
                        if file_path.exists():
                            rel_path = relative_path(file_path)
                            if dry_run:
                                console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                            else:
                                file_path.unlink()
                                console.print(f"  [red]Deleted[/red] {rel_path}")
                            result.deleted.append(entity_id)
            else:
                orphaned = [eid for eid in local if eid not in remote]
                if orphaned:
                    console.print(
                        f"  [dim]{len(orphaned)} local file(s) not in HA "
                        "(use --sync-deletions to remove)[/dim]"
                    )

            logfire.info(
                "Pull complete: {created} created, {updated} updated, {deleted} deleted",
                created=len(result.created),
                updated=len(result.updated),
                deleted=len(result.deleted),
            )
            return result

    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local entities to Home Assistant.

        Args:
            force: Push all local entities regardless of changes.
            sync_deletions: Also delete remote entities not in local.
            dry_run: Only show what would be done.
            diff_items: Pre-computed diff items to use (skips API call if provided).
                       Ignored when force=True.
        """
        with logfire.span(
            "Push {entity_type}s", entity_type=self.entity_type, force=force, dry_run=dry_run
        ):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            local = self.get_local_entities()

            # If force mode or no pre-computed diff, fetch remote and compute diff
            if force or diff_items is None:
                remote = await self.get_remote_entities()
                diff_items = await self.diff(remote=remote)
                remote_ids = set(remote.keys())
            else:
                # Derive remote_ids from diff_items status
                # Items with status modified, deleted, or renamed exist in remote
                remote_ids = {
                    item.entity_id for item in diff_items
                    if item.status in ("modified", "deleted", "renamed")
                }
                remote = None  # Not fetched when using pre-computed diff

            # Track processed items to avoid double-processing
            processed_ids: set[str] = set()

            # Process renames first (always, regardless of force)
            for item in diff_items:
                if item.status != "renamed" or not item.new_id:
                    continue

                old_id = item.entity_id
                new_id = item.new_id
                processed_ids.add(old_id)
                processed_ids.add(new_id)

                old_file = self.local_path / filename_from_id(old_id)
                new_file = self.local_path / filename_from_id(new_id)
                old_rel_path = relative_path(old_file)
                new_rel_path = relative_path(new_file)

                if dry_run:
                    console.print(f"  [cyan]Would rename[/cyan] {old_rel_path} -> {new_rel_path}")
                    result.renamed.append((old_id, new_id))
                    continue

                try:
                    config = load_yaml(old_file)
                    if not config:
                        continue

                    push_config = self.clean_config(config)

                    # Delete old and create new
                    await self.delete_remote(old_id)
                    await self.save_remote(new_id, push_config)

                    # Rename local file
                    old_file.rename(new_file)

                    result.renamed.append((old_id, new_id))
                    console.print(f"  [blue]Renamed[/blue] {old_rel_path} -> {new_rel_path}")
                    logfire.info("Renamed {old_id} -> {new_id}", old_id=old_id, new_id=new_id)

                except Exception as e:
                    result.errors.append((old_id, str(e)))
                    console.print(f"  [red]Error renaming[/red] {old_rel_path}: {e}")
                    logfire.error("Error renaming {old_id}: {error}", old_id=old_id, error=str(e))

            # Determine items to create/update
            if force:
                # Force mode: all local items not already processed
                items_to_process = [(eid, local[eid]) for eid in local if eid not in processed_ids]
            else:
                # Normal mode: only items from diff (added or modified)
                items_to_process = [
                    (item.entity_id, local[item.entity_id])
                    for item in diff_items
                    if item.status in ("added", "modified") and item.entity_id in local
                ]

            # Process creates and updates
            for entity_id, config in items_to_process:
                push_config = self.clean_config(config)
                filename = config.get("_filename", self.get_filename(entity_id, config))
                file_path = self.local_path / filename
                rel_path = relative_path(file_path)

                is_update = entity_id in remote_ids

                try:
                    if dry_run:
                        action = "Would update" if is_update else "Would create"
                        console.print(f"  [cyan]{action}[/cyan] {rel_path}")
                        (result.updated if is_update else result.created).append(entity_id)
                        continue

                    await self.save_remote(entity_id, push_config)
                    (result.updated if is_update else result.created).append(entity_id)
                    action = "Updated" if is_update else "Created"
                    color = "yellow" if is_update else "green"
                    console.print(f"  [{color}]{action}[/{color}] {rel_path}")

                except Exception as e:
                    result.errors.append((entity_id, str(e)))
                    console.print(f"  [red]Error[/red] {rel_path}: {e}")
                    logfire.error(
                        "Error pushing {entity_id}: {error}", entity_id=entity_id, error=str(e)
                    )

            # Process deletions
            if sync_deletions:
                if force:
                    # Force mode: delete all remote items not in local (requires remote dict)
                    assert remote is not None
                    items_to_delete: list[tuple[str, str]] = [
                        (eid, relative_path(self.local_path / self.get_filename(eid, remote[eid])))
                        for eid in remote
                        if eid not in local and eid not in processed_ids
                    ]
                else:
                    # Normal mode: use diff_items (may have pre-computed file_path)
                    items_to_delete = [
                        (item.entity_id, item.file_path or item.entity_id)
                        for item in diff_items
                        if item.status == "deleted"
                    ]

                for entity_id, rel_path in items_to_delete:
                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                            result.deleted.append(entity_id)
                            continue

                        await self.delete_remote(entity_id)
                        result.deleted.append(entity_id)
                        console.print(f"  [red]Deleted[/red] {rel_path}")
                    except Exception as e:
                        result.errors.append((entity_id, str(e)))
                        console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")
                        logfire.error(
                            "Error deleting {entity_id}: {error}",
                            entity_id=entity_id,
                            error=str(e),
                        )
            else:
                # Warn about remote items without local counterpart
                if remote is not None:
                    orphaned = [
                        eid for eid in remote if eid not in local and eid not in processed_ids
                    ]
                else:
                    # When using pre-computed diff, count deleted items
                    orphaned = [item.entity_id for item in diff_items if item.status == "deleted"]
                if orphaned:
                    console.print(
                        f"  [dim]{len(orphaned)} remote item(s) not in local files "
                        "(use --sync-deletions to remove)[/dim]"
                    )

            # Reload if changes were made
            if not dry_run and result.has_changes:
                try:
                    await self.reload_remote()
                    console.print(f"  [dim]Reloaded {self.entity_type}s[/dim]")
                except Exception as e:
                    console.print(f"  [red]Error reloading[/red]: {e}")

            logfire.info(
                "Push complete: {created} created, {updated} updated, "
                "{deleted} deleted, {renamed} renamed, {errors} errors",
                created=len(result.created),
                updated=len(result.updated),
                deleted=len(result.deleted),
                renamed=len(result.renamed),
                errors=len(result.errors),
            )
            return result

    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local entities with remote.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        with logfire.span("Diff {entity_type}s", entity_type=self.entity_type):
            items: list[DiffItem] = []

            if remote is None:
                remote = await self.get_remote_entities()
            local = self.get_local_entities()
            renames = self.detect_renames(remote)

            # Add rename items
            for old_id, new_id in renames.items():
                old_file = self.local_path / filename_from_id(old_id)
                new_file = self.local_path / filename_from_id(new_id)
                items.append(
                    DiffItem(
                        entity_id=old_id,
                        status="renamed",
                        entity_type=self.entity_type,
                        local=local.get(new_id),
                        remote=remote.get(old_id),
                        new_id=new_id,
                        file_path=f"{relative_path(old_file)} -> {relative_path(new_file)}",
                    )
                )

            # Check for additions and modifications
            for entity_id, local_config in local.items():
                if entity_id in renames.values():
                    # Already handled as rename target
                    continue

                local_clean = self.clean_config(local_config)
                filename = local_config.get("_filename", self.get_filename(entity_id, local_config))
                file_path = self.local_path / filename

                if entity_id not in remote:
                    items.append(
                        DiffItem(
                            entity_id=entity_id,
                            status="added",
                            entity_type=self.entity_type,
                            local=local_clean,
                            file_path=relative_path(file_path),
                        )
                    )
                else:
                    remote_config = self.ensure_id_in_config(entity_id, remote[entity_id])
                    local_normalized = self.normalize(local_clean)
                    remote_normalized = self.normalize(remote_config)

                    if local_normalized != remote_normalized:
                        items.append(
                            DiffItem(
                                entity_id=entity_id,
                                status="modified",
                                entity_type=self.entity_type,
                                local=local_normalized,
                                remote=remote_normalized,
                                file_path=relative_path(file_path),
                            )
                        )

            # Check for deletions
            for entity_id in remote:
                if entity_id not in local and entity_id not in renames:
                    filename = self.get_filename(entity_id, remote[entity_id])
                    file_path = self.local_path / filename
                    items.append(
                        DiffItem(
                            entity_id=entity_id,
                            status="deleted",
                            entity_type=self.entity_type,
                            remote=remote[entity_id],
                            file_path=relative_path(file_path),
                        )
                    )

            return items


class ConfigEntryBasedSyncer(BaseSyncer):
    """Base class for config entry-based helper syncers (templates, groups).

    These syncers manage helpers that use Home Assistant's config entry system,
    which requires:
    - Entry ID-based identification
    - Entity registry management for entity_id customization
    - Subtype-based directory structure (e.g., helpers/template/sensor/)

    Subclasses must implement:
        - local_path property
        - entity_type class attribute
        - _get_model_for_subtype() - returns Pydantic model for normalization
        - _get_entity_types() - returns set of valid entity types
        - _get_helper_type_name() - returns display name for warnings
        - _get_remote_helpers() - fetches helpers from HA
        - _create_helper() - creates a new helper in HA
        - _update_helper() - updates an existing helper in HA
        - _delete_helper() - deletes a helper in HA
    """

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)
        self._entity_registry_cache: dict[str, list[dict[str, Any]]] | None = None
        self._warned_types: set[str] = set()

    def _subtype_path(self, subtype: str) -> Path:
        """Get path for a specific subtype (sensor, binary_sensor, etc.)."""
        return self.local_path / subtype

    # Abstract methods to be implemented by subclasses

    @abstractmethod
    def _get_model_for_subtype(self, subtype: str) -> type | None:
        """Get the Pydantic model for a subtype."""
        ...

    @abstractmethod
    def _get_entity_types(self) -> set[str]:
        """Get the set of valid entity types for this helper category."""
        ...

    @abstractmethod
    def _get_helper_type_name(self) -> str:
        """Get the display name for this helper type (for warnings)."""
        ...

    @abstractmethod
    async def _get_remote_helpers(self) -> list[dict[str, Any]]:
        """Fetch all helpers of this type from Home Assistant."""
        ...

    @abstractmethod
    async def _create_helper(self, subtype: str, config: dict[str, Any]) -> str:
        """Create a helper in HA. Returns the new entry_id."""
        ...

    @abstractmethod
    async def _update_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a helper in HA."""
        ...

    @abstractmethod
    async def _delete_helper(self, entry_id: str) -> None:
        """Delete a helper in HA."""
        ...

    # Entity registry management (shared across all config entry-based helpers)

    async def _get_entity_registry_for_entry(
        self, entry_id: str
    ) -> list[dict[str, Any]]:
        """Get entity registry entries for a config entry (with caching)."""
        if self._entity_registry_cache is None:
            all_entities = await self.client.get_entity_registry()
            self._entity_registry_cache = {}
            for entity in all_entities:
                config_entry_id = entity.get("config_entry_id")
                if config_entry_id:
                    if config_entry_id not in self._entity_registry_cache:
                        self._entity_registry_cache[config_entry_id] = []
                    self._entity_registry_cache[config_entry_id].append(entity)

        return self._entity_registry_cache.get(entry_id, [])

    def _invalidate_entity_registry_cache(self) -> None:
        """Invalidate the entity registry cache."""
        self._entity_registry_cache = None

    def _expand_entity_id(self, entity_id: str, subtype: str) -> str:
        """Expand a suffix-only entity_id to full form."""
        if "." in entity_id:
            return entity_id
        return f"{subtype}.{entity_id}"

    def _validate_entity_id(self, entity_id: str, subtype: str) -> str | None:
        """Validate entity_id domain prefix matches expected domain."""
        if "." not in entity_id:
            return None  # Will be expanded, no validation needed

        actual_domain = entity_id.split(".")[0]
        if actual_domain != subtype:
            return (
                f"Invalid entity_id domain '{actual_domain}' "
                f"for {self._get_helper_type_name()} {subtype}. "
                f"Expected '{subtype}'."
            )
        return None

    async def _update_entity_id(
        self,
        entry_id: str,
        local_id: str,
        subtype: str,
        dry_run: bool = False,
    ) -> tuple[str, str] | None:
        """Update entity_id if it differs from local config."""

        local_id = self._expand_entity_id(local_id, subtype)

        error = self._validate_entity_id(local_id, subtype)
        if error:
            console.print(f"    [red]Error[/red] {error}")
            return None

        entity_entries = await self._get_entity_registry_for_entry(entry_id)
        if not entity_entries:
            return None

        current_id = entity_entries[0].get("entity_id")
        if not current_id or current_id == local_id:
            return None

        if dry_run:
            console.print(f"    [cyan]Would rename[/cyan] {current_id} -> {local_id}")
        else:
            try:
                await self.client.update_entity_registry(
                    current_id, new_entity_id=local_id
                )
                console.print(f"    [blue]Renamed[/blue] {current_id} -> {local_id}")
                self._invalidate_entity_registry_cache()
            except Exception as e:
                console.print(f"    [red]Error renaming[/red] {current_id}: {e}")
                return None

        return (current_id, local_id)

    def _get_filename(self, name: str, entry_id: str, existing_filenames: set[str]) -> str:
        """Get a unique filename for a helper, handling collisions."""
        from ha_sync.utils import filename_from_name

        filename = filename_from_name(name, entry_id)
        if filename not in existing_filenames:
            return filename
        # Handle collision by appending entry_id suffix
        base = filename.rsplit(".yaml", 1)[0]
        return f"{base}-{entry_id}.yaml"

    # Common implementations

    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all helpers from Home Assistant."""
        import logging

        logger = logging.getLogger(__name__)

        with logfire.span(f"Fetch remote {self.entity_type}s", entity_type=self.entity_type):
            result: dict[str, dict[str, Any]] = {}

            helpers = await self._get_remote_helpers()
            entity_types = self._get_entity_types()
            helper_type_name = self._get_helper_type_name()

            for helper in helpers:
                entry_id = helper.get("entry_id", "")
                step_id = helper.get("step_id", "unknown")
                if entry_id:
                    # Warn about unknown entity types
                    if step_id not in entity_types and step_id not in self._warned_types:
                        self._warned_types.add(step_id)
                        logger.warning(
                            f"Unknown {helper_type_name} entity type '{step_id}' - "
                            "Home Assistant may have added a new type. "
                            "Please report this at https://github.com/DouweM/ha-sync/issues"
                        )
                        console.print(
                            f"  [yellow]Warning:[/yellow] "
                            f"Unknown {helper_type_name} type '{step_id}'"
                        )

                    # Fetch entity_id from entity registry
                    entity_entries = await self._get_entity_registry_for_entry(entry_id)
                    if entity_entries:
                        helper["id"] = entity_entries[0].get("entity_id")

                    result[f"{step_id}/{entry_id}"] = {
                        "subtype": step_id,
                        **helper,
                    }

            return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local helper files."""
        from ha_sync.utils import load_yaml

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

    async def pull(
        self,
        sync_deletions: bool = False,
        dry_run: bool = False,
        remote: dict[str, Any] | None = None,
    ) -> SyncResult:
        """Pull helpers from Home Assistant to local files."""
        from ha_sync.utils import dump_yaml

        with logfire.span(
            f"Pull {self.entity_type}s", entity_type=self.entity_type, dry_run=dry_run
        ):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            if not dry_run:
                self.local_path.mkdir(parents=True, exist_ok=True)
            if remote is None:
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
                if not dry_run:
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
                            k: v for k, v in local_data.items() if k not in ("subtype", "_filename")
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
                                old_rel = relative_path(old_path)
                                new_rel = relative_path(new_path)
                                if dry_run:
                                    console.print(
                                        f"  [cyan]Would rename[/cyan] {old_rel} -> {new_rel}"
                                    )
                                else:
                                    dump_yaml(ordered, new_path)
                                    old_path.unlink()
                                    console.print(f"  [blue]Renamed[/blue] {old_rel} -> {new_rel}")
                                result.renamed.append((full_id, full_id))
                        elif ordered != local_normalized:
                            file_path = subtype_path / (current_filename or expected_filename)
                            rel_path = relative_path(file_path)
                            if dry_run:
                                console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                            else:
                                dump_yaml(ordered, file_path)
                                console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                            result.updated.append(full_id)
                    else:
                        # New entry
                        filename = self._get_filename(name, entry_id, used_filenames[subtype])
                        used_filenames[subtype].add(filename)
                        file_path = subtype_path / filename
                        rel_path = relative_path(file_path)
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                        else:
                            dump_yaml(ordered, file_path)
                            console.print(f"  [green]Created[/green] {rel_path}")
                        result.created.append(full_id)

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

    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local helpers to Home Assistant."""
        import asyncio

        from ha_sync.utils import dump_yaml, filename_from_name

        with logfire.span(
            f"Push {self.entity_type}s",
            entity_type=self.entity_type,
            force=force,
            dry_run=dry_run,
        ):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            # Invalidate entity registry cache for fresh data
            self._invalidate_entity_registry_cache()

            local = self.get_local_entities()

            # Determine whether we need to fetch remote entities
            has_deletions = diff_items and any(item.status == "deleted" for item in diff_items)
            need_remote = force or diff_items is None or has_deletions
            remote: dict[str, Any] | None = None
            if need_remote:
                remote = await self.get_remote_entities()

            # Determine what to process
            if force or diff_items is None:
                assert remote is not None
                diff_items = await self.diff(remote=remote)
            # else: Use the provided diff_items directly

            # Build a map of diff_item status by entity_id for quick lookup
            diff_status_map = {item.entity_id: item.status for item in diff_items}

            # Determine items to create/update
            if force:
                items_to_process = list(local.items())
            else:
                items_to_process = [
                    (item.entity_id, local[item.entity_id])
                    for item in diff_items
                    if item.status in ("added", "modified") and item.entity_id in local
                ]

            # Process creates and updates
            for full_id, data in items_to_process:
                subtype = data["subtype"]
                entry_id: str | None = data.get("entry_id")
                local_id = data.get("id")  # Desired entity_id from local config
                name = data.get("name", entry_id or full_id)
                current_filename = data.get("_filename")
                # Remove metadata and id before sending to HA
                config = {k: v for k, v in data.items() if k not in ("subtype", "_filename", "id")}
                file_path = self._subtype_path(subtype) / (
                    current_filename or filename_from_name(name, entry_id or "new")
                )
                rel_path = relative_path(file_path)

                # Determine if this is an update or create
                if remote is not None:
                    is_update = full_id in remote and entry_id is not None
                else:
                    is_update = diff_status_map.get(full_id) == "modified" and entry_id is not None

                try:
                    if is_update:
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                            result.updated.append(full_id)
                            if local_id and entry_id:
                                await self._update_entity_id(
                                    entry_id, local_id, subtype, dry_run=True
                                )
                            continue

                        await self._update_helper(entry_id, config)  # type: ignore[arg-type]
                        result.updated.append(full_id)
                        console.print(f"  [yellow]Updated[/yellow] {rel_path}")

                        # Handle entity_id renaming if id is specified
                        if local_id and entry_id:
                            rename_result = await self._update_entity_id(
                                entry_id, local_id, subtype, dry_run=False
                            )
                            if rename_result:
                                result.renamed.append(rename_result)
                    else:
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                            result.created.append(full_id)
                            continue

                        new_entry_id = await self._create_helper(subtype, config)
                        result.created.append(full_id)
                        console.print(f"  [green]Created[/green] {rel_path}")

                        # Update local file with new entry_id
                        config["entry_id"] = new_entry_id
                        if local_id:
                            config["id"] = local_id
                        new_filename = filename_from_name(name, new_entry_id)
                        new_file_path = self._subtype_path(subtype) / new_filename

                        dump_yaml(config, new_file_path)

                        # Remove old file if filename changed
                        if current_filename and current_filename != new_filename:
                            old_path = self._subtype_path(subtype) / current_filename
                            if old_path.exists():
                                old_path.unlink()

                        # Handle entity_id renaming for new entries
                        if local_id:
                            await asyncio.sleep(0.5)  # Brief wait for HA to create entity
                            self._invalidate_entity_registry_cache()
                            rename_result = await self._update_entity_id(
                                new_entry_id, local_id, subtype, dry_run=False
                            )
                            if rename_result:
                                result.renamed.append(rename_result)

                except Exception as e:
                    result.errors.append((full_id, str(e)))
                    console.print(f"  [red]Error[/red] {rel_path}: {e}")

            # Process deletions
            if sync_deletions:
                assert remote is not None

                if force:
                    items_to_delete = [full_id for full_id in remote if full_id not in local]
                else:
                    items_to_delete = [
                        item.entity_id for item in diff_items if item.status == "deleted"
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

                        await self._delete_helper(del_entry_id)
                        result.deleted.append(full_id)
                        console.print(f"  [red]Deleted[/red] {rel_path}")
                    except Exception as e:
                        result.errors.append((full_id, str(e)))
                        console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")
            else:
                if remote is not None:
                    orphaned = [fid for fid in remote if fid not in local]
                    if orphaned:
                        console.print(
                            f"  [dim]{len(orphaned)} remote item(s) not in local files "
                            "(use --sync-deletions to remove)[/dim]"
                        )

            return result

    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local helpers with remote."""
        from ha_sync.utils import filename_from_name

        with logfire.span(f"Diff {self.entity_type}s", entity_type=self.entity_type):
            items: list[DiffItem] = []

            if remote is None:
                remote = await self.get_remote_entities()
            local = self.get_local_entities()

            for full_id, local_data in local.items():
                subtype = local_data["subtype"]
                entry_id = local_data.get("entry_id", full_id.split("/")[-1])
                name = local_data.get("name", entry_id)
                filename = local_data.get("_filename", filename_from_name(name, entry_id))
                file_path = self._subtype_path(subtype) / filename
                rel_path = relative_path(file_path)

                # Remove metadata from comparison
                local_config = {
                    k: v for k, v in local_data.items() if k not in ("subtype", "_filename")
                }

                if full_id not in remote:
                    items.append(
                        DiffItem(
                            entity_id=full_id,
                            status="added",
                            entity_type=self.entity_type,
                            local=local_config,
                            file_path=rel_path,
                        )
                    )
                else:
                    remote_data = remote[full_id]
                    remote_entry_id = full_id.split("/")[-1]
                    remote_config = {k: v for k, v in remote_data.items() if k != "subtype"}

                    # Ensure entry_id is in remote config for comparison
                    if "entry_id" not in remote_config:
                        remote_config = {"entry_id": remote_entry_id, **remote_config}

                    # Normalize both through Pydantic
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
                                entity_type=self.entity_type,
                                local=local_normalized,
                                remote=remote_normalized,
                                file_path=rel_path,
                            )
                        )

            for full_id in remote:
                if full_id not in local:
                    remote_data = remote[full_id]
                    subtype = remote_data.get("subtype", full_id.split("/")[0])
                    entry_id = remote_data.get("entry_id", full_id.split("/")[-1])
                    name = remote_data.get("name", entry_id)
                    filename = filename_from_name(name, entry_id)
                    file_path = self._subtype_path(subtype) / filename
                    rel_path = relative_path(file_path)
                    remote_config = {k: v for k, v in remote_data.items() if k != "subtype"}
                    items.append(
                        DiffItem(
                            entity_id=full_id,
                            status="deleted",
                            entity_type=self.entity_type,
                            remote=remote_config,
                            file_path=rel_path,
                        )
                    )

            return items

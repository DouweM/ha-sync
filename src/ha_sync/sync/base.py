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
    local: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None
    new_id: str | None = None  # For renames


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
    async def pull(self, sync_deletions: bool = False) -> SyncResult:
        """Pull entities from Home Assistant to local files.

        Args:
            sync_deletions: If True, delete local files that don't exist remotely.
        """
        ...

    @abstractmethod
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Push local files to Home Assistant."""
        ...

    @abstractmethod
    async def diff(self) -> list[DiffItem]:
        """Compare local files with remote state."""
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

    async def pull(self, sync_deletions: bool = False) -> SyncResult:
        """Pull entities from Home Assistant to local files."""
        with logfire.span("Pull {entity_type}s", entity_type=self.entity_type):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            self.local_path.mkdir(parents=True, exist_ok=True)
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
                        dump_yaml(ordered, file_path)
                        result.updated.append(entity_id)
                        console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                else:
                    dump_yaml(ordered, file_path)
                    result.created.append(entity_id)
                    console.print(f"  [green]Created[/green] {rel_path}")

            if sync_deletions:
                for entity_id, local_data in local.items():
                    if entity_id not in remote:
                        filename = local_data.get(
                            "_filename", self.get_filename(entity_id, local_data)
                        )
                        file_path = self.local_path / filename
                        if file_path.exists():
                            file_path.unlink()
                            result.deleted.append(entity_id)
                            rel_path = relative_path(file_path)
                            console.print(f"  [red]Deleted[/red] {rel_path}")
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
    ) -> SyncResult:
        """Push local entities to Home Assistant."""
        with logfire.span(
            "Push {entity_type}s", entity_type=self.entity_type, force=force, dry_run=dry_run
        ):
            result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

            local = self.get_local_entities()
            remote = await self.get_remote_entities()

            # Get diff to determine what needs syncing
            diff_items = await self.diff()

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

                is_update = entity_id in remote

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
                    # Force mode: delete all remote items not in local
                    items_to_delete = [
                        eid for eid in remote if eid not in local and eid not in processed_ids
                    ]
                else:
                    # Normal mode: only items from diff
                    items_to_delete = [
                        item.entity_id for item in diff_items if item.status == "deleted"
                    ]

                for entity_id in items_to_delete:
                    filename = self.get_filename(entity_id, remote.get(entity_id, {}))
                    file_path = self.local_path / filename
                    rel_path = relative_path(file_path)
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
                orphaned = [eid for eid in remote if eid not in local and eid not in processed_ids]
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

    async def diff(self) -> list[DiffItem]:
        """Compare local entities with remote."""
        with logfire.span("Diff {entity_type}s", entity_type=self.entity_type):
            items: list[DiffItem] = []

            remote = await self.get_remote_entities()
            local = self.get_local_entities()
            renames = self.detect_renames(remote)

            # Add rename items
            for old_id, new_id in renames.items():
                items.append(
                    DiffItem(
                        entity_id=old_id,
                        status="renamed",
                        local=local.get(new_id),
                        remote=remote.get(old_id),
                        new_id=new_id,
                    )
                )

            # Check for additions and modifications
            for entity_id, local_config in local.items():
                if entity_id in renames.values():
                    # Already handled as rename target
                    continue

                local_clean = self.clean_config(local_config)

                if entity_id not in remote:
                    items.append(
                        DiffItem(
                            entity_id=entity_id,
                            status="added",
                            local=local_clean,
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
                                local=local_normalized,
                                remote=remote_normalized,
                            )
                        )

            # Check for deletions
            for entity_id in remote:
                if entity_id not in local and entity_id not in renames:
                    items.append(
                        DiffItem(
                            entity_id=entity_id,
                            status="deleted",
                            remote=remote[entity_id],
                        )
                    )

            return items

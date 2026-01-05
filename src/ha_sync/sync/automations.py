"""Automation sync implementation."""

from pathlib import Path
from typing import Any

import logfire
from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import Automation
from ha_sync.utils import (
    dump_yaml,
    filename_from_name,
    load_yaml,
    relative_path,
)

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()


class AutomationSyncer(BaseSyncer):
    """Syncer for Home Assistant automations."""

    entity_type = "automation"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.automations_path

    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all automations from Home Assistant."""
        with logfire.span("Fetch remote automations"):
            automations = await self.client.get_automations()
            result: dict[str, dict[str, Any]] = {}

            for automation in automations:
                # The internal ID is in attributes, not the entity_id suffix
                auto_id = automation.get("attributes", {}).get("id")
                if not auto_id:
                    continue

                # Get full config using the internal ID
                config = await self.client.get_automation_config(auto_id)
                if config:
                    result[auto_id] = config

            logfire.info("Found {count} automations", count=len(result))
            return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local automation files."""
        result: dict[str, dict[str, Any]] = {}

        if not self.local_path.exists():
            return result

        for yaml_file in self.local_path.glob("*.yaml"):
            data = load_yaml(yaml_file)
            if data and isinstance(data, dict):
                # ID must come from file content
                auto_id = data.get("id")
                if auto_id:
                    # Store filename for later reference
                    data["_filename"] = yaml_file.name
                    result[auto_id] = data

        return result

    @logfire.instrument("Pull automations")
    async def pull(self, sync_deletions: bool = False, dry_run: bool = False) -> SyncResult:
        """Pull automations from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        if not dry_run:
            self.local_path.mkdir(parents=True, exist_ok=True)
        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Track used filenames to handle collisions
        used_filenames: set[str] = set()

        with logfire.span("Write local files", dry_run=dry_run):
            for auto_id, config in remote.items():
                alias = config.get("alias", "")

                # Ensure ID is in config
                if "id" not in config:
                    config = {"id": auto_id, **config}

                # Validate and order through Pydantic model
                ordered = Automation.normalize(config)

                # Determine filename - use existing if updating, else create from alias
                if auto_id in local and "_filename" in local[auto_id]:
                    filename = local[auto_id]["_filename"]
                else:
                    filename = filename_from_name(alias, auto_id)
                    # Handle collisions by appending ID suffix
                    if filename in used_filenames:
                        stem = filename.rsplit(".yaml", 1)[0]
                        filename = f"{stem}-{auto_id}.yaml"

                used_filenames.add(filename)
                file_path = self.local_path / filename
                rel_path = relative_path(file_path)

                if auto_id in local:
                    # Check if content changed (exclude _filename metadata)
                    local_config = {
                        k: v for k, v in local[auto_id].items() if not k.startswith("_")
                    }
                    local_normalized = Automation.normalize(local_config)
                    if ordered != local_normalized:
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        else:
                            dump_yaml(ordered, file_path)
                            console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                        result.updated.append(auto_id)
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                    else:
                        dump_yaml(ordered, file_path)
                        console.print(f"  [green]Created[/green] {rel_path}")
                    result.created.append(auto_id)

            # Delete local files that don't exist in remote
            if sync_deletions:
                for auto_id, local_data in local.items():
                    if auto_id not in remote:
                        filename = local_data.get("_filename")
                        if filename:
                            file_path = self.local_path / filename
                            if file_path.exists():
                                rel_path = relative_path(file_path)
                                if dry_run:
                                    console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                                else:
                                    file_path.unlink()
                                    console.print(f"  [red]Deleted[/red] {rel_path}")
                                result.deleted.append(auto_id)
            else:
                # Warn about local files without remote counterpart
                orphaned = [aid for aid in local if aid not in remote]
                if orphaned:
                    console.print(
                        f"  [dim]{len(orphaned)} local file(s) not in HA "
                        "(use --sync-deletions to remove)[/dim]"
                    )

        return result

    @logfire.instrument("Push automations")
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
        diff_items: list[DiffItem] | None = None,
    ) -> SyncResult:
        """Push local automations to Home Assistant."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # When force=True, push all local items; otherwise only push changed items
        if force:
            # Build diff items for all local entities
            diff_items = []
            for auto_id, local_config in local.items():
                local_clean = {k: v for k, v in local_config.items() if not k.startswith("_")}
                if auto_id in remote:
                    diff_items.append(
                        DiffItem(
                            entity_id=auto_id,
                            status="modified",
                            local=local_clean,
                            remote=remote[auto_id],
                        )
                    )
                else:
                    diff_items.append(
                        DiffItem(entity_id=auto_id, status="added", local=local_clean)
                    )
            # Add deletions if sync_deletions
            if sync_deletions:
                for auto_id in remote:
                    if auto_id not in local:
                        diff_items.append(
                            DiffItem(entity_id=auto_id, status="deleted", remote=remote[auto_id])
                        )
        else:
            # Pass remote to avoid re-fetching
            diff_items = await self.diff(remote=remote)
            if not diff_items:
                console.print("  [dim]No changes to push[/dim]")
                return result

        # Track files to rename after successful push
        files_to_rename: list[tuple[Path, Path]] = []

        # Process only changed items from diff
        with logfire.span("Save to remote"):
            for item in diff_items:
                auto_id = item.entity_id

                if item.status == "added":
                    config = local.get(auto_id, {})
                    push_config = {k: v for k, v in config.items() if not k.startswith("_")}
                    alias = config.get("alias", "")
                    current_filename = config.get("_filename", "")
                    file_path = self.local_path / (
                        current_filename or filename_from_name(alias, auto_id)
                    )
                    rel_path = relative_path(file_path)

                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                            result.created.append(auto_id)
                        else:
                            await self.client.save_automation_config(auto_id, push_config)
                            result.created.append(auto_id)
                            console.print(f"  [green]Created[/green] {rel_path}")

                        # Check if file should be renamed to match alias
                        if current_filename and alias:
                            expected_filename = filename_from_name(alias, auto_id)
                            if current_filename != expected_filename:
                                old_path = self.local_path / current_filename
                                new_path = self.local_path / expected_filename
                                if old_path.exists() and not new_path.exists():
                                    files_to_rename.append((old_path, new_path))

                    except Exception as e:
                        result.errors.append((auto_id, str(e)))
                        console.print(f"  [red]Error[/red] {rel_path}: {e}")

                elif item.status == "modified":
                    config = local.get(auto_id, {})
                    push_config = {k: v for k, v in config.items() if not k.startswith("_")}
                    alias = config.get("alias", "")
                    current_filename = config.get("_filename", "")
                    file_path = self.local_path / (
                        current_filename or filename_from_name(alias, auto_id)
                    )
                    rel_path = relative_path(file_path)

                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                            result.updated.append(auto_id)
                        else:
                            await self.client.save_automation_config(auto_id, push_config)
                            result.updated.append(auto_id)
                            console.print(f"  [yellow]Updated[/yellow] {rel_path}")

                        # Check if file should be renamed to match alias
                        if current_filename and alias:
                            expected_filename = filename_from_name(alias, auto_id)
                            if current_filename != expected_filename:
                                old_path = self.local_path / current_filename
                                new_path = self.local_path / expected_filename
                                if old_path.exists() and not new_path.exists():
                                    files_to_rename.append((old_path, new_path))

                    except Exception as e:
                        result.errors.append((auto_id, str(e)))
                        console.print(f"  [red]Error[/red] {rel_path}: {e}")

                elif item.status == "deleted" and sync_deletions:
                    alias = item.remote.get("alias", "") if item.remote else ""
                    file_path = self.local_path / filename_from_name(alias, auto_id)
                    rel_path = relative_path(file_path)
                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                            result.deleted.append(auto_id)
                        else:
                            await self.client.delete_automation(auto_id)
                            result.deleted.append(auto_id)
                            console.print(f"  [red]Deleted[/red] {rel_path}")
                    except Exception as e:
                        result.errors.append((auto_id, str(e)))
                        console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")

        # Reload automations if we made changes
        if not dry_run and result.has_changes:
            try:
                await self.client.reload_automations()
                console.print("  [dim]Reloaded automations[/dim]")
            except Exception as e:
                console.print(f"  [red]Error reloading[/red]: {e}")

        # Rename files to match aliases (after successful push)
        if not dry_run:
            for old_path, new_path in files_to_rename:
                try:
                    old_path.rename(new_path)
                    result.renamed.append((old_path.name, new_path.name))
                    old_rel = relative_path(old_path)
                    new_rel = relative_path(new_path)
                    console.print(f"  [blue]Renamed[/blue] {old_rel} -> {new_rel}")
                except Exception as e:
                    old_rel = relative_path(old_path)
                    console.print(f"  [red]Error renaming[/red] {old_rel}: {e}")
        elif files_to_rename:
            for old_path, new_path in files_to_rename:
                old_rel = relative_path(old_path)
                new_rel = relative_path(new_path)
                console.print(f"  [cyan]Would rename[/cyan] {old_rel} -> {new_rel}")

        # Warn about remote items without local counterpart
        if not sync_deletions:
            orphaned = [aid for aid in remote if aid not in local]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} remote item(s) not in local files "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    @logfire.instrument("Diff automations")
    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local automations with remote.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        items: list[DiffItem] = []

        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Check for additions and modifications
        for auto_id, local_config in local.items():
            # Remove internal metadata for comparison
            local_clean = {k: v for k, v in local_config.items() if not k.startswith("_")}
            filename = local_config.get("_filename", filename_from_name(local_config.get("alias", ""), auto_id))
            file_path = self.local_path / filename
            rel_path = relative_path(file_path)

            if auto_id not in remote:
                items.append(
                    DiffItem(
                        entity_id=auto_id,
                        status="added",
                        local=local_clean,
                        file_path=rel_path,
                    )
                )
            else:
                # Compare configs
                remote_config = remote[auto_id]
                # Add id to remote config for comparison (like pull does)
                if "id" not in remote_config:
                    remote_config = {"id": auto_id, **remote_config}

                # Normalize both through Pydantic for consistent comparison
                local_normalized = Automation.normalize(local_clean)
                remote_normalized = Automation.normalize(remote_config)

                if local_normalized != remote_normalized:
                    items.append(
                        DiffItem(
                            entity_id=auto_id,
                            status="modified",
                            local=local_normalized,
                            remote=remote_normalized,
                            file_path=rel_path,
                        )
                    )

        # Check for deletions
        for auto_id in remote:
            if auto_id not in local:
                alias = remote[auto_id].get("alias", "")
                filename = filename_from_name(alias, auto_id)
                file_path = self.local_path / filename
                rel_path = relative_path(file_path)
                items.append(
                    DiffItem(
                        entity_id=auto_id,
                        status="deleted",
                        remote=remote[auto_id],
                        file_path=rel_path,
                    )
                )

        return items

"""Generic config entry-based helper sync implementation.

This syncer handles any config entry-based helper type, including ones
that don't have explicit model definitions. It auto-discovers helpers
by domain and syncs them to/from local files.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import logfire
from rich.console import Console

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import (
    BaseEntityModel,
    IntegrationHelper,
    ThresholdHelper,
    TodHelper,
    UtilityMeterHelper,
)
from ha_sync.utils import dump_yaml, filename_from_name, load_yaml, relative_path

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()
logger = logging.getLogger(__name__)

# Track warned domains to avoid repeated warnings
_warned_config_entry_domains: set[str] = set()

# Known helper domains that use config entries (not YAML/WebSocket-based)
# These are domains that can be created via Settings > Helpers in HA UI
# Note: counter, timer, schedule use WebSocket API like input_*, not config entries
CONFIG_ENTRY_HELPER_DOMAINS = {
    # Implemented with specific models
    "integration",
    "utility_meter",
    "threshold",
    "tod",
    # Additional helper domains (will use generic handling)
    "derivative",
    "min_max",
    "filter",
    "switch_as_x",
    "generic_thermostat",
    "generic_hygrostat",
    "bayesian",
    "trend",
    "random",
    "statistics",
    "mold_indicator",
}

# Models for known helper types (for proper field ordering)
HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "integration": IntegrationHelper,
    "utility_meter": UtilityMeterHelper,
    "threshold": ThresholdHelper,
    "tod": TodHelper,
}

# Map helper domain -> entity domain for entity_id expansion/validation
# Used when user provides just the suffix (e.g., "my_thermostat" -> "climate.my_thermostat")
ENTITY_DOMAIN_MAP: dict[str, str] = {
    "integration": "sensor",
    "utility_meter": "sensor",
    "threshold": "binary_sensor",
    "tod": "binary_sensor",
    "derivative": "sensor",
    "min_max": "sensor",
    "filter": "sensor",
    "statistics": "sensor",
    "generic_thermostat": "climate",
    "generic_hygrostat": "humidifier",
    "bayesian": "binary_sensor",
    "trend": "binary_sensor",
    "random": "sensor",  # Can also be binary_sensor
    "mold_indicator": "sensor",
    "switch_as_x": "light",  # Can be various types
}


class ConfigEntrySyncer(BaseSyncer):
    """Generic syncer for any config entry-based helper type.

    This syncer can handle any helper domain, including ones without
    explicit model definitions. It stores files in helpers/<domain>/.
    """

    def __init__(
        self,
        client: HAClient,
        config: SyncConfig,
        domain: str,
        entity_type_override: str | None = None,
    ) -> None:
        super().__init__(client, config)
        self.domain = domain
        self.entity_type = entity_type_override or domain
        self._entity_registry_cache: dict[str, list[dict[str, Any]]] | None = None

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path / self.domain

    def _get_model(self) -> type[BaseEntityModel] | None:
        """Get the Pydantic model for this domain, if available."""
        return HELPER_MODELS.get(self.domain)

    def _get_entity_domain(self) -> str | None:
        """Get the expected entity domain for this helper type."""
        return ENTITY_DOMAIN_MAP.get(self.domain)

    def _expand_entity_id(self, entity_id: str) -> str:
        """Expand a suffix-only entity_id to full form.

        Args:
            entity_id: Either full entity_id (e.g., "climate.my_thermostat")
                      or just suffix (e.g., "my_thermostat")

        Returns:
            Full entity_id with domain prefix
        """
        if "." in entity_id:
            return entity_id
        entity_domain = self._get_entity_domain()
        if entity_domain:
            return f"{entity_domain}.{entity_id}"
        return entity_id

    def _validate_entity_id(self, entity_id: str) -> str | None:
        """Validate entity_id domain prefix matches expected domain.

        Args:
            entity_id: Full entity_id to validate

        Returns:
            Error message if invalid, None if valid
        """
        if "." not in entity_id:
            return None  # Will be expanded, no validation needed

        expected_domain = self._get_entity_domain()
        if not expected_domain:
            return None  # Unknown helper type, can't validate

        actual_domain = entity_id.split(".")[0]
        if actual_domain != expected_domain:
            return (
                f"Invalid entity_id domain '{actual_domain}' for {self.domain} helper. "
                f"Expected '{expected_domain}'."
            )
        return None

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize data through model if available, otherwise pass through.

        Also expands suffix-only `id` to full entity_id format.
        """
        # Expand id if present and is suffix-only
        if "id" in data and data["id"] is not None:
            data = dict(data)
            data["id"] = self._expand_entity_id(data["id"])

        model = self._get_model()
        if model:
            try:
                return model.normalize(data)
            except Exception:
                pass
        # For unknown domains, ensure proper ordering and remove None values
        result: dict[str, Any] = {}
        # Priority fields first
        for key in ["entry_id", "id", "name"]:
            if key in data and data[key] is not None:
                result[key] = data[key]
        # Then remaining fields
        for k, v in data.items():
            if k not in result and v is not None:
                result[k] = v
        return result

    async def _get_entity_registry_for_entry(
        self, entry_id: str
    ) -> list[dict[str, Any]]:
        """Get entity registry entries for a config entry (with caching)."""
        if self._entity_registry_cache is None:
            # Build cache on first access
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

    async def _get_helpers(self) -> list[dict[str, Any]]:
        """Get all helpers of this domain from Home Assistant."""
        entries = await self.client.get_config_entries(self.domain)
        result = []
        for entry in entries:
            try:
                config = await self.client.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")

                # Fetch entity_id from entity registry
                entity_entries = await self._get_entity_registry_for_entry(
                    entry["entry_id"]
                )
                if len(entity_entries) == 1:
                    # Single entity - set the id field
                    config["id"] = entity_entries[0].get("entity_id")
                elif len(entity_entries) > 1:
                    # Multiple entities (e.g., utility_meter with tariffs)
                    # Use the first one as primary id
                    config["id"] = entity_entries[0].get("entity_id")

                result.append(config)
            except Exception:
                pass
        return result

    async def _update_entity_id(
        self,
        entry_id: str,
        local_id: str,
        dry_run: bool = False,
    ) -> tuple[str, str] | None:
        """Update entity_id if it differs from local config.

        Args:
            entry_id: The config entry ID
            local_id: The desired entity_id from local config
            dry_run: If True, only print what would happen

        Returns:
            Tuple of (old_id, new_id) if renamed, None otherwise
        """
        # Expand the local_id to full form
        local_id = self._expand_entity_id(local_id)

        # Validate domain
        error = self._validate_entity_id(local_id)
        if error:
            console.print(f"    [red]Error[/red] {error}")
            return None

        # Get current entity from registry
        entity_entries = await self._get_entity_registry_for_entry(entry_id)
        if not entity_entries:
            return None

        # Check first entity (primary entity for multi-entity helpers)
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

    @logfire.instrument("Fetch remote {self.domain} helpers")
    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all helpers of this domain from Home Assistant."""
        result: dict[str, dict[str, Any]] = {}
        helpers = await self._get_helpers()
        for helper in helpers:
            entry_id = helper.get("entry_id", "")
            if entry_id:
                result[entry_id] = helper
        return result

    def get_local_entities(self) -> dict[str, dict[str, Any]]:
        """Get all local helper files for this domain.

        Returns dict keyed by entry_id. Each value includes '_filename' to track
        which file the entity came from (needed for renames when name changes).
        """
        result: dict[str, dict[str, Any]] = {}

        if not self.local_path.exists():
            return result

        for yaml_file in self.local_path.glob("*.yaml"):
            data = load_yaml(yaml_file)
            if data and isinstance(data, dict):
                entry_id = data.get("entry_id")
                if entry_id:
                    data["_filename"] = yaml_file.name
                    result[entry_id] = data

        return result

    def _get_filename(self, name: str, entry_id: str, existing_filenames: set[str]) -> str:
        """Get a unique filename for a helper, handling collisions."""
        filename = filename_from_name(name, entry_id)
        if filename not in existing_filenames:
            return filename

        # Handle collision by appending entry_id suffix
        base = filename.rsplit(".yaml", 1)[0]
        return f"{base}-{entry_id}.yaml"

    @logfire.instrument("Pull {self.domain} helpers")
    async def pull(self, sync_deletions: bool = False, dry_run: bool = False) -> SyncResult:
        """Pull helpers from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        if not dry_run:
            self.local_path.mkdir(parents=True, exist_ok=True)
        remote = await self.get_remote_entities()
        local = self.get_local_entities()

        # Track used filenames to handle collisions
        used_filenames: set[str] = set()

        for entry_id, data in remote.items():
            name = data.get("name", entry_id)
            config = dict(data)

            if "entry_id" not in config:
                config = {"entry_id": entry_id, **config}

            ordered = self._normalize(config)

            try:
                if entry_id in local:
                    # Existing entry - check if name changed (needs rename)
                    local_data = local[entry_id]
                    current_filename = local_data.get("_filename")
                    expected_filename = self._get_filename(name, entry_id, used_filenames)
                    used_filenames.add(expected_filename)

                    # Remove _filename from comparison
                    local_normalized = self._normalize(
                        {k: v for k, v in local_data.items() if k != "_filename"}
                    )

                    if current_filename and current_filename != expected_filename:
                        # Name changed - rename file
                        old_path = self.local_path / current_filename
                        new_path = self.local_path / expected_filename
                        if old_path.exists():
                            old_rel = relative_path(old_path)
                            new_rel = relative_path(new_path)
                            if dry_run:
                                console.print(f"  [cyan]Would rename[/cyan] {old_rel} -> {new_rel}")
                            else:
                                dump_yaml(ordered, new_path)
                                old_path.unlink()
                                console.print(f"  [blue]Renamed[/blue] {old_rel} -> {new_rel}")
                            result.renamed.append((entry_id, entry_id))
                    elif ordered != local_normalized:
                        file_path = self.local_path / (current_filename or expected_filename)
                        rel_path = relative_path(file_path)
                        if dry_run:
                            console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        else:
                            dump_yaml(ordered, file_path)
                            console.print(f"  [yellow]Updated[/yellow] {rel_path}")
                        result.updated.append(entry_id)
                else:
                    # New entry
                    filename = self._get_filename(name, entry_id, used_filenames)
                    used_filenames.add(filename)
                    file_path = self.local_path / filename
                    rel_path = relative_path(file_path)
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                    else:
                        dump_yaml(ordered, file_path)
                        console.print(f"  [green]Created[/green] {rel_path}")
                    result.created.append(entry_id)

            except Exception as e:
                result.errors.append((entry_id, str(e)))
                file_path = self.local_path / self._get_filename(name, entry_id, set())
                rel_path = relative_path(file_path)
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        if sync_deletions:
            for entry_id, local_data in local.items():
                if entry_id not in remote:
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
                            result.deleted.append(entry_id)
        else:
            orphaned = [eid for eid in local if eid not in remote]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} local file(s) not in HA "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    @logfire.instrument("Push {self.domain} helpers")
    async def push(
        self,
        force: bool = False,
        sync_deletions: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Push local helpers to Home Assistant."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

        # Invalidate entity registry cache for fresh data
        self._invalidate_entity_registry_cache()

        local = self.get_local_entities()
        remote = await self.get_remote_entities()

        # Get diff to determine what needs syncing (pass remote to avoid re-fetching)
        diff_items = await self.diff(remote=remote)

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

        for entry_id, data in items_to_process:
            name = data.get("name", entry_id)
            local_id = data.get("id")  # Desired entity_id from local config
            current_filename = data.get("_filename")
            # Remove _filename and id before sending to HA (id is for entity registry)
            config = {k: v for k, v in data.items() if k not in ("_filename", "id")}
            file_path = self.local_path / (current_filename or filename_from_name(name, entry_id))
            rel_path = relative_path(file_path)

            is_update = entry_id in remote

            try:
                if is_update:
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {rel_path}")
                        result.updated.append(entry_id)
                        # Check entity_id rename in dry_run mode too
                        if local_id:
                            await self._update_entity_id(entry_id, local_id, dry_run=True)
                        continue

                    await self.client.update_config_entry(entry_id, config)
                    result.updated.append(entry_id)
                    console.print(f"  [yellow]Updated[/yellow] {rel_path}")

                    # Handle entity_id renaming if id is specified
                    if local_id:
                        rename_result = await self._update_entity_id(
                            entry_id, local_id, dry_run=False
                        )
                        if rename_result:
                            result.renamed.append(rename_result)
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {rel_path}")
                        result.created.append(entry_id)
                        continue

                    new_entry_id = await self.client.create_config_entry(self.domain, config)
                    result.created.append(entry_id)
                    console.print(f"  [green]Created[/green] {rel_path}")

                    # Update local file with new entry_id (preserve id if set)
                    config["entry_id"] = new_entry_id
                    if local_id:
                        config["id"] = local_id
                    new_filename = filename_from_name(name, new_entry_id)
                    new_file_path = self.local_path / new_filename

                    dump_yaml(self._normalize(config), new_file_path)

                    # Remove old file if filename changed
                    if current_filename and current_filename != new_filename:
                        old_path = self.local_path / current_filename
                        if old_path.exists():
                            old_path.unlink()

                    # Handle entity_id renaming for new entries (wait for entity to be created)
                    if local_id:
                        await asyncio.sleep(0.5)  # Brief wait for HA to create entity
                        self._invalidate_entity_registry_cache()
                        rename_result = await self._update_entity_id(
                            new_entry_id, local_id, dry_run=False
                        )
                        if rename_result:
                            result.renamed.append(rename_result)

            except Exception as e:
                result.errors.append((entry_id, str(e)))
                console.print(f"  [red]Error[/red] {rel_path}: {e}")

        if sync_deletions:
            if force:
                # Force mode: delete all remote items not in local
                items_to_delete = [entry_id for entry_id in remote if entry_id not in local]
            else:
                # Normal mode: only items from diff
                items_to_delete = [
                    item.entity_id for item in diff_items if item.status == "deleted"
                ]

            for entry_id in items_to_delete:
                name = remote[entry_id].get("name", entry_id)
                file_path = self.local_path / filename_from_name(name, entry_id)
                rel_path = relative_path(file_path)
                try:
                    if dry_run:
                        console.print(f"  [cyan]Would delete[/cyan] {rel_path}")
                        result.deleted.append(entry_id)
                        continue

                    await self.client.delete_config_entry(entry_id)
                    result.deleted.append(entry_id)
                    console.print(f"  [red]Deleted[/red] {rel_path}")
                except Exception as e:
                    result.errors.append((entry_id, str(e)))
                    console.print(f"  [red]Error deleting[/red] {rel_path}: {e}")
        else:
            orphaned = [eid for eid in remote if eid not in local]
            if orphaned:
                console.print(
                    f"  [dim]{len(orphaned)} remote item(s) not in local files "
                    "(use --sync-deletions to remove)[/dim]"
                )

        return result

    @logfire.instrument("Diff {self.domain} helpers")
    async def diff(self, remote: dict[str, dict[str, Any]] | None = None) -> list[DiffItem]:
        """Compare local helpers with remote.

        Args:
            remote: Optional pre-fetched remote entities. If not provided, will fetch.
        """
        items: list[DiffItem] = []

        if remote is None:
            remote = await self.get_remote_entities()
        local = self.get_local_entities()

        for entry_id, local_data in local.items():
            name = local_data.get("name", entry_id)
            filename = local_data.get("_filename", filename_from_name(name, entry_id))
            file_path = self.local_path / filename
            rel_path = relative_path(file_path)

            # Remove _filename from comparison
            local_clean = {k: v for k, v in local_data.items() if k != "_filename"}

            if entry_id not in remote:
                items.append(
                    DiffItem(
                        entity_id=entry_id,
                        status="added",
                        local=local_clean,
                        file_path=rel_path,
                    )
                )
            else:
                remote_data = remote[entry_id]
                if "entry_id" not in remote_data:
                    remote_data = {"entry_id": entry_id, **remote_data}

                local_normalized = self._normalize(local_clean)
                remote_normalized = self._normalize(remote_data)

                if local_normalized != remote_normalized:
                    items.append(
                        DiffItem(
                            entity_id=entry_id,
                            status="modified",
                            local=local_normalized,
                            remote=remote_normalized,
                            file_path=rel_path,
                        )
                    )

        for entry_id in remote:
            if entry_id not in local:
                remote_data = remote[entry_id]
                name = remote_data.get("name", entry_id)
                filename = filename_from_name(name, entry_id)
                file_path = self.local_path / filename
                rel_path = relative_path(file_path)
                items.append(
                    DiffItem(
                        entity_id=entry_id,
                        status="deleted",
                        remote=remote_data,
                        file_path=rel_path,
                    )
                )

        return items


@logfire.instrument("Discover helper domains")
async def discover_helper_domains(client: HAClient) -> set[str]:
    """Discover which helper domains have entries in this HA instance.

    Returns domains that have at least one config entry and are known
    helper domains.
    """
    found_domains: set[str] = set()

    # Get all config entries
    all_entries = await client.get_config_entries()

    for entry in all_entries:
        domain = entry.get("domain", "")
        if domain in CONFIG_ENTRY_HELPER_DOMAINS:
            found_domains.add(domain)

    return found_domains


def get_config_entry_syncers(
    client: HAClient,
    config: SyncConfig,
    domains: set[str] | None = None,
) -> list[ConfigEntrySyncer]:
    """Get ConfigEntrySyncers for the specified domains.

    Args:
        client: HA client
        config: Sync config
        domains: Specific domains to sync. If None, returns syncers for
                all known helper domains.
    """
    if domains is None:
        domains = CONFIG_ENTRY_HELPER_DOMAINS

    return [ConfigEntrySyncer(client, config, domain) for domain in sorted(domains)]

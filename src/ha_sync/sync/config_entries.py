"""Generic config entry-based helper sync implementation.

This syncer handles any config entry-based helper type, including ones
that don't have explicit model definitions. It auto-discovers helpers
by domain and syncs them to/from local files.
"""

from pathlib import Path
from typing import Any

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
from ha_sync.utils import dump_yaml, filename_from_name, load_yaml

from .base import BaseSyncer, DiffItem, SyncResult

console = Console()

# Known helper domains that use config entries (not YAML-only)
# These are domains that can be created via Settings > Helpers in HA UI
CONFIG_ENTRY_HELPER_DOMAINS = {
    # Implemented with specific models
    "integration",
    "utility_meter",
    "threshold",
    "tod",
    # Additional helper domains (will use generic handling)
    "counter",
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
}

# Models for known helper types (for proper field ordering)
HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "integration": IntegrationHelper,
    "utility_meter": UtilityMeterHelper,
    "threshold": ThresholdHelper,
    "tod": TodHelper,
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

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path / self.domain

    def _get_model(self) -> type[BaseEntityModel] | None:
        """Get the Pydantic model for this domain, if available."""
        return HELPER_MODELS.get(self.domain)

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize data through model if available, otherwise pass through."""
        model = self._get_model()
        if model:
            try:
                return model.normalize(data)
            except Exception:
                pass
        # For unknown domains, just ensure entry_id is first and remove None values
        return {k: v for k, v in data.items() if v is not None}

    async def _get_helpers(self) -> list[dict[str, Any]]:
        """Get all helpers of this domain from Home Assistant."""
        entries = await self.client.get_config_entries(self.domain)
        result = []
        for entry in entries:
            try:
                config = await self.client.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                pass
        return result

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
        """Pull helpers from Home Assistant to local files."""
        result = SyncResult(created=[], updated=[], deleted=[], renamed=[], errors=[])

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
                            dump_yaml(ordered, new_path)
                            old_path.unlink()
                            result.renamed.append((entry_id, entry_id))
                            console.print(
                                f"  [blue]Renamed[/blue] {current_filename} -> {expected_filename}"
                            )
                    elif ordered != local_normalized:
                        file_path = self.local_path / (current_filename or expected_filename)
                        dump_yaml(ordered, file_path)
                        result.updated.append(entry_id)
                        console.print(f"  [yellow]Updated[/yellow] {name}")
                else:
                    # New entry
                    filename = self._get_filename(name, entry_id, used_filenames)
                    used_filenames.add(filename)
                    file_path = self.local_path / filename
                    dump_yaml(ordered, file_path)
                    result.created.append(entry_id)
                    console.print(f"  [green]Created[/green] {name}")

            except Exception as e:
                result.errors.append((entry_id, str(e)))
                console.print(f"  [red]Error[/red] {name}: {e}")

        if sync_deletions:
            for entry_id, local_data in local.items():
                if entry_id not in remote:
                    name = local_data.get("name", entry_id)
                    filename = local_data.get("_filename")
                    if filename:
                        file_path = self.local_path / filename
                        if file_path.exists():
                            file_path.unlink()
                            result.deleted.append(entry_id)
                            console.print(f"  [red]Deleted[/red] {name}")
        else:
            orphaned = [eid for eid in local if eid not in remote]
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

        for entry_id, data in local.items():
            name = data.get("name", entry_id)
            current_filename = data.get("_filename")
            # Remove _filename before sending to HA
            config = {k: v for k, v in data.items() if k != "_filename"}

            try:
                if entry_id in remote:
                    if dry_run:
                        console.print(f"  [cyan]Would update[/cyan] {name}")
                        result.updated.append(entry_id)
                        continue

                    await self.client.update_config_entry(entry_id, config)
                    result.updated.append(entry_id)
                    console.print(f"  [yellow]Updated[/yellow] {name}")
                else:
                    if dry_run:
                        console.print(f"  [cyan]Would create[/cyan] {name}")
                        result.created.append(entry_id)
                        continue

                    new_entry_id = await self.client.create_config_entry(
                        self.domain, config
                    )
                    result.created.append(entry_id)
                    console.print(f"  [green]Created[/green] {name}")

                    # Update local file with new entry_id
                    config["entry_id"] = new_entry_id
                    new_filename = filename_from_name(name, new_entry_id)
                    new_file_path = self.local_path / new_filename

                    dump_yaml(config, new_file_path)

                    # Remove old file if filename changed
                    if current_filename and current_filename != new_filename:
                        old_path = self.local_path / current_filename
                        if old_path.exists():
                            old_path.unlink()

            except Exception as e:
                result.errors.append((entry_id, str(e)))
                console.print(f"  [red]Error[/red] {name}: {e}")

        if sync_deletions:
            for entry_id in remote:
                if entry_id not in local:
                    name = remote[entry_id].get("name", entry_id)
                    try:
                        if dry_run:
                            console.print(f"  [cyan]Would delete[/cyan] {name}")
                            result.deleted.append(entry_id)
                            continue

                        await self.client.delete_config_entry(entry_id)
                        result.deleted.append(entry_id)
                        console.print(f"  [red]Deleted[/red] {name}")
                    except Exception as e:
                        result.errors.append((entry_id, str(e)))
                        console.print(f"  [red]Error deleting[/red] {name}: {e}")
        else:
            orphaned = [eid for eid in remote if eid not in local]
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

        for entry_id, local_data in local.items():
            # Remove _filename from comparison
            local_clean = {k: v for k, v in local_data.items() if k != "_filename"}

            if entry_id not in remote:
                items.append(
                    DiffItem(entity_id=entry_id, status="added", local=local_clean)
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
                        )
                    )

        for entry_id in remote:
            if entry_id not in local:
                items.append(
                    DiffItem(entity_id=entry_id, status="deleted", remote=remote[entry_id])
                )

        return items


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

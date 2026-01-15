"""Group helper sync implementation (config entry-based helpers)."""

from pathlib import Path
from typing import Any

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import GROUP_ENTITY_TYPES, GROUP_HELPER_MODELS

from .base import ConfigEntryBasedSyncer


class GroupSyncer(ConfigEntryBasedSyncer):
    """Syncer for group helpers (binary_sensors, sensors, lights, etc.).

    Group helpers are config entry-based, so they use a different API than
    traditional input_* helpers.
    """

    entity_type = "group"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path / "group"

    def _get_model_for_subtype(self, subtype: str) -> type | None:
        """Get the Pydantic model for a subtype."""
        return GROUP_HELPER_MODELS.get(subtype)

    def _get_entity_types(self) -> set[str]:
        """Get the set of valid entity types for groups."""
        return GROUP_ENTITY_TYPES

    def _get_helper_type_name(self) -> str:
        """Get the display name for this helper type."""
        return "group"

    async def _get_remote_helpers(self) -> list[dict[str, Any]]:
        """Fetch all group helpers from Home Assistant."""
        return await self.client.get_group_helpers()

    async def _create_helper(self, subtype: str, config: dict[str, Any]) -> str:
        """Create a group helper in HA. Returns the new entry_id."""
        return await self.client.create_group_helper(subtype, config)

    async def _update_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a group helper in HA."""
        await self.client.update_group_helper(entry_id, config)

    async def _delete_helper(self, entry_id: str) -> None:
        """Delete a group helper in HA."""
        await self.client.delete_group_helper(entry_id)

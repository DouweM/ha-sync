"""Template helper sync implementation (config entry-based helpers)."""

from pathlib import Path
from typing import Any

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import TEMPLATE_ENTITY_TYPES, TEMPLATE_HELPER_MODELS

from .base import ConfigEntryBasedSyncer


class TemplateSyncer(ConfigEntryBasedSyncer):
    """Syncer for template helpers (sensors, binary_sensors, switches).

    Template helpers are config entry-based, so they use a different API than
    traditional input_* helpers.
    """

    entity_type = "template"

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.helpers_path / "template"

    def _get_model_for_subtype(self, subtype: str) -> type | None:
        """Get the Pydantic model for a subtype."""
        return TEMPLATE_HELPER_MODELS.get(subtype)

    def _get_entity_types(self) -> set[str]:
        """Get the set of valid entity types for templates."""
        return TEMPLATE_ENTITY_TYPES

    def _get_helper_type_name(self) -> str:
        """Get the display name for this helper type."""
        return "template"

    async def _get_remote_helpers(self) -> list[dict[str, Any]]:
        """Fetch all template helpers from Home Assistant."""
        return await self.client.get_template_helpers()

    async def _create_helper(self, subtype: str, config: dict[str, Any]) -> str:
        """Create a template helper in HA. Returns the new entry_id."""
        return await self.client.create_template_helper(subtype, config)

    async def _update_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a template helper in HA."""
        await self.client.update_template_helper(entry_id, config)

    async def _delete_helper(self, entry_id: str) -> None:
        """Delete a template helper in HA."""
        await self.client.delete_template_helper(entry_id)

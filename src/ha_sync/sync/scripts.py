"""Script sync implementation."""

from pathlib import Path
from typing import Any

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import Script

from .base import SimpleEntitySyncer


class ScriptSyncer(SimpleEntitySyncer):
    """Syncer for Home Assistant scripts."""

    entity_type = "script"
    model_class = Script

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.scripts_path

    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all scripts from Home Assistant."""
        scripts = await self.client.get_scripts()
        result: dict[str, dict[str, Any]] = {}

        for script in scripts:
            entity_id = script["entity_id"]
            script_id = entity_id.replace("script.", "")

            config = await self.client.get_script_config(script_id)
            if config:
                result[script_id] = config

        return result

    async def save_remote(self, entity_id: str, config: dict[str, Any]) -> None:
        """Save script to Home Assistant."""
        await self.client.save_script_config(entity_id, config)

    async def delete_remote(self, entity_id: str) -> None:
        """Delete script from Home Assistant."""
        await self.client.delete_script(entity_id)

    async def reload_remote(self) -> None:
        """Reload scripts in Home Assistant."""
        await self.client.reload_scripts()

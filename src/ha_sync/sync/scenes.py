"""Scene sync implementation."""

from pathlib import Path
from typing import Any

import logfire

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.models import Scene

from .base import SimpleEntitySyncer


class SceneSyncer(SimpleEntitySyncer):
    """Syncer for Home Assistant scenes."""

    entity_type = "scene"
    model_class = Scene

    def __init__(self, client: HAClient, config: SyncConfig) -> None:
        super().__init__(client, config)

    @property
    def local_path(self) -> Path:
        return self.config.scenes_path

    @logfire.instrument("Fetch remote scenes")
    async def get_remote_entities(self) -> dict[str, dict[str, Any]]:
        """Get all scenes from Home Assistant."""
        scenes = await self.client.get_scenes()
        result: dict[str, dict[str, Any]] = {}

        for scene in scenes:
            entity_id = scene["entity_id"]
            scene_id = entity_id.replace("scene.", "")

            config = await self.client.get_scene_config(scene_id)
            if config:
                result[scene_id] = config

        return result

    async def save_remote(self, entity_id: str, config: dict[str, Any]) -> None:
        """Save scene to Home Assistant."""
        await self.client.save_scene_config(entity_id, config)

    async def delete_remote(self, entity_id: str) -> None:
        """Delete scene from Home Assistant."""
        await self.client.delete_scene(entity_id)

    async def reload_remote(self) -> None:
        """Reload scenes in Home Assistant."""
        await self.client.reload_scenes()

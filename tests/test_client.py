"""Tests for HAClient entity-registry discovery."""

import pytest

from ha_sync.client import HAClient


class TestGetScenes:
    """Tests for HAClient.get_scenes()."""

    @pytest.mark.asyncio
    async def test_returns_unique_id_not_object_id(self) -> None:
        """Scenes must be discovered by unique_id (the storage config id).

        HA's /api/config/scene/config/<id> endpoint is keyed by the scene's
        numeric storage id, exposed as unique_id in the entity registry. UI
        scenes have an object_id (slugified name) that differs from that id, so
        returning the object_id makes the config fetch 404.
        """
        client = HAClient("http://test", "token")
        client._entity_registry_cache = [
            {"entity_id": "scene.good_morning", "unique_id": "1779999288609"},
            {"entity_id": "automation.foo", "unique_id": "abc"},
        ]

        assert await client.get_scenes() == ["1779999288609"]

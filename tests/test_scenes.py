"""Tests for SceneSyncer."""

from ha_sync.sync.scenes import SceneSyncer


class TestSceneSyncerFilename:
    """Tests for SceneSyncer.get_filename()."""

    def test_uses_slugified_name_not_numeric_id(self, mock_ha_client, sync_config) -> None:
        """Scene files are named from the scene's name, not its opaque id.

        UI scenes have numeric storage ids (e.g. "1779999288609") that make
        files hard to find locally. The filename should come from the scene's
        human-readable name instead, mirroring automation alias naming.
        """
        syncer = SceneSyncer(mock_ha_client, sync_config)
        config = {"id": "1779999288609", "name": "Good morning", "entities": {}}

        assert syncer.get_filename("1779999288609", config) == "good_morning.yaml"

    def test_falls_back_to_id_when_name_missing(self, mock_ha_client, sync_config) -> None:
        """Without a name to slugify, fall back to the scene id."""
        syncer = SceneSyncer(mock_ha_client, sync_config)

        assert syncer.get_filename("1779999288609", {"id": "1779999288609"}) == "1779999288609.yaml"

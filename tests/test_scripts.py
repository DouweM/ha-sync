"""Tests for ScriptSyncer (verifies SimpleEntitySyncer base class)."""

from pathlib import Path

import pytest

from ha_sync.client import HAClient
from ha_sync.sync.base import DiffItem
from ha_sync.sync.scripts import ScriptSyncer

from .conftest import MockSyncConfig, SampleScript, create_script_file


class TestScriptSyncerDiff:
    """Tests for ScriptSyncer.diff()."""

    @pytest.mark.asyncio
    async def test_diff_detects_added_script(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects locally added scripts."""
        create_script_file(
            temp_sync_dir,
            script_id="new_script",
            alias="New Script",
        )

        # Remote has no scripts
        mock_ha_client.get_scripts.return_value = []

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 1
        assert diff_items[0].entity_id == "new_script"
        assert diff_items[0].status == "added"

    @pytest.mark.asyncio
    async def test_diff_detects_modified_script(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects modified scripts."""
        create_script_file(
            temp_sync_dir,
            script_id="existing",
            alias="Modified Script",
        )

        # Remote has the script with different content
        mock_ha_client.get_scripts.return_value = [
            SampleScript.create_state("existing", "Original Script")
        ]
        mock_ha_client.get_script_config.return_value = SampleScript.create(
            script_id="existing",
            alias="Original Script",
        )

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 1
        assert diff_items[0].entity_id == "existing"
        assert diff_items[0].status == "modified"


class TestScriptSyncerPush:
    """Tests for ScriptSyncer.push() - verifies SimpleEntitySyncer behavior."""

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_added(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses pre-computed diff_items (SimpleEntitySyncer)."""
        create_script_file(
            temp_sync_dir,
            script_id="new_script",
            alias="New Script",
        )

        # Pre-computed diff item
        diff_items = [
            DiffItem(
                entity_id="new_script",
                status="added",
                local=SampleScript.create(script_id="new_script", alias="New Script"),
            )
        ]

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote (optimization)
        mock_ha_client.get_scripts.assert_not_called()
        mock_ha_client.get_script_config.assert_not_called()

        # Should have saved the script
        mock_ha_client.save_script_config.assert_called_once()
        assert result.created == ["new_script"]

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_modified(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push handles modified items from diff_items."""
        create_script_file(
            temp_sync_dir,
            script_id="existing",
            alias="Updated Script",
        )

        diff_items = [
            DiffItem(
                entity_id="existing",
                status="modified",
                local=SampleScript.create(script_id="existing", alias="Updated Script"),
                remote=SampleScript.create(script_id="existing", alias="Original Script"),
            )
        ]

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote
        mock_ha_client.get_scripts.assert_not_called()

        # Should have saved the script
        mock_ha_client.save_script_config.assert_called_once()
        assert result.updated == ["existing"]

    @pytest.mark.asyncio
    async def test_push_skips_unrelated_diff_items(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push only processes the diff_items passed."""
        # Create TWO local scripts
        create_script_file(temp_sync_dir, script_id="script_a", alias="Script A")
        create_script_file(temp_sync_dir, script_id="script_b", alias="Script B")

        # Pre-computed diff only includes script_a
        diff_items = [
            DiffItem(
                entity_id="script_a",
                status="added",
                local=SampleScript.create(script_id="script_a", alias="Script A"),
            )
        ]

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should only create script_a, not script_b
        assert mock_ha_client.save_script_config.call_count == 1
        assert result.created == ["script_a"]

    @pytest.mark.asyncio
    async def test_push_dry_run_no_changes(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that dry_run doesn't make any API calls."""
        create_script_file(temp_sync_dir, script_id="new_script", alias="New Script")

        diff_items = [
            DiffItem(
                entity_id="new_script",
                status="added",
                local=SampleScript.create(script_id="new_script", alias="New Script"),
            )
        ]

        syncer = ScriptSyncer(mock_ha_client, sync_config)
        result = await syncer.push(dry_run=True, diff_items=diff_items)

        # Should NOT save or reload
        mock_ha_client.save_script_config.assert_not_called()
        mock_ha_client.reload_scripts.assert_not_called()

        # But should still report what would be created
        assert result.created == ["new_script"]


class TestScriptSyncerIntegration:
    """Integration tests for ScriptSyncer."""

    @pytest.mark.asyncio
    async def test_diff_then_push_consistency(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push with diff_items produces same result as shown in diff."""
        # Create local scripts
        create_script_file(temp_sync_dir, script_id="to_add", alias="To Add")
        create_script_file(temp_sync_dir, script_id="to_modify", alias="Modified Version")

        # Remote has one script (to_modify) with different content
        mock_ha_client.get_scripts.return_value = [
            SampleScript.create_state("to_modify", "Original Version")
        ]
        mock_ha_client.get_script_config.return_value = SampleScript.create(
            script_id="to_modify",
            alias="Original Version",
        )

        syncer = ScriptSyncer(mock_ha_client, sync_config)

        # Step 1: Compute diff
        diff_items = await syncer.diff()

        # Verify diff shows expected changes
        statuses = {item.entity_id: item.status for item in diff_items}
        assert statuses["to_add"] == "added"
        assert statuses["to_modify"] == "modified"

        # Reset mocks
        mock_ha_client.reset_mock()

        # Step 2: Push using the diff_items
        result = await syncer.push(diff_items=diff_items)

        # Should NOT re-fetch remote
        mock_ha_client.get_scripts.assert_not_called()

        # Should have pushed exactly the items from diff
        assert sorted(result.created) == ["to_add"]
        assert sorted(result.updated) == ["to_modify"]

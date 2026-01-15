"""Tests for AutomationSyncer."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ha_sync.client import HAClient
from ha_sync.sync.automations import AutomationSyncer
from ha_sync.sync.base import DiffItem

from .conftest import SampleAutomation, MockSyncConfig, create_automation_file


class TestAutomationSyncerDiff:
    """Tests for AutomationSyncer.diff()."""

    @pytest.mark.asyncio
    async def test_diff_detects_added_automation(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects locally added automations."""
        # Create a local automation file
        create_automation_file(
            temp_sync_dir,
            auto_id="new_automation",
            alias="New Automation",
        )

        # Remote has no automations
        mock_ha_client.get_automations.return_value = []

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 1
        assert diff_items[0].entity_id == "new_automation"
        assert diff_items[0].status == "added"

    @pytest.mark.asyncio
    async def test_diff_detects_modified_automation(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects modified automations."""
        # Create a local automation with modified content
        create_automation_file(
            temp_sync_dir,
            auto_id="existing",
            alias="Modified Alias",
        )

        # Remote has the automation with different content
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("existing", "Original Alias")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="existing",
            alias="Original Alias",
        )

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 1
        assert diff_items[0].entity_id == "existing"
        assert diff_items[0].status == "modified"

    @pytest.mark.asyncio
    async def test_diff_detects_deleted_automation(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects remotely-only automations (deletions)."""
        # No local automations
        # Remote has an automation
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("remote_only", "Remote Only")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="remote_only",
            alias="Remote Only",
        )

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 1
        assert diff_items[0].entity_id == "remote_only"
        assert diff_items[0].status == "deleted"

    @pytest.mark.asyncio
    async def test_diff_no_changes(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff returns empty list when no changes."""
        # Create matching local and remote automations
        auto_config = SampleAutomation.create(
            auto_id="unchanged",
            alias="Unchanged Automation",
        )
        create_automation_file(
            temp_sync_dir,
            auto_id="unchanged",
            alias="Unchanged Automation",
        )

        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("unchanged", "Unchanged Automation")
        ]
        mock_ha_client.get_automation_config.return_value = auto_config

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        assert len(diff_items) == 0


class TestAutomationSyncerPush:
    """Tests for AutomationSyncer.push()."""

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_added(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses pre-computed diff_items for added automations."""
        # Create local automation
        create_automation_file(
            temp_sync_dir,
            auto_id="new_auto",
            alias="New Auto",
        )

        # Pre-computed diff item
        diff_items = [
            DiffItem(
                entity_id="new_auto",
                status="added",
                local=SampleAutomation.create(auto_id="new_auto", alias="New Auto"),
            )
        ]

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote (optimization)
        mock_ha_client.get_automations.assert_not_called()
        mock_ha_client.get_automation_config.assert_not_called()

        # Should have saved the automation
        mock_ha_client.save_automation_config.assert_called_once()
        assert result.created == ["new_auto"]

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_modified(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses pre-computed diff_items for modified automations."""
        # Create local automation
        create_automation_file(
            temp_sync_dir,
            auto_id="existing_auto",
            alias="Updated Auto",
        )

        # Pre-computed diff item (modified)
        diff_items = [
            DiffItem(
                entity_id="existing_auto",
                status="modified",
                local=SampleAutomation.create(auto_id="existing_auto", alias="Updated Auto"),
                remote=SampleAutomation.create(auto_id="existing_auto", alias="Original Auto"),
            )
        ]

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote
        mock_ha_client.get_automations.assert_not_called()

        # Should have saved the automation
        mock_ha_client.save_automation_config.assert_called_once()
        assert result.updated == ["existing_auto"]

    @pytest.mark.asyncio
    async def test_push_skips_unrelated_diff_items(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push only processes the diff_items passed."""
        # Create TWO local automations
        create_automation_file(
            temp_sync_dir,
            auto_id="auto_a",
            alias="Auto A",
        )
        create_automation_file(
            temp_sync_dir,
            auto_id="auto_b",
            alias="Auto B",
        )

        # Pre-computed diff only includes auto_a
        diff_items = [
            DiffItem(
                entity_id="auto_a",
                status="added",
                local=SampleAutomation.create(auto_id="auto_a", alias="Auto A"),
            )
        ]

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should only create auto_a, not auto_b
        assert mock_ha_client.save_automation_config.call_count == 1
        call_args = mock_ha_client.save_automation_config.call_args
        assert call_args[0][0] == "auto_a"

        assert result.created == ["auto_a"]

    @pytest.mark.asyncio
    async def test_push_computes_diff_when_none_provided(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push computes diff when no diff_items provided."""
        # Create local automation
        create_automation_file(
            temp_sync_dir,
            auto_id="new_auto",
            alias="New Auto",
        )

        # Remote is empty
        mock_ha_client.get_automations.return_value = []

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=None)

        # Should have fetched remote to compute diff
        mock_ha_client.get_automations.assert_called_once()

        # Should have saved the automation
        mock_ha_client.save_automation_config.assert_called_once()
        assert result.created == ["new_auto"]

    @pytest.mark.asyncio
    async def test_push_force_mode_ignores_diff_items(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that force mode rebuilds diff_items from scratch."""
        # Create local automations
        create_automation_file(
            temp_sync_dir,
            auto_id="auto_a",
            alias="Auto A",
        )
        create_automation_file(
            temp_sync_dir,
            auto_id="auto_b",
            alias="Auto B",
        )

        # Remote only knows about auto_a
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("auto_a", "Auto A")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="auto_a",
            alias="Auto A",
        )

        # Pass diff_items that only include auto_a, but use force=True
        diff_items = [
            DiffItem(
                entity_id="auto_a",
                status="modified",
                local=SampleAutomation.create(auto_id="auto_a", alias="Auto A"),
            )
        ]

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(force=True, diff_items=diff_items)

        # Should have fetched remote (force mode rebuilds everything)
        mock_ha_client.get_automations.assert_called_once()

        # Should have saved BOTH automations (force pushes all)
        assert mock_ha_client.save_automation_config.call_count == 2

    @pytest.mark.asyncio
    async def test_push_dry_run_no_changes(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that dry_run doesn't make any API calls."""
        create_automation_file(
            temp_sync_dir,
            auto_id="new_auto",
            alias="New Auto",
        )

        diff_items = [
            DiffItem(
                entity_id="new_auto",
                status="added",
                local=SampleAutomation.create(auto_id="new_auto", alias="New Auto"),
            )
        ]

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.push(dry_run=True, diff_items=diff_items)

        # Should NOT save or reload
        mock_ha_client.save_automation_config.assert_not_called()
        mock_ha_client.reload_automations.assert_not_called()

        # But should still report what would be created
        assert result.created == ["new_auto"]


class TestAutomationSyncerPull:
    """Tests for AutomationSyncer.pull()."""

    @pytest.mark.asyncio
    async def test_pull_creates_new_files(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that pull creates files for remote automations."""
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("remote_auto", "Remote Auto")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="remote_auto",
            alias="Remote Auto",
        )

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.pull()

        # Should have created the file
        assert result.created == ["remote_auto"]

        # Verify file exists (filename is generated from alias using slugify)
        auto_file = sync_config.automations_path / "remote_auto.yaml"
        assert auto_file.exists()

    @pytest.mark.asyncio
    async def test_pull_dry_run_no_files_created(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that pull dry_run doesn't create files."""
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("remote_auto", "Remote Auto")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="remote_auto",
            alias="Remote Auto",
        )

        syncer = AutomationSyncer(mock_ha_client, sync_config)
        result = await syncer.pull(dry_run=True)

        # Should report what would be created
        assert result.created == ["remote_auto"]

        # But no file should exist
        auto_files = list(sync_config.automations_path.glob("*.yaml"))
        assert len(auto_files) == 0


class TestAutomationSyncerDiffItemsIntegration:
    """Integration tests verifying diff/push consistency."""

    @pytest.mark.asyncio
    async def test_diff_then_push_consistency(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push with diff_items produces same result as shown in diff.

        This is the core safety test - ensures what user sees is what gets applied.
        """
        # Create local automations
        create_automation_file(
            temp_sync_dir,
            auto_id="to_add",
            alias="To Add",
        )
        create_automation_file(
            temp_sync_dir,
            auto_id="to_modify",
            alias="Modified Version",
        )

        # Remote has one automation (to_modify) with different content
        mock_ha_client.get_automations.return_value = [
            SampleAutomation.create_state("to_modify", "Original Version")
        ]
        mock_ha_client.get_automation_config.return_value = SampleAutomation.create(
            auto_id="to_modify",
            alias="Original Version",
        )

        syncer = AutomationSyncer(mock_ha_client, sync_config)

        # Step 1: Compute diff (this is what CLI shows to user)
        diff_items = await syncer.diff()

        # Verify diff shows expected changes
        assert len(diff_items) == 2
        statuses = {item.entity_id: item.status for item in diff_items}
        assert statuses["to_add"] == "added"
        assert statuses["to_modify"] == "modified"

        # Reset mocks to track push calls
        mock_ha_client.reset_mock()

        # Step 2: Push using the diff_items (like CLI does after user confirms)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT re-fetch remote (uses pre-computed diff)
        mock_ha_client.get_automations.assert_not_called()

        # Should have pushed exactly the items from diff
        assert sorted(result.created) == ["to_add"]
        assert sorted(result.updated) == ["to_modify"]
        assert mock_ha_client.save_automation_config.call_count == 2

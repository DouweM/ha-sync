"""Tests for DashboardSyncer."""

from pathlib import Path

import pytest

from ha_sync.client import HAClient
from ha_sync.sync.base import DiffItem
from ha_sync.sync.dashboards import DashboardSyncer

from .conftest import MockSyncConfig, SampleDashboard, create_dashboard_files


class TestDashboardSyncerDiff:
    """Tests for DashboardSyncer.diff()."""

    @pytest.mark.asyncio
    async def test_diff_detects_added_dashboard(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects locally added dashboards."""
        # Create a local dashboard
        create_dashboard_files(
            temp_sync_dir,
            dir_name="new_dash",
            title="New Dashboard",
            url_path="dashboard-new_dash",
        )

        # Remote has only the default lovelace dashboard
        mock_ha_client.get_dashboards.return_value = []
        mock_ha_client.get_dashboard_config.return_value = {
            "title": "Home",
            "views": [{"path": "home", "title": "Home", "cards": []}],
        }

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        # Should find the new dashboard
        added_items = [item for item in diff_items if item.status == "added"]
        assert len(added_items) == 1
        assert added_items[0].entity_id == "new_dash"

    @pytest.mark.asyncio
    async def test_diff_detects_modified_dashboard(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects modified dashboards."""
        # Create local dashboard with modified content
        create_dashboard_files(
            temp_sync_dir,
            dir_name="test",
            title="Test Dashboard",
            url_path="dashboard-test",
            views=[
                SampleDashboard.create_view(
                    path="home", title="Modified Home", position=1
                )
            ],
        )

        # Remote has the dashboard with different content
        mock_ha_client.get_dashboards.return_value = [
            {
                "url_path": "dashboard-test",
                "title": "Test Dashboard",
            }
        ]
        mock_ha_client.get_dashboard_config.side_effect = [
            # Default lovelace
            {"views": [{"path": "home", "title": "Home", "cards": []}]},
            # dashboard-test
            {"views": [{"path": "home", "title": "Original Home", "cards": []}]},
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        modified_items = [item for item in diff_items if item.status == "modified"]
        assert len(modified_items) == 1
        assert modified_items[0].entity_id == "test"

    @pytest.mark.asyncio
    async def test_diff_detects_deleted_dashboard(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff detects remotely-only dashboards (deletions)."""
        # No local dashboards (except the default created by temp_sync_dir)

        # Remote has a dashboard
        mock_ha_client.get_dashboards.return_value = [
            {
                "url_path": "dashboard-remote_only",
                "title": "Remote Only Dashboard",
            }
        ]
        mock_ha_client.get_dashboard_config.side_effect = [
            # Default lovelace
            {"views": [{"path": "home", "title": "Home", "cards": []}]},
            # dashboard-remote_only
            {"views": [{"path": "overview", "title": "Overview", "cards": []}]},
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        diff_items = await syncer.diff()

        # Should detect both lovelace and remote_only as deleted (not in local)
        deleted_items = [item for item in diff_items if item.status == "deleted"]
        entity_ids = {item.entity_id for item in deleted_items}
        assert "remote_only" in entity_ids


class TestDashboardSyncerPush:
    """Tests for DashboardSyncer.push()."""

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_added(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses pre-computed diff_items for added dashboards."""
        # Create local dashboard
        create_dashboard_files(
            temp_sync_dir,
            dir_name="new_dash",
            title="New Dashboard",
            url_path="dashboard-new_dash",
        )

        # Pre-computed diff item
        diff_items = [
            DiffItem(
                entity_id="new_dash",
                status="added",
                local=SampleDashboard.create_config(),
            )
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote (optimization for add-only operations)
        mock_ha_client.get_dashboards.assert_not_called()

        # Should have created the dashboard
        mock_ha_client.create_dashboard.assert_called_once()
        assert result.created == ["new_dash"]

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_modified(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses pre-computed diff_items for modified dashboards."""
        # Create local dashboard
        create_dashboard_files(
            temp_sync_dir,
            dir_name="test",
            title="Updated Dashboard",
            url_path="dashboard-test",
        )

        # Pre-computed diff item (modified)
        diff_items = [
            DiffItem(
                entity_id="test",
                status="modified",
                local=SampleDashboard.create_config(title="Updated"),
                remote=SampleDashboard.create_config(title="Original"),
            )
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should NOT have fetched remote
        mock_ha_client.get_dashboards.assert_not_called()

        # Should have saved the dashboard config
        mock_ha_client.save_dashboard_config.assert_called_once()
        assert result.updated == ["test"]

    @pytest.mark.asyncio
    async def test_push_skips_unrelated_diff_items(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push only processes the diff_items passed."""
        # Create TWO local dashboards
        create_dashboard_files(
            temp_sync_dir,
            dir_name="dash_a",
            title="Dashboard A",
            url_path="dashboard-dash_a",
        )
        create_dashboard_files(
            temp_sync_dir,
            dir_name="dash_b",
            title="Dashboard B",
            url_path="dashboard-dash_b",
        )

        # Pre-computed diff only includes dash_a
        diff_items = [
            DiffItem(
                entity_id="dash_a",
                status="added",
                local=SampleDashboard.create_config(),
            )
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=diff_items)

        # Should only create dash_a, not dash_b
        assert mock_ha_client.create_dashboard.call_count == 1
        assert result.created == ["dash_a"]

    @pytest.mark.asyncio
    async def test_push_computes_diff_when_none_provided(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push computes diff when no diff_items provided."""
        # Create local dashboard
        create_dashboard_files(
            temp_sync_dir,
            dir_name="new_dash",
            title="New Dashboard",
            url_path="dashboard-new_dash",
        )

        # Remote has only default lovelace
        mock_ha_client.get_dashboards.return_value = []
        mock_ha_client.get_dashboard_config.return_value = {
            "views": [{"path": "home", "title": "Home", "cards": []}]
        }

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.push(diff_items=None)

        # Should have fetched remote to compute diff
        mock_ha_client.get_dashboards.assert_called_once()

        # Should have created the dashboard
        mock_ha_client.create_dashboard.assert_called_once()
        assert "new_dash" in result.created

    @pytest.mark.asyncio
    async def test_push_dry_run_no_changes(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that dry_run doesn't make any API calls."""
        create_dashboard_files(
            temp_sync_dir,
            dir_name="new_dash",
            title="New Dashboard",
            url_path="dashboard-new_dash",
        )

        diff_items = [
            DiffItem(
                entity_id="new_dash",
                status="added",
                local=SampleDashboard.create_config(),
            )
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.push(dry_run=True, diff_items=diff_items)

        # Should NOT create or save
        mock_ha_client.create_dashboard.assert_not_called()
        mock_ha_client.save_dashboard_config.assert_not_called()

        # But should still report what would be created
        assert result.created == ["new_dash"]


class TestDashboardSyncerPull:
    """Tests for DashboardSyncer.pull()."""

    @pytest.mark.asyncio
    async def test_pull_creates_new_directories(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that pull creates directories for remote dashboards."""
        mock_ha_client.get_dashboards.return_value = [
            {
                "url_path": "dashboard-new",
                "title": "New Dashboard",
            }
        ]
        mock_ha_client.get_dashboard_config.side_effect = [
            # Default lovelace
            {"views": [{"path": "home", "title": "Home", "cards": []}]},
            # dashboard-new
            {"views": [{"path": "overview", "title": "Overview", "cards": []}]},
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.pull()

        # Should have created both dashboards
        assert "lovelace" in result.created
        assert "new" in result.created

        # Verify directories exist
        assert (sync_config.dashboards_path / "lovelace").exists()
        assert (sync_config.dashboards_path / "new").exists()

    @pytest.mark.asyncio
    async def test_pull_dry_run_no_directories_created(
        self,
        mock_ha_client: HAClient,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that pull dry_run doesn't create directories."""
        mock_ha_client.get_dashboards.return_value = []
        mock_ha_client.get_dashboard_config.return_value = {
            "views": [{"path": "home", "title": "Home", "cards": []}]
        }

        syncer = DashboardSyncer(mock_ha_client, sync_config)
        result = await syncer.pull(dry_run=True)

        # Should report what would be created
        assert "lovelace" in result.created

        # But no directory should exist
        assert not (sync_config.dashboards_path / "lovelace").exists()


class TestDashboardSyncerDiffItemsIntegration:
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
        # Create local dashboards
        create_dashboard_files(
            temp_sync_dir,
            dir_name="to_add",
            title="To Add Dashboard",
            url_path="dashboard-to_add",
        )
        create_dashboard_files(
            temp_sync_dir,
            dir_name="to_modify",
            title="Modified Dashboard",
            url_path="dashboard-to_modify",
            views=[SampleDashboard.create_view(path="modified", title="Modified View", position=1)],
        )

        # Remote has one dashboard (to_modify) with different content
        mock_ha_client.get_dashboards.return_value = [
            {
                "url_path": "dashboard-to_modify",
                "title": "Original Dashboard",
            }
        ]
        mock_ha_client.get_dashboard_config.side_effect = [
            # Default lovelace
            {"views": [{"path": "home", "title": "Home", "cards": []}]},
            # dashboard-to_modify
            {"views": [{"path": "original", "title": "Original View", "cards": []}]},
        ]

        syncer = DashboardSyncer(mock_ha_client, sync_config)

        # Step 1: Compute diff (this is what CLI shows to user)
        diff_items = await syncer.diff()

        # Filter to get relevant items
        statuses = {item.entity_id: item.status for item in diff_items}
        assert statuses.get("to_add") == "added"
        assert statuses.get("to_modify") == "modified"

        # Reset mocks to track push calls
        mock_ha_client.reset_mock()

        # Filter diff_items to just what we want to push (excluding lovelace deletion)
        push_items = [item for item in diff_items if item.entity_id in ("to_add", "to_modify")]

        # Step 2: Push using the diff_items (like CLI does after user confirms)
        result = await syncer.push(diff_items=push_items)

        # Should NOT re-fetch remote when only adding/modifying (no renames/deletions)
        mock_ha_client.get_dashboards.assert_not_called()

        # Should have pushed exactly the items from diff
        assert "to_add" in result.created
        assert "to_modify" in result.updated

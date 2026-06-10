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
            views=[SampleDashboard.create_view(path="home", title="Modified Home", position=1)],
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


def _fp_tail(file_path: str | None) -> str | None:
    """Return the ``dashboards/...`` tail of a (possibly absolute) file path.

    ``relative_path`` produces absolute paths in tests because the temp sync
    dir isn't under cwd; this normalizes for stable assertions.
    """
    if file_path is None:
        return None
    idx = file_path.find("dashboards/")
    return file_path[idx:] if idx != -1 else file_path


def _entity(views: list[dict] | None = None, **meta: object) -> dict:
    """Build a dashboard entity dict ({"meta", "config"}) for view-diff tests."""
    base_meta = {
        "title": "Test",
        "icon": "mdi:home",
        "show_in_sidebar": True,
        "require_admin": False,
        "url_path": "dashboard-test",
    }
    base_meta.update(meta)
    config: dict = {"views": views if views is not None else []}
    return {"meta": base_meta, "config": config}


def _view(path: str, title: str | None = None, cards: list | None = None) -> dict:
    return {"path": path, "title": title or path.title(), "cards": cards or []}


class TestComputeViewThreeWay:
    """Tests for per-view three-way dashboard diffing (auto-merge)."""

    def _syncer(self, mock_ha_client: HAClient, sync_config: MockSyncConfig) -> DashboardSyncer:
        return DashboardSyncer(mock_ha_client, sync_config)

    def test_no_changes(self, mock_ha_client: HAClient, sync_config: MockSyncConfig) -> None:
        """Identical base/local/remote -> nothing to do, round trip is a no-op."""
        syncer = self._syncer(mock_ha_client, sync_config)
        entity = _entity([_view("a"), _view("b")])
        diff = syncer.compute_view_three_way({"test": entity}, {"test": entity}, {"test": entity})
        assert not diff.local_only
        assert not diff.remote_only
        assert not diff.conflicts
        assert not diff.merged_remote

    def test_disjoint_edits_auto_merge(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Local edits view A, remote edits view B -> no conflict, both preserved."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a"), _view("b")])}
        local = {"test": _entity([_view("a", cards=[{"type": "local"}]), _view("b")])}
        remote = {"test": _entity([_view("a"), _view("b", cards=[{"type": "remote"}])])}

        diff = syncer.compute_view_three_way(base, local, remote)

        # No conflict; view A is local-only, view B is remote-only.
        assert not diff.conflicts
        assert {_fp_tail(i.file_path) for i in diff.local_only} == {"dashboards/test/a.yaml"}
        assert {_fp_tail(i.file_path) for i in diff.remote_only} == {"dashboards/test/b.yaml"}

        # Merged config keeps local A edit AND pulls remote B edit.
        merged_views = diff.merged_remote["test"]["config"]["views"]
        by_path = {v["path"]: v for v in merged_views}
        assert by_path["a"]["cards"] == [{"type": "local"}]
        assert by_path["b"]["cards"] == [{"type": "remote"}]

    def test_same_view_diverges_is_conflict(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Same view changed differently on both sides -> conflict on that file."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")])}
        local = {"test": _entity([_view("a", cards=[{"type": "local"}])])}
        remote = {"test": _entity([_view("a", cards=[{"type": "remote"}])])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert len(diff.conflicts) == 1
        conflict = diff.conflicts[0]
        assert conflict.entity_id == "test"
        assert _fp_tail(conflict.file_path) == "dashboards/test/a.yaml"
        assert conflict.has_conflict
        # Not auto-pulled while unresolved.
        assert not diff.merged_remote

    def test_same_view_changed_same_way_no_conflict(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Both sides made the identical view change -> no conflict, no action."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")])}
        changed = {"test": _entity([_view("a", cards=[{"type": "same"}])])}

        diff = syncer.compute_view_three_way(base, changed, changed)

        assert not diff.conflicts
        assert not diff.local_only
        assert not diff.remote_only

    def test_meta_only_change_remote_merges(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Remote-only meta change (icon) merges via _meta.yaml, views untouched."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")], icon="mdi:home")}
        local = {"test": _entity([_view("a")], icon="mdi:home")}
        remote = {"test": _entity([_view("a")], icon="mdi:star")}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        assert not diff.local_only
        assert [_fp_tail(i.file_path) for i in diff.remote_only] == ["dashboards/test/_meta.yaml"]
        assert diff.merged_remote["test"]["meta"]["icon"] == "mdi:star"

    def test_meta_diverges_is_conflict(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Meta changed differently on both sides -> conflict on _meta.yaml."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")], title="Base")}
        local = {"test": _entity([_view("a")], title="Local")}
        remote = {"test": _entity([_view("a")], title="Remote")}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert len(diff.conflicts) == 1
        assert _fp_tail(diff.conflicts[0].file_path) == "dashboards/test/_meta.yaml"

    def test_remote_added_view_merges(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """A view added only remotely is pulled into the merged config."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")])}
        local = {"test": _entity([_view("a")])}
        remote = {"test": _entity([_view("a"), _view("b")])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        assert [_fp_tail(i.file_path) for i in diff.remote_only] == ["dashboards/test/b.yaml"]
        merged_paths = [v["path"] for v in diff.merged_remote["test"]["config"]["views"]]
        assert merged_paths == ["a", "b"]

    def test_remote_deleted_view_drops_in_merge(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """A view deleted only remotely is dropped from the merged config."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a"), _view("b")])}
        local = {"test": _entity([_view("a"), _view("b")])}
        remote = {"test": _entity([_view("a")])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        remote_item = diff.remote_only[0]
        assert remote_item.remote_status == "deleted"
        merged_paths = [v["path"] for v in diff.merged_remote["test"]["config"]["views"]]
        assert merged_paths == ["a"]

    def test_local_added_view_is_local_only(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """A view added only locally is reported local-only and not pulled."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")])}
        local = {"test": _entity([_view("a"), _view("b")])}
        remote = {"test": _entity([_view("a")])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        assert not diff.remote_only
        assert [_fp_tail(i.file_path) for i in diff.local_only] == ["dashboards/test/b.yaml"]
        # No remote change -> nothing to pull/merge.
        assert "test" not in diff.merged_remote

    def test_disjoint_plus_merge_keeps_local_when_both_change(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Mixed: local edits A, remote edits B -> merged has both, pull writes both."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a"), _view("b"), _view("c")])}
        local = {"test": _entity([_view("a", cards=[{"x": 1}]), _view("b"), _view("c")])}
        remote = {"test": _entity([_view("a"), _view("b", cards=[{"y": 2}]), _view("c")])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        merged = {v["path"]: v for v in diff.merged_remote["test"]["config"]["views"]}
        assert merged["a"]["cards"] == [{"x": 1}]
        assert merged["b"]["cards"] == [{"y": 2}]
        assert merged["c"]["cards"] == []

    def test_theirs_resolution_takes_remote_for_conflict(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """--theirs resolution folds the remote view into the merged config."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a"), _view("b")])}
        local = {"test": _entity([_view("a", cards=[{"type": "local"}]), _view("b")])}
        remote = {"test": _entity([_view("a", cards=[{"type": "remote"}]), _view("b")])}

        diff = syncer.compute_view_three_way(base, local, remote, conflict_resolution="theirs")

        merged = {v["path"]: v for v in diff.merged_remote["test"]["config"]["views"]}
        assert merged["a"]["cards"] == [{"type": "remote"}]

    def test_ours_resolution_keeps_local_for_conflict(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """--ours resolution keeps the local view in the merged config."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base = {"test": _entity([_view("a")])}
        local = {"test": _entity([_view("a", cards=[{"type": "local"}])])}
        remote = {"test": _entity([_view("a", cards=[{"type": "remote"}])])}

        diff = syncer.compute_view_three_way(base, local, remote, conflict_resolution="ours")

        merged = {v["path"]: v for v in diff.merged_remote["test"]["config"]["views"]}
        assert merged["a"]["cards"] == [{"type": "local"}]

    def test_view_without_path_falls_back_to_title(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Views lacking a path are keyed by title slug and don't crash."""
        syncer = self._syncer(mock_ha_client, sync_config)
        v_base = {"title": "No Path", "cards": []}
        v_local = {"title": "No Path", "cards": [{"x": 1}]}
        base = {"test": _entity([v_base])}
        local = {"test": _entity([v_local])}
        remote = {"test": _entity([v_base])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert not diff.conflicts
        assert [_fp_tail(i.file_path) for i in diff.local_only] == ["dashboards/test/no_path.yaml"]

    def test_strategy_dashboard_meta_only(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Strategy-based dashboards (no views) diff via the meta unit only."""
        syncer = self._syncer(mock_ha_client, sync_config)
        base_cfg = {"meta": {"title": "S"}, "config": {"strategy": {"type": "original-states"}}}
        local_cfg = {"meta": {"title": "S"}, "config": {"strategy": {"type": "original-states"}}}
        remote_cfg = {"meta": {"title": "S"}, "config": {"strategy": {"type": "areas"}}}

        diff = syncer.compute_view_three_way({"s": base_cfg}, {"s": local_cfg}, {"s": remote_cfg})

        assert not diff.conflicts
        assert [_fp_tail(i.file_path) for i in diff.remote_only] == ["dashboards/s/_meta.yaml"]
        # Strategy dashboards keep no "views" key in the merged config.
        assert "views" not in diff.merged_remote["s"]["config"]


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


class TestViewFilePath:
    """Diff items must report the real on-disk view file path."""

    def test_prefers_on_disk_prefixed_file(
        self, mock_ha_client: HAClient, sync_config: MockSyncConfig
    ) -> None:
        """Saved view files carry a numeric prefix (e.g. 00_a.yaml). If the
        diff item reports a.yaml instead, path filters like
        `diff dashboards/test/00_a.yaml` silently drop the item and the diff
        lies with "No differences".
        """
        syncer = DashboardSyncer(mock_ha_client, sync_config)
        view_dir = syncer.local_path / "test"
        view_dir.mkdir(parents=True, exist_ok=True)
        (view_dir / "00_a.yaml").write_text("position: 1\npath: a\n")

        base = {"test": _entity([_view("a")])}
        local = {"test": _entity([_view("a", cards=[{"type": "local"}])])}
        remote = {"test": _entity([_view("a")])}

        diff = syncer.compute_view_three_way(base, local, remote)

        assert {_fp_tail(i.file_path) for i in diff.local_only} == {"dashboards/test/00_a.yaml"}

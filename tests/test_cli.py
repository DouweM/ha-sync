"""Tests for CLI commands."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_sync.cli import _check_file_staleness, _record_file_states, app
from ha_sync.sync.base import DiffItem

from .conftest import MockSyncConfig, SampleAutomation, create_automation_file

runner = CliRunner()


class TestPushCommand:
    """Tests for the push CLI command."""

    def test_push_passes_diff_items_to_syncer(
        self,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push command passes pre-computed diff_items to syncer.push().

        This is the key integration test - verifies the CLI doesn't recompute diff.
        """
        # Create a local automation
        create_automation_file(
            temp_sync_dir,
            auto_id="test_auto",
            alias="Test Auto",
        )

        # Track what diff_items are passed to push()
        push_calls: list[dict[str, Any]] = []

        async def mock_push(
            force: bool = False,
            sync_deletions: bool = False,
            dry_run: bool = False,
            diff_items: list[DiffItem] | None = None,
        ):
            push_calls.append({
                "force": force,
                "sync_deletions": sync_deletions,
                "dry_run": dry_run,
                "diff_items": diff_items,
            })
            from ha_sync.sync.base import SyncResult
            return SyncResult(created=["test_auto"], updated=[], deleted=[], renamed=[], errors=[])

        async def mock_diff(remote=None):
            return [
                DiffItem(
                    entity_id="test_auto",
                    status="added",
                    entity_type="automation",
                    local=SampleAutomation.create(auto_id="test_auto", alias="Test Auto"),
                    file_path="automations/test_auto.yaml",
                )
            ]

        # Mock the syncer and client
        mock_syncer = MagicMock()
        mock_syncer.entity_type = "automation"
        mock_syncer.push = mock_push
        mock_syncer.diff = mock_diff

        mock_client = MagicMock()

        with patch("ha_sync.cli.get_config") as mock_get_config, \
             patch("ha_sync.cli.HAClient") as mock_ha_client_class, \
             patch("ha_sync.cli.get_syncers_for_paths") as mock_get_syncers:
            mock_get_config.return_value = sync_config
            mock_ha_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ha_client_class.return_value.__aexit__ = AsyncMock()
            mock_get_syncers.return_value = [(mock_syncer, None)]

            # Run push with --yes to skip confirmation
            runner.invoke(app, ["push", "--yes"])

            # Verify push was called with diff_items (not None)
            assert len(push_calls) == 1
            call = push_calls[0]
            assert call["diff_items"] is not None, "diff_items should be passed to push()"
            assert len(call["diff_items"]) == 1
            assert call["diff_items"][0].entity_id == "test_auto"

    def test_push_dry_run_does_not_modify(
        self,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push --dry-run doesn't actually push."""
        create_automation_file(
            temp_sync_dir,
            auto_id="test_auto",
            alias="Test Auto",
        )

        push_calls: list[dict[str, Any]] = []

        async def mock_push(
            force: bool = False,
            sync_deletions: bool = False,
            dry_run: bool = False,
            diff_items: list[DiffItem] | None = None,
        ):
            push_calls.append({"dry_run": dry_run})
            from ha_sync.sync.base import SyncResult
            return SyncResult(created=["test_auto"], updated=[], deleted=[], renamed=[], errors=[])

        mock_syncer = MagicMock()
        mock_syncer.entity_type = "automation"
        mock_syncer.push = mock_push

        with patch("ha_sync.cli.get_config") as mock_get_config, \
             patch("ha_sync.cli.HAClient") as mock_ha_client_class, \
             patch("ha_sync.cli.get_syncers_for_paths") as mock_get_syncers:
            mock_get_config.return_value = sync_config
            mock_ha_client_class.return_value.__aenter__ = AsyncMock()
            mock_ha_client_class.return_value.__aexit__ = AsyncMock()
            mock_get_syncers.return_value = [(mock_syncer, None)]

            runner.invoke(app, ["push", "--dry-run"])

            # dry_run mode should pass dry_run=True to syncer
            assert len(push_calls) == 1
            assert push_calls[0]["dry_run"] is True


class TestDiffCommand:
    """Tests for the diff CLI command."""

    def test_diff_shows_changes(
        self,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that diff command displays differences."""
        create_automation_file(
            temp_sync_dir,
            auto_id="test_auto",
            alias="Test Auto",
        )

        async def mock_diff(remote=None):
            return [
                DiffItem(
                    entity_id="test_auto",
                    status="added",
                    entity_type="automation",
                    local=SampleAutomation.create(auto_id="test_auto", alias="Test Auto"),
                    file_path="automations/test_auto.yaml",
                )
            ]

        mock_syncer = MagicMock()
        mock_syncer.entity_type = "automation"
        mock_syncer.diff = mock_diff

        with patch("ha_sync.cli.get_config") as mock_get_config, \
             patch("ha_sync.cli.HAClient") as mock_ha_client_class, \
             patch("ha_sync.cli.get_syncers_for_paths") as mock_get_syncers:
            mock_get_config.return_value = sync_config
            mock_ha_client_class.return_value.__aenter__ = AsyncMock()
            mock_ha_client_class.return_value.__aexit__ = AsyncMock()
            mock_get_syncers.return_value = [(mock_syncer, None)]

            result = runner.invoke(app, ["diff"])

            # Should show the added file
            assert result.exit_code == 0
            assert "test_auto" in result.output or "automations" in result.output


class TestInitCommand:
    """Tests for the init CLI command."""

    def test_init_creates_directories(
        self,
        temp_sync_dir: Path,
    ) -> None:
        """Test that init creates required directories."""
        import os

        # Change to temp directory
        original_cwd = os.getcwd()
        os.chdir(temp_sync_dir)

        try:
            with patch("ha_sync.cli.get_config") as mock_get_config:
                mock_config = MockSyncConfig(
                    base_path=temp_sync_dir,
                    ha_url="http://test:8123",
                    ha_token="test_token",
                )
                mock_get_config.return_value = mock_config

                runner.invoke(app, ["init"])

                # Check directories exist
                assert (temp_sync_dir / "automations").exists()
                assert (temp_sync_dir / "scripts").exists()
                assert (temp_sync_dir / "scenes").exists()
                assert (temp_sync_dir / "dashboards").exists()
        finally:
            os.chdir(original_cwd)


class TestVersionCommand:
    """Tests for the version CLI command."""

    def test_version_shows_version(self) -> None:
        """Test that version command shows version."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "ha-sync version" in result.output


class TestDiffItemsConsistency:
    """Tests verifying diff_items flow through CLI correctly."""

    def test_push_uses_same_diff_items_from_preview(
        self,
        temp_sync_dir: Path,
        sync_config: MockSyncConfig,
    ) -> None:
        """Test that push uses the exact diff_items computed for preview.

        This is the critical safety test for the CLI layer:
        1. _get_push_diff() computes diff_items for preview
        2. User confirms
        3. _push() is called with those SAME diff_items
        4. Syncer.push() uses them directly without re-fetching

        If any of these steps recomputes the diff, the actual changes
        could differ from what was shown to the user.
        """
        create_automation_file(
            temp_sync_dir,
            auto_id="auto_to_push",
            alias="Auto To Push",
        )

        # Track IDs that pass through each stage
        diff_computed_ids: list[str] = []
        push_received_ids: list[str] = []

        async def mock_diff(remote=None):
            items = [
                DiffItem(
                    entity_id="auto_to_push",
                    status="added",
                    entity_type="automation",
                    local=SampleAutomation.create(auto_id="auto_to_push", alias="Auto To Push"),
                    file_path="automations/auto_to_push.yaml",
                )
            ]
            diff_computed_ids.extend(item.entity_id for item in items)
            return items

        async def mock_push(
            force: bool = False,
            sync_deletions: bool = False,
            dry_run: bool = False,
            diff_items: list[DiffItem] | None = None,
        ):
            if diff_items:
                push_received_ids.extend(item.entity_id for item in diff_items)
            from ha_sync.sync.base import SyncResult
            return SyncResult(
                created=["auto_to_push"], updated=[], deleted=[], renamed=[], errors=[]
            )

        mock_syncer = MagicMock()
        mock_syncer.entity_type = "automation"
        mock_syncer.diff = mock_diff
        mock_syncer.push = mock_push

        with patch("ha_sync.cli.get_config") as mock_get_config, \
             patch("ha_sync.cli.HAClient") as mock_ha_client_class, \
             patch("ha_sync.cli.get_syncers_for_paths") as mock_get_syncers:
            mock_get_config.return_value = sync_config
            mock_ha_client_class.return_value.__aenter__ = AsyncMock()
            mock_ha_client_class.return_value.__aexit__ = AsyncMock()
            mock_get_syncers.return_value = [(mock_syncer, None)]

            runner.invoke(app, ["push", "--yes"])

            # Verify the same IDs flow through
            assert diff_computed_ids == push_received_ids, \
                "Push should receive exactly the same diff_items that were computed for preview"
            assert "auto_to_push" in diff_computed_ids


class TestStalenessDetection:
    """Tests for staleness detection functionality."""

    def test_record_file_states_captures_mtime(
        self,
        temp_sync_dir: Path,
    ) -> None:
        """Test that _record_file_states captures file modification times."""
        import time

        # Create a test file
        test_file = temp_sync_dir / "test.yaml"
        test_file.write_text("test: data")

        # Wait a moment to ensure mtime is set
        time.sleep(0.01)

        # Create diff items referencing the file
        diff_items = [
            DiffItem(
                entity_id="test",
                status="modified",
                file_path=str(test_file),
            )
        ]

        # Record states
        states = _record_file_states(diff_items)

        # Should have recorded the file's mtime
        assert str(test_file) in states
        assert states[str(test_file)] == test_file.stat().st_mtime

    def test_check_file_staleness_detects_changes(
        self,
        temp_sync_dir: Path,
    ) -> None:
        """Test that _check_file_staleness detects when files change."""
        import time

        # Create a test file
        test_file = temp_sync_dir / "test.yaml"
        test_file.write_text("test: data")

        # Record initial state
        initial_mtime = test_file.stat().st_mtime
        recorded_states = {str(test_file): initial_mtime}

        # Initially should not be stale
        stale = _check_file_staleness(recorded_states)
        assert len(stale) == 0

        # Modify the file
        time.sleep(0.01)  # Ensure mtime changes
        test_file.write_text("test: modified")

        # Should now detect staleness
        stale = _check_file_staleness(recorded_states)
        assert str(test_file) in stale

    def test_check_file_staleness_detects_deletion(
        self,
        temp_sync_dir: Path,
    ) -> None:
        """Test that _check_file_staleness detects when files are deleted."""
        # Create a test file
        test_file = temp_sync_dir / "test.yaml"
        test_file.write_text("test: data")

        # Record initial state
        initial_mtime = test_file.stat().st_mtime
        recorded_states = {str(test_file): initial_mtime}

        # Delete the file
        test_file.unlink()

        # Should detect staleness (file no longer exists)
        stale = _check_file_staleness(recorded_states)
        assert str(test_file) in stale

    def test_record_file_states_handles_missing_file_path(self) -> None:
        """Test that _record_file_states handles diff items without file_path."""
        diff_items = [
            DiffItem(
                entity_id="test",
                status="deleted",
                file_path=None,  # No file path (e.g., remote-only item)
            )
        ]

        # Should not crash, just return empty states
        states = _record_file_states(diff_items)
        assert len(states) == 0

    def test_record_file_states_handles_nonexistent_files(
        self,
        temp_sync_dir: Path,
    ) -> None:
        """Test that _record_file_states handles files that don't exist."""
        diff_items = [
            DiffItem(
                entity_id="test",
                status="deleted",
                file_path=str(temp_sync_dir / "nonexistent.yaml"),
            )
        ]

        # Should not crash, just not record the missing file
        states = _record_file_states(diff_items)
        assert len(states) == 0

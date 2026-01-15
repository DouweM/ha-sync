"""Tests for TemplateSyncer (config entry-based syncer)."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_sync.sync.base import DiffItem
from ha_sync.sync.templates import TemplateSyncer
from ha_sync.utils import dump_yaml

from .conftest import MockSyncConfig


def create_template_file(
    temp_dir: Path,
    subtype: str,
    entry_id: str,
    name: str,
    **extra_fields: Any,
) -> Path:
    """Create a template helper YAML file."""
    subtype_dir = temp_dir / "helpers" / "template" / subtype
    subtype_dir.mkdir(parents=True, exist_ok=True)

    # Build filename from name (slug)
    slug = name.lower().replace(" ", "_")
    filename = f"{slug}.yaml"
    file_path = subtype_dir / filename

    data = {
        "entry_id": entry_id,
        "name": name,
        **extra_fields,
    }
    dump_yaml(data, file_path)
    return file_path


class SampleTemplate:
    """Factory for sample template helper data."""

    @staticmethod
    def create(
        entry_id: str = "abc123",
        name: str = "Test Sensor",
        subtype: str = "sensor",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "entry_id": entry_id,
            "name": name,
            "step_id": subtype,  # Remote uses step_id
            **kwargs,
        }


class TestTemplateSyncerDiff:
    """Tests for TemplateSyncer.diff() method."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        client = MagicMock()
        client.get_template_helpers = AsyncMock(return_value=[])
        client.get_entity_registry = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def syncer(
        self, temp_sync_dir: Path, sync_config: MockSyncConfig, mock_client: MagicMock
    ) -> TemplateSyncer:
        return TemplateSyncer(mock_client, sync_config)

    @pytest.mark.asyncio
    async def test_diff_detects_added_template(
        self, temp_sync_dir: Path, syncer: TemplateSyncer
    ) -> None:
        """Test that diff detects locally added templates."""
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="new123",
            name="New Sensor",
            state="{{ states('sensor.test') }}",
        )

        diff = await syncer.diff(remote={})

        assert len(diff) == 1
        assert diff[0].status == "added"
        assert diff[0].entity_id == "sensor/new123"

    @pytest.mark.asyncio
    async def test_diff_detects_deleted_template(
        self, temp_sync_dir: Path, syncer: TemplateSyncer
    ) -> None:
        """Test that diff detects remotely deleted templates."""
        remote = {
            "sensor/remote123": {
                "subtype": "sensor",
                "entry_id": "remote123",
                "name": "Remote Sensor",
            }
        }

        diff = await syncer.diff(remote=remote)

        assert len(diff) == 1
        assert diff[0].status == "deleted"
        assert diff[0].entity_id == "sensor/remote123"


class TestTemplateSyncerPush:
    """Tests for TemplateSyncer.push() method."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        client = MagicMock()
        client.get_template_helpers = AsyncMock(return_value=[])
        client.get_entity_registry = AsyncMock(return_value=[])
        client.create_template_helper = AsyncMock(return_value="new_entry_id")
        client.update_template_helper = AsyncMock()
        client.delete_template_helper = AsyncMock()
        return client

    @pytest.fixture
    def syncer(
        self, temp_sync_dir: Path, sync_config: MockSyncConfig, mock_client: MagicMock
    ) -> TemplateSyncer:
        return TemplateSyncer(mock_client, sync_config)

    @pytest.mark.asyncio
    async def test_push_respects_diff_items_added(
        self,
        temp_sync_dir: Path,
        syncer: TemplateSyncer,
        mock_client: MagicMock,
    ) -> None:
        """Test that push uses provided diff_items for added templates."""
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="new123",
            name="New Sensor",
        )

        # Create another file that should NOT be pushed
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="other456",
            name="Other Sensor",
        )

        # Only push the first one via diff_items
        diff_items = [
            DiffItem(
                entity_id="sensor/new123",
                status="added",
                entity_type="template",
                local={"entry_id": "new123", "name": "New Sensor"},
                file_path="helpers/template/sensor/new_sensor.yaml",
            )
        ]

        result = await syncer.push(diff_items=diff_items)

        # Should only create the one from diff_items
        assert "sensor/new123" in result.created
        assert "sensor/other456" not in result.created
        mock_client.create_template_helper.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_skips_unrelated_diff_items(
        self,
        temp_sync_dir: Path,
        syncer: TemplateSyncer,
        mock_client: MagicMock,
    ) -> None:
        """Test that push skips diff_items for other entity types."""
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="test123",
            name="Test Sensor",
        )

        # Pass a diff_item for a different entity type
        diff_items = [
            DiffItem(
                entity_id="automation.different",
                status="added",
                entity_type="automation",
            )
        ]

        result = await syncer.push(diff_items=diff_items)

        # Should not push anything (different entity type)
        assert len(result.created) == 0
        mock_client.create_template_helper.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_dry_run_no_changes(
        self,
        temp_sync_dir: Path,
        syncer: TemplateSyncer,
        mock_client: MagicMock,
    ) -> None:
        """Test that push with dry_run doesn't make API calls."""
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="test123",
            name="Test Sensor",
        )

        diff_items = [
            DiffItem(
                entity_id="sensor/test123",
                status="added",
                entity_type="template",
                local={"entry_id": "test123", "name": "Test Sensor"},
            )
        ]

        result = await syncer.push(diff_items=diff_items, dry_run=True)

        # Should report created but not actually call API
        assert "sensor/test123" in result.created
        mock_client.create_template_helper.assert_not_called()


class TestTemplateSyncerIntegration:
    """Integration tests for diff -> push consistency."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        client = MagicMock()
        client.get_template_helpers = AsyncMock(return_value=[])
        client.get_entity_registry = AsyncMock(return_value=[])
        client.create_template_helper = AsyncMock(return_value="new_entry_id")
        return client

    @pytest.fixture
    def syncer(
        self, temp_sync_dir: Path, sync_config: MockSyncConfig, mock_client: MagicMock
    ) -> TemplateSyncer:
        return TemplateSyncer(mock_client, sync_config)

    @pytest.mark.asyncio
    async def test_diff_then_push_consistency(
        self,
        temp_sync_dir: Path,
        syncer: TemplateSyncer,
        mock_client: MagicMock,
    ) -> None:
        """Test that diff output matches what push processes."""
        create_template_file(
            temp_sync_dir,
            subtype="sensor",
            entry_id="test123",
            name="Test Sensor",
        )

        # Get diff
        diff_items = await syncer.diff(remote={})

        # Push using the diff
        result = await syncer.push(diff_items=diff_items, dry_run=True)

        # Should match
        assert len(diff_items) == 1
        assert len(result.created) == 1
        assert diff_items[0].entity_id == result.created[0]

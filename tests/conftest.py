"""Pytest fixtures for ha-sync tests."""

import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_sync.client import HAClient
from ha_sync.config import SyncConfig
from ha_sync.utils import dump_yaml


class MockSyncConfig(SyncConfig):
    """Test-specific SyncConfig that uses a provided base path.

    The real SyncConfig uses relative paths (e.g., Path("automations")).
    For tests, we need absolute paths pointing to our temp directory.
    """

    _base_path: Path

    def __init__(self, base_path: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Use object.__setattr__ since Pydantic models are frozen by default
        object.__setattr__(self, "_base_path", base_path)

    @property
    def dashboards_path(self) -> Path:
        return self._base_path / "dashboards"

    @property
    def automations_path(self) -> Path:
        return self._base_path / "automations"

    @property
    def scripts_path(self) -> Path:
        return self._base_path / "scripts"

    @property
    def scenes_path(self) -> Path:
        return self._base_path / "scenes"

    @property
    def helpers_path(self) -> Path:
        return self._base_path / "helpers"


# --- Mock HAClient Fixture ---


@pytest.fixture
def mock_ha_client() -> HAClient:
    """Create a mocked HAClient for testing.

    The mock client has all async methods replaced with AsyncMock instances.
    Test code can configure return values like:
        mock_ha_client.get_automations.return_value = [...]
    """
    client = MagicMock(spec=HAClient)
    client.url = "http://homeassistant.local:8123"
    client.token = "test_token"

    # Dashboard methods
    client.get_dashboards = AsyncMock(return_value=[])
    client.get_dashboard_config = AsyncMock(return_value={})
    client.save_dashboard_config = AsyncMock()
    client.create_dashboard = AsyncMock()
    client.update_dashboard = AsyncMock()
    client.delete_dashboard = AsyncMock()

    # Automation methods
    client.get_automations = AsyncMock(return_value=[])
    client.get_automation_config = AsyncMock(return_value={})
    client.save_automation_config = AsyncMock()
    client.delete_automation = AsyncMock()
    client.reload_automations = AsyncMock()

    # Script methods
    client.get_scripts = AsyncMock(return_value=[])
    client.get_script_config = AsyncMock(return_value={})
    client.save_script_config = AsyncMock()
    client.delete_script = AsyncMock()
    client.reload_scripts = AsyncMock()

    # Scene methods
    client.get_scenes = AsyncMock(return_value=[])
    client.get_scene_config = AsyncMock(return_value={})
    client.save_scene_config = AsyncMock()
    client.delete_scene = AsyncMock()
    client.reload_scenes = AsyncMock()

    # Helper methods (generic)
    client._get_helpers = AsyncMock(return_value=[])
    client._create_helper = AsyncMock()
    client._update_helper = AsyncMock()
    client._delete_helper = AsyncMock()

    # Connection methods
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.send_command = AsyncMock()
    client.call_service = AsyncMock()

    return client


# --- Temp Directory Fixtures ---


@pytest.fixture
def temp_sync_dir(tmp_path: Path) -> Path:
    """Create a temporary sync directory structure.

    Returns a path containing empty directories for each entity type:
    - automations/
    - scripts/
    - scenes/
    - dashboards/
    """
    automations_dir = tmp_path / "automations"
    scripts_dir = tmp_path / "scripts"
    scenes_dir = tmp_path / "scenes"
    dashboards_dir = tmp_path / "dashboards"

    automations_dir.mkdir()
    scripts_dir.mkdir()
    scenes_dir.mkdir()
    dashboards_dir.mkdir()

    return tmp_path


@pytest.fixture
def sync_config(temp_sync_dir: Path) -> MockSyncConfig:
    """Create a SyncConfig pointing to the temporary directory."""
    return MockSyncConfig(
        base_path=temp_sync_dir,
        ha_url="http://homeassistant.local:8123",
        ha_token="test_token",
    )


# --- Sample Entity Factories ---


class SampleAutomation:
    """Factory for creating sample automation data."""

    @staticmethod
    def create(
        auto_id: str = "test_automation",
        alias: str = "Test Automation",
        triggers: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a sample automation config."""
        return {
            "id": auto_id,
            "alias": alias,
            "triggers": triggers or [{"trigger": "state", "entity_id": "input_boolean.test"}],
            "actions": actions or [{"action": "light.turn_on", "entity_id": "light.test"}],
            **extra,
        }

    @staticmethod
    def create_state(
        auto_id: str = "test_automation",
        alias: str = "Test Automation",
        state: str = "on",
    ) -> dict[str, Any]:
        """Create a sample automation state (as returned by get_automations)."""
        return {
            "entity_id": f"automation.{auto_id}",
            "state": state,
            "attributes": {
                "id": auto_id,
                "friendly_name": alias,
            },
        }


class SampleScript:
    """Factory for creating sample script data."""

    @staticmethod
    def create(
        script_id: str = "test_script",
        alias: str = "Test Script",
        sequence: list[dict[str, Any]] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a sample script config."""
        return {
            "id": script_id,
            "alias": alias,
            "sequence": sequence or [{"action": "light.turn_on", "entity_id": "light.test"}],
            **extra,
        }

    @staticmethod
    def create_state(
        script_id: str = "test_script",
        alias: str = "Test Script",
        state: str = "off",
    ) -> dict[str, Any]:
        """Create a sample script state (as returned by get_scripts)."""
        return {
            "entity_id": f"script.{script_id}",
            "state": state,
            "attributes": {
                "friendly_name": alias,
            },
        }


class SampleScene:
    """Factory for creating sample scene data."""

    @staticmethod
    def create(
        scene_id: str = "test_scene",
        name: str = "Test Scene",
        entities: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a sample scene config."""
        return {
            "id": scene_id,
            "name": name,
            "entities": entities or {"light.test": {"state": "on"}},
            **extra,
        }

    @staticmethod
    def create_state(
        scene_id: str = "test_scene",
        name: str = "Test Scene",
    ) -> dict[str, Any]:
        """Create a sample scene state (as returned by get_scenes)."""
        return {
            "entity_id": f"scene.{scene_id}",
            "state": "scening",
            "attributes": {
                "friendly_name": name,
            },
        }


class SampleDashboard:
    """Factory for creating sample dashboard data."""

    @staticmethod
    def create_meta(
        title: str = "Test Dashboard",
        url_path: str | None = "dashboard-test",
        icon: str | None = "mdi:home",
        show_in_sidebar: bool = True,
        require_admin: bool = False,
    ) -> dict[str, Any]:
        """Create sample dashboard metadata."""
        return {
            "title": title,
            "url_path": url_path,
            "icon": icon,
            "show_in_sidebar": show_in_sidebar,
            "require_admin": require_admin,
        }

    @staticmethod
    def create_config(
        views: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Create a sample dashboard config."""
        config: dict[str, Any] = {}
        if title:
            config["title"] = title
        config["views"] = views or [
            {"path": "home", "title": "Home", "cards": []},
        ]
        return config

    @staticmethod
    def create_view(
        path: str = "home",
        title: str = "Home",
        cards: list[dict[str, Any]] | None = None,
        position: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a sample view config."""
        view: dict[str, Any] = {}
        if position is not None:
            view["position"] = position
        view.update(
            {
                "path": path,
                "title": title,
                "cards": cards or [],
                **extra,
            }
        )
        return view


@pytest.fixture
def sample_automation() -> type[SampleAutomation]:
    """Factory fixture for creating sample automations."""
    return SampleAutomation


@pytest.fixture
def sample_script() -> type[SampleScript]:
    """Factory fixture for creating sample scripts."""
    return SampleScript


@pytest.fixture
def sample_scene() -> type[SampleScene]:
    """Factory fixture for creating sample scenes."""
    return SampleScene


@pytest.fixture
def sample_dashboard() -> type[SampleDashboard]:
    """Factory fixture for creating sample dashboards."""
    return SampleDashboard


# --- Helper Functions ---


def write_yaml_file(directory: Path, filename: str, data: dict[str, Any]) -> Path:
    """Write a YAML file to the specified directory."""
    file_path = directory / filename
    dump_yaml(data, file_path)
    return file_path


def create_automation_file(
    sync_dir: Path,
    auto_id: str = "test_automation",
    alias: str = "Test Automation",
    **extra: Any,
) -> Path:
    """Create an automation YAML file in the sync directory."""
    automations_dir = sync_dir / "automations"
    automations_dir.mkdir(exist_ok=True)
    data = SampleAutomation.create(auto_id=auto_id, alias=alias, **extra)
    filename = f"{alias.lower().replace(' ', '-')}.yaml"
    return write_yaml_file(automations_dir, filename, data)


def create_script_file(
    sync_dir: Path,
    script_id: str = "test_script",
    alias: str = "Test Script",
    **extra: Any,
) -> Path:
    """Create a script YAML file in the sync directory."""
    scripts_dir = sync_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    data = SampleScript.create(script_id=script_id, alias=alias, **extra)
    filename = f"{script_id}.yaml"
    return write_yaml_file(scripts_dir, filename, data)


def create_dashboard_files(
    sync_dir: Path,
    dir_name: str = "test",
    title: str = "Test Dashboard",
    url_path: str | None = "dashboard-test",
    views: list[dict[str, Any]] | None = None,
) -> Path:
    """Create a dashboard directory with meta and view files."""
    dashboards_dir = sync_dir / "dashboards"
    dashboards_dir.mkdir(exist_ok=True)

    dashboard_dir = dashboards_dir / dir_name
    dashboard_dir.mkdir(exist_ok=True)

    # Write _meta.yaml
    meta = SampleDashboard.create_meta(title=title, url_path=url_path)
    write_yaml_file(dashboard_dir, "_meta.yaml", meta)

    # Write view files
    views = views or [SampleDashboard.create_view(position=1)]
    for i, view in enumerate(views):
        if "position" not in view:
            view = {"position": i + 1, **view}
        path = view.get("path", f"view{i}")
        filename = f"{i:02d}_{path}.yaml"
        write_yaml_file(dashboard_dir, filename, view)

    return dashboard_dir


# Export helper functions
@pytest.fixture
def create_test_automation():
    """Fixture for creating automation files."""
    return create_automation_file


@pytest.fixture
def create_test_script():
    """Fixture for creating script files."""
    return create_script_file


@pytest.fixture
def create_test_dashboard():
    """Fixture for creating dashboard files."""
    return create_dashboard_files

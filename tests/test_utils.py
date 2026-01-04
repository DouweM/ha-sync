"""Tests for utility functions."""

from pathlib import Path
from tempfile import TemporaryDirectory

from ha_sync.utils import (
    dump_yaml,
    filename_from_id,
    filename_from_name,
    id_from_filename,
    load_yaml,
    slugify,
)


def test_slugify() -> None:
    assert slugify("Hello World") == "hello_world"
    assert slugify("This is a Test!") == "this_is_a_test"
    assert slugify("already_slugified") == "already_slugified"
    assert slugify("  spaces  ") == "spaces"
    assert slugify("Multiple---dashes") == "multiple_dashes"


def test_id_from_filename() -> None:
    assert id_from_filename(Path("sunset_lights.yaml")) == "sunset_lights"
    assert id_from_filename(Path("/path/to/file.yaml")) == "file"


def test_filename_from_id() -> None:
    assert filename_from_id("sunset_lights") == "sunset_lights.yaml"
    assert filename_from_id("my_automation") == "my_automation.yaml"


def test_filename_from_name() -> None:
    assert filename_from_name("My Automation") == "my_automation.yaml"
    assert filename_from_name("", "fallback_id") == "fallback_id.yaml"
    assert filename_from_name("") == "unnamed.yaml"


def test_dump_and_load_yaml() -> None:
    data = {
        "id": "test_automation",
        "alias": "Test Automation",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"service": "light.turn_on"}],
    }

    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.yaml"

        # Dump to file
        yaml_str = dump_yaml(data, path)
        assert path.exists()

        # Load from file
        loaded = load_yaml(path)
        assert loaded == data

        # Check YAML formatting
        assert "id: test_automation" in yaml_str
        assert "alias: Test Automation" in yaml_str

"""Tests for utility functions."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ha_sync.utils import (
    dump_yaml,
    filename_from_id,
    filename_from_name,
    git_has_commits,
    git_list_files,
    git_read_file,
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


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )


def test_git_read_file(tmp_path: Path) -> None:
    """Read a committed file from git HEAD."""
    _init_git_repo(tmp_path)

    # Create and commit a file
    test_file = tmp_path / "test.yaml"
    test_file.write_text("id: test\nname: Hello\n")
    subprocess.run(["git", "add", "test.yaml"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    # Read from HEAD
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        content = git_read_file("test.yaml")
        assert content is not None
        assert "id: test" in content
        assert "name: Hello" in content
    finally:
        os.chdir(old_cwd)


def test_git_read_file_not_found(tmp_path: Path) -> None:
    """Reading a non-existent file returns None."""
    _init_git_repo(tmp_path)

    # Make an initial commit so HEAD exists
    readme = tmp_path / "README"
    readme.write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert git_read_file("nonexistent.yaml") is None
    finally:
        os.chdir(old_cwd)


def test_git_list_files(tmp_path: Path) -> None:
    """List files in a directory from git HEAD."""
    _init_git_repo(tmp_path)

    # Create directory with files and commit
    subdir = tmp_path / "automations"
    subdir.mkdir()
    (subdir / "auto1.yaml").write_text("id: auto1")
    (subdir / "auto2.yaml").write_text("id: auto2")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        files = git_list_files("automations")
        assert sorted(files) == ["automations/auto1.yaml", "automations/auto2.yaml"]
    finally:
        os.chdir(old_cwd)


def test_git_list_files_empty_dir(tmp_path: Path) -> None:
    """Listing files in a non-existent directory returns empty list."""
    _init_git_repo(tmp_path)

    readme = tmp_path / "README"
    readme.write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert git_list_files("nonexistent") == []
    finally:
        os.chdir(old_cwd)


def test_git_has_commits(tmp_path: Path) -> None:
    """Check if repo has commits."""
    _init_git_repo(tmp_path)

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert not git_has_commits()

        readme = tmp_path / "README"
        readme.write_text("init")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path, capture_output=True, check=True,
        )
        assert git_has_commits()
    finally:
        os.chdir(old_cwd)


def test_git_read_file_modified_locally(tmp_path: Path) -> None:
    """Git read returns HEAD version even when file is modified on disk."""
    _init_git_repo(tmp_path)

    test_file = tmp_path / "test.yaml"
    test_file.write_text("name: original\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    # Modify on disk (not committed)
    test_file.write_text("name: modified\n")

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        content = git_read_file("test.yaml")
        assert content is not None
        assert "original" in content
        assert "modified" not in content
    finally:
        os.chdir(old_cwd)


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

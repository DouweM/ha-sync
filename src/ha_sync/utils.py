"""Utility functions for YAML formatting and file operations."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# --- Git utilities ---


def is_git_repo() -> bool:
    """Check if current directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


# Folders managed by ha-sync
MANAGED_FOLDERS = ["automations", "scripts", "scenes", "dashboards", "helpers"]


def git_has_changes(paths: list[str] | None = None) -> bool:
    """Check if there are uncommitted changes (staged or unstaged).

    Args:
        paths: Optional list of paths to check. If None, checks all paths.
    """
    try:
        cmd = ["git", "status", "--porcelain"]
        if paths:
            cmd.append("--")
            cmd.extend(paths)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@dataclass
class GitStashResult:
    """Result of a git stash operation."""

    stashed: bool
    message: str | None = None


def git_stash(paths: list[str] | None = None) -> GitStashResult:
    """Stash uncommitted changes if any exist.

    Args:
        paths: Optional list of paths to stash. If None, stashes all changes.

    Returns:
        GitStashResult indicating whether changes were stashed.
    """
    if not git_has_changes(paths):
        return GitStashResult(stashed=False)

    try:
        cmd = ["git", "stash", "push", "-m", "ha-sync autostash"]
        if paths:
            cmd.append("--")
            cmd.extend(paths)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        # Check if something was actually stashed
        if "No local changes to save" in result.stdout:
            return GitStashResult(stashed=False)
        return GitStashResult(stashed=True, message=result.stdout.strip())
    except subprocess.CalledProcessError as e:
        return GitStashResult(stashed=False, message=f"Stash failed: {e.stderr}")


@dataclass
class GitStashPopResult:
    """Result of a git stash pop operation."""

    success: bool
    has_conflicts: bool
    message: str | None = None


def git_stash_pop() -> GitStashPopResult:
    """Pop the most recent stash.

    Returns:
        GitStashPopResult with success status and conflict info.
    """
    try:
        result = subprocess.run(
            ["git", "stash", "pop"],
            capture_output=True,
            text=True,
            check=False,  # Don't raise on conflict
        )
        if result.returncode == 0:
            return GitStashPopResult(success=True, has_conflicts=False)
        # Check for merge conflicts
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            return GitStashPopResult(
                success=False,
                has_conflicts=True,
                message="Conflicts detected. Resolve them before pushing.",
            )
        return GitStashPopResult(
            success=False,
            has_conflicts=False,
            message=result.stderr.strip() or result.stdout.strip(),
        )
    except subprocess.CalledProcessError as e:
        return GitStashPopResult(success=False, has_conflicts=False, message=str(e))


class CleanDumper(yaml.SafeDumper):
    """Custom YAML dumper with cleaner output."""

    pass


def _str_representer(dumper: CleanDumper, data: str) -> yaml.ScalarNode:
    """Represent strings, using literal style for multiline or templates."""
    # Use literal block style for multiline strings or templates (to avoid quote escaping)
    if "\n" in data or ("{{" in data and "}}" in data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _none_representer(dumper: CleanDumper, data: None) -> yaml.ScalarNode:
    """Represent None as empty string."""
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


CleanDumper.add_representer(str, _str_representer)
CleanDumper.add_representer(type(None), _none_representer)


def dump_yaml(data: Any, path: Path | None = None) -> str:
    """Dump data to YAML string with clean formatting."""
    result = yaml.dump(
        data,
        Dumper=CleanDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        indent=2,
        width=120,
    )
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result, encoding="utf-8")
    return result


def load_yaml(path: Path) -> Any:
    """Load YAML from file."""
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def slugify(text: str) -> str:
    """Convert text to a valid filename/ID slug."""
    import re

    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and special chars with underscores
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    # Remove leading/trailing underscores
    slug = slug.strip("_")
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    return slug


def id_from_filename(path: Path) -> str:
    """Extract entity ID from filename (without .yaml extension)."""
    return path.stem


def filename_from_id(entity_id: str) -> str:
    """Create filename from entity ID."""
    return f"{entity_id}.yaml"


def filename_from_name(name: str, fallback_id: str | None = None) -> str:
    """Create a human-readable filename from a name/alias.

    Args:
        name: The human-readable name (e.g., alias)
        fallback_id: ID to use if name is empty

    Returns:
        Filename with .yaml extension
    """
    if name:
        slug = slugify(name)
        if slug:
            return f"{slug}.yaml"
    if fallback_id:
        return f"{fallback_id}.yaml"
    return "unnamed.yaml"


def relative_path(path: Path) -> str:
    """Get path relative to current working directory for clickable output."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)

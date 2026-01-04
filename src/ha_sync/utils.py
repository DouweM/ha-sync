"""Utility functions for YAML formatting and file operations."""

from pathlib import Path
from typing import Any

import yaml


class CleanDumper(yaml.SafeDumper):
    """Custom YAML dumper with cleaner output."""

    pass


def _str_representer(dumper: CleanDumper, data: str) -> yaml.ScalarNode:
    """Represent strings, using literal style for multiline."""
    if "\n" in data:
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

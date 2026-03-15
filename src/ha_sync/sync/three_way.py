"""Three-way diff model for sync operations.

Compares Base (git HEAD), Local (disk), and Remote (HA API) states to determine
what changed where and whether there are conflicts.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThreeWayDiffItem:
    """A single entity's three-way diff result."""

    entity_id: str
    entity_type: str
    change_location: str  # "local_only", "remote_only", "both"
    local_status: str | None  # "added", "modified", "deleted", or None
    remote_status: str | None  # "added", "modified", "deleted", or None
    base: dict[str, Any] | None
    local: dict[str, Any] | None
    remote: dict[str, Any] | None
    file_path: str | None = None
    has_conflict: bool = False


@dataclass
class ThreeWayDiffResult:
    """Result of a three-way diff computation."""

    local_only: list[ThreeWayDiffItem] = field(default_factory=list)
    remote_only: list[ThreeWayDiffItem] = field(default_factory=list)
    conflicts: list[ThreeWayDiffItem] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.local_only or self.remote_only or self.conflicts)

    @property
    def all_items(self) -> list[ThreeWayDiffItem]:
        return self.local_only + self.remote_only + self.conflicts


def compute_three_way_diff(
    base: dict[str, dict[str, Any]],
    local: dict[str, dict[str, Any]],
    remote: dict[str, dict[str, Any]],
    entity_type: str,
    normalize_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    file_path_fn: Callable[[str], str | None] | None = None,
) -> ThreeWayDiffResult:
    """Compute a three-way diff between base, local, and remote states.

    This is a pure function with no I/O.

    Args:
        base: Entities from git HEAD (last committed state).
              Empty dict means no git history (falls back to two-way).
        local: Entities from disk.
        remote: Entities from HA API.
        entity_type: Type label for diff items (e.g., "automation").
        normalize_fn: Optional function to normalize entity data for comparison.
        file_path_fn: Optional function to get file path from entity ID.

    Returns:
        ThreeWayDiffResult with local_only, remote_only, and conflict items.
    """
    result = ThreeWayDiffResult()
    all_ids = set(base) | set(local) | set(remote)

    def norm(data: dict[str, Any]) -> dict[str, Any]:
        if normalize_fn is not None:
            return normalize_fn(data)
        return data

    def get_file_path(entity_id: str) -> str | None:
        if file_path_fn is not None:
            return file_path_fn(entity_id)
        return None

    for entity_id in sorted(all_ids):
        base_data = base.get(entity_id)
        local_data = local.get(entity_id)
        remote_data = remote.get(entity_id)

        base_norm = norm(base_data) if base_data is not None else None
        local_norm = norm(local_data) if local_data is not None else None
        remote_norm = norm(remote_data) if remote_data is not None else None

        local_status = _compute_status(base_norm, local_norm)
        remote_status = _compute_status(base_norm, remote_norm)

        # No changes anywhere
        if local_status is None and remote_status is None:
            continue

        fp = get_file_path(entity_id)

        if local_status is not None and remote_status is None:
            # Only local changed
            result.local_only.append(ThreeWayDiffItem(
                entity_id=entity_id,
                entity_type=entity_type,
                change_location="local_only",
                local_status=local_status,
                remote_status=None,
                base=base_data,
                local=local_data,
                remote=remote_data,
                file_path=fp,
                has_conflict=False,
            ))
        elif local_status is None and remote_status is not None:
            # Only remote changed
            result.remote_only.append(ThreeWayDiffItem(
                entity_id=entity_id,
                entity_type=entity_type,
                change_location="remote_only",
                local_status=None,
                remote_status=remote_status,
                base=base_data,
                local=local_data,
                remote=remote_data,
                file_path=fp,
                has_conflict=False,
            ))
        else:
            # Both sides changed - check if it's the same change
            if local_norm == remote_norm:
                # Same change on both sides: not a conflict, no action needed
                continue

            result.conflicts.append(ThreeWayDiffItem(
                entity_id=entity_id,
                entity_type=entity_type,
                change_location="both",
                local_status=local_status,
                remote_status=remote_status,
                base=base_data,
                local=local_data,
                remote=remote_data,
                file_path=fp,
                has_conflict=True,
            ))

    return result


def _compute_status(
    base: dict[str, Any] | None, current: dict[str, Any] | None
) -> str | None:
    """Compute the change status of one side relative to base.

    Returns:
        "added" if not in base but in current,
        "deleted" if in base but not in current,
        "modified" if in both but different,
        None if unchanged.
    """
    if base is None and current is None:
        return None
    if base is None and current is not None:
        return "added"
    if base is not None and current is None:
        return "deleted"
    # Both exist - compare
    if base == current:
        return None
    return "modified"

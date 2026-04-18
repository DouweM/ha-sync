"""Tests for three-way diff logic."""

from ha_sync.sync.three_way import compute_three_way_diff


def test_no_changes() -> None:
    """All three states identical -> no diff items."""
    base = {"a": {"id": "a", "name": "Auto A"}}
    local = {"a": {"id": "a", "name": "Auto A"}}
    remote = {"a": {"id": "a", "name": "Auto A"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert not result.has_changes
    assert result.local_only == []
    assert result.remote_only == []
    assert result.conflicts == []


def test_local_only_added() -> None:
    """Entity added locally (not in base or remote)."""
    base: dict = {}
    local = {"a": {"id": "a", "name": "New"}}
    remote: dict = {}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.local_only) == 1
    item = result.local_only[0]
    assert item.entity_id == "a"
    assert item.local_status == "added"
    assert item.remote_status is None
    assert item.change_location == "local_only"
    assert not item.has_conflict


def test_local_only_modified() -> None:
    """Entity modified locally (base and remote unchanged)."""
    base = {"a": {"id": "a", "name": "Old"}}
    local = {"a": {"id": "a", "name": "New"}}
    remote = {"a": {"id": "a", "name": "Old"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.local_only) == 1
    item = result.local_only[0]
    assert item.entity_id == "a"
    assert item.local_status == "modified"
    assert item.remote_status is None
    assert not item.has_conflict


def test_local_only_deleted() -> None:
    """Entity deleted locally (still in base and remote)."""
    base = {"a": {"id": "a", "name": "Auto"}}
    local: dict = {}
    remote = {"a": {"id": "a", "name": "Auto"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.local_only) == 1
    item = result.local_only[0]
    assert item.entity_id == "a"
    assert item.local_status == "deleted"
    assert item.remote_status is None
    assert not item.has_conflict


def test_remote_only_added() -> None:
    """Entity added remotely (not in base or local)."""
    base: dict = {}
    local: dict = {}
    remote = {"a": {"id": "a", "name": "Remote New"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.remote_only) == 1
    item = result.remote_only[0]
    assert item.entity_id == "a"
    assert item.remote_status == "added"
    assert item.local_status is None
    assert not item.has_conflict


def test_remote_only_modified() -> None:
    """Entity modified remotely (base and local unchanged)."""
    base = {"a": {"id": "a", "name": "Old"}}
    local = {"a": {"id": "a", "name": "Old"}}
    remote = {"a": {"id": "a", "name": "Updated"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.remote_only) == 1
    item = result.remote_only[0]
    assert item.entity_id == "a"
    assert item.remote_status == "modified"
    assert item.local_status is None
    assert not item.has_conflict


def test_remote_only_deleted() -> None:
    """Entity deleted remotely (still in base and local)."""
    base = {"a": {"id": "a", "name": "Auto"}}
    local = {"a": {"id": "a", "name": "Auto"}}
    remote: dict = {}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.remote_only) == 1
    item = result.remote_only[0]
    assert item.entity_id == "a"
    assert item.remote_status == "deleted"
    assert item.local_status is None
    assert not item.has_conflict


def test_conflict_both_modified() -> None:
    """Same entity modified differently on both sides."""
    base = {"a": {"id": "a", "name": "Original"}}
    local = {"a": {"id": "a", "name": "Local Change"}}
    remote = {"a": {"id": "a", "name": "Remote Change"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.conflicts) == 1
    item = result.conflicts[0]
    assert item.entity_id == "a"
    assert item.local_status == "modified"
    assert item.remote_status == "modified"
    assert item.has_conflict
    assert item.change_location == "both"


def test_conflict_modified_vs_deleted() -> None:
    """Entity modified locally but deleted remotely."""
    base = {"a": {"id": "a", "name": "Original"}}
    local = {"a": {"id": "a", "name": "Modified"}}
    remote: dict = {}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.conflicts) == 1
    item = result.conflicts[0]
    assert item.entity_id == "a"
    assert item.local_status == "modified"
    assert item.remote_status == "deleted"
    assert item.has_conflict


def test_conflict_deleted_vs_modified() -> None:
    """Entity deleted locally but modified remotely."""
    base = {"a": {"id": "a", "name": "Original"}}
    local: dict = {}
    remote = {"a": {"id": "a", "name": "Remote Change"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.conflicts) == 1
    item = result.conflicts[0]
    assert item.entity_id == "a"
    assert item.local_status == "deleted"
    assert item.remote_status == "modified"
    assert item.has_conflict


def test_both_modified_same_way_not_conflict() -> None:
    """Both sides made the same change -> not a conflict."""
    base = {"a": {"id": "a", "name": "Original"}}
    local = {"a": {"id": "a", "name": "Same Change"}}
    remote = {"a": {"id": "a", "name": "Same Change"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert not result.has_changes


def test_both_added_same_not_conflict() -> None:
    """Both sides added same entity with same data -> not a conflict."""
    base: dict = {}
    local = {"a": {"id": "a", "name": "New"}}
    remote = {"a": {"id": "a", "name": "New"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert not result.has_changes


def test_both_added_differently_is_conflict() -> None:
    """Both sides added same entity with different data -> conflict."""
    base: dict = {}
    local = {"a": {"id": "a", "name": "Local Version"}}
    remote = {"a": {"id": "a", "name": "Remote Version"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.conflicts) == 1
    item = result.conflicts[0]
    assert item.local_status == "added"
    assert item.remote_status == "added"
    assert item.has_conflict


def test_both_deleted_not_conflict() -> None:
    """Both sides deleted same entity -> not a conflict."""
    base = {"a": {"id": "a", "name": "Gone"}}
    local: dict = {}
    remote: dict = {}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert not result.has_changes


def test_empty_base_fallback_to_two_way() -> None:
    """No git history (empty base) -> everything looks added.

    If local and remote differ, that's a conflict.
    If they're the same, no action needed.
    """
    base: dict = {}
    local = {"a": {"id": "a", "name": "Local"}}
    remote = {"a": {"id": "a", "name": "Remote"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    # Both added with different data -> conflict
    assert len(result.conflicts) == 1
    item = result.conflicts[0]
    assert item.local_status == "added"
    assert item.remote_status == "added"


def test_empty_base_same_data_no_conflict() -> None:
    """No git history but local and remote match -> no changes."""
    base: dict = {}
    local = {"a": {"id": "a", "name": "Same"}}
    remote = {"a": {"id": "a", "name": "Same"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert not result.has_changes


def test_normalize_fn_applied() -> None:
    """Normalize function is used for comparison."""
    base = {"a": {"id": "a", "NAME": "Original"}}
    local = {"a": {"id": "a", "NAME": "Modified"}}
    remote = {"a": {"id": "a", "NAME": "Original"}}

    # Without normalize: detects change
    result = compute_three_way_diff(base, local, remote, "automation")
    assert len(result.local_only) == 1

    # With normalize that strips NAME: no change
    def strip_name(data: dict) -> dict:
        return {"id": data["id"]}

    result = compute_three_way_diff(base, local, remote, "automation", normalize_fn=strip_name)
    assert not result.has_changes


def test_file_path_fn() -> None:
    """File path function is called for each item."""
    base: dict = {}
    local = {"a": {"id": "a"}}
    remote: dict = {}

    def fp(entity_id: str) -> str:
        return f"automations/{entity_id}.yaml"

    result = compute_three_way_diff(base, local, remote, "automation", file_path_fn=fp)

    assert result.local_only[0].file_path == "automations/a.yaml"


def test_multiple_entities_mixed() -> None:
    """Multiple entities with different change types."""
    base = {
        "a": {"id": "a", "name": "A"},
        "b": {"id": "b", "name": "B"},
        "c": {"id": "c", "name": "C"},
    }
    local = {
        "a": {"id": "a", "name": "A Modified"},  # Modified locally
        "b": {"id": "b", "name": "B"},  # Unchanged
        # c deleted locally
        "d": {"id": "d", "name": "D"},  # Added locally
    }
    remote = {
        "a": {"id": "a", "name": "A"},  # Unchanged
        "b": {"id": "b", "name": "B Modified"},  # Modified remotely
        "c": {"id": "c", "name": "C"},  # Unchanged
        "e": {"id": "e", "name": "E"},  # Added remotely
    }

    result = compute_three_way_diff(base, local, remote, "automation")

    # a: local modified, remote unchanged -> local_only
    # b: remote modified, local unchanged -> remote_only
    # c: local deleted, remote unchanged -> local_only
    # d: local added -> local_only
    # e: remote added -> remote_only

    assert len(result.local_only) == 3  # a, c, d
    assert len(result.remote_only) == 2  # b, e
    assert len(result.conflicts) == 0

    local_ids = {item.entity_id for item in result.local_only}
    remote_ids = {item.entity_id for item in result.remote_only}

    assert local_ids == {"a", "c", "d"}
    assert remote_ids == {"b", "e"}


def test_all_items_property() -> None:
    """ThreeWayDiffResult.all_items combines all lists."""
    base: dict = {}
    local = {"a": {"id": "a"}}
    remote = {"b": {"id": "b"}}

    result = compute_three_way_diff(base, local, remote, "automation")

    assert len(result.all_items) == 2
    assert result.has_changes


def test_entity_type_set_on_items() -> None:
    """Entity type is set on all diff items."""
    base: dict = {}
    local = {"a": {"id": "a"}}
    remote: dict = {}

    result = compute_three_way_diff(base, local, remote, "my_type")

    assert result.local_only[0].entity_type == "my_type"

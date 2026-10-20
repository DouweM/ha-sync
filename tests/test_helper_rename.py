"""Renaming a config entry helper on push.

A helper's options flow never asks for its name again after creation, so an
options update alone leaves a rename behind: the entry title (what pull reads
back as `name`) and the entity's name both stay as they were.
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_sync.sync.base import DiffItem
from ha_sync.sync.config_entries import ConfigEntrySyncer
from ha_sync.sync.templates import TemplateSyncer
from ha_sync.utils import dump_yaml

from .conftest import MockSyncConfig


def _client(
    entry_id: str, title: str, entity: dict[str, Any] | list[dict[str, Any]] | None
) -> MagicMock:
    entities = entity if isinstance(entity, list) else ([entity] if entity else [])
    client = MagicMock()
    client.get_config_entries = AsyncMock(
        return_value=[{"entry_id": entry_id, "title": title, "domain": "template"}]
    )
    client.get_entity_registry = AsyncMock(
        return_value=[{**e, "config_entry_id": entry_id} for e in entities]
    )
    client.update_template_helper = AsyncMock()
    client.update_config_entry = AsyncMock()
    client.update_config_entry_title = AsyncMock()
    client.update_entity_registry = AsyncMock(return_value={})
    return client


def _entity(name: str | None, original_name: str, **extra: Any) -> dict[str, Any]:
    return {
        "entity_id": "binary_sensor.out_in_the_city",
        "name": name,
        "original_name": original_name,
        "has_entity_name": False,
        **extra,
    }


def _template_file(base: Path, name: str) -> None:
    path = base / "helpers" / "template" / "binary_sensor" / "out_in_the_city.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(
        {
            "entry_id": "e1",
            "id": "binary_sensor.out_in_the_city",
            "name": name,
            "state": "{{ true }}",
        },
        path,
    )


def _modified(entity_id: str) -> list[DiffItem]:
    return [
        DiffItem(
            entity_id=entity_id,
            status="modified",
            entity_type="template",
            file_path="x.yaml",
        )
    ]


async def _push_template(
    base: Path, config: MockSyncConfig, client: MagicMock, name: str, dry_run: bool = False
) -> None:
    _template_file(base, name)
    syncer = TemplateSyncer(client, config)  # type: ignore[arg-type]
    result = await syncer.push(diff_items=_modified("binary_sensor/e1"), dry_run=dry_run)
    assert not result.errors


@pytest.mark.asyncio
async def test_renamed_template_sets_title_and_entity_name(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client("e1", "Douwe Out Late", _entity(None, "Douwe Out Late"))
    await _push_template(temp_sync_dir, sync_config, client, "Douwe out in the City")

    client.update_template_helper.assert_awaited_once()
    client.update_config_entry_title.assert_awaited_once_with("e1", "Douwe out in the City")
    client.update_entity_registry.assert_awaited_once_with(
        "binary_sensor.out_in_the_city", name="Douwe out in the City"
    )


@pytest.mark.asyncio
async def test_unchanged_name_renames_nothing(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client("e1", "Douwe Out", _entity(None, "Douwe Out"))
    await _push_template(temp_sync_dir, sync_config, client, "Douwe Out")

    client.update_config_entry_title.assert_not_awaited()
    client.update_entity_registry.assert_not_awaited()


@pytest.mark.asyncio
async def test_registry_name_already_matching_only_sets_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """Renamed by hand in the UI first: the entity already shows the new name,
    which is not the old title, so it is not following it and is left alone."""
    client = _client("e1", "Old", _entity("New", "Old"))
    await _push_template(temp_sync_dir, sync_config, client, "New")

    client.update_config_entry_title.assert_awaited_once_with("e1", "New")
    client.update_entity_registry.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_named_entity_only_gets_the_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """With no registry name HA shows device name + original name; a registry
    name would replace that whole friendly name, so leave it alone."""
    client = _client("e1", "Old", _entity(None, "Old", has_entity_name=True))
    await _push_template(temp_sync_dir, sync_config, client, "New")

    client.update_config_entry_title.assert_awaited_once_with("e1", "New")
    client.update_entity_registry.assert_not_awaited()


@pytest.mark.asyncio
async def test_several_entities_only_get_the_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """A utility meter with tariffs names each entity after its tariff."""
    entities = [
        {**_entity(None, "Old peak"), "entity_id": "sensor.a"},
        {**_entity(None, "Old offpeak"), "entity_id": "sensor.b"},
    ]
    client = _client("e1", "Old", entities)
    await _push_template(temp_sync_dir, sync_config, client, "New")

    client.update_config_entry_title.assert_awaited_once_with("e1", "New")
    assert not [c for c in client.update_entity_registry.await_args_list if "name" in c.kwargs]


@pytest.mark.asyncio
async def test_dry_run_renames_nothing(temp_sync_dir: Path, sync_config: MockSyncConfig) -> None:
    client = _client("e1", "Old", _entity(None, "Old"))
    await _push_template(temp_sync_dir, sync_config, client, "New", dry_run=True)

    client.update_template_helper.assert_not_awaited()
    client.update_config_entry_title.assert_not_awaited()
    client.update_entity_registry.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_id_rename_still_happens_alongside(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """The name is set on the entity by its old id, before the id moves."""
    client = _client("e1", "Old", {**_entity(None, "Old"), "entity_id": "binary_sensor.old"})
    await _push_template(temp_sync_dir, sync_config, client, "New")

    calls = client.update_entity_registry.await_args_list
    assert calls[0].args == ("binary_sensor.old",) and calls[0].kwargs == {"name": "New"}
    assert calls[1].args == ("binary_sensor.old",)
    assert calls[1].kwargs == {"new_entity_id": "binary_sensor.out_in_the_city"}


@pytest.mark.asyncio
async def test_generic_config_entry_helper_is_renamed(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client(
        "t1",
        "Telcel Modem Up One Week",
        {**_entity(None, "Telcel Modem Up One Week"), "entity_id": "binary_sensor.modem"},
    )
    syncer = ConfigEntrySyncer(client, sync_config, "threshold")  # type: ignore[arg-type]
    path = syncer.local_path / "modem.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(
        {
            "entry_id": "t1",
            "id": "binary_sensor.modem",
            "name": "LTE Modem Up One Week",
            "entity_id": "sensor.uptime",
        },
        path,
    )

    result = await syncer.push(diff_items=_modified("t1"))

    assert not result.errors
    client.update_config_entry.assert_awaited_once()
    client.update_config_entry_title.assert_awaited_once_with("t1", "LTE Modem Up One Week")
    client.update_entity_registry.assert_awaited_once_with(
        "binary_sensor.modem", name="LTE Modem Up One Week"
    )


@pytest.mark.asyncio
async def test_options_only_push_keeps_a_registry_name_override(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """A name chosen in HA ("Gaby Out") survives a push that only edits options."""
    client = _client("e1", "Gaby out in the City", _entity("Gaby Out", "Gaby out in the City"))
    await _push_template(temp_sync_dir, sync_config, client, "Gaby out in the City")

    client.update_template_helper.assert_awaited_once()
    client.update_config_entry_title.assert_not_awaited()
    assert not [c for c in client.update_entity_registry.await_args_list if "name" in c.kwargs]


@pytest.mark.asyncio
async def test_rename_keeps_a_registry_name_that_differs_from_the_old_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client("e1", "Gaby out in the City", _entity("Gaby Out", "Gaby out in the City"))
    await _push_template(temp_sync_dir, sync_config, client, "Gaby in Town")

    client.update_config_entry_title.assert_awaited_once_with("e1", "Gaby in Town")
    assert not [c for c in client.update_entity_registry.await_args_list if "name" in c.kwargs]


@pytest.mark.asyncio
async def test_rename_moves_a_registry_name_equal_to_the_old_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client("e1", "Old", _entity("Old", "Something Else"))
    await _push_template(temp_sync_dir, sync_config, client, "New")

    client.update_entity_registry.assert_awaited_once_with(
        "binary_sensor.out_in_the_city", name="New"
    )
    client.update_config_entry_title.assert_awaited_once_with("e1", "New")


@pytest.mark.asyncio
async def test_registry_name_is_written_before_the_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    client = _client("e1", "Old", _entity(None, "Old"))
    order: list[str] = []
    client.update_entity_registry.side_effect = lambda *a, **k: order.append("registry") or {}
    client.update_config_entry_title.side_effect = lambda *a, **k: order.append("title")
    await _push_template(temp_sync_dir, sync_config, client, "New")

    assert order == ["registry", "title"]


@pytest.mark.asyncio
async def test_failed_registry_rename_is_an_error_and_leaves_the_title(
    temp_sync_dir: Path, sync_config: MockSyncConfig
) -> None:
    """The title is what makes the next diff clean, so it must not be written
    when the friendly name could not be: the rename shows again and is retried."""
    client = _client("e1", "Old", _entity(None, "Old"))
    client.update_entity_registry.side_effect = RuntimeError("websocket closed")
    _template_file(temp_sync_dir, "New")
    syncer = TemplateSyncer(client, sync_config)  # type: ignore[arg-type]
    result = await syncer.push(diff_items=_modified("binary_sensor/e1"))

    client.update_config_entry_title.assert_not_awaited()
    assert [e for e, _ in result.errors] == ["binary_sensor/e1"]
    assert "binary_sensor/e1" not in result.updated

"""Tests for view resolution logic in render.py."""

import pytest

from ha_sync.client import HAClient
from ha_sync.render import ViewResolver
from ha_sync.render_models import CachedEntityState, VisibilityConditionState


@pytest.fixture
def resolver(mock_ha_client: HAClient) -> ViewResolver:
    resolver = ViewResolver(mock_ha_client)
    resolver.state_cache["media_player.tv"] = CachedEntityState(state="playing")
    return resolver


class TestCheckVisibilityState:
    def test_state_string_match(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state="playing"
        )
        assert resolver.check_visibility([condition]) is True

    def test_state_string_mismatch(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state="off"
        )
        assert resolver.check_visibility([condition]) is False

    def test_state_list_match(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state=["playing", "paused"]
        )
        assert resolver.check_visibility([condition]) is True

    def test_state_list_mismatch(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state=["off", "idle"]
        )
        assert resolver.check_visibility([condition]) is False

    def test_state_not_string_match_hides(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state_not="playing"
        )
        assert resolver.check_visibility([condition]) is False

    def test_state_not_list_match_hides(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state_not=["playing", "paused"]
        )
        assert resolver.check_visibility([condition]) is False

    def test_state_not_list_mismatch_shows(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="media_player.tv", state_not=["unknown", "unavailable"]
        )
        assert resolver.check_visibility([condition]) is True

    def test_unknown_entity_defaults_to_unknown_state(self, resolver: ViewResolver) -> None:
        condition = VisibilityConditionState(
            condition="state", entity="sensor.missing", state_not=["unknown", "unavailable"]
        )
        assert resolver.check_visibility([condition]) is False

"""Tests for render_models.py — Pydantic models and format_state function."""

import json

import pytest
from pydantic import ValidationError

from ha_sync.render_models import (
    AutoEntitiesCardConfig,
    EntityBadgeConfig,
    FormattedState,
    HeadingCardConfig,
    LogbookCardConfig,
    OtherCardConfig,
    RenderedAutoEntities,
    RenderedEntityBadge,
    RenderedHeading,
    RenderedIcon,
    RenderedLogbook,
    RenderedLogbookEntry,
    RenderedSection,
    RenderedSpacing,
    RenderedTemplateBadge,
    RenderedTile,
    RenderedView,
    RenderedWeather,
    SectionConfig,
    SemanticColor,
    TemplateBadgeConfig,
    TileCardConfig,
    ViewConfig,
    VisibilityConditionOr,
    VisibilityConditionState,
    WeatherCardConfig,
    format_state,
)

# =============================================================================
# format_state tests
# =============================================================================


class TestFormatState:
    def test_unavailable(self) -> None:
        result = format_state("sensor.temp", "unavailable")
        assert result == FormattedState(text="?", color=SemanticColor.INACTIVE)

    def test_unknown(self) -> None:
        result = format_state("light.hall", "unknown")
        assert result == FormattedState(text="?", color=SemanticColor.INACTIVE)

    def test_person_home(self) -> None:
        result = format_state("person.douwe", "home")
        assert result.text == "Home"
        assert result.color == SemanticColor.POSITIVE

    def test_person_away(self) -> None:
        result = format_state("person.douwe", "not_home")
        assert result.text == "Away"
        assert result.color == SemanticColor.INACTIVE

    def test_person_zone(self) -> None:
        result = format_state("person.douwe", "Office")
        assert result.text == "Office"
        assert result.color == SemanticColor.INFO

    def test_lock_locked(self) -> None:
        result = format_state("lock.front_door", "locked")
        assert result.text == "Locked"
        assert result.color == SemanticColor.POSITIVE

    def test_lock_unlocked(self) -> None:
        result = format_state("lock.front_door", "unlocked")
        assert result.text == "Unlocked"
        assert result.color == SemanticColor.DANGER

    def test_cover_closed(self) -> None:
        result = format_state("cover.garage", "closed")
        assert result.text == "Closed"
        assert result.color == SemanticColor.POSITIVE

    def test_cover_open(self) -> None:
        result = format_state("cover.garage", "open")
        assert result.text == "Open"
        assert result.color == SemanticColor.WARNING

    def test_binary_sensor_door_open(self) -> None:
        result = format_state("binary_sensor.door", "on", device_class="door")
        assert result.text == "Open"
        assert result.color == SemanticColor.WARNING

    def test_binary_sensor_door_closed(self) -> None:
        result = format_state("binary_sensor.door", "off", device_class="door")
        assert result.text == "Closed"
        assert result.color == SemanticColor.POSITIVE

    def test_binary_sensor_motion_detected(self) -> None:
        result = format_state("binary_sensor.hall", "on", device_class="motion")
        assert result.text == "Motion"
        assert result.color == SemanticColor.WARNING

    def test_binary_sensor_motion_clear(self) -> None:
        result = format_state("binary_sensor.hall", "off", device_class="motion")
        assert result.text == "Clear"
        assert result.color == SemanticColor.INACTIVE

    def test_binary_sensor_battery_low(self) -> None:
        result = format_state("binary_sensor.batt", "on", device_class="battery")
        assert result.text == "Low"
        assert result.color == SemanticColor.DANGER

    def test_binary_sensor_problem(self) -> None:
        result = format_state("binary_sensor.check", "on", device_class="problem")
        assert result.text == "Problem"
        assert result.color == SemanticColor.DANGER

    def test_light_on(self) -> None:
        result = format_state("light.hall", "on")
        assert result.text == "On"
        assert result.color == SemanticColor.ACTIVE

    def test_light_off(self) -> None:
        result = format_state("light.hall", "off")
        assert result.text == "Off"
        assert result.color == SemanticColor.INACTIVE

    def test_switch_on(self) -> None:
        result = format_state("switch.pump", "on")
        assert result.text == "On"
        assert result.color == SemanticColor.ACTIVE

    def test_alarm_armed(self) -> None:
        result = format_state("alarm_control_panel.home", "armed_away")
        assert result.text == "Armed away"
        assert result.color == SemanticColor.POSITIVE

    def test_alarm_triggered(self) -> None:
        result = format_state("alarm_control_panel.home", "triggered")
        assert result.text == "TRIGGERED"
        assert result.color == SemanticColor.DANGER

    def test_climate_heat(self) -> None:
        result = format_state("climate.bedroom", "heat")
        assert result.text == "Heating"
        assert result.color == SemanticColor.HEAT

    def test_climate_cool(self) -> None:
        result = format_state("climate.bedroom", "cool")
        assert result.text == "Cooling"
        assert result.color == SemanticColor.COOL

    def test_climate_auto(self) -> None:
        result = format_state("climate.bedroom", "auto")
        assert result.text == "Auto"
        assert result.color == SemanticColor.INFO

    def test_sensor_integer(self) -> None:
        result = format_state("sensor.temp", "22.0", unit="°C")
        assert result.text == "22°C"
        assert result.color is None

    def test_sensor_decimal(self) -> None:
        result = format_state("sensor.temp", "22.5", unit="°C")
        assert result.text == "22.5°C"

    def test_sensor_no_unit(self) -> None:
        result = format_state("sensor.count", "42")
        assert result.text == "42"

    def test_sensor_non_numeric(self) -> None:
        result = format_state("sensor.status", "idle")
        assert result.text == "idle"

    def test_weather(self) -> None:
        result = format_state("weather.home", "partlycloudy")
        assert result.text == "Partly Cloudy"
        assert result.color == SemanticColor.INFO

    def test_image_empty(self) -> None:
        result = format_state("image.photo", "2024-01-01")
        assert result.text == ""

    def test_unknown_domain(self) -> None:
        result = format_state("automation.test", "on")
        assert result.text == "on"
        assert result.color is None


# =============================================================================
# Config model tests
# =============================================================================


class TestConfigModels:
    def test_view_config_from_yaml(self) -> None:
        data = {
            "title": "Oasis",
            "path": "oasis",
            "icon": "mdi:home-circle",
            "badges": [
                {"type": "entity", "entity": "light.hall", "show_name": False},
            ],
            "sections": [
                {
                    "cards": [
                        {"type": "tile", "entity": "light.hall"},
                        {"type": "heading", "heading": "Climate"},
                    ]
                }
            ],
        }
        view = ViewConfig.model_validate(data)
        assert view.title == "Oasis"
        assert view.icon == "mdi:home-circle"
        assert len(view.badges) == 1
        assert isinstance(view.badges[0], EntityBadgeConfig)
        assert view.badges[0].entity == "light.hall"
        assert len(view.sections) == 1
        assert len(view.sections[0].cards) == 2

    def test_card_discriminator(self) -> None:
        """Cards are discriminated by type field."""
        section = SectionConfig.model_validate(
            {
                "cards": [
                    {"type": "tile", "entity": "light.hall"},
                    {"type": "heading", "heading": "Test"},
                    {"type": "custom:auto-entities", "filter": {"include": []}},
                    {"type": "logbook", "entities": ["sensor.temp"]},
                    {"type": "weather-forecast", "entity": "weather.home"},
                    {"type": "picture-entity", "entity": "camera.front"},
                ]
            }
        )
        assert isinstance(section.cards[0], TileCardConfig)
        assert isinstance(section.cards[1], HeadingCardConfig)
        assert isinstance(section.cards[2], AutoEntitiesCardConfig)
        assert isinstance(section.cards[3], LogbookCardConfig)
        assert isinstance(section.cards[4], WeatherCardConfig)
        assert isinstance(section.cards[5], OtherCardConfig)

    def test_badge_discriminator(self) -> None:
        view = ViewConfig.model_validate(
            {
                "badges": [
                    {"type": "entity", "entity": "person.douwe"},
                    {
                        "type": "custom:mushroom-template-badge",
                        "entity": "person.douwe",
                        "content": "{{ states('person.douwe') }}",
                    },
                ]
            }
        )
        assert isinstance(view.badges[0], EntityBadgeConfig)
        assert isinstance(view.badges[1], TemplateBadgeConfig)

    def test_visibility_condition_discriminator(self) -> None:
        badge = EntityBadgeConfig.model_validate(
            {
                "entity": "light.hall",
                "visibility": [
                    {"condition": "state", "entity": "light.hall", "state": "on"},
                    {"condition": "numeric_state", "entity": "sensor.temp", "above": 20},
                    {
                        "condition": "or",
                        "conditions": [
                            {"condition": "state", "entity": "input_boolean.away", "state": "on"},
                        ],
                    },
                ],
            }
        )
        assert len(badge.visibility) == 3
        assert isinstance(badge.visibility[0], VisibilityConditionState)
        assert isinstance(badge.visibility[2], VisibilityConditionOr)

    def test_extra_fields_allowed(self) -> None:
        """Config models allow extra fields (HA has many we don't need)."""
        tile = TileCardConfig.model_validate(
            {
                "type": "tile",
                "entity": "light.hall",
                "features_position": "bottom",
                "vertical": True,
                "color": "red",
                "tap_action": {"action": "toggle"},
            }
        )
        assert tile.entity == "light.hall"


# =============================================================================
# Rendered model tests
# =============================================================================


class TestRenderedModels:
    def test_rendered_view_json_roundtrip(self) -> None:
        """RenderedView serializes to JSON and back — critical for watchOS API."""
        view = RenderedView(
            title="Oasis",
            path="dashboards/welcome/00_oasis.yaml",
            icon=RenderedIcon(mdi_name="home-circle"),
            badges=[
                RenderedEntityBadge(
                    entity_id="person.douwe",
                    name="Douwe",
                    state=FormattedState(text="Home", color=SemanticColor.POSITIVE),
                    icon=RenderedIcon(mdi_name="account", entity_id="person.douwe"),
                ),
                RenderedTemplateBadge(
                    entity_id="person.gaby",
                    content="Away",
                    content_color=SemanticColor.INACTIVE,
                    label="10m",
                    icon=RenderedIcon(mdi_name="account", entity_id="person.gaby"),
                ),
            ],
            sections=[
                RenderedSection(
                    items=[
                        RenderedSpacing(),
                        RenderedHeading(
                            heading="Climate",
                            icon=RenderedIcon(mdi_name="thermometer"),
                        ),
                        RenderedTile(
                            entity_id="sensor.temp",
                            name="Temperature",
                            state=FormattedState(text="22°C"),
                            icon=RenderedIcon(
                                mdi_name="thermometer",
                                entity_id="sensor.temp",
                                device_class="temperature",
                            ),
                        ),
                        RenderedAutoEntities(
                            tiles=[
                                RenderedTile(
                                    entity_id="light.hall",
                                    name="Hall",
                                    state=FormattedState(text="On", color=SemanticColor.ACTIVE),
                                    icon=RenderedIcon(mdi_name="lightbulb", entity_id="light.hall"),
                                ),
                            ]
                        ),
                        RenderedLogbook(
                            entries=[
                                RenderedLogbookEntry(
                                    entity_id="lock.front",
                                    name="Front Door",
                                    state=FormattedState(
                                        text="Locked", color=SemanticColor.POSITIVE
                                    ),
                                    time_ago="5m ago",
                                    icon=RenderedIcon(mdi_name="lock", entity_id="lock.front"),
                                ),
                            ]
                        ),
                        RenderedWeather(
                            entity_id="weather.home",
                            condition="Partly Cloudy",
                            raw_condition="partlycloudy",
                            temperature="22°C",
                            icon=RenderedIcon(mdi_name="weather-cloudy", entity_id="weather.home"),
                        ),
                    ]
                ),
            ],
        )

        # Serialize to JSON
        json_str = view.model_dump_json()
        data = json.loads(json_str)

        # Verify structure
        assert data["title"] == "Oasis"
        assert len(data["badges"]) == 2
        assert data["badges"][0]["type"] == "entity"
        assert data["badges"][1]["type"] == "template"
        assert len(data["sections"]) == 1
        assert len(data["sections"][0]["items"]) == 6
        assert data["sections"][0]["items"][0]["type"] == "spacing"
        assert data["sections"][0]["items"][1]["type"] == "heading"
        assert data["sections"][0]["items"][2]["type"] == "tile"
        assert data["sections"][0]["items"][3]["type"] == "auto_entities"
        assert data["sections"][0]["items"][4]["type"] == "logbook"
        assert data["sections"][0]["items"][5]["type"] == "weather"

        # Roundtrip
        view2 = RenderedView.model_validate_json(json_str)
        assert view2 == view

    def test_formatted_state_frozen(self) -> None:
        state = FormattedState(text="Home", color=SemanticColor.POSITIVE)
        with pytest.raises(ValidationError):
            state.text = "Away"  # type: ignore[misc]

    def test_rendered_icon_frozen(self) -> None:
        icon = RenderedIcon(mdi_name="home")
        with pytest.raises(ValidationError):
            icon.mdi_name = "lightbulb"  # type: ignore[misc]

    def test_semantic_color_json_value(self) -> None:
        """SemanticColor serializes as its string value."""
        state = FormattedState(text="On", color=SemanticColor.ACTIVE)
        data = state.model_dump()
        assert data["color"] == "active"

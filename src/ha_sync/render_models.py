"""Pydantic models for the dashboard render pipeline.

Two layers:
- Config models: typed representation of dashboard YAML (ViewConfig, CardConfig, etc.)
- Rendered models: resolved output after state fetching and template evaluation (RenderedView, etc.)

The rendered models are format-agnostic and JSON-serializable, suitable for
Rich CLI, SwiftBar, or a future API endpoint serving the watchOS app.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

# =============================================================================
# Semantic color enum
# =============================================================================


class SemanticColor(StrEnum):
    """Format-agnostic semantic color for entity states.

    Each renderer maps these to its own format:
    - Rich CLI: "dim", "green", "yellow", "bold red", "cyan", etc.
    - SwiftBar: "gray", "green", "#F5A623", "red", "#4A90D9", etc.
    - watchOS: SwiftUI Color values
    """

    INACTIVE = "inactive"  # off, away, disconnected, disarmed, empty, clear
    POSITIVE = "positive"  # home, locked, closed, connected, OK, armed
    ACTIVE = "active"  # on (lights/switches/fans), occupied
    WARNING = "warning"  # open (doors/windows), motion
    DANGER = "danger"  # unlocked, triggered, low battery, problem
    INFO = "info"  # named zones, weather conditions, auto climate
    HEAT = "heat"  # heating
    COOL = "cool"  # cooling


# =============================================================================
# Cached entity state (internal — used by ViewResolver)
# =============================================================================


class CachedEntityState(BaseModel):
    """Cached state and attributes for a single entity."""

    state: str = "unknown"
    name: str = ""
    unit: str = ""
    icon: str = ""
    device_class: str = ""


# =============================================================================
# Rendered models (output layer)
# =============================================================================


class FormattedState(BaseModel):
    """A formatted entity state with semantic color."""

    model_config = ConfigDict(frozen=True)

    text: str
    """Human-readable state text, e.g. "Home", "Locked", "23°C"."""

    color: SemanticColor | None = None
    """Semantic color. None means default/no emphasis."""


class RenderedIcon(BaseModel):
    """Format-agnostic icon reference.

    Stores enough context for any renderer to resolve to its format
    (emoji, SF Symbol, etc.) using its own mapping tables and fallback chain.
    """

    model_config = ConfigDict(frozen=True)

    mdi_name: str | None = None
    """MDI icon name without 'mdi:' prefix, e.g. 'lightbulb', 'home-circle'."""

    entity_id: str | None = None
    """Entity ID for domain-based fallback, e.g. 'light.hall_lights'."""

    device_class: str | None = None
    """Device class for fallback, e.g. 'temperature', 'motion'."""


# -- Badges --


class RenderedEntityBadge(BaseModel):
    """A resolved entity badge."""

    type: Literal["entity"] = "entity"
    entity_id: str
    name: str
    state: FormattedState
    icon: RenderedIcon


class RenderedTemplateBadge(BaseModel):
    """A resolved mushroom-template-badge."""

    type: Literal["template"] = "template"
    entity_id: str | None = None
    content: str | None = None
    """Resolved template content text."""
    content_color: SemanticColor | None = None
    label: str | None = None
    """Resolved template label text."""
    icon: RenderedIcon


RenderedBadge = Annotated[
    RenderedEntityBadge | RenderedTemplateBadge,
    Field(discriminator="type"),
]


# -- Section items --


class RenderedTile(BaseModel):
    """A resolved tile card."""

    type: Literal["tile"] = "tile"
    entity_id: str
    name: str
    state: FormattedState
    icon: RenderedIcon


class RenderedAutoEntities(BaseModel):
    """A resolved auto-entities card (expanded to tiles)."""

    type: Literal["auto_entities"] = "auto_entities"
    tiles: list[RenderedTile] = Field(default_factory=list)


class RenderedLogbookEntry(BaseModel):
    """A single logbook entry."""

    model_config = ConfigDict(frozen=True)

    entity_id: str
    name: str
    state: FormattedState
    time_ago: str
    """Relative time, e.g. "5m ago", "2h ago", "just now"."""
    icon: RenderedIcon


class RenderedLogbook(BaseModel):
    """A resolved logbook card."""

    type: Literal["logbook"] = "logbook"
    entries: list[RenderedLogbookEntry] = Field(default_factory=list)


class RenderedWeather(BaseModel):
    """A resolved weather-forecast card."""

    type: Literal["weather"] = "weather"
    entity_id: str
    condition: str
    """Formatted condition, e.g. "Partly Cloudy"."""
    raw_condition: str
    """Raw HA weather state, e.g. "partlycloudy". For condition-based icon lookup."""
    temperature: str
    """Formatted temperature with unit, e.g. "23°C"."""
    icon: RenderedIcon


class RenderedHeading(BaseModel):
    """A resolved heading card."""

    type: Literal["heading"] = "heading"
    heading: str
    icon: RenderedIcon
    badges: list[RenderedBadge] = Field(default_factory=list)


class RenderedSpacing(BaseModel):
    """A blank line / visual separator."""

    type: Literal["spacing"] = "spacing"


RenderedSectionItem = Annotated[
    RenderedHeading
    | RenderedTile
    | RenderedAutoEntities
    | RenderedLogbook
    | RenderedWeather
    | RenderedSpacing,
    Field(discriminator="type"),
]


class RenderedSection(BaseModel):
    """A resolved dashboard section."""

    items: list[RenderedSectionItem] = Field(default_factory=list)


class RenderedView(BaseModel):
    """A fully resolved, format-agnostic dashboard view.

    Complete output of the ViewResolver: all data fetched, templates evaluated,
    visibility filtered, states formatted. Ready for any renderer to consume,
    or to serialize as JSON for a watchOS API endpoint.
    """

    title: str
    path: str
    """Source view file path."""
    icon: RenderedIcon
    badges: list[RenderedBadge] = Field(default_factory=list)
    sections: list[RenderedSection] = Field(default_factory=list)


# =============================================================================
# Config models (input layer — typed dashboard YAML)
# =============================================================================


class VisibilityConditionState(BaseModel):
    """State-based visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["state"]
    entity: str | None = None
    state: str | None = None
    state_not: str | None = None


class VisibilityConditionNumericState(BaseModel):
    """Numeric state visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["numeric_state"]
    entity: str | None = None
    above: float | None = None
    below: float | None = None


class VisibilityConditionScreen(BaseModel):
    """Screen/media query visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["screen"]
    media_query: str = ""


class VisibilityConditionUser(BaseModel):
    """User-based visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["user"]
    users: list[str] = Field(default_factory=list)


class VisibilityConditionOr(BaseModel):
    """OR composite visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["or"]
    conditions: list[VisibilityCondition] = Field(default_factory=list)


class VisibilityConditionAnd(BaseModel):
    """AND composite visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["and"]
    conditions: list[VisibilityCondition] = Field(default_factory=list)


class VisibilityConditionNot(BaseModel):
    """NOT composite visibility condition."""

    model_config = ConfigDict(extra="allow")

    condition: Literal["not"]
    conditions: list[VisibilityCondition] = Field(default_factory=list)


VisibilityCondition = Annotated[
    VisibilityConditionState
    | VisibilityConditionNumericState
    | VisibilityConditionScreen
    | VisibilityConditionUser
    | VisibilityConditionOr
    | VisibilityConditionAnd
    | VisibilityConditionNot,
    Field(discriminator="condition"),
]

# -- Badge configs --


class EntityBadgeConfig(BaseModel):
    """Entity badge configuration from dashboard YAML."""

    model_config = ConfigDict(extra="allow")

    type: Literal["entity"] = "entity"
    entity: str | None = None
    name: str | None = None
    icon: str | None = None
    show_name: bool | None = None
    show_state: bool = True
    show_icon: bool = True
    state_content: str | list[str] | None = None
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class TemplateBadgeConfig(BaseModel):
    """Mushroom template badge configuration from dashboard YAML."""

    model_config = ConfigDict(extra="allow")

    type: Literal["custom:mushroom-template-badge"]
    entity: str | None = None
    icon: str | None = None
    content: str | None = None
    label: str | None = None
    visibility: list[VisibilityCondition] = Field(default_factory=list)


BadgeConfig = Annotated[
    EntityBadgeConfig | TemplateBadgeConfig,
    Field(discriminator="type"),
]


# -- Card configs --


class TileCardConfig(BaseModel):
    """Tile card configuration."""

    model_config = ConfigDict(extra="allow")

    type: Literal["tile"]
    entity: str | None = None
    name: str | None = None
    icon: str | None = None
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class HeadingCardConfig(BaseModel):
    """Heading card configuration."""

    model_config = ConfigDict(extra="allow")

    type: Literal["heading"]
    heading: str = ""
    icon: str | None = None
    badges: list[BadgeConfig] = Field(default_factory=list)
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class AutoEntitiesNotCondition(BaseModel):
    """A single condition inside an auto-entities not.or list."""

    model_config = ConfigDict(extra="allow")

    state: str | None = None
    label: str | None = None


class AutoEntitiesNotFilter(BaseModel):
    """Auto-entities 'not' filter with OR conditions."""

    model_config = ConfigDict(extra="allow")

    or_: list[AutoEntitiesNotCondition] = Field(default_factory=list, alias="or")


class AutoEntitiesIncludeRule(BaseModel):
    """A single include rule for auto-entities filter."""

    model_config = ConfigDict(extra="allow")

    entity_id: str | None = None
    domain: str | None = None
    integration: str | None = None
    label: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    not_: AutoEntitiesNotFilter | None = Field(default=None, alias="not")


class AutoEntitiesFilter(BaseModel):
    """Auto-entities filter configuration."""

    model_config = ConfigDict(extra="allow")

    include: list[AutoEntitiesIncludeRule] = Field(default_factory=list)
    exclude: list[dict[str, Any]] = Field(default_factory=list)


class AutoEntitiesInnerCardConfig(BaseModel):
    """Inner card configuration for auto-entities (just the type matters for filtering)."""

    model_config = ConfigDict(extra="allow")

    type: str = ""


class AutoEntitiesCardConfig(BaseModel):
    """Auto-entities card configuration."""

    model_config = ConfigDict(extra="allow")

    type: Literal["custom:auto-entities"]
    card: AutoEntitiesInnerCardConfig = Field(default_factory=AutoEntitiesInnerCardConfig)
    filter: AutoEntitiesFilter = Field(default_factory=AutoEntitiesFilter)
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class LogbookTarget(BaseModel):
    """Logbook card target configuration."""

    model_config = ConfigDict(extra="allow")

    entity_id: list[str] | str = Field(default_factory=list)


class LogbookCardConfig(BaseModel):
    """Logbook card configuration."""

    model_config = ConfigDict(extra="allow")

    type: Literal["logbook"]
    target: LogbookTarget = Field(default_factory=LogbookTarget)
    entities: list[str] | str = Field(default_factory=list)
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class WeatherCardConfig(BaseModel):
    """Weather-forecast card configuration."""

    model_config = ConfigDict(extra="allow")

    type: Literal["weather-forecast"]
    entity: str | None = None
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class OtherCardConfig(BaseModel):
    """Catch-all for card types we don't render (picture-entity, map-card, etc.)."""

    model_config = ConfigDict(extra="allow")

    type: str
    visibility: list[VisibilityCondition] = Field(default_factory=list)


_KNOWN_CARD_TYPES = frozenset(
    {"tile", "heading", "custom:auto-entities", "logbook", "weather-forecast"}
)


def _card_type_discriminator(v: Any) -> str:
    t = v.get("type", "") if isinstance(v, dict) else getattr(v, "type", "")
    return t if t in _KNOWN_CARD_TYPES else "other"


CardConfig = Annotated[
    Annotated[TileCardConfig, Tag("tile")]
    | Annotated[HeadingCardConfig, Tag("heading")]
    | Annotated[AutoEntitiesCardConfig, Tag("custom:auto-entities")]
    | Annotated[LogbookCardConfig, Tag("logbook")]
    | Annotated[WeatherCardConfig, Tag("weather-forecast")]
    | Annotated[OtherCardConfig, Tag("other")],
    Discriminator(_card_type_discriminator),
]


class SectionConfig(BaseModel):
    """Dashboard section configuration."""

    model_config = ConfigDict(extra="allow")

    cards: list[CardConfig] = Field(default_factory=list)
    visibility: list[VisibilityCondition] = Field(default_factory=list)


class ViewConfig(BaseModel):
    """Dashboard view configuration (top-level YAML structure)."""

    model_config = ConfigDict(extra="allow")

    title: str = "View"
    path: str = ""
    icon: str | None = None
    badges: list[BadgeConfig] = Field(default_factory=list)
    sections: list[SectionConfig] = Field(default_factory=list)


# =============================================================================
# State formatting (pure function, no HA client needed)
# =============================================================================


def format_state(
    entity_id: str,
    state: str,
    *,
    device_class: str = "",
    unit: str = "",
) -> FormattedState:
    """Format an entity state into human-readable text with semantic color.

    Pure function — testable without a Home Assistant connection.
    This is the single source of truth for state formatting across all renderers.
    """
    domain = entity_id.split(".")[0]

    if state in ("unavailable", "unknown"):
        return FormattedState(text="?", color=SemanticColor.INACTIVE)

    if domain == "person":
        if state == "home":
            return FormattedState(text="Home", color=SemanticColor.POSITIVE)
        elif state == "not_home":
            return FormattedState(text="Away", color=SemanticColor.INACTIVE)
        return FormattedState(text=state, color=SemanticColor.INFO)

    if domain == "lock":
        if state == "locked":
            return FormattedState(text="Locked", color=SemanticColor.POSITIVE)
        return FormattedState(text="Unlocked", color=SemanticColor.DANGER)

    if domain == "cover":
        if state == "closed":
            return FormattedState(text="Closed", color=SemanticColor.POSITIVE)
        return FormattedState(text=state.title(), color=SemanticColor.WARNING)

    if domain == "binary_sensor":
        if device_class in ("door", "window", "garage_door", "opening"):
            if state == "on":
                return FormattedState(text="Open", color=SemanticColor.WARNING)
            return FormattedState(text="Closed", color=SemanticColor.POSITIVE)
        if device_class == "motion":
            if state == "on":
                return FormattedState(text="Motion", color=SemanticColor.WARNING)
            return FormattedState(text="Clear", color=SemanticColor.INACTIVE)
        if device_class == "occupancy":
            if state == "on":
                return FormattedState(text="Occupied", color=SemanticColor.ACTIVE)
            return FormattedState(text="Empty", color=SemanticColor.INACTIVE)
        if device_class in ("connectivity", "plug", "power"):
            if state == "on":
                return FormattedState(text="Connected", color=SemanticColor.POSITIVE)
            return FormattedState(text="Disconnected", color=SemanticColor.INACTIVE)
        if device_class == "battery":
            if state == "on":
                return FormattedState(text="Low", color=SemanticColor.DANGER)
            return FormattedState(text="OK", color=SemanticColor.POSITIVE)
        if device_class == "problem":
            if state == "on":
                return FormattedState(text="Problem", color=SemanticColor.DANGER)
            return FormattedState(text="OK", color=SemanticColor.POSITIVE)
        if state == "on":
            return FormattedState(text="On", color=SemanticColor.WARNING)
        return FormattedState(text="Off", color=SemanticColor.INACTIVE)

    if domain in ("light", "switch", "fan", "input_boolean"):
        if state == "on":
            return FormattedState(text="On", color=SemanticColor.ACTIVE)
        return FormattedState(text="Off", color=SemanticColor.INACTIVE)

    if domain == "alarm_control_panel":
        alarm_map: dict[str, tuple[str, SemanticColor]] = {
            "disarmed": ("Disarmed", SemanticColor.INACTIVE),
            "armed_home": ("Armed home", SemanticColor.POSITIVE),
            "armed_away": ("Armed away", SemanticColor.POSITIVE),
            "armed_night": ("Armed night", SemanticColor.POSITIVE),
            "armed_vacation": ("Armed vacation", SemanticColor.POSITIVE),
            "armed_custom_bypass": ("Armed custom", SemanticColor.POSITIVE),
            "triggered": ("TRIGGERED", SemanticColor.DANGER),
        }
        if state in alarm_map:
            text, color = alarm_map[state]
            return FormattedState(text=text, color=color)
        return FormattedState(text=state)

    if domain == "climate":
        climate_map: dict[str, tuple[str, SemanticColor]] = {
            "off": ("Off", SemanticColor.INACTIVE),
            "heat": ("Heating", SemanticColor.HEAT),
            "cool": ("Cooling", SemanticColor.COOL),
            "heat_cool": ("Auto", SemanticColor.INFO),
            "auto": ("Auto", SemanticColor.INFO),
        }
        if state in climate_map:
            text, color = climate_map[state]
            return FormattedState(text=text, color=color)
        return FormattedState(text=state.title())

    if domain == "sensor":
        try:
            val = float(state)
            state = str(int(val)) if val == int(val) else f"{val:.1f}"
        except ValueError:
            pass
        if unit:
            return FormattedState(text=f"{state}{unit}")
        return FormattedState(text=state)

    if domain == "weather":
        text = state.replace("_", " ").replace("partlycloudy", "Partly Cloudy").title()
        return FormattedState(text=text, color=SemanticColor.INFO)

    if domain == "image":
        return FormattedState(text="")

    return FormattedState(text=state)

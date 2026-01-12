"""Pydantic models for Home Assistant entities.

These models define the schema and field ordering for each entity type.
Field order in the model definition determines YAML output order.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseEntityModel(BaseModel):
    """Base model with common configuration."""

    model_config = ConfigDict(
        extra="allow",  # Allow extra fields not defined in model
        populate_by_name=True,
    )

    @classmethod
    def key_order(cls) -> list[str]:
        """Get field order from model definition."""
        return list(cls.model_fields.keys())

    @classmethod
    def normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Validate data and return ordered dict with None values excluded.

        This is the standard way to normalize entity configs for comparison
        and serialization. It ensures:
        - Data is validated against the model
        - Keys are ordered according to model field definition
        - None values are excluded
        - Extra fields are preserved
        """
        return cls.model_validate(data).model_dump(exclude_none=True)


# =============================================================================
# Automation
# =============================================================================


class Automation(BaseEntityModel):
    """Home Assistant automation.

    Note: HA uses 'triggers', 'conditions', 'actions' (plural) in newer versions.
    The model normalizes to plural form but accepts both for compatibility.
    """

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    alias: str = ""
    description: str = ""
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["single", "restart", "queued", "parallel"] = "single"

    @classmethod
    def normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Validate data and return ordered dict with normalized field names.

        Handles both singular (trigger/condition/action) and plural forms,
        normalizing to plural (triggers/conditions/actions).
        """
        # First, normalize singular to plural (newer HA format)
        normalized = dict(data)

        # Map singular to plural, merging if both exist
        for singular, plural in [
            ("trigger", "triggers"),
            ("condition", "conditions"),
            ("action", "actions"),
        ]:
            if singular in normalized:
                singular_val = normalized.pop(singular)
                # Only use singular value if plural is not set or is empty
                if plural not in normalized or not normalized[plural]:
                    normalized[plural] = singular_val

        return cls.model_validate(normalized).model_dump(exclude_none=True)


# =============================================================================
# Script
# =============================================================================


class Script(BaseEntityModel):
    """Home Assistant script."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    alias: str | None = None
    description: str | None = None
    icon: str | None = None
    mode: Literal["single", "restart", "queued", "parallel"] = "single"
    sequence: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Scene
# =============================================================================


class Scene(BaseEntityModel):
    """Home Assistant scene."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Helpers
# =============================================================================


class InputBoolean(BaseEntityModel):
    """Input boolean helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    initial: bool | None = None


class InputNumber(BaseEntityModel):
    """Input number helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    min: float = 0
    max: float = 100
    step: float = 1
    initial: float | None = None
    unit_of_measurement: str | None = None
    mode: Literal["box", "slider"] = "slider"


class InputSelect(BaseEntityModel):
    """Input select helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    options: list[str] = Field(default_factory=list)
    initial: str | None = None


class InputText(BaseEntityModel):
    """Input text helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    min: int = 0
    max: int = 100
    initial: str | None = None
    pattern: str | None = None
    mode: Literal["text", "password"] = "text"


class InputDatetime(BaseEntityModel):
    """Input datetime helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    has_date: bool = True
    has_time: bool = True
    initial: str | None = None


class InputButton(BaseEntityModel):
    """Input button helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None


class Timer(BaseEntityModel):
    """Timer helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    duration: str | None = None  # HH:MM:SS format
    restore: bool = True


class Schedule(BaseEntityModel):
    """Schedule helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    # Schedule stores time blocks per day - structure varies


class Counter(BaseEntityModel):
    """Counter helper."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    icon: str | None = None
    initial: int | None = None
    step: int = 1
    minimum: int | None = None
    maximum: int | None = None
    restore: bool = True


# Traditional input_* helpers (WebSocket-based)
HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "input_boolean": InputBoolean,
    "input_number": InputNumber,
    "input_select": InputSelect,
    "input_text": InputText,
    "input_datetime": InputDatetime,
    "input_button": InputButton,
    "timer": Timer,
    "schedule": Schedule,
    "counter": Counter,
}


# =============================================================================
# Config Entry-based Helpers (template, group)
# =============================================================================


class TemplateSensor(BaseEntityModel):
    """Template sensor helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., sensor.my_template) - optional, for renaming
    name: str
    step_id: Literal["sensor"] = "sensor"
    state: str  # Template string
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    device_id: str | None = None
    availability: str | None = None


class TemplateBinarySensor(BaseEntityModel):
    """Template binary sensor helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., binary_sensor.my_template) - optional, for renaming
    name: str
    step_id: Literal["binary_sensor"] = "binary_sensor"
    state: str  # Template string
    device_class: str | None = None
    device_id: str | None = None
    availability: str | None = None


class TemplateSwitch(BaseEntityModel):
    """Template switch helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., switch.my_template) - optional, for renaming
    name: str
    step_id: Literal["switch"] = "switch"
    value_template: str | None = None
    turn_on: list[dict[str, Any]] | None = None
    turn_off: list[dict[str, Any]] | None = None
    device_id: str | None = None
    availability: str | None = None


class GroupBinarySensor(BaseEntityModel):
    """Group binary sensor helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., binary_sensor.all_motion) - optional, for renaming
    name: str
    step_id: Literal["binary_sensor"] = "binary_sensor"
    entities: list[str] = Field(default_factory=list)
    hide_members: bool = False
    all: bool = False


class GroupSensor(BaseEntityModel):
    """Group sensor helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., sensor.average_temp) - optional, for renaming
    name: str
    step_id: Literal["sensor"] = "sensor"
    entities: list[str] = Field(default_factory=list)
    type: str | None = None  # min, max, mean, etc.
    hide_members: bool = False


class GroupLight(BaseEntityModel):
    """Group light helper."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., light.all_lights) - optional, for renaming
    name: str
    step_id: Literal["light"] = "light"
    entities: list[str] = Field(default_factory=list)
    hide_members: bool = False
    all: bool = False


# Template helper models by step_id (entity type)
# UI supports: alarm_control_panel, binary_sensor, button, cover, event, fan,
# image, light, lock, number, select, sensor, switch, update, vacuum, weather
# We define models for common ones; others use generic handling with extra="allow"
TEMPLATE_HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "sensor": TemplateSensor,
    "binary_sensor": TemplateBinarySensor,
    "switch": TemplateSwitch,
    # Additional types supported via generic handling:
    # alarm_control_panel, button, cover, event, fan, image, light,
    # lock, number, select, update, vacuum, weather
}

# All template entity types that can be created via UI
TEMPLATE_ENTITY_TYPES = {
    "alarm_control_panel",
    "binary_sensor",
    "button",
    "cover",
    "event",
    "fan",
    "image",
    "light",
    "lock",
    "number",
    "select",
    "sensor",
    "switch",
    "update",
    "vacuum",
    "weather",
}

# Group helper models by step_id (entity type)
# UI supports: binary_sensor, button, cover, event, fan, light, lock,
# media_player, notify, number, sensor, switch, valve
# We define models for common ones; others use generic handling with extra="allow"
GROUP_HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "binary_sensor": GroupBinarySensor,
    "sensor": GroupSensor,
    "light": GroupLight,
    # Additional types supported via generic handling:
    # button, cover, event, fan, lock, media_player, notify, number, switch, valve
}

# All group entity types that can be created via UI
GROUP_ENTITY_TYPES = {
    "binary_sensor",
    "button",
    "cover",
    "event",
    "fan",
    "light",
    "lock",
    "media_player",
    "notify",
    "number",
    "sensor",
    "switch",
    "valve",
}


# =============================================================================
# Other Config Entry Helpers (integration, utility_meter, etc.)
# =============================================================================


class IntegrationHelper(BaseEntityModel):
    """Integration helper (Riemann sum integral - converts power to energy)."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., sensor.energy_total) - optional, for renaming
    name: str
    source: str  # Source sensor entity_id
    method: str = "trapezoidal"  # left, right, trapezoidal
    round: float | None = None
    max_sub_interval: dict[str, int] | None = None  # {"hours": 0, "minutes": 0, "seconds": 0}


class UtilityMeterHelper(BaseEntityModel):
    """Utility meter helper (tracks consumption over time periods)."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., sensor.electricity_daily) - optional, for renaming
    name: str
    source: str  # Source sensor entity_id
    cycle: str | None = None  # hourly, daily, weekly, monthly, quarterly, yearly
    offset: int | None = None
    periodically_resetting: bool = True
    always_available: bool = False
    delta_values: bool = False
    net_consumption: bool = False
    tariffs: list[str] | None = None


class ThresholdHelper(BaseEntityModel):
    """Threshold helper (binary sensor based on numeric threshold)."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., binary_sensor.motion_detected) - for renaming
    name: str
    entity_id: str  # Source entity to monitor
    hysteresis: float = 0.0
    lower: float | None = None
    upper: float | None = None


class TodHelper(BaseEntityModel):
    """Time of Day helper (binary sensor for time periods)."""

    entry_id: str
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # Entity ID (e.g., binary_sensor.daytime) - optional, for renaming
    name: str
    after_time: str  # HH:MM:SS format
    before_time: str  # HH:MM:SS format


# =============================================================================
# Dashboard
# =============================================================================


class DashboardMeta(BaseEntityModel):
    """Dashboard metadata stored in _meta.yaml."""

    title: str
    icon: str | None = None
    url_path: str | None = None
    show_in_sidebar: bool = True
    require_admin: bool = False


class View(BaseEntityModel):
    """Dashboard view."""

    position: int | None = None
    type: str | None = None
    title: str | None = None
    path: str | None = None
    icon: str | None = None
    badges: list[dict[str, Any]] | None = None
    cards: list[dict[str, Any]] = Field(default_factory=list)


class Dashboard(BaseEntityModel):
    """Complete dashboard configuration."""

    title: str = ""
    views: list[View] = Field(default_factory=list)


# =============================================================================
# Key order exports (derived from models)
# =============================================================================

AUTOMATION_KEY_ORDER = Automation.key_order()
SCRIPT_KEY_ORDER = Script.key_order()
SCENE_KEY_ORDER = Scene.key_order()
HELPER_KEY_ORDER = InputBoolean.key_order()  # Base helper fields (id, name, icon)
VIEW_KEY_ORDER = View.key_order()
DASHBOARD_META_KEY_ORDER = DashboardMeta.key_order()

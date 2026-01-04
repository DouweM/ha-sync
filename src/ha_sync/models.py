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
    """Home Assistant automation."""

    id: str
    alias: str = ""
    description: str = ""
    trigger: list[dict[str, Any]] = Field(default_factory=list)
    condition: list[dict[str, Any]] = Field(default_factory=list)
    action: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["single", "restart", "queued", "parallel"] = "single"


# =============================================================================
# Script
# =============================================================================


class Script(BaseEntityModel):
    """Home Assistant script."""

    id: str
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

    id: str
    name: str
    icon: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Helpers
# =============================================================================


class InputBoolean(BaseEntityModel):
    """Input boolean helper."""

    id: str
    name: str
    icon: str | None = None
    initial: bool | None = None


class InputNumber(BaseEntityModel):
    """Input number helper."""

    id: str
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

    id: str
    name: str
    icon: str | None = None
    options: list[str] = Field(default_factory=list)
    initial: str | None = None


class InputText(BaseEntityModel):
    """Input text helper."""

    id: str
    name: str
    icon: str | None = None
    min: int = 0
    max: int = 100
    initial: str | None = None
    pattern: str | None = None
    mode: Literal["text", "password"] = "text"


class InputDatetime(BaseEntityModel):
    """Input datetime helper."""

    id: str
    name: str
    icon: str | None = None
    has_date: bool = True
    has_time: bool = True
    initial: str | None = None


class InputButton(BaseEntityModel):
    """Input button helper."""

    id: str
    name: str
    icon: str | None = None


# Traditional input_* helpers (WebSocket-based)
HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "input_boolean": InputBoolean,
    "input_number": InputNumber,
    "input_select": InputSelect,
    "input_text": InputText,
    "input_datetime": InputDatetime,
    "input_button": InputButton,
}


# =============================================================================
# Config Entry-based Helpers (template, group)
# =============================================================================


class TemplateSensor(BaseEntityModel):
    """Template sensor helper."""

    entry_id: str
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
    name: str
    step_id: Literal["binary_sensor"] = "binary_sensor"
    state: str  # Template string
    device_class: str | None = None
    device_id: str | None = None
    availability: str | None = None


class TemplateSwitch(BaseEntityModel):
    """Template switch helper."""

    entry_id: str
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
    name: str
    step_id: Literal["binary_sensor"] = "binary_sensor"
    entities: list[str] = Field(default_factory=list)
    hide_members: bool = False
    all: bool = False


class GroupSensor(BaseEntityModel):
    """Group sensor helper."""

    entry_id: str
    name: str
    step_id: Literal["sensor"] = "sensor"
    entities: list[str] = Field(default_factory=list)
    type: str | None = None  # min, max, mean, etc.
    hide_members: bool = False


class GroupLight(BaseEntityModel):
    """Group light helper."""

    entry_id: str
    name: str
    step_id: Literal["light"] = "light"
    entities: list[str] = Field(default_factory=list)
    hide_members: bool = False
    all: bool = False


# Template helper models by step_id (entity type)
TEMPLATE_HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "sensor": TemplateSensor,
    "binary_sensor": TemplateBinarySensor,
    "switch": TemplateSwitch,
}

# Group helper models by step_id (entity type)
GROUP_HELPER_MODELS: dict[str, type[BaseEntityModel]] = {
    "binary_sensor": GroupBinarySensor,
    "sensor": GroupSensor,
    "light": GroupLight,
}


# =============================================================================
# Other Config Entry Helpers (integration, utility_meter, etc.)
# =============================================================================


class IntegrationHelper(BaseEntityModel):
    """Integration helper (Riemann sum integral - converts power to energy)."""

    entry_id: str
    name: str
    source: str  # Source sensor entity_id
    method: str = "trapezoidal"  # left, right, trapezoidal
    round: float | None = None
    max_sub_interval: dict[str, int] | None = None  # {"hours": 0, "minutes": 0, "seconds": 0}


class UtilityMeterHelper(BaseEntityModel):
    """Utility meter helper (tracks consumption over time periods)."""

    entry_id: str
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
    name: str
    entity_id: str  # Source entity to monitor
    hysteresis: float = 0.0
    lower: float | None = None
    upper: float | None = None


class TodHelper(BaseEntityModel):
    """Time of Day helper (binary sensor for time periods)."""

    entry_id: str
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

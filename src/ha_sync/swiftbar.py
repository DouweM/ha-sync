"""Render a Home Assistant dashboard view as SwiftBar menu bar output."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ha_sync.client import HAClient

from ha_sync.render_models import (
    RenderedAutoEntities,
    RenderedBadge,
    RenderedEntityBadge,
    RenderedHeading,
    RenderedIcon,
    RenderedLogbook,
    RenderedSection,
    RenderedSpacing,
    RenderedTemplateBadge,
    RenderedTile,
    RenderedView,
    RenderedWeather,
    SemanticColor,
)

# MDI -> SF Symbol mapping (ported from watchOS IconMapper.swift)
MDI_TO_SF_SYMBOL: dict[str, str] = {
    # Home / Building
    "home": "house.fill",
    "home-circle": "house.circle.fill",
    "home-heart": "house.fill",
    "house": "house.fill",
    "home-account": "person.2.fill",
    # People
    "account": "person.fill",
    "account-group": "person.2.fill",
    "account-multiple": "person.2.fill",
    "human": "person.fill",
    "face-man": "person.fill",
    "face-woman": "person.fill",
    "face": "person.fill",
    "baby-face": "face.smiling",
    "baby-face-outline": "face.smiling",
    "baby-buggy": "stroller.fill",
    "baby-carriage": "stroller.fill",
    "stroller": "stroller.fill",
    # Pets
    "cat": "cat.fill",
    "cats": "cat.fill",
    "dog": "dog.fill",
    "paw": "pawprint.fill",
    "fishbowl": "fish.fill",
    "fishbowl-outline": "fish.fill",
    # Lighting
    "lightbulb": "lightbulb.fill",
    "lightbulb-outline": "lightbulb",
    "lightbulb-group": "lightbulb.2.fill",
    "light": "lightbulb.fill",
    "lamp": "lamp.desk.fill",
    "lamp-outline": "lamp.desk",
    "floor-lamp": "lamp.floor.fill",
    "floor-lamp-dual": "lamp.floor.fill",
    "desk-lamp": "lamp.desk.fill",
    "ceiling-light": "lamp.ceiling.fill",
    "ceiling-fan-light": "lamp.ceiling.fill",
    "track-light": "light.recessed.fill",
    "led-strip": "light.strip.leftright.fill",
    "led-strip-variant": "light.strip.leftright.fill",
    "pillar": "light.cylindrical.ceiling.fill",
    "wall-sconce": "light.panel.fill",
    "wall-sconce-round": "light.panel.fill",
    "outdoor-lamp": "lamp.floor.fill",
    "string-lights": "light.strip.leftright.fill",
    "looks": "sparkles",
    # Doors / Windows
    "door": "door.left.hand.closed",
    "door-open": "door.left.hand.open",
    "door-closed": "door.left.hand.closed",
    "door-closed-lock": "door.left.hand.closed",
    "garage-variant": "door.garage.closed",
    "garage-variant-lock": "door.garage.closed",
    "garage-open-variant": "door.garage.open",
    "window-closed": "window.vertical.closed",
    "window-closed-variant": "window.vertical.closed",
    "window-open": "window.vertical.open",
    "window-open-variant": "window.vertical.open",
    "blinds": "blinds.vertical.closed",
    "blinds-open": "blinds.vertical.open",
    "roller-shade": "blinds.vertical.closed",
    "roller-shade-closed": "blinds.vertical.closed",
    "curtains": "curtains.closed",
    "curtains-closed": "curtains.closed",
    # Climate / HVAC
    "fan": "fan.fill",
    "fan-off": "fan",
    "ceiling-fan": "fan.ceiling.fill",
    "thermometer": "thermometer.medium",
    "thermometer-high": "thermometer.high",
    "thermometer-low": "thermometer.low",
    "home-thermometer": "thermometer.medium",
    "home-thermometer-outline": "thermometer.medium",
    "water-thermometer": "thermometer.medium",
    "coolant-temperature": "thermometer.medium",
    "heat-pump": "thermometer.medium",
    "hvac": "thermometer.medium",
    "air-conditioner": "snowflake",
    "snowflake": "snowflake",
    "fire": "flame.fill",
    "radiator": "flame.fill",
    "radiator-off": "flame",
    "heating-coil": "flame.fill",
    # Weather
    "weather-sunny": "sun.max.fill",
    "weather-night": "moon.fill",
    "weather-cloudy": "cloud.fill",
    "weather-partly-cloudy": "cloud.sun.fill",
    "weather-partly-rainy": "cloud.sun.rain.fill",
    "weather-rainy": "cloud.rain.fill",
    "weather-pouring": "cloud.heavyrain.fill",
    "weather-snowy": "cloud.snow.fill",
    "weather-snowy-rainy": "cloud.sleet.fill",
    "weather-fog": "cloud.fog.fill",
    "weather-hazy": "sun.haze.fill",
    "weather-windy": "wind",
    "weather-windy-variant": "wind",
    "weather-lightning": "cloud.bolt.fill",
    "weather-lightning-rainy": "cloud.bolt.rain.fill",
    "weather-tornado": "tornado",
    "weather-hurricane": "hurricane",
    "weather-sunset-up": "sunrise.fill",
    "weather-sunset-down": "sunset.fill",
    "sun-clock": "sun.max.fill",
    "sun-wireless": "sun.max.fill",
    "sun-wireless-outline": "sun.max.fill",
    # Security
    "lock": "lock.fill",
    "lock-open": "lock.open.fill",
    "lock-smart": "lock.fill",
    "lock-outline": "lock",
    "shield": "shield.fill",
    "shield-home": "shield.fill",
    "shield-moon": "moon.fill",
    "shield-sun": "sun.max.fill",
    "alarm-panel": "bell.shield.fill",
    "cctv": "video.fill",
    "webcam": "camera.fill",
    "bell": "bell.fill",
    "bell-ring": "bell.badge.fill",
    "motion-sensor": "sensor.fill",
    # Appliances
    "washing-machine": "washer.fill",
    "tumble-dryer": "dryer.fill",
    "dryer": "dryer.fill",
    "dishwasher": "dishwasher.fill",
    "stove": "stove.fill",
    "oven": "oven.fill",
    "microwave": "microwave.fill",
    "fridge": "refrigerator.fill",
    "fridge-outline": "refrigerator",
    "robot-vacuum": "robot.fill",
    "robot": "robot.fill",
    "hot-tub": "bathtub.fill",
    "shower": "shower.fill",
    # Media
    "television": "tv.fill",
    "tv": "tv.fill",
    "desktop-tower-monitor": "desktopcomputer",
    "monitor": "display",
    "speaker": "hifispeaker.fill",
    "speaker-wireless": "hifispeaker.fill",
    "music": "music.note",
    "play": "play.fill",
    "pause": "pause.fill",
    "stop": "stop.fill",
    "plex": "play.fill",
    "hdmi-port": "tv.fill",
    "video-input-hdmi": "tv.fill",
    "controller": "gamecontroller.fill",
    "volume": "speaker.wave.2.fill",
    "volume-high": "speaker.wave.3.fill",
    "volume-off": "speaker.slash.fill",
    # Network / Connectivity
    "wifi": "wifi",
    "wifi-off": "wifi.slash",
    "access-point": "wifi.router.fill",
    "access-point-network": "wifi.router.fill",
    "server": "server.rack",
    "printer": "printer.fill",
    "printer-3d": "printer.fill",
    "cellphone": "iphone",
    "phone": "phone.fill",
    "devices": "laptopcomputer.and.iphone",
    # Navigation / Location
    "map": "map.fill",
    "map-marker": "mappin.circle.fill",
    "home-map-marker": "mappin.circle.fill",
    "pin": "mappin",
    "pin-outline": "mappin",
    "airplane": "airplane",
    # Power / Energy
    "power-plug": "powerplug.fill",
    "power-plug-battery": "battery.100.bolt",
    "power-socket": "powerplug.fill",
    "ev-station": "ev.plug.dc.ccs1",
    "battery": "battery.100",
    "battery-charging": "battery.100.bolt",
    "battery-low": "battery.25",
    "battery-medium": "battery.50",
    "battery-high": "battery.75",
    "lightning-bolt": "bolt.fill",
    "solar-power": "sun.max.fill",
    "solar-power-variant": "sun.max.fill",
    "solar-panel": "sun.max.fill",
    "transmission-tower": "bolt.fill",
    "home-lightning-bolt": "house.fill",
    "home-lightning-bolt-outline": "house.fill",
    # Transport
    "car": "car.fill",
    "car-estate": "car.fill",
    "car-door": "car.fill",
    "car-tire-alert": "car.fill",
    "car-sports": "car.fill",
    "gas-station": "fuelpump.fill",
    "fuel": "fuelpump.fill",
    # Work / Activity
    "briefcase": "briefcase.fill",
    "weight-lifter": "figure.strengthtraining.traditional",
    # Misc
    "sofa": "sofa.fill",
    "bed": "bed.double.fill",
    "bed-outline": "bed.double",
    "bed-king": "bed.double.fill",
    "hanger": "tshirt.fill",
    "glass-cocktail": "wineglass.fill",
    "fountain": "drop.fill",
    "tree": "tree.fill",
    "flower": "leaf.fill",
    "greenhouse": "leaf.fill",
    "water": "drop.fill",
    "water-pump": "drop.fill",
    "waves": "water.waves",
    "air-filter": "aqi.medium",
    "air-purifier": "aqi.medium",
    "gauge": "gauge.with.needle.fill",
    "gauge-empty": "gauge.with.needle",
    "gauge-full": "gauge.with.needle.fill",
    "history": "clock.arrow.circlepath",
    "time": "clock.fill",
    "video": "video.fill",
    "video-off": "video.slash.fill",
    "format-list-bulleted-type": "list.bullet",
    "launch": "arrow.up.right.square",
    "account-question": "questionmark.circle.fill",
    "account-check": "checkmark.circle.fill",
    "rotate": "arrow.triangle.2.circlepath",
    "rotate-3d": "arrow.triangle.2.circlepath",
    "party-popper": "party.popper.fill",
    "exit-run": "figure.walk",
    "run": "figure.run",
    "home-export-outline": "figure.walk",
    "account-arrow-right": "figure.walk",
    "select": "list.bullet",
    "input-boolean": "togglepower",
    "button": "button.horizontal.fill",
    "input-select": "list.bullet",
    "input-button": "button.horizontal.fill",
}

DOMAIN_TO_SF_SYMBOL: dict[str, str] = {
    "person": "person.fill",
    "light": "lightbulb.fill",
    "switch": "powerplug.fill",
    "fan": "fan.fill",
    "climate": "thermometer.medium",
    "lock": "lock.fill",
    "cover": "door.left.hand.closed",
    "sensor": "gauge.with.needle.fill",
    "binary_sensor": "bolt.fill",
    "camera": "video.fill",
    "media_player": "tv.fill",
    "alarm_control_panel": "shield.fill",
    "input_boolean": "togglepower",
    "weather": "sun.max.fill",
    "input_datetime": "clock.fill",
    "input_number": "number",
    "zone": "mappin.circle.fill",
    "device_tracker": "mappin.circle.fill",
    "image": "photo",
    "select": "list.bullet",
    "button": "button.horizontal.fill",
    "number": "number",
    "vacuum": "robot.fill",
    "input_select": "list.bullet",
    "input_button": "button.horizontal.fill",
    "automation": "gearshape.fill",
    "script": "scroll.fill",
    "scene": "theatermasks.fill",
    "group": "rectangle.3.group.fill",
    "timer": "timer",
    "counter": "number.circle.fill",
    "update": "arrow.down.circle.fill",
    "remote": "appletvremote.gen4.fill",
    "siren": "megaphone.fill",
    "water_heater": "flame.fill",
    "humidifier": "humidity.fill",
}

DEVICE_CLASS_TO_SF_SYMBOL: dict[str, str] = {
    "temperature": "thermometer.medium",
    "humidity": "humidity.fill",
    "battery": "battery.100",
    "power": "bolt.fill",
    "energy": "bolt.fill",
    "voltage": "bolt.fill",
    "current": "bolt.fill",
    "illuminance": "sun.max.fill",
    "pressure": "gauge.with.needle.fill",
    "carbon_dioxide": "aqi.medium",
    "carbon_monoxide": "aqi.medium",
    "pm25": "aqi.medium",
    "pm10": "aqi.medium",
    "volatile_organic_compounds": "aqi.medium",
    "nitrogen_dioxide": "aqi.medium",
    "motion": "figure.walk",
    "occupancy": "person.fill",
    "door": "door.left.hand.closed",
    "window": "window.vertical.closed",
    "moisture": "drop.fill",
    "gas": "flame.fill",
    "connectivity": "wifi",
    "plug": "powerplug.fill",
    "problem": "exclamationmark.triangle.fill",
    "safety": "exclamationmark.shield.fill",
    "sound": "speaker.wave.2.fill",
    "vibration": "waveform",
    "opening": "door.left.hand.open",
    "garage_door": "door.garage.closed",
}

WEATHER_CONDITION_TO_SF_SYMBOL: dict[str, str] = {
    "clear-night": "moon.stars.fill",
    "cloudy": "cloud.fill",
    "exceptional": "exclamationmark.triangle.fill",
    "fog": "cloud.fog.fill",
    "hail": "cloud.hail.fill",
    "lightning": "cloud.bolt.fill",
    "lightning-rainy": "cloud.bolt.rain.fill",
    "partlycloudy": "cloud.sun.fill",
    "pouring": "cloud.heavyrain.fill",
    "rainy": "cloud.rain.fill",
    "snowy": "cloud.snow.fill",
    "snowy-rainy": "cloud.sleet.fill",
    "sunny": "sun.max.fill",
    "windy": "wind",
    "windy-variant": "wind",
}


# --- SwiftBar output helpers ---

_xbar_nesting = 0


@contextmanager
def xbar_submenu() -> Generator[None]:
    global _xbar_nesting
    _xbar_nesting += 1
    try:
        yield
    finally:
        _xbar_nesting -= 1


def xbar_sep() -> None:
    print("--" * _xbar_nesting + "---", flush=True)


def xbar(text: str | None = None, **params: Any) -> None:
    segments: list[str] = []

    if text:
        segments.append(str(text))

    # Default to disabling emoji/symbol interpretation in dropdown items
    # to prevent SwiftBar from misinterpreting colons or text as emoji
    if _xbar_nesting > 0 or text:
        params.setdefault("emojize", False)
        params.setdefault("symbolize", False)

    params_segments = [f"{key}={value}" for key, value in params.items() if value is not None]
    if params_segments:
        segments.append("|")
        segments.extend(params_segments)

    if segments:
        print("--" * _xbar_nesting + " ".join(segments), flush=True)


def xbar_kv(label: str, value: str, **params: Any) -> None:
    xbar(f"{label}\t{value}", **params)


# --- SF Symbol resolution ---


def resolve_sf_symbol(icon: RenderedIcon) -> str:
    """Resolve a RenderedIcon to an SF Symbol name."""
    mdi_name = icon.mdi_name

    if not mdi_name and icon.entity_id:
        if icon.device_class and icon.device_class in DEVICE_CLASS_TO_SF_SYMBOL:
            return DEVICE_CLASS_TO_SF_SYMBOL[icon.device_class]
        domain = icon.entity_id.split(".")[0]
        return DOMAIN_TO_SF_SYMBOL.get(domain, "circle.fill")

    if not mdi_name:
        return "circle.fill"

    # Direct lookup
    if mdi_name in MDI_TO_SF_SYMBOL:
        return MDI_TO_SF_SYMBOL[mdi_name]

    # Weather condition lookup (HA states like "weather-partlycloudy")
    if mdi_name.startswith("weather-"):
        condition = mdi_name.removeprefix("weather-")
        if condition in WEATHER_CONDITION_TO_SF_SYMBOL:
            return WEATHER_CONDITION_TO_SF_SYMBOL[condition]

    # Partial match
    for key, symbol in MDI_TO_SF_SYMBOL.items():
        if key in mdi_name:
            return symbol

    # Fallback to device class / domain
    if icon.device_class and icon.device_class in DEVICE_CLASS_TO_SF_SYMBOL:
        return DEVICE_CLASS_TO_SF_SYMBOL[icon.device_class]
    if icon.entity_id:
        domain = icon.entity_id.split(".")[0]
        return DOMAIN_TO_SF_SYMBOL.get(domain, "circle.fill")

    return "circle.fill"


class SwiftBarViewRenderer:
    """Renders a RenderedView as SwiftBar menu bar output.

    Pure, sync transformation: RenderedView -> stdout print calls.
    No HAClient, no async, no data fetching.
    """

    SEMANTIC_COLOR_MAP: ClassVar[dict[SemanticColor, str]] = {
        SemanticColor.INACTIVE: "gray",
        SemanticColor.POSITIVE: "green",
        SemanticColor.ACTIVE: "#F5A623",
        SemanticColor.WARNING: "#F5A623",
        SemanticColor.DANGER: "red",
        SemanticColor.INFO: "#4A90D9",
        SemanticColor.HEAT: "red",
        SemanticColor.COOL: "#4A90D9",
    }

    def _resolve_color(self, color: SemanticColor | None) -> str | None:
        if color is None:
            return None
        return self.SEMANTIC_COLOR_MAP.get(color)

    def _resolve_icon(self, icon: RenderedIcon) -> str:
        """Resolve icon to SF Symbol, with weather condition override."""
        return resolve_sf_symbol(icon)

    def _resolve_weather_icon(self, weather: RenderedWeather) -> str:
        """Use condition-based SF Symbol for weather entities."""
        return WEATHER_CONDITION_TO_SF_SYMBOL.get(weather.raw_condition, "cloud.fill")

    def render(self, view: RenderedView) -> None:
        """Render a RenderedView as SwiftBar output to stdout."""
        # Menu bar header (icon only)
        sf = self._resolve_icon(view.icon)
        xbar(sfimage=sf)

        xbar_sep()

        # Badges
        for badge in view.badges:
            self._render_badge(badge)

        # Sections
        for section in view.sections:
            self._render_section(section)

        # Footer
        xbar_sep()
        xbar("Refresh", sfimage="arrow.clockwise", refresh=True)

    def _render_badge(self, badge: RenderedBadge) -> None:
        if isinstance(badge, RenderedEntityBadge):
            sf = self._resolve_icon(badge.icon)
            state_text = badge.state.text
            text = f"{badge.name}\t{state_text}" if state_text else badge.name
            params: dict[str, Any] = {"sfimage": sf}
            color = self._resolve_color(badge.state.color)
            if color:
                params["sfcolor"] = color
            xbar(text, **params)

        elif isinstance(badge, RenderedTemplateBadge):
            sf = self._resolve_icon(badge.icon)
            parts = []
            if badge.content:
                parts.append(badge.content)
            if badge.label:
                parts.append(f"({badge.label})")
            if not parts:
                return
            text = " ".join(parts)
            params = {"sfimage": sf}
            color = self._resolve_color(badge.content_color)
            if color:
                params["sfcolor"] = color
            xbar(text, **params)

    def _render_section(self, section: RenderedSection) -> None:
        for item in section.items:
            if isinstance(item, RenderedSpacing):
                xbar_sep()
            elif isinstance(item, RenderedHeading):
                self._render_heading(item)
            elif isinstance(item, RenderedTile):
                self._render_tile(item)
            elif isinstance(item, RenderedAutoEntities):
                for tile in item.tiles:
                    self._render_tile(tile)
            elif isinstance(item, RenderedLogbook):
                for entry in item.entries:
                    sf = self._resolve_icon(entry.icon)
                    text = f"{entry.name}\t{entry.state.text} ({entry.time_ago})"
                    params: dict[str, Any] = {"sfimage": sf}
                    color = self._resolve_color(entry.state.color)
                    if color:
                        params["sfcolor"] = color
                    xbar(text, **params)
            elif isinstance(item, RenderedWeather):
                sf = self._resolve_weather_icon(item)
                text = (
                    f"{item.condition}\t{item.temperature}" if item.temperature else item.condition
                )
                xbar(text, sfimage=sf, sfcolor="#4A90D9")

    def _render_heading(self, heading: RenderedHeading) -> None:
        sf = self._resolve_icon(heading.icon)
        xbar(heading.heading, sfimage=sf, size=13)
        for badge in heading.badges:
            self._render_badge(badge)

    def _render_tile(self, tile: RenderedTile) -> None:
        sf = self._resolve_icon(tile.icon)
        state_text = tile.state.text
        text = f"{tile.name}\t{state_text}" if state_text else tile.name
        params: dict[str, Any] = {"sfimage": sf}
        color = self._resolve_color(tile.state.color)
        if color:
            params["sfcolor"] = color
        xbar(text, **params)


async def render_view_swiftbar(
    client: HAClient, view_path: Path, user: str | None = None
) -> None:
    """Render a dashboard view file as SwiftBar output."""
    from ha_sync.render import ViewResolver

    resolver = ViewResolver(client)
    try:
        view = await resolver.resolve_view(view_path, user=user)
    except (FileNotFoundError, ValueError) as e:
        xbar(str(e), sfimage="exclamationmark.triangle.fill", color="red")
        return
    SwiftBarViewRenderer().render(view)

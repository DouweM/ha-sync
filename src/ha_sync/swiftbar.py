"""Render a Home Assistant dashboard view as SwiftBar menu bar output."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from ha_sync.client import HAClient
from ha_sync.render import ViewRenderer

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

# State -> color mapping for SwiftBar
STATE_COLORS: dict[str, str] = {
    "home": "green",
    "on": "#F5A623",
    "locked": "green",
    "closed": "green",
    "armed_home": "green",
    "armed_away": "green",
    "armed_night": "green",
    "armed_vacation": "green",
    "triggered": "red",
    "unavailable": "gray",
    "unknown": "gray",
    "off": "gray",
    "not_home": "gray",
    "idle": "gray",
    "standby": "gray",
    "disarmed": "gray",
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


def get_sf_symbol(
    icon: str | None,
    entity_id: str | None = None,
    device_class: str | None = None,
) -> str:
    """Resolve an MDI icon to an SF Symbol name."""
    if not icon and entity_id:
        if device_class and device_class in DEVICE_CLASS_TO_SF_SYMBOL:
            return DEVICE_CLASS_TO_SF_SYMBOL[device_class]
        domain = entity_id.split(".")[0]
        return DOMAIN_TO_SF_SYMBOL.get(domain, "circle.fill")

    if not icon:
        return "circle.fill"

    icon_name = icon.replace("mdi:", "").lower()

    # Direct lookup
    if icon_name in MDI_TO_SF_SYMBOL:
        return MDI_TO_SF_SYMBOL[icon_name]

    # Partial match
    for key, symbol in MDI_TO_SF_SYMBOL.items():
        if key in icon_name:
            return symbol

    # Fallback to device class / domain
    if device_class and device_class in DEVICE_CLASS_TO_SF_SYMBOL:
        return DEVICE_CLASS_TO_SF_SYMBOL[device_class]
    if entity_id:
        domain = entity_id.split(".")[0]
        return DOMAIN_TO_SF_SYMBOL.get(domain, "circle.fill")

    return "circle.fill"


def state_color(entity_id: str, state: str) -> str | None:
    """Get SwiftBar color for an entity state."""
    if state in STATE_COLORS:
        return STATE_COLORS[state]

    domain = entity_id.split(".")[0]
    if domain == "person" and state not in ("home", "not_home"):
        return "#4A90D9"  # Blue for named zones
    if domain in ("light", "switch", "fan", "input_boolean") and state == "on":
        return "#F5A623"
    return None


class SwiftBarRenderer(ViewRenderer):
    """Renders a Lovelace dashboard view as SwiftBar menu output."""

    def _sf_symbol(self, icon: str | None, entity_id: str | None = None) -> str:
        """Get SF Symbol for an icon/entity."""
        # Weather entities: use condition-based symbol
        if entity_id and entity_id.startswith("weather."):
            state = self.get_state(entity_id)
            if state and state in WEATHER_CONDITION_TO_SF_SYMBOL:
                return WEATHER_CONDITION_TO_SF_SYMBOL[state]
        device_class = self.state_cache.get(entity_id or "", {}).get("device_class", "")
        return get_sf_symbol(icon, entity_id, device_class)

    def _state_color(self, entity_id: str, state: str) -> str | None:
        return state_color(entity_id, state)

    async def render_view(self, view_path: Path, user: str | None = None) -> None:
        """Render a dashboard view as SwiftBar output."""
        if not view_path.exists():
            xbar("View not found", sfimage="exclamationmark.triangle.fill", color="red")
            return

        with open(view_path) as f:
            view = yaml.safe_load(f)

        if not view:
            xbar("Parse error", sfimage="exclamationmark.triangle.fill", color="red")
            return

        # Set up user
        if user:
            self.user_ids = await self.fetch_user_ids()
            user_name = user.lower()
            if user_name in self.user_ids:
                self.current_user = self.user_ids[user_name]
            else:
                xbar("Unknown user", sfimage="exclamationmark.triangle.fill", color="red")
                return

        # Fetch all entity states
        entities: set[str] = set()
        self.extract_entities(view, entities)
        await self.fetch_all_states(entities)

        # Menu bar header (icon only)
        icon = view.get("icon", "")
        sf = self._sf_symbol(icon)
        xbar(sfimage=sf)

        xbar_sep()

        # Badges
        for badge in view.get("badges", []):
            line = await self._render_badge_swiftbar(badge)
            if line:
                text, params = line
                xbar(text, **params)

        # Sections
        for section in view.get("sections", []):
            await self._render_section_swiftbar(section)

        # Footer
        xbar_sep()
        xbar("Refresh", sfimage="arrow.clockwise", refresh=True)

    async def _render_badge_swiftbar(
        self, badge: dict[str, Any]
    ) -> tuple[str, dict[str, Any]] | None:
        """Render a badge as (text, params) for SwiftBar."""
        if not self.check_visibility(badge.get("visibility", [])):
            return None

        badge_type = badge.get("type", "entity")

        if badge_type == "entity":
            entity_id = badge.get("entity")
            if not entity_id:
                return None

            state = self.get_state(entity_id)
            name = badge.get("name") or self.get_display_name(entity_id)
            icon = badge.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")
            show_state = badge.get("show_state", True)  # noqa: F841
            state_content = badge.get("state_content")

            sf = self._sf_symbol(icon, entity_id)
            formatted, _ = self.format_state(entity_id, state)

            text = f"{name}\t{formatted}" if state_content != "name" and formatted else name

            params: dict[str, Any] = {"sfimage": sf}
            color = self._state_color(entity_id, state)
            if color:
                params["sfcolor"] = color
            return text, params

        elif badge_type == "custom:mushroom-template-badge":
            entity_id = badge.get("entity")
            content = badge.get("content")
            label = badge.get("label")
            icon = badge.get("icon", "")

            sf = self._sf_symbol(icon, entity_id)
            parts = []

            if content:
                rendered = await self.eval_template(content)
                if rendered and rendered != "[error]":
                    parts.append(rendered)

            if label:
                rendered = await self.eval_template(label)
                if rendered and rendered != "[error]":
                    parts.append(f"({rendered})")

            if not parts:
                return None

            text = " ".join(parts)
            params = {"sfimage": sf}

            # Color based on content
            if parts:
                val = parts[0].lower()
                if val in ("home", "oasis"):
                    params["sfcolor"] = "green"
                elif val in ("away", "not_home"):
                    params["sfcolor"] = "gray"
                else:
                    params["sfcolor"] = "#4A90D9"

            return text, params

        return None

    async def _render_section_swiftbar(self, section: dict[str, Any]) -> None:
        """Render a section as SwiftBar output."""
        if not self.check_visibility(section.get("visibility", [])):
            return

        cards = section.get("cards", [])
        pending_heading: dict[str, Any] | None = None

        for card in cards:
            card_type = card.get("type", "")

            if card_type == "heading" and card.get("heading"):
                if not self.check_visibility(card.get("visibility", [])):
                    continue

                # Emit previous pending heading (had no non-heading content)
                if pending_heading:
                    await self._emit_heading_swiftbar(pending_heading)

                # Check if this heading has badges (inline content)
                heading_badges = card.get("badges", [])
                heading_badge_items = []
                for badge in heading_badges:
                    rendered = await self._render_badge_swiftbar(badge)
                    if rendered:
                        heading_badge_items.append(rendered)

                if heading_badge_items:
                    # Heading with badges — emit immediately
                    xbar_sep()
                    self._render_heading_swiftbar(card)
                    for text, params in heading_badge_items:
                        xbar(text, **params)
                    pending_heading = None
                else:
                    pending_heading = card
                continue

            card_items = await self._render_card_swiftbar(card)

            if card_items and pending_heading:
                xbar_sep()
                self._render_heading_swiftbar(pending_heading)
                pending_heading = None

            for text, params in card_items:
                xbar(text, **params)

        # Emit trailing heading with no content
        if pending_heading:
            await self._emit_heading_swiftbar(pending_heading)

    async def _emit_heading_swiftbar(self, card: dict[str, Any]) -> None:
        """Emit a heading that had no subsequent card content."""
        xbar_sep()
        self._render_heading_swiftbar(card)
        for badge in card.get("badges", []):
            rendered = await self._render_badge_swiftbar(badge)
            if rendered:
                text, params = rendered
                xbar(text, **params)

    def _render_heading_swiftbar(self, card: dict[str, Any]) -> None:
        """Render a heading card as SwiftBar output."""
        if not self.check_visibility(card.get("visibility", [])):
            return

        heading = card.get("heading", "")
        icon = card.get("icon", "")
        sf = self._sf_symbol(icon) if icon else "circle.fill"

        xbar(heading, sfimage=sf, size=13)

    async def _render_card_swiftbar(
        self, card: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Render a card as a list of (text, params) for SwiftBar."""
        if not self.check_visibility(card.get("visibility", [])):
            return []

        card_type = card.get("type", "")

        if card_type == "tile":
            item = self._render_tile_swiftbar(card)
            return [item] if item else []
        elif card_type == "custom:auto-entities":
            return await self._render_auto_entities_swiftbar(card)
        elif card_type == "logbook":
            return await self._render_logbook_swiftbar(card)
        elif card_type == "weather-forecast":
            result = await self.fetch_weather(card)
            if result:
                condition, temp_str, entity_id = result
                state = self.get_state(entity_id)
                sf = WEATHER_CONDITION_TO_SF_SYMBOL.get(state, "cloud.fill")
                text = f"{condition}\t{temp_str}" if temp_str else condition
                return [(text, {"sfimage": sf, "sfcolor": "#4A90D9"})]
            return []

        return []

    def _render_tile_swiftbar(
        self, card: dict[str, Any]
    ) -> tuple[str, dict[str, Any]] | None:
        """Render a tile card as (text, params) for SwiftBar."""
        if not self.check_visibility(card.get("visibility", [])):
            return None

        entity_id = card.get("entity")
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        name = card.get("name") or self.get_display_name(entity_id)
        icon = card.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")

        sf = self._sf_symbol(icon, entity_id)
        formatted, _ = self.format_state(entity_id, state)

        text = f"{name}\t{formatted}" if formatted else name
        params: dict[str, Any] = {"sfimage": sf}
        color = self._state_color(entity_id, state)
        if color:
            params["sfcolor"] = color
        return text, params

    async def _render_auto_entities_swiftbar(
        self, card: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Render auto-entities card as SwiftBar items."""
        items: list[tuple[str, dict[str, Any]]] = []

        for entity_id, name, icon, _options in await self.resolve_auto_entities(card):
            state = self.state_cache.get(entity_id, {}).get("state", "")
            sf = self._sf_symbol(icon, entity_id)
            formatted, _ = self.format_state(entity_id, state)

            text = f"{name}\t{formatted}" if formatted else name
            params: dict[str, Any] = {"sfimage": sf}
            color = self._state_color(entity_id, state)
            if color:
                params["sfcolor"] = color
            items.append((text, params))

        return items

    async def _render_logbook_swiftbar(
        self, card: dict[str, Any], max_entries: int = 5
    ) -> list[tuple[str, dict[str, Any]]]:
        """Render logbook card as SwiftBar items."""
        items: list[tuple[str, dict[str, Any]]] = []

        for entity_id, name, state, formatted, time_str in await self.fetch_logbook_entries(
            card, max_entries
        ):
            icon = self.state_cache.get(entity_id, {}).get("icon", "")
            sf = self._sf_symbol(icon, entity_id)
            text = f"{name}\t{formatted} ({time_str})"
            params: dict[str, Any] = {"sfimage": sf}
            color = self._state_color(entity_id, state)
            if color:
                params["sfcolor"] = color
            items.append((text, params))

        return items


async def render_view_swiftbar(
    client: HAClient, view_path: Path, user: str | None = None
) -> None:
    """Render a dashboard view file as SwiftBar output."""
    renderer = SwiftBarRenderer(client)
    await renderer.render_view(view_path, user)

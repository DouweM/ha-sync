"""Render a Home Assistant dashboard view as CLI text output."""

import json
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.text import Text

from ha_sync.client import HAClient

console = Console()


# Icon to emoji mappings
ICON_EMOJI = {
    "home": "🏠",
    "home-circle": "🏠",
    "home-heart": "🏠",
    "account": "👤",
    "account-group": "👥",
    "home-account": "👥",
    "television": "📺",
    "bed-king": "🛏️",
    "baby-face": "👶",
    "baby-face-outline": "👶",
    "desktop-tower-monitor": "🖥️",
    "sofa": "🛋️",
    "stove": "🍳",
    "tree": "🌳",
    "flower": "🌸",
    "greenhouse": "🌿",
    "garage-variant-lock": "🚗",
    "car-estate": "🚗",
    "thermometer": "🌡️",
    "home-thermometer": "🌡️",
    "home-thermometer-outline": "🌡️",
    "fan": "🌀",
    "lightbulb": "💡",
    "light": "💡",
    "track-light": "💡",
    "pillar": "🏛️",
    "shield": "🛡️",
    "shield-home": "🛡️",
    "shield-moon": "🌙",
    "shield-sun": "☀️",
    "lock": "🔒",
    "lock-smart": "🔐",
    "door": "🚪",
    "door-open": "🚪",
    "garage-variant": "🚗",
    "garage-open-variant": "🚗",
    "cctv": "📹",
    "webcam": "📷",
    "weather-sunny": "☀️",
    "weather-sunset-up": "🌅",
    "weather-sunset-down": "🌇",
    "sun-clock": "⏰",
    "history": "📜",
    "map": "🗺️",
    "map-marker": "📍",
    "home-map-marker": "📍",
    "music": "🎵",
    "speaker": "🔊",
    "hot-tub": "🛁",
    "fountain": "⛲",
    "sun-wireless": "☀️",
    "sun-wireless-outline": "☀️",
    "fishbowl": "🐟",
    "fishbowl-outline": "🐟",
    "glass-cocktail": "🍸",
    "hanger": "👔",
    "wifi": "📶",
    "airplane": "✈️",
    "looks": "✨",
    "led-strip": "💡",
    "led-strip-variant": "💡",
    "power-plug-battery": "🔋",
    "lightning-bolt": "⚡",
    "format-list-bulleted-type": "📋",
    "alarm-panel": "🚨",
    "controller": "🎮",
    "launch": "🚀",
    "account-question": "❓",
    "account-check": "✅",
    "washing-machine": "🧺",
    "human": "👤",
    "server": "🖥️",
    "plex": "▶️",
    "cats": "🐱",
    "cat": "🐱",
    "time": "🕐",
    "devices": "📱",
    "cellphone": "📱",
    "phone": "📱",
    "printer": "🖨️",
    "printer-3d": "🖨️",
    "air-filter": "🌬️",
    "air-purifier": "🌬️",
    "water-thermometer": "🌡️",
    "coolant-temperature": "🌡️",
    "gas-station": "⛽",
    "fuel": "⛽",
    "ev-station": "🔌",
    "car-door": "🚗",
    "car-tire-alert": "🚗",
    "window-closed": "🪟",
    "window-open": "🪟",
    "volume": "🔊",
    "volume-high": "🔊",
    "volume-off": "🔇",
    "radiator": "🔥",
    "radiator-off": "🔥",
    "heating-coil": "🔥",
    "video": "📹",
    "video-off": "📹",
    "baby-buggy": "👩‍🍼",
    "baby-carriage": "👩‍🍼",
    "stroller": "👩‍🍼",
    "face-man": "👨",
    "face-woman": "👩",
    "face": "👤",
    "battery": "🔋",
    "battery-charging": "🔋",
    "tumble-dryer": "🧺",
    "dryer": "🧺",
    "waves": "🌊",
    "water": "💧",
    "water-pump": "💧",
    "gauge": "📊",
    "gauge-empty": "📊",
    "gauge-full": "📊",
    "heat-pump": "🌡️",
    "hvac": "🌡️",
    "air-conditioner": "❄️",
    "pause": "⏸️",
    "play": "▶️",
    "stop": "⏹️",
    "robot-vacuum": "🤖",
    "robot": "🤖",
    "hdmi-port": "📺",
    "video-input-hdmi": "📺",
    "pin": "📌",
    "pin-outline": "📌",
    "rotate": "🔄",
    "rotate-3d": "🔄",
    "access-point": "📶",
    "access-point-network": "📶",
    "solar-power": "☀️",
    "solar-power-variant": "☀️",
    "solar-panel": "☀️",
    "transmission-tower": "⚡",
    "power-plug": "🔌",
    "power-socket": "🔌",
    "home-lightning-bolt": "🏠",
    "home-lightning-bolt-outline": "🏠",
    "party-popper": "🎉",
    "exit-run": "🏃",
    "run": "🏃",
    "home-export-outline": "🏃",
    "account-arrow-right": "🏃",
    "account-multiple": "👥",
    "bed": "🛏️",
    "bed-outline": "🛏️",
}

DOMAIN_EMOJI = {
    "person": "👤",
    "light": "💡",
    "switch": "🔌",
    "fan": "🌀",
    "climate": "🌡️",
    "lock": "🔒",
    "cover": "🚪",
    "sensor": "📊",
    "binary_sensor": "⚡",
    "camera": "📹",
    "media_player": "📺",
    "alarm_control_panel": "🛡️",
    "input_boolean": "🔘",
    "weather": "☀️",
    "input_datetime": "🕐",
    "input_number": "🔢",
    "zone": "📍",
    "device_tracker": "📍",
    "image": "🖼️",
    "select": "📋",
    "button": "🔘",
    "number": "🔢",
    "vacuum": "🤖",
    "input_select": "📋",
    "input_button": "🔘",
}

DEVICE_CLASS_EMOJI = {
    "temperature": "🌡️",
    "humidity": "💧",
    "battery": "🔋",
    "power": "⚡",
    "energy": "⚡",
    "voltage": "⚡",
    "current": "⚡",
    "illuminance": "☀️",
    "pressure": "🌡️",
    "carbon_dioxide": "💨",
    "carbon_monoxide": "💨",
    "pm25": "💨",
    "pm10": "💨",
    "volatile_organic_compounds": "💨",
    "nitrogen_dioxide": "💨",
    "motion": "🚶",
    "occupancy": "👤",
    "door": "🚪",
    "window": "🪟",
    "moisture": "💧",
    "gas": "🔥",
}


class ViewRenderer:
    """Renders a Lovelace dashboard view as CLI text output."""

    def __init__(self, client: HAClient) -> None:
        self.client = client
        self.state_cache: dict[str, dict[str, Any]] = {}
        self.user_ids: dict[str, str] = {}
        self.current_user: str | None = None
        self.label_cache: dict[str, set[str]] = {}

    async def fetch_user_ids(self) -> dict[str, str]:
        """Fetch user name to ID mapping from HA person entities."""
        template = (
            "[{% for p in states.person %}"
            '{"name": {{ p.name | lower | tojson }}, '
            '"user_id": {{ (p.attributes.user_id | default("")) | tojson }}}'
            "{% if not loop.last %},{% endif %}"
            "{% endfor %}]"
        )
        try:
            output = await self.client.render_template(template)
            output = output.replace("\n", "")
            persons = json.loads(output)
            return {p["name"]: p["user_id"] for p in persons if p.get("user_id")}
        except (json.JSONDecodeError, Exception):
            return {}

    def extract_entities(self, obj: Any, entities: set[str]) -> None:
        """Recursively extract all entity IDs from a YAML structure."""
        if isinstance(obj, dict):
            for key in ("entity", "entity_id"):
                if key in obj and isinstance(obj[key], str):
                    entities.add(obj[key])
                elif key in obj and isinstance(obj[key], list):
                    entities.update(e for e in obj[key] if isinstance(e, str))
            for v in obj.values():
                self.extract_entities(v, entities)
        elif isinstance(obj, list):
            for item in obj:
                self.extract_entities(item, entities)

    async def fetch_all_states(self, entities: set[str]) -> None:
        """Fetch all entity states in a single template call."""
        if not entities:
            return

        entity_list = list(entities)
        lines = []
        for e in entity_list:
            lines.append(
                f'{e}|||{{{{ states("{e}") }}}}|||'
                f'{{{{ state_attr("{e}", "friendly_name") '
                f'| default("", true) | replace("\\n", " ") }}}}|||'
                f'{{{{ state_attr("{e}", "unit_of_measurement") | default("", true) }}}}|||'
                f'{{{{ state_attr("{e}", "icon") | default("", true) }}}}|||'
                f'{{{{ state_attr("{e}", "device_class") | default("", true) }}}}'
            )

        template = "\n".join(lines)

        try:
            output = await self.client.render_template(template)
            for line in output.strip().split("\n"):
                parts = line.split("|||")
                if len(parts) >= 3:
                    entity_id = parts[0].strip()
                    state = parts[1].strip() if len(parts) > 1 else ""
                    name = parts[2].strip() if len(parts) > 2 else ""
                    unit = parts[3].strip() if len(parts) > 3 else ""
                    icon = parts[4].strip() if len(parts) > 4 else ""
                    device_class = parts[5].strip() if len(parts) > 5 else ""
                    self.state_cache[entity_id] = {
                        "state": state,
                        "name": name,
                        "unit": unit,
                        "icon": icon,
                        "device_class": device_class,
                    }
        except Exception as e:
            console.print(f"[dim]Warning: Failed to batch fetch states: {e}[/dim]")

    def get_state(self, entity_id: str) -> str:
        """Get current state of an entity from cache."""
        if entity_id in self.state_cache:
            return self.state_cache[entity_id].get("state", "unknown")
        return "unknown"

    def get_attribute(self, entity_id: str, attribute: str) -> Any:
        """Get an attribute of an entity from cache."""
        if entity_id in self.state_cache:
            if attribute == "friendly_name":
                return self.state_cache[entity_id].get("name")
            elif attribute == "unit_of_measurement":
                return self.state_cache[entity_id].get("unit")
        return None

    def get_display_name(self, entity_id: str) -> str:
        """Get friendly_name from HA, or clean up entity_id as fallback."""
        if entity_id in self.state_cache:
            name = self.state_cache[entity_id].get("name")
            if name:
                return name
        return entity_id.split(".")[-1].replace("_", " ").title()

    async def eval_template(self, template: str) -> str:
        """Evaluate a Jinja2 template."""
        try:
            return await self.client.render_template(template)
        except Exception:
            return "[error]"

    def check_visibility(self, conditions: list[dict[str, Any]]) -> bool:
        """Check if visibility conditions are met. Returns True if visible."""
        if not conditions:
            return True

        for condition in conditions:
            cond_type = condition.get("condition")

            if cond_type == "state":
                entity = condition.get("entity")
                if not entity:
                    return False
                state = self.get_state(entity)
                if "state" in condition and state != str(condition["state"]):
                    return False
                if "state_not" in condition and state == str(condition["state_not"]):
                    return False

            elif cond_type == "numeric_state":
                entity = condition.get("entity")
                if not entity:
                    return False
                state = self.get_state(entity)
                try:
                    value = float(state)
                    if "above" in condition and value <= float(condition["above"]):
                        return False
                    if "below" in condition and value >= float(condition["below"]):
                        return False
                except (ValueError, TypeError):
                    return False

            elif cond_type == "screen":
                media_query = condition.get("media_query", "")
                if "max-width: 767px" in media_query:
                    return False  # Mobile-only

            elif cond_type == "user":
                if self.current_user is None:
                    return False
                users = condition.get("users", [])
                if self.current_user not in users:
                    return False

            elif cond_type == "or":
                sub_conditions = condition.get("conditions", [])
                if not any(self.check_visibility([c]) for c in sub_conditions):
                    return False

            elif cond_type == "and":
                sub_conditions = condition.get("conditions", [])
                if not all(self.check_visibility([c]) for c in sub_conditions):
                    return False

            elif cond_type == "not":
                sub_conditions = condition.get("conditions", [])
                if self.check_visibility(sub_conditions):
                    return False

        return True

    def get_icon_emoji(self, icon: str | None, entity_id: str | None = None) -> str:
        """Convert MDI icon to emoji."""
        if not icon and entity_id:
            device_class = self.state_cache.get(entity_id, {}).get("device_class", "")
            if device_class and device_class in DEVICE_CLASS_EMOJI:
                return DEVICE_CLASS_EMOJI[device_class]
            domain = entity_id.split(".")[0]
            return DOMAIN_EMOJI.get(domain, "•")

        if not icon:
            return "•"

        icon_name = icon.replace("mdi:", "").lower()
        if icon_name in ICON_EMOJI:
            return ICON_EMOJI[icon_name]

        for key, emoji in ICON_EMOJI.items():
            if key in icon_name:
                return emoji

        return "•"

    def format_state(self, entity_id: str, state: str) -> tuple[str, str | None]:
        """Format entity state for display. Returns (text, style) where style is for rich."""
        domain = entity_id.split(".")[0]

        if state in ("unavailable", "unknown"):
            return "?", "dim"

        if domain == "person":
            if state == "home":
                return "Home", "green"
            elif state == "not_home":
                return "Away", "dim"
            else:
                return state, "cyan"
        elif domain == "lock":
            if state == "locked":
                return "Locked", "green"
            else:
                return "Unlocked", "bold red"
        elif domain == "cover":
            if state == "closed":
                return "Closed", "green"
            else:
                return state.title(), "bold yellow"
        elif domain == "binary_sensor":
            device_class = self.state_cache.get(entity_id, {}).get("device_class", "")
            if device_class in ("door", "window", "garage_door", "opening"):
                if state == "on":
                    return "Open", "bold yellow"
                return "Closed", "green"
            elif device_class == "motion":
                if state == "on":
                    return "Motion", "bold yellow"
                return "Clear", "dim"
            elif device_class == "occupancy":
                if state == "on":
                    return "Occupied", "yellow"
                return "Empty", "dim"
            elif device_class in ("connectivity", "plug", "power"):
                if state == "on":
                    return "Connected", "green"
                return "Disconnected", "dim"
            elif device_class == "battery":
                if state == "on":
                    return "Low", "bold red"
                return "OK", "green"
            elif device_class == "problem":
                if state == "on":
                    return "Problem", "bold red"
                return "OK", "green"
            else:
                if state == "on":
                    return "On", "bold yellow"
                return "Off", "dim"
        elif domain in ("light", "switch", "fan", "input_boolean"):
            if state == "on":
                return "On", "yellow"
            return "Off", "dim"
        elif domain == "alarm_control_panel":
            state_map = {
                "disarmed": ("Disarmed", "dim"),
                "armed_home": ("Armed", "green"),
                "armed_away": ("Armed", "green"),
                "triggered": ("TRIGGERED", "bold red"),
            }
            return state_map.get(state, (state, None))
        elif domain == "climate":
            state_map = {
                "off": ("Off", "dim"),
                "heat": ("Heating", "red"),
                "cool": ("Cooling", "blue"),
                "heat_cool": ("Auto", "cyan"),
                "auto": ("Auto", "cyan"),
            }
            return state_map.get(state, (state.title(), None))
        elif domain == "sensor":
            unit = self.get_attribute(entity_id, "unit_of_measurement")
            try:
                val = float(state)
                # Show integers without decimal places
                state = str(int(val)) if val == int(val) else f"{val:.1f}"
            except ValueError:
                pass
            if unit:
                return f"{state}{unit}", None
            return state, None
        elif domain == "weather":
            return state.replace("_", " ").replace("partlycloudy", "Partly Cloudy").title(), "cyan"
        elif domain == "image":
            return "", None

        return state, None

    async def render_badge(self, badge: dict[str, Any]) -> Text | None:
        """Render a single badge as a rich Text object."""
        if not self.check_visibility(badge.get("visibility", [])):
            return None

        badge_type = badge.get("type", "entity")

        if badge_type == "entity":
            entity_id = badge.get("entity")
            if not entity_id:
                return None

            state = self.get_state(entity_id)
            name = badge.get("name")
            icon = badge.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")
            show_state = badge.get("show_state", True)
            state_content = badge.get("state_content")

            emoji = self.get_icon_emoji(icon, entity_id) if badge.get("show_icon", True) else ""
            display_name = name or self.get_display_name(entity_id)

            text = Text()
            if emoji:
                text.append(f"{emoji} ")
            text.append(f"{display_name}")

            if state_content != "name" and show_state:
                formatted, style = self.format_state(entity_id, state)
                if formatted:
                    text.append(": ")
                    text.append(formatted, style=style)

            if text.plain.strip() in ("", emoji.strip()):
                return None
            return text

        elif badge_type == "custom:mushroom-template-badge":
            entity_id = badge.get("entity")
            content = badge.get("content")
            label = badge.get("label")
            icon = badge.get("icon", "")

            text = Text()
            emoji = self.get_icon_emoji(icon, entity_id)
            text.append(f"{emoji} ")

            if content:
                rendered = await self.eval_template(content)
                if rendered:
                    style = (
                        "green"
                        if rendered.lower() in ("home", "oasis")
                        else "cyan"
                        if rendered not in ("Away", "not_home")
                        else "dim"
                    )
                    text.append(rendered, style=style)

            if label:
                rendered = await self.eval_template(label)
                if rendered:
                    text.append(f" ({rendered})", style="dim")

            return text if text.plain.strip() and text.plain.strip() != emoji.strip() else None

        return None

    def render_tile(self, card: dict[str, Any]) -> Text | None:
        """Render a tile card as a rich Text object."""
        if not self.check_visibility(card.get("visibility", [])):
            return None

        entity_id = card.get("entity")
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        name = card.get("name") or self.get_display_name(entity_id)
        icon = card.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")

        emoji = self.get_icon_emoji(icon, entity_id)
        formatted, style = self.format_state(entity_id, state)

        text = Text()
        text.append(f"  {emoji} {name}")
        if formatted:
            text.append(": ")
            text.append(formatted, style=style)

        return text

    async def render_heading(self, card: dict[str, Any]) -> list[Text]:
        """Render a heading card as a list of rich Text lines."""
        if not self.check_visibility(card.get("visibility", [])):
            return []

        heading = card.get("heading", "")
        icon = card.get("icon", "")

        if not heading and not icon:
            return []

        emoji = self.get_icon_emoji(icon) if icon else ""

        lines = []

        header = Text()
        if emoji:
            header.append(f"{emoji} ")
        header.append(heading.upper(), style="bold")
        lines.append(header)

        for badge in card.get("badges", []):
            rendered = await self.render_badge(badge)
            if rendered:
                badge_line = Text("  ")
                badge_line.append_text(rendered)
                lines.append(badge_line)

        return lines

    async def get_entities_with_label(self, label: str) -> set[str]:
        """Get entity IDs that have a specific HA label (cached)."""
        if label in self.label_cache:
            return self.label_cache[label]

        template = '{{ label_entities("' + label + '") | tojson }}'

        try:
            output = await self.client.render_template(template)
            entities = set(json.loads(output.replace("\n", "")))
            self.label_cache[label] = entities
            return entities
        except (json.JSONDecodeError, Exception):
            self.label_cache[label] = set()
            return set()

    async def search_entities(self, domain: str | None = None) -> list[dict[str, Any]]:
        """Search for entities using template."""
        if not domain:
            return []

        template = (
            "[{% for e in states." + domain + " %}"
            '{"entity_id": {{ e.entity_id | tojson }}, '
            '"state": {{ e.state | tojson }}, '
            '"name": {{ (e.name | default("")) | tojson }}, '
            '"icon": {{ (e.attributes.get("icon", "") | string) | tojson }}, '
            '"attributes": {'
            '"known": {{ (e.attributes.get("known", "") | string) | tojson }}, '
            '"device_class": {{ (e.attributes.get("device_class", "") | string) | tojson }}, '
            '"friendly_name": {{ (e.attributes.get("friendly_name", "") | string) | tojson }}'
            "}}"
            "{% if not loop.last %},{% endif %}"
            "{% endfor %}]"
        )

        try:
            output = await self.client.render_template(template)
            return json.loads(output.replace("\n", ""))
        except (json.JSONDecodeError, Exception):
            return []

    async def render_auto_entities(self, card: dict[str, Any]) -> list[Text]:
        """Render auto-entities card by evaluating the filter rules."""
        lines: list[Text] = []

        card_config = card.get("card", {})
        if card_config.get("type") in ("custom:map-card", "logbook"):
            return []

        filters = card.get("filter", {})
        include_rules = filters.get("include", [])

        matched_entities: list[tuple[str, dict[str, Any]]] = []

        for rule in include_rules:
            if "entity_id" in rule and not rule.get("domain"):
                entity_id = rule["entity_id"]
                options = rule.get("options", {})
                if entity_id not in self.state_cache:
                    await self.fetch_all_states({entity_id})
                if entity_id in self.state_cache:
                    matched_entities.append((entity_id, options))
                continue

            domain = rule.get("domain")
            if not domain:
                continue

            if rule.get("integration"):
                continue

            include_label = rule.get("label")
            attrs = rule.get("attributes", {})
            domain_entities = await self.search_entities(domain=domain)
            include_label_entities = (
                await self.get_entities_with_label(include_label) if include_label else None
            )

            for ent in domain_entities:
                entity_id = ent["entity_id"]
                state = ent["state"]

                if entity_id in [m[0] for m in matched_entities]:
                    continue

                if include_label_entities is not None and entity_id not in include_label_entities:
                    continue

                not_filter = rule.get("not", {})
                skip = False

                if not_filter:
                    or_conditions = not_filter.get("or", [])
                    for cond in or_conditions:
                        if "state" in cond and state == cond["state"]:
                            skip = True
                            break
                        if "label" in cond:
                            label_entities = await self.get_entities_with_label(cond["label"])
                            if entity_id in label_entities:
                                skip = True
                                break

                if skip:
                    continue

                attr_match = True
                ent_attrs = ent.get("attributes", {})
                for attr_name, attr_val in attrs.items():
                    ent_attr = str(ent_attrs.get(attr_name, "")).lower()
                    expected = str(attr_val).lower()
                    if ent_attr != expected:
                        attr_match = False
                        break
                if not attr_match:
                    continue

                options = rule.get("options", {})
                matched_entities.append((entity_id, options))
                self.state_cache[entity_id] = {
                    "state": ent["state"],
                    "name": ent["name"],
                    "icon": ent.get("icon", ""),
                    "unit": "",
                }

        seen: set[str] = set()
        unique_entities: list[tuple[str, dict[str, Any]]] = []
        for entity_id, options in matched_entities:
            if entity_id not in seen:
                seen.add(entity_id)
                unique_entities.append((entity_id, options))

        for entity_id, options in unique_entities:
            cached = self.state_cache.get(entity_id, {})
            state = cached.get("state", "")
            opt_name = options.get("name", "").strip()
            name = (
                opt_name
                if opt_name
                else cached.get("name", "") or entity_id.split(".")[-1].replace("_", " ").title()
            )
            icon = options.get("icon", "") or cached.get("icon", "")

            if state in ("unavailable", "unknown", ""):
                continue

            formatted_state, style = self.format_state(entity_id, state)
            emoji = self.get_icon_emoji(icon, entity_id)

            text = Text()
            text.append(f"  {emoji} {name}")
            if formatted_state:
                text.append(": ")
                text.append(formatted_state, style=style)

            lines.append(text)

        return lines

    async def render_logbook(self, card: dict[str, Any], max_entries: int = 5) -> list[Text]:
        """Render a logbook card showing recent state changes."""
        lines: list[Text] = []

        target = card.get("target", {})
        entity_ids = target.get("entity_id", [])
        if not entity_ids:
            entity_ids = card.get("entities", [])
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        if not entity_ids:
            return []

        template_lines = []
        for eid in entity_ids:
            template_lines.append(
                f'{eid}|||{{{{ states("{eid}") }}}}|||'
                f'{{{{ state_attr("{eid}", "friendly_name") '
                f'| default("", true) | replace("\\n", " ") }}}}|||'
                f"{{{{ as_timestamp(states.{eid}.last_changed) | default(0) }}}}"
            )

        template = "\n".join(template_lines)

        try:
            output = await self.client.render_template(template)
        except Exception:
            return []

        entries: list[tuple[Any, str, str, str]] = []
        from datetime import UTC, datetime

        for line in output.strip().split("\n"):
            parts = line.split("|||")
            if len(parts) >= 4:
                entity_id = parts[0].strip()
                state = parts[1].strip()
                name = parts[2].strip() or entity_id.split(".")[-1].replace("_", " ").title()
                last_changed_str = parts[3].strip()

                if last_changed_str and state not in ("unavailable", "unknown"):
                    try:
                        timestamp = float(last_changed_str)
                        if timestamp > 0:
                            last_changed = datetime.fromtimestamp(timestamp, tz=UTC)
                            entries.append((last_changed, name, state, entity_id))
                    except ValueError:
                        pass

        entries.sort(reverse=True, key=lambda x: x[0])

        now = datetime.now(UTC)

        for last_changed, name, state, entity_id in entries[:max_entries]:
            formatted_state, style = self.format_state(entity_id, state)

            if not formatted_state:
                continue

            delta = now - last_changed
            if delta.days > 0:
                time_str = f"{delta.days}d ago"
            elif delta.seconds >= 3600:
                time_str = f"{delta.seconds // 3600}h ago"
            elif delta.seconds >= 60:
                time_str = f"{delta.seconds // 60}m ago"
            else:
                time_str = "just now"

            text = Text("  ")
            text.append(f"{name}: ", style="dim")
            text.append(formatted_state, style=style)
            text.append(f" ({time_str})", style="dim")
            lines.append(text)

        return lines

    async def render_card(self, card: dict[str, Any]) -> list[Text]:
        """Render a single card as a list of rich Text lines."""
        if not self.check_visibility(card.get("visibility", [])):
            return []

        card_type = card.get("type", "")

        if card_type == "tile":
            tile = self.render_tile(card)
            return [tile] if tile else []
        elif card_type == "heading":
            return await self.render_heading(card)
        elif card_type == "picture-entity":
            return []  # Skip cameras
        elif card_type == "custom:auto-entities":
            return await self.render_auto_entities(card)
        elif card_type == "logbook":
            return await self.render_logbook(card)
        elif card_type in ("custom:map-card", "history-graph", "custom:navbar-card"):
            return []

        return []

    async def render_section(self, section: dict[str, Any]) -> list[Text | None]:
        """Render a section as a list of rich Text lines (None = blank line)."""
        if not self.check_visibility(section.get("visibility", [])):
            return []

        cards = section.get("cards", [])
        lines: list[Text | None] = []
        pending_heading: dict[str, Any] | None = None

        for card in cards:
            card_type = card.get("type", "")

            if card_type == "heading" and card.get("heading"):
                heading_lines = await self.render_heading(card)
                if heading_lines:
                    if pending_heading:
                        lines.append(None)
                        lines.extend(await self.render_heading(pending_heading))
                        pending_heading = None
                    if len(heading_lines) > 1:
                        lines.append(None)
                        lines.extend(heading_lines)
                    else:
                        pending_heading = card
                continue

            card_lines = await self.render_card(card)

            if card_lines and pending_heading:
                lines.append(None)
                lines.extend(await self.render_heading(pending_heading))
                pending_heading = None

            lines.extend(card_lines)

        return lines

    async def render_view(self, view_path: Path, user: str | None = None) -> None:
        """Render a dashboard view using rich console."""
        if not view_path.exists():
            console.print(f"[red]View file not found: {view_path}[/red]")
            return

        with open(view_path) as f:
            view = yaml.safe_load(f)

        if not view:
            console.print(f"[red]Could not parse view file: {view_path}[/red]")
            return

        # Set up user if specified
        if user:
            self.user_ids = await self.fetch_user_ids()
            user_name = user.lower()
            if user_name in self.user_ids:
                self.current_user = self.user_ids[user_name]
            else:
                available = ", ".join(self.user_ids.keys()) if self.user_ids else "none found"
                console.print(f"[red]Unknown user: {user}[/red]")
                console.print(f"[dim]Available: {available}[/dim]")
                return

        # Extract all entities and fetch states in one call
        entities: set[str] = set()
        self.extract_entities(view, entities)
        await self.fetch_all_states(entities)

        # Render header
        title = view.get("title", "View")
        icon = view.get("icon", "")
        emoji = self.get_icon_emoji(icon)

        header = Text()
        header.append(f"═══ {emoji} ", style="bold")
        header.append(title.upper(), style="bold cyan")
        header.append(" ═══", style="bold")
        console.print(header)

        # Badges as data points
        for badge in view.get("badges", []):
            rendered = await self.render_badge(badge)
            if rendered:
                line = Text("  ")
                line.append_text(rendered)
                console.print(line)

        # Sections with consistent spacing
        for section in view.get("sections", []):
            section_lines = await self.render_section(section)
            if section_lines:
                for line in section_lines:
                    if line is None:
                        console.print()  # Blank line before heading
                    else:
                        console.print(line)


async def render_view_file(client: HAClient, view_path: Path, user: str | None = None) -> None:
    """Render a dashboard view file.

    Args:
        client: Connected HAClient instance
        view_path: Path to the dashboard view YAML file
        user: Optional user name for user-specific visibility
    """
    renderer = ViewRenderer(client)
    await renderer.render_view(view_path, user)

"""Render a Home Assistant dashboard view as CLI text output.

Split into two layers:
- ViewResolver: async class that fetches data and produces a RenderedView model
- RichViewRenderer: sync class that renders a RenderedView to Rich console output
"""

import json
from pathlib import Path
from typing import Any, ClassVar

import yaml
from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from ha_sync.client import HAClient
from ha_sync.render_models import (
    FormattedState,
    RenderedAutoEntities,
    RenderedBadge,
    RenderedEntityBadge,
    RenderedHeading,
    RenderedIcon,
    RenderedLogbook,
    RenderedLogbookEntry,
    RenderedSection,
    RenderedSectionItem,
    RenderedSpacing,
    RenderedTemplateBadge,
    RenderedTile,
    RenderedView,
    RenderedWeather,
    SemanticColor,
    format_state,
)

console = Console()


# =============================================================================
# ViewResolver — async data fetching and resolution
# =============================================================================


class ViewResolver:
    """Resolves a Lovelace dashboard view into a RenderedView model.

    Handles all async data fetching (states, templates, registry) and produces
    a format-agnostic RenderedView that any renderer can consume.
    """

    def __init__(self, client: HAClient) -> None:
        self.client = client
        self.state_cache: dict[str, dict[str, Any]] = {}
        self.user_ids: dict[str, str] = {}
        self.current_user: str | None = None
        self.label_cache: dict[str, set[str]] = {}
        self.registry_icons: dict[str, str] = {}

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
        """Fetch all entity states in batched template calls."""
        if not entities:
            return

        entity_list = list(entities)
        batch_size = 20

        for i in range(0, len(entity_list), batch_size):
            batch = entity_list[i : i + batch_size]
            lines = []
            for e in batch:
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
                console.print(f"[dim]Warning: Failed to fetch states for batch: {e}[/dim]")

        # Fill in missing icons from entity registry (platform-provided icons)
        missing_icon_entities = [
            eid for eid, cached in self.state_cache.items() if not cached.get("icon")
        ]
        if missing_icon_entities:
            await self._fetch_registry_icons(missing_icon_entities)

    async def _fetch_registry_icons(self, entity_ids: list[str]) -> None:
        """Fetch icons from entity registry for entities missing icon attributes."""
        try:
            registry = await self.client.get_entity_registry_cached()
            registry_by_id = {e["entity_id"]: e for e in registry if "entity_id" in e}
            for entity_id in entity_ids:
                entry = registry_by_id.get(entity_id)
                if entry:
                    icon = entry.get("icon") or entry.get("original_icon") or ""
                    if icon and entity_id in self.state_cache:
                        self.state_cache[entity_id]["icon"] = icon
        except Exception:
            pass  # Registry not available, fall back to domain/device_class

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

    async def eval_template(self, template: str, entity_id: str | None = None) -> str:
        """Evaluate a Jinja2 template.

        If entity_id is provided, wraps the template in a {% set entity = '...' %}
        block so that mushroom-style templates using `entity` as a variable work.
        """
        if entity_id and "entity" in template:
            template = f'{{% set entity = "{entity_id}" %}}{template}'
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

    # -- Icon helper --

    def _make_icon(self, icon: str | None, entity_id: str | None = None) -> RenderedIcon:
        """Create a RenderedIcon from a raw icon string and entity context."""
        mdi_name: str | None = None
        if icon:
            mdi_name = icon.replace("mdi:", "").lower()

        device_class: str | None = None
        if entity_id:
            device_class = self.state_cache.get(entity_id, {}).get("device_class", "") or None

        return RenderedIcon(
            mdi_name=mdi_name,
            entity_id=entity_id,
            device_class=device_class,
        )

    # -- Format state helper --

    def _format_state(self, entity_id: str, state: str) -> FormattedState:
        """Format entity state using the shared format_state function."""
        device_class = self.state_cache.get(entity_id, {}).get("device_class", "")
        unit = self.state_cache.get(entity_id, {}).get("unit", "")
        return format_state(entity_id, state, device_class=device_class, unit=unit)

    # -- Legacy API (used by SwiftBarRenderer) --

    def format_state(self, entity_id: str, state: str) -> tuple[str, str | None]:
        """Format entity state for display. Returns (text, style).

        Legacy method preserved for SwiftBarRenderer compatibility.
        """
        fs = self._format_state(entity_id, state)
        style: str | None = None
        if fs.color is not None:
            style = RichViewRenderer.SEMANTIC_COLOR_MAP.get(fs.color)
        return fs.text, style

    async def resolve_auto_entities(
        self, card: dict[str, Any]
    ) -> list[tuple[str, str, str, dict[str, Any]]]:
        """Resolve auto-entities filter rules to matched entities.

        Legacy method preserved for SwiftBarRenderer compatibility.
        Returns list of (entity_id, name, icon, options) tuples.
        """
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
                await self.get_entities_with_label(include_label)
                if include_label
                else None
            )

            for ent in domain_entities:
                entity_id = ent["entity_id"]
                state = ent["state"]

                if entity_id in [m[0] for m in matched_entities]:
                    continue

                if (
                    include_label_entities is not None
                    and entity_id not in include_label_entities
                ):
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
                            label_entities = (
                                await self.get_entities_with_label(cond["label"])
                            )
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

        result: list[tuple[str, str, str, dict[str, Any]]] = []
        for entity_id, options in unique_entities:
            cached = self.state_cache.get(entity_id, {})
            state = cached.get("state", "")
            if state in ("unavailable", "unknown", ""):
                continue

            opt_name = options.get("name", "").strip()
            name = (
                opt_name
                if opt_name
                else cached.get("name", "")
                or entity_id.split(".")[-1].replace("_", " ").title()
            )
            icon = options.get("icon", "") or cached.get("icon", "")
            result.append((entity_id, name, icon, options))

        return result

    async def fetch_logbook_entries(
        self, card: dict[str, Any], max_entries: int = 5
    ) -> list[tuple[str, str, str, str, str]]:
        """Fetch logbook entries for a card.

        Legacy method preserved for SwiftBarRenderer compatibility.
        Returns list of (entity_id, name, state, formatted_state, time_str).
        """
        from datetime import UTC, datetime

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
                f"{{{{ as_timestamp(states.{eid}.last_changed)"
                f" | default(0) }}}}"
            )

        template = "\n".join(template_lines)

        try:
            output = await self.client.render_template(template)
        except Exception:
            return []

        entries: list[tuple[Any, str, str, str]] = []
        for line in output.strip().split("\n"):
            parts = line.split("|||")
            if len(parts) >= 4:
                entity_id = parts[0].strip()
                state = parts[1].strip()
                name = (
                    parts[2].strip()
                    or entity_id.split(".")[-1].replace("_", " ").title()
                )
                last_changed_str = parts[3].strip()

                if last_changed_str and state not in (
                    "unavailable",
                    "unknown",
                ):
                    try:
                        timestamp = float(last_changed_str)
                        if timestamp > 0:
                            last_changed = datetime.fromtimestamp(
                                timestamp, tz=UTC
                            )
                            entries.append(
                                (last_changed, name, state, entity_id)
                            )
                    except ValueError:
                        pass

        entries.sort(reverse=True, key=lambda x: x[0])
        now = datetime.now(UTC)

        result: list[tuple[str, str, str, str, str]] = []
        for last_changed, name, state, entity_id in entries[:max_entries]:
            formatted, _ = self.format_state(entity_id, state)
            if not formatted:
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

            result.append(
                (entity_id, name, state, formatted, time_str)
            )

        return result

    async def fetch_weather(
        self, card: dict[str, Any]
    ) -> tuple[str, str, str] | None:
        """Fetch weather data for a weather-forecast card.

        Legacy method preserved for SwiftBarRenderer compatibility.
        Returns (condition, temperature_str, entity_id) or None.
        """
        entity_id = card.get("entity")
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        if state in ("unavailable", "unknown"):
            return None

        template = (
            f'{{{{ state_attr("{entity_id}", "temperature")'
            f' | default("", true) }}}}|||'
            f'{{{{ state_attr("{entity_id}", "temperature_unit")'
            f' | default("", true) }}}}'
        )
        try:
            output = await self.eval_template(template)
            parts = output.split("|||")
            temp = parts[0].strip() if parts else ""
            unit = parts[1].strip() if len(parts) > 1 else ""
            try:
                val = float(temp)
                temp = (
                    str(int(val)) if val == int(val) else f"{val:.1f}"
                )
            except (ValueError, TypeError):
                pass
            temp_str = f"{temp}{unit}" if temp else ""
        except Exception:
            temp_str = ""

        condition = (
            state.replace("_", " ")
            .replace("partlycloudy", "Partly Cloudy")
            .title()
        )
        return condition, temp_str, entity_id

    # -- Resolve methods --

    async def _resolve_badge(self, badge: dict[str, Any]) -> RenderedBadge | None:
        """Resolve a single badge into a RenderedBadge model."""
        if not self.check_visibility(badge.get("visibility", [])):
            return None

        badge_type = badge.get("type", "entity")

        if badge_type == "entity":
            entity_id = badge.get("entity")
            if not entity_id:
                return None

            state = self.get_state(entity_id)
            name = badge.get("name")
            icon_str = badge.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")
            state_content = badge.get("state_content")
            show_icon = badge.get("show_icon", True)

            display_name = name or self.get_display_name(entity_id)

            formatted = self._format_state(entity_id, state)

            # Match the old logic: if state_content == "name", don't show state
            if state_content == "name":
                formatted = FormattedState(text="")

            # Check if badge would be empty (same logic as old code)
            icon = self._make_icon(
                icon_str if show_icon else None,
                entity_id if show_icon else None,
            )

            # The old code checked: if text.plain.strip() in ("", emoji.strip()): return None
            # This means: if after building the text, only whitespace or only the emoji remains,
            # skip it. We approximate: if name is empty and formatted text is empty, skip.
            if not display_name and not formatted.text:
                return None

            return RenderedEntityBadge(
                entity_id=entity_id,
                name=display_name,
                state=formatted,
                icon=icon,
            )

        elif badge_type == "custom:mushroom-template-badge":
            entity_id = badge.get("entity")
            content_template = badge.get("content")
            label_template = badge.get("label")
            icon_str = badge.get("icon", "")
            # Icon can be a template (e.g. conditional mdi:controller vs mdi:television)
            if icon_str and "{" in icon_str:
                icon_str = (await self.eval_template(icon_str, entity_id)).strip()

            icon = self._make_icon(icon_str, entity_id)

            content: str | None = None
            content_color: SemanticColor | None = None
            if content_template:
                rendered = await self.eval_template(content_template, entity_id)
                if rendered and rendered != "[error]":
                    content = rendered
                    # Color logic: home/oasis -> POSITIVE, away/not_home -> INACTIVE, else -> INFO
                    if rendered.lower() in ("home", "oasis"):
                        content_color = SemanticColor.POSITIVE
                    elif rendered in ("Away", "not_home"):
                        content_color = SemanticColor.INACTIVE
                    else:
                        content_color = SemanticColor.INFO

            label: str | None = None
            if label_template:
                rendered = await self.eval_template(label_template, entity_id)
                if rendered and rendered != "[error]":
                    label = rendered

            # Old code returned None if text was empty or only the emoji icon.
            # This means: must have content or label beyond just the icon
            if not content and not label:
                return None

            return RenderedTemplateBadge(
                entity_id=entity_id,
                content=content,
                content_color=content_color,
                label=label,
                icon=icon,
            )

        return None

    def _resolve_tile(self, card: dict[str, Any]) -> RenderedTile | None:
        """Resolve a tile card into a RenderedTile model."""
        if not self.check_visibility(card.get("visibility", [])):
            return None

        entity_id = card.get("entity")
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        name = card.get("name") or self.get_display_name(entity_id)
        icon_str = card.get("icon") or self.state_cache.get(entity_id, {}).get("icon", "")

        icon = self._make_icon(icon_str, entity_id)
        formatted = self._format_state(entity_id, state)

        return RenderedTile(
            entity_id=entity_id,
            name=name,
            state=formatted,
            icon=icon,
        )

    async def _resolve_heading(self, card: dict[str, Any]) -> RenderedHeading | None:
        """Resolve a heading card into a RenderedHeading model."""
        if not self.check_visibility(card.get("visibility", [])):
            return None

        heading = card.get("heading", "")
        icon_str = card.get("icon", "")

        if not heading and not icon_str:
            return None

        icon = self._make_icon(icon_str) if icon_str else RenderedIcon()

        badges: list[RenderedBadge] = []
        for badge in card.get("badges", []):
            rendered = await self._resolve_badge(badge)
            if rendered:
                badges.append(rendered)

        return RenderedHeading(
            heading=heading,
            icon=icon,
            badges=badges,
        )

    async def _resolve_auto_entities(self, card: dict[str, Any]) -> RenderedAutoEntities:
        """Resolve auto-entities card by evaluating filter rules."""
        tiles: list[RenderedTile] = []

        card_config = card.get("card", {})
        if card_config.get("type") in ("custom:map-card", "logbook"):
            return RenderedAutoEntities(tiles=tiles)

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
            if state in ("unavailable", "unknown", ""):
                continue

            opt_name = options.get("name", "").strip()
            name = (
                opt_name
                if opt_name
                else cached.get("name", "") or entity_id.split(".")[-1].replace("_", " ").title()
            )
            icon_str = options.get("icon", "") or cached.get("icon", "")
            icon = self._make_icon(icon_str, entity_id)
            formatted = self._format_state(entity_id, state)

            tiles.append(RenderedTile(
                entity_id=entity_id,
                name=name,
                state=formatted,
                icon=icon,
            ))

        return RenderedAutoEntities(tiles=tiles)

    async def _resolve_logbook(
        self, card: dict[str, Any], max_entries: int = 5
    ) -> RenderedLogbook:
        """Resolve a logbook card into a RenderedLogbook model."""
        from datetime import UTC, datetime

        entries: list[RenderedLogbookEntry] = []

        target = card.get("target", {})
        entity_ids = target.get("entity_id", [])
        if not entity_ids:
            entity_ids = card.get("entities", [])
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        if not entity_ids:
            return RenderedLogbook(entries=entries)

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
            return RenderedLogbook(entries=entries)

        raw_entries: list[tuple[Any, str, str, str]] = []
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
                            raw_entries.append((last_changed, name, state, entity_id))
                    except ValueError:
                        pass

        raw_entries.sort(reverse=True, key=lambda x: x[0])
        now = datetime.now(UTC)

        for last_changed, name, state, entity_id in raw_entries[:max_entries]:
            formatted = self._format_state(entity_id, state)
            if not formatted.text:
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

            icon_str = self.state_cache.get(entity_id, {}).get("icon", "")
            icon = self._make_icon(icon_str, entity_id)

            entries.append(RenderedLogbookEntry(
                entity_id=entity_id,
                name=name,
                state=formatted,
                time_ago=time_str,
                icon=icon,
            ))

        return RenderedLogbook(entries=entries)

    async def _resolve_weather(self, card: dict[str, Any]) -> RenderedWeather | None:
        """Resolve a weather-forecast card into a RenderedWeather model."""
        entity_id = card.get("entity")
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        if state in ("unavailable", "unknown"):
            return None

        # Get temperature from attributes via template
        template = (
            f'{{{{ state_attr("{entity_id}", "temperature") | default("", true) }}}}|||'
            f'{{{{ state_attr("{entity_id}", "temperature_unit") | default("", true) }}}}'
        )
        try:
            output = await self.eval_template(template)
            parts = output.split("|||")
            temp = parts[0].strip() if parts else ""
            unit = parts[1].strip() if len(parts) > 1 else ""
            try:
                val = float(temp)
                temp = str(int(val)) if val == int(val) else f"{val:.1f}"
            except (ValueError, TypeError):
                pass
            temp_str = f"{temp}{unit}" if temp else ""
        except Exception:
            temp_str = ""

        condition = state.replace("_", " ").replace("partlycloudy", "Partly Cloudy").title()

        icon_str = self.state_cache.get(entity_id, {}).get("icon", "")
        icon = self._make_icon(icon_str, entity_id)

        return RenderedWeather(
            entity_id=entity_id,
            condition=condition,
            raw_condition=state,
            temperature=temp_str,
            icon=icon,
        )

    async def _resolve_card(self, card: dict[str, Any]) -> list[RenderedSectionItem]:
        """Resolve a single card into RenderedSectionItem(s)."""
        if not self.check_visibility(card.get("visibility", [])):
            return []

        card_type = card.get("type", "")

        if card_type == "tile":
            tile = self._resolve_tile(card)
            return [tile] if tile else []
        elif card_type == "heading":
            heading = await self._resolve_heading(card)
            return [heading] if heading else []
        elif card_type == "picture-entity":
            return []  # Skip cameras
        elif card_type == "custom:auto-entities":
            auto = await self._resolve_auto_entities(card)
            return [auto] if auto.tiles else []
        elif card_type == "logbook":
            logbook = await self._resolve_logbook(card)
            return [logbook] if logbook.entries else []
        elif card_type == "weather-forecast":
            weather = await self._resolve_weather(card)
            return [weather] if weather else []
        elif card_type in ("custom:map-card", "history-graph", "custom:navbar-card"):
            return []

        return []

    async def _resolve_section(self, section: dict[str, Any]) -> RenderedSection:
        """Resolve a section into a RenderedSection model.

        Implements the pending heading pattern: headings with only text (no badges)
        are deferred until non-heading content follows. A blank line (RenderedSpacing)
        is inserted before headings that have subsequent content.
        """
        if not self.check_visibility(section.get("visibility", [])):
            return RenderedSection()

        cards = section.get("cards", [])
        items: list[RenderedSectionItem] = []
        pending_heading: dict[str, Any] | None = None

        for card in cards:
            card_type = card.get("type", "")

            if card_type == "heading" and card.get("heading"):
                resolved_heading = await self._resolve_heading(card)
                if resolved_heading:
                    if pending_heading:
                        # Previous heading had no content — emit it now
                        items.append(RenderedSpacing())
                        prev_heading = await self._resolve_heading(pending_heading)
                        if prev_heading:
                            items.append(prev_heading)
                        pending_heading = None
                    if resolved_heading.badges:
                        # Heading with badges — emit immediately
                        items.append(RenderedSpacing())
                        items.append(resolved_heading)
                    else:
                        # Heading without badges — defer
                        pending_heading = card
                continue

            card_items = await self._resolve_card(card)

            if card_items and pending_heading:
                items.append(RenderedSpacing())
                heading = await self._resolve_heading(pending_heading)
                if heading:
                    items.append(heading)
                pending_heading = None

            items.extend(card_items)

        return RenderedSection(items=items)

    async def resolve_view(self, view_path: Path, user: str | None = None) -> RenderedView:
        """Resolve a dashboard view YAML file into a RenderedView model.

        Args:
            view_path: Path to the dashboard view YAML file
            user: Optional user name for user-specific visibility

        Returns:
            A fully resolved RenderedView model ready for rendering.

        Raises:
            FileNotFoundError: If the view file does not exist.
            ValueError: If the view file cannot be parsed.
        """
        if not view_path.exists():
            raise FileNotFoundError(f"View file not found: {view_path}")

        with open(view_path) as f:
            view = yaml.safe_load(f)

        if not view:
            raise ValueError(f"Could not parse view file: {view_path}")

        # Set up user if specified
        if user:
            self.user_ids = await self.fetch_user_ids()
            user_name = user.lower()
            if user_name in self.user_ids:
                self.current_user = self.user_ids[user_name]
            else:
                available = ", ".join(self.user_ids.keys()) if self.user_ids else "none found"
                raise ValueError(f"Unknown user: {user}. Available: {available}")

        # Extract all entities and fetch states in one call
        entities: set[str] = set()
        self.extract_entities(view, entities)
        await self.fetch_all_states(entities)

        # Resolve header
        title = view.get("title", "View")
        icon_str = view.get("icon", "")
        icon = self._make_icon(icon_str)

        # Resolve badges
        badges: list[RenderedBadge] = []
        for badge in view.get("badges", []):
            rendered = await self._resolve_badge(badge)
            if rendered:
                badges.append(rendered)

        # Resolve sections
        sections: list[RenderedSection] = []
        for section in view.get("sections", []):
            resolved = await self._resolve_section(section)
            if resolved.items:
                sections.append(resolved)

        return RenderedView(
            title=title,
            path=str(view_path),
            icon=icon,
            badges=badges,
            sections=sections,
        )


# =============================================================================
# RichViewRenderer — sync Rich console rendering
# =============================================================================


# Icon to emoji mappings
ICON_EMOJI = {
    "home": "\U0001f3e0",
    "home-circle": "\U0001f3e0",
    "home-heart": "\U0001f3e0",
    "account": "\U0001f464",
    "account-group": "\U0001f465",
    "home-account": "\U0001f465",
    "television": "\U0001f4fa",
    "bed-king": "\U0001f6cf\ufe0f",
    "baby-face": "\U0001f476",
    "baby-face-outline": "\U0001f476",
    "desktop-tower-monitor": "\U0001f5a5\ufe0f",
    "sofa": "\U0001f6cb\ufe0f",
    "briefcase": "\U0001f4bc",
    "weight-lifter": "\U0001f3cb\ufe0f",
    "stove": "\U0001f373",
    "tree": "\U0001f333",
    "flower": "\U0001f338",
    "greenhouse": "\U0001f33f",
    "garage-variant-lock": "\U0001f697",
    "car-estate": "\U0001f697",
    "thermometer": "\U0001f321\ufe0f",
    "home-thermometer": "\U0001f321\ufe0f",
    "home-thermometer-outline": "\U0001f321\ufe0f",
    "fan": "\U0001f300",
    "lightbulb": "\U0001f4a1",
    "light": "\U0001f4a1",
    "track-light": "\U0001f4a1",
    "pillar": "\U0001f3db\ufe0f",
    "shield": "\U0001f6e1\ufe0f",
    "shield-home": "\U0001f6e1\ufe0f",
    "shield-moon": "\U0001f319",
    "shield-sun": "\u2600\ufe0f",
    "lock": "\U0001f512",
    "lock-smart": "\U0001f510",
    "door": "\U0001f6aa",
    "door-open": "\U0001f6aa",
    "garage-variant": "\U0001f697",
    "garage-open-variant": "\U0001f697",
    "cctv": "\U0001f4f9",
    "webcam": "\U0001f4f7",
    "weather-sunny": "\u2600\ufe0f",
    "weather-sunset-up": "\U0001f305",
    "weather-sunset-down": "\U0001f307",
    "sun-clock": "\u23f0",
    "history": "\U0001f4dc",
    "map": "\U0001f5fa\ufe0f",
    "map-marker": "\U0001f4cd",
    "home-map-marker": "\U0001f4cd",
    "music": "\U0001f3b5",
    "speaker": "\U0001f50a",
    "hot-tub": "\U0001f6c1",
    "fountain": "\u26f2",
    "sun-wireless": "\u2600\ufe0f",
    "sun-wireless-outline": "\u2600\ufe0f",
    "fishbowl": "\U0001f41f",
    "fishbowl-outline": "\U0001f41f",
    "glass-cocktail": "\U0001f378",
    "hanger": "\U0001f454",
    "wifi": "\U0001f4f6",
    "airplane": "\u2708\ufe0f",
    "looks": "\u2728",
    "lamp": "\U0001f4a1",
    "led-strip": "\U0001f4a1",
    "led-strip-variant": "\U0001f4a1",
    "power-plug-battery": "\U0001f50b",
    "lightning-bolt": "\u26a1",
    "format-list-bulleted-type": "\U0001f4cb",
    "alarm-panel": "\U0001f6a8",
    "controller": "\U0001f3ae",
    "launch": "\U0001f680",
    "account-question": "\u2753",
    "account-check": "\u2705",
    "washing-machine": "\U0001f9fa",
    "human": "\U0001f464",
    "server": "\U0001f5a5\ufe0f",
    "plex": "\u25b6\ufe0f",
    "cats": "\U0001f431",
    "cat": "\U0001f431",
    "time": "\U0001f550",
    "devices": "\U0001f4f1",
    "cellphone": "\U0001f4f1",
    "phone": "\U0001f4f1",
    "printer": "\U0001f5a8\ufe0f",
    "printer-3d": "\U0001f5a8\ufe0f",
    "air-filter": "\U0001f32c\ufe0f",
    "air-purifier": "\U0001f32c\ufe0f",
    "water-thermometer": "\U0001f321\ufe0f",
    "coolant-temperature": "\U0001f321\ufe0f",
    "gas-station": "\u26fd",
    "fuel": "\u26fd",
    "ev-station": "\U0001f50c",
    "car-door": "\U0001f697",
    "car-tire-alert": "\U0001f697",
    "window-closed": "\U0001fa9f",
    "window-open": "\U0001fa9f",
    "volume": "\U0001f50a",
    "volume-high": "\U0001f50a",
    "volume-off": "\U0001f507",
    "radiator": "\U0001f525",
    "radiator-off": "\U0001f525",
    "heating-coil": "\U0001f525",
    "video": "\U0001f4f9",
    "video-off": "\U0001f4f9",
    "baby-buggy": "\U0001f37c",
    "baby-carriage": "\U0001f37c",
    "stroller": "\U0001f37c",
    "face-man": "\U0001f468",
    "face-woman": "\U0001f469",
    "face": "\U0001f464",
    "battery": "\U0001f50b",
    "battery-charging": "\U0001f50b",
    "tumble-dryer": "\U0001f9fa",
    "dryer": "\U0001f9fa",
    "waves": "\U0001f30a",
    "water": "\U0001f4a7",
    "water-pump": "\U0001f4a7",
    "gauge": "\U0001f4ca",
    "gauge-empty": "\U0001f4ca",
    "gauge-full": "\U0001f4ca",
    "heat-pump": "\U0001f321\ufe0f",
    "hvac": "\U0001f321\ufe0f",
    "air-conditioner": "\u2744\ufe0f",
    "pause": "\u23f8\ufe0f",
    "play": "\u25b6\ufe0f",
    "stop": "\u23f9\ufe0f",
    "robot-vacuum": "\U0001f916",
    "robot": "\U0001f916",
    "hdmi-port": "\U0001f4fa",
    "video-input-hdmi": "\U0001f4fa",
    "pin": "\U0001f4cc",
    "pin-outline": "\U0001f4cc",
    "rotate": "\U0001f504",
    "rotate-3d": "\U0001f504",
    "access-point": "\U0001f4f6",
    "access-point-network": "\U0001f4f6",
    "solar-power": "\u2600\ufe0f",
    "solar-power-variant": "\u2600\ufe0f",
    "solar-panel": "\u2600\ufe0f",
    "transmission-tower": "\u26a1",
    "power-plug": "\U0001f50c",
    "power-socket": "\U0001f50c",
    "home-lightning-bolt": "\U0001f3e0",
    "home-lightning-bolt-outline": "\U0001f3e0",
    "party-popper": "\U0001f389",
    "exit-run": "\U0001f3c3",
    "run": "\U0001f3c3",
    "home-export-outline": "\U0001f3c3",
    "account-arrow-right": "\U0001f3c3",
    "account-multiple": "\U0001f465",
    "bed": "\U0001f6cf\ufe0f",
    "bed-outline": "\U0001f6cf\ufe0f",
    "car-sports": "\U0001f3ce\ufe0f",
}

DOMAIN_EMOJI = {
    "person": "\U0001f464",
    "light": "\U0001f4a1",
    "switch": "\U0001f50c",
    "fan": "\U0001f300",
    "climate": "\U0001f321\ufe0f",
    "lock": "\U0001f512",
    "cover": "\U0001fa9f",
    "sensor": "\U0001f4ca",
    "binary_sensor": "\u26a1",
    "camera": "\U0001f4f9",
    "media_player": "\U0001f4fa",
    "alarm_control_panel": "\U0001f6e1\ufe0f",
    "input_boolean": "\U0001f518",
    "weather": "\u2600\ufe0f",
    "input_datetime": "\U0001f550",
    "input_number": "\U0001f522",
    "zone": "\U0001f4cd",
    "device_tracker": "\U0001f4cd",
    "image": "\U0001f5bc\ufe0f",
    "select": "\U0001f4cb",
    "button": "\U0001f518",
    "number": "\U0001f522",
    "vacuum": "\U0001f916",
    "input_select": "\U0001f4cb",
    "input_button": "\U0001f518",
    "automation": "\u2699\ufe0f",
    "script": "\U0001f4dc",
    "scene": "\U0001f3ad",
    "group": "\U0001f4e6",
    "timer": "\u23f1\ufe0f",
    "counter": "\U0001f522",
    "update": "\u2b07\ufe0f",
    "remote": "\U0001f4e1",
    "siren": "\U0001f4e2",
    "water_heater": "\U0001f525",
    "humidifier": "\U0001f4a7",
}

DEVICE_CLASS_EMOJI = {
    "temperature": "\U0001f321\ufe0f",
    "humidity": "\U0001f4a7",
    "battery": "\U0001f50b",
    "power": "\u26a1",
    "energy": "\u26a1",
    "voltage": "\u26a1",
    "current": "\u26a1",
    "illuminance": "\u2600\ufe0f",
    "pressure": "\U0001f321\ufe0f",
    "carbon_dioxide": "\U0001f4a8",
    "carbon_monoxide": "\U0001f4a8",
    "pm25": "\U0001f4a8",
    "pm10": "\U0001f4a8",
    "volatile_organic_compounds": "\U0001f4a8",
    "nitrogen_dioxide": "\U0001f4a8",
    "motion": "\U0001f6b6",
    "occupancy": "\U0001f464",
    "door": "\U0001f6aa",
    "window": "\U0001fa9f",
    "moisture": "\U0001f4a7",
    "gas": "\U0001f525",
    "connectivity": "\U0001f4f6",
    "plug": "\U0001f50c",
    "problem": "\u26a0\ufe0f",
    "safety": "\u26a0\ufe0f",
    "sound": "\U0001f50a",
    "opening": "\U0001f6aa",
    "garage_door": "\U0001f697",
}


class RichViewRenderer:
    """Renders a RenderedView model to Rich console output.

    Pure sync class — no HAClient, no async. Takes a fully resolved
    RenderedView and produces identical output to the old ViewRenderer.
    """

    SEMANTIC_COLOR_MAP: ClassVar[dict[SemanticColor, str]] = {
        SemanticColor.INACTIVE: "dim",
        SemanticColor.POSITIVE: "green",
        SemanticColor.ACTIVE: "yellow",
        SemanticColor.WARNING: "bold yellow",
        SemanticColor.DANGER: "bold red",
        SemanticColor.INFO: "cyan",
        SemanticColor.HEAT: "red",
        SemanticColor.COOL: "blue",
    }

    @staticmethod
    def pad_emoji(emoji: str, target_width: int = 2) -> str:
        """Pad emoji to consistent terminal cell width.

        Many emojis (especially those with FE0F variation selectors or ZWJ
        sequences) have cell_len that doesn't match their actual terminal
        rendering width. This pads to a target width for consistent alignment.
        """
        padding = max(0, target_width - cell_len(emoji))
        return emoji + " " * padding

    def resolve_icon(self, icon: RenderedIcon) -> str:
        """Resolve a RenderedIcon to an emoji string.

        Fallback chain: mdi_name direct -> partial match -> device_class -> domain -> bullet.
        """
        mdi_name = icon.mdi_name
        entity_id = icon.entity_id
        device_class = icon.device_class

        if not mdi_name and entity_id:
            if device_class and device_class in DEVICE_CLASS_EMOJI:
                return DEVICE_CLASS_EMOJI[device_class]
            domain = entity_id.split(".")[0]
            return DOMAIN_EMOJI.get(domain, "\u2022")

        if not mdi_name:
            return "\u2022"

        if mdi_name in ICON_EMOJI:
            return ICON_EMOJI[mdi_name]

        for key, emoji in ICON_EMOJI.items():
            if key in mdi_name:
                return emoji

        # Unrecognized icon — fall back to domain/device_class
        if entity_id:
            if device_class and device_class in DEVICE_CLASS_EMOJI:
                return DEVICE_CLASS_EMOJI[device_class]
            domain = entity_id.split(".")[0]
            return DOMAIN_EMOJI.get(domain, "\u2022")

        return "\u2022"

    def _resolve_color(self, color: SemanticColor | None) -> str | None:
        """Map a SemanticColor to a Rich style string."""
        if color is None:
            return None
        return self.SEMANTIC_COLOR_MAP.get(color)

    def _render_badge(self, badge: RenderedBadge) -> Text | None:
        """Render a single badge as a Rich Text object."""
        if isinstance(badge, RenderedEntityBadge):
            has_icon = badge.icon.mdi_name or badge.icon.entity_id
            emoji = self.resolve_icon(badge.icon) if has_icon else ""
            display_name = badge.name

            text = Text()
            if emoji:
                text.append(f"{self.pad_emoji(emoji)} ")
            text.append(f"{display_name}")

            if badge.state.text:
                text.append(": ")
                text.append(badge.state.text, style=self._resolve_color(badge.state.color))

            if text.plain.strip() in ("", emoji.strip()):
                return None
            return text

        elif isinstance(badge, RenderedTemplateBadge):
            emoji = self.resolve_icon(badge.icon)
            text = Text()
            text.append(f"{self.pad_emoji(emoji)} ")

            if badge.content:
                style = self._resolve_color(badge.content_color)
                text.append(badge.content, style=style)

            if badge.label:
                text.append(f" ({badge.label})", style="dim")

            return text if text.plain.strip() and text.plain.strip() != emoji.strip() else None

        return None

    def _render_tile(self, tile: RenderedTile) -> Text:
        """Render a tile as a Rich Text object."""
        emoji = self.resolve_icon(tile.icon)
        style = self._resolve_color(tile.state.color)

        text = Text()
        text.append(f"  {self.pad_emoji(emoji)} {tile.name}")
        if tile.state.text:
            text.append(": ")
            text.append(tile.state.text, style=style)

        return text

    def _render_heading(self, heading: RenderedHeading) -> list[Text]:
        """Render a heading as a list of Rich Text lines."""
        has_icon = heading.icon.mdi_name or heading.icon.entity_id
        emoji = self.resolve_icon(heading.icon) if has_icon else ""

        lines: list[Text] = []

        header = Text()
        if emoji:
            header.append(f"{self.pad_emoji(emoji)} ")
        header.append(heading.heading.upper(), style="bold")
        lines.append(header)

        for badge in heading.badges:
            rendered = self._render_badge(badge)
            if rendered:
                badge_line = Text("  ")
                badge_line.append_text(rendered)
                lines.append(badge_line)

        return lines

    def _render_auto_entities(self, auto: RenderedAutoEntities) -> list[Text]:
        """Render auto-entities card tiles."""
        return [self._render_tile(tile) for tile in auto.tiles]

    def _render_logbook(self, logbook: RenderedLogbook) -> list[Text]:
        """Render a logbook card."""
        lines: list[Text] = []
        for entry in logbook.entries:
            style = self._resolve_color(entry.state.color)
            text = Text("  ")
            text.append(f"{entry.name}: ", style="dim")
            text.append(entry.state.text, style=style)
            text.append(f" ({entry.time_ago})", style="dim")
            lines.append(text)
        return lines

    def _render_weather(self, weather: RenderedWeather) -> Text:
        """Render a weather card."""
        emoji = self.resolve_icon(weather.icon)

        text = Text()
        text.append(f"  {self.pad_emoji(emoji)} ")
        text.append(weather.condition, style="cyan")
        if weather.temperature:
            text.append(f"  {weather.temperature}")
        return text

    def render(self, view: RenderedView) -> None:
        """Render a RenderedView to the Rich console.

        Produces output identical to the old ViewRenderer.render_view method.
        """
        # Render header
        emoji = self.resolve_icon(view.icon)

        header = Text()
        header.append(f"\u2550\u2550\u2550 {self.pad_emoji(emoji)} ", style="bold")
        header.append(view.title.upper(), style="bold cyan")
        header.append(" \u2550\u2550\u2550", style="bold")
        console.print(header)

        # Badges
        for badge in view.badges:
            rendered = self._render_badge(badge)
            if rendered:
                line = Text("  ")
                line.append_text(rendered)
                console.print(line)

        # Sections
        for section in view.sections:
            for item in section.items:
                if isinstance(item, RenderedSpacing):
                    console.print()
                elif isinstance(item, RenderedHeading):
                    for line in self._render_heading(item):
                        console.print(line)
                elif isinstance(item, RenderedTile):
                    console.print(self._render_tile(item))
                elif isinstance(item, RenderedAutoEntities):
                    for line in self._render_auto_entities(item):
                        console.print(line)
                elif isinstance(item, RenderedLogbook):
                    for line in self._render_logbook(item):
                        console.print(line)
                elif isinstance(item, RenderedWeather):
                    console.print(self._render_weather(item))


# =============================================================================
# Entry points
# =============================================================================


async def render_view_file(client: HAClient, view_path: Path, user: str | None = None) -> None:
    """Render a dashboard view file.

    Args:
        client: Connected HAClient instance
        view_path: Path to the dashboard view YAML file
        user: Optional user name for user-specific visibility
    """
    resolver = ViewResolver(client)
    try:
        view = await resolver.resolve_view(view_path, user)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return
    except ValueError as e:
        msg = str(e)
        if "Unknown user" in msg:
            # Split into error + available hint
            parts = msg.split(". Available: ", 1)
            console.print(f"[red]{parts[0]}[/red]")
            if len(parts) > 1:
                console.print(f"[dim]Available: {parts[1]}[/dim]")
        else:
            console.print(f"[red]{e}[/red]")
        return

    renderer = RichViewRenderer()
    renderer.render(view)

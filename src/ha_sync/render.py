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
    AutoEntitiesCardConfig,
    CachedEntityState,
    CardConfig,
    EntityBadgeConfig,
    FormattedState,
    HeadingCardConfig,
    LogbookCardConfig,
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
    SectionConfig,
    SemanticColor,
    TemplateBadgeConfig,
    TileCardConfig,
    ViewConfig,
    VisibilityCondition,
    VisibilityConditionAnd,
    VisibilityConditionNot,
    VisibilityConditionNumericState,
    VisibilityConditionOr,
    VisibilityConditionScreen,
    VisibilityConditionState,
    VisibilityConditionUser,
    WeatherCardConfig,
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
        self.state_cache: dict[str, CachedEntityState] = {}
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
                        self.state_cache[entity_id] = CachedEntityState(
                            state=state,
                            name=name,
                            unit=unit,
                            icon=icon,
                            device_class=device_class,
                        )
            except Exception as e:
                console.print(
                    f"[dim]Warning: Failed to fetch states for batch: {type(e).__name__}: {e}[/dim]"
                )

        # Fill in missing icons from entity registry (platform-provided icons)
        missing_icon_entities = [eid for eid, cached in self.state_cache.items() if not cached.icon]
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
                        self.state_cache[entity_id].icon = icon
        except Exception:
            pass  # Registry not available, fall back to domain/device_class

    def get_state(self, entity_id: str) -> str:
        """Get current state of an entity from cache."""
        if entity_id in self.state_cache:
            return self.state_cache[entity_id].state
        return "unknown"

    def get_attribute(self, entity_id: str, attribute: str) -> Any:
        """Get an attribute of an entity from cache."""
        if entity_id in self.state_cache:
            if attribute == "friendly_name":
                return self.state_cache[entity_id].name
            elif attribute == "unit_of_measurement":
                return self.state_cache[entity_id].unit
        return None

    def get_display_name(self, entity_id: str) -> str:
        """Get friendly_name from HA, or clean up entity_id as fallback."""
        if entity_id in self.state_cache:
            name = self.state_cache[entity_id].name
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

    def check_visibility(self, conditions: list[VisibilityCondition]) -> bool:
        """Check if visibility conditions are met. Returns True if visible."""
        if not conditions:
            return True

        for condition in conditions:
            if isinstance(condition, VisibilityConditionState):
                if not condition.entity:
                    return False
                state = self.get_state(condition.entity)
                if condition.state is not None and state != str(condition.state):
                    return False
                if condition.state_not is not None and state == str(condition.state_not):
                    return False

            elif isinstance(condition, VisibilityConditionNumericState):
                if not condition.entity:
                    return False
                state = self.get_state(condition.entity)
                try:
                    value = float(state)
                    if condition.above is not None and value <= condition.above:
                        return False
                    if condition.below is not None and value >= condition.below:
                        return False
                except (ValueError, TypeError):
                    return False

            elif isinstance(condition, VisibilityConditionScreen):
                if "max-width: 767px" in condition.media_query:
                    return False  # Mobile-only

            elif isinstance(condition, VisibilityConditionUser):
                if self.current_user is None:
                    return False
                if self.current_user not in condition.users:
                    return False

            elif isinstance(condition, VisibilityConditionOr):
                if not any(self.check_visibility([c]) for c in condition.conditions):
                    return False

            elif isinstance(condition, VisibilityConditionAnd):
                if not all(self.check_visibility([c]) for c in condition.conditions):
                    return False

            elif isinstance(condition, VisibilityConditionNot):
                if self.check_visibility(condition.conditions):
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
            "{% for k, v in e.attributes.items() if v is string or v is number %}"
            "{{ k | tojson }}: {{ v | string | tojson }}"
            "{% if not loop.last %}, {% endif %}"
            "{% endfor %}"
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
        """Create a RenderedIcon from a raw icon string and entity context.

        For weather entities without an explicit icon, uses the condition state
        as the icon name (e.g. "weather-partlycloudy") so renderers can map to
        condition-specific symbols.
        """
        mdi_name: str | None = None
        if icon:
            mdi_name = icon.replace("mdi:", "").lower()

        device_class: str | None = None
        if entity_id:
            cached = self.state_cache.get(entity_id)
            device_class = (cached.device_class if cached else "") or None

        # Weather entities: use condition as icon for condition-based SF Symbol lookup
        if not mdi_name and entity_id and entity_id.startswith("weather."):
            state = self.get_state(entity_id)
            if state not in ("unavailable", "unknown"):
                mdi_name = f"weather-{state.replace('_', '-')}"

        return RenderedIcon(
            mdi_name=mdi_name,
            entity_id=entity_id,
            device_class=device_class,
        )

    # -- Format state helper --

    def _format_state(self, entity_id: str, state: str) -> FormattedState:
        """Format entity state using the shared format_state function."""
        cached = self.state_cache.get(entity_id)
        device_class = cached.device_class if cached else ""
        unit = cached.unit if cached else ""
        return format_state(entity_id, state, device_class=device_class, unit=unit)

    # -- Resolve methods --

    async def _resolve_badge(
        self, badge: EntityBadgeConfig | TemplateBadgeConfig
    ) -> RenderedBadge | None:
        """Resolve a single badge into a RenderedBadge model."""
        if not self.check_visibility(badge.visibility):
            return None

        if isinstance(badge, EntityBadgeConfig):
            entity_id = badge.entity
            if not entity_id:
                return None

            state = self.get_state(entity_id)
            cached = self.state_cache.get(entity_id)
            icon_str = badge.icon or (cached.icon if cached else "")

            display_name = badge.name or self.get_display_name(entity_id)

            formatted = self._format_state(entity_id, state)

            if badge.state_content == "name":
                formatted = FormattedState(text="")

            icon = self._make_icon(
                icon_str if badge.show_icon else None,
                entity_id if badge.show_icon else None,
            )

            if not display_name and not formatted.text:
                return None

            return RenderedEntityBadge(
                entity_id=entity_id,
                name=display_name,
                state=formatted,
                icon=icon,
            )

        elif isinstance(badge, TemplateBadgeConfig):
            entity_id = badge.entity
            icon_str = badge.icon or ""
            # Icon can be a template (e.g. conditional mdi:controller vs mdi:television)
            if icon_str and "{" in icon_str:
                icon_str = (await self.eval_template(icon_str, entity_id)).strip()

            icon = self._make_icon(icon_str, entity_id)

            content: str | None = None
            content_color: SemanticColor | None = None
            if badge.content:
                rendered = await self.eval_template(badge.content, entity_id)
                if rendered and rendered != "[error]":
                    content = rendered
                    if rendered.lower() in ("home", "oasis"):
                        content_color = SemanticColor.POSITIVE
                    elif rendered.lower() in ("away", "not_home"):
                        content_color = SemanticColor.INACTIVE
                    else:
                        content_color = SemanticColor.INFO

            label: str | None = None
            if badge.label:
                rendered = await self.eval_template(badge.label, entity_id)
                if rendered and rendered != "[error]":
                    label = rendered

            if not content and not label and not icon.mdi_name:
                return None

            return RenderedTemplateBadge(
                entity_id=entity_id,
                content=content,
                content_color=content_color,
                label=label,
                icon=icon,
            )

        return None

    def _resolve_tile(self, card: TileCardConfig) -> RenderedTile | None:
        """Resolve a tile card into a RenderedTile model."""
        if not self.check_visibility(card.visibility):
            return None

        entity_id = card.entity
        if not entity_id:
            return None

        state = self.get_state(entity_id)
        name = card.name or self.get_display_name(entity_id)
        cached = self.state_cache.get(entity_id)
        icon_str = card.icon or (cached.icon if cached else "")

        icon = self._make_icon(icon_str, entity_id)
        formatted = self._format_state(entity_id, state)

        return RenderedTile(
            entity_id=entity_id,
            name=name,
            state=formatted,
            icon=icon,
        )

    async def _resolve_heading(self, card: HeadingCardConfig) -> RenderedHeading | None:
        """Resolve a heading card into a RenderedHeading model."""
        if not self.check_visibility(card.visibility):
            return None

        if not card.heading and not card.icon:
            return None

        icon = self._make_icon(card.icon) if card.icon else RenderedIcon()

        badges: list[RenderedBadge] = []
        for badge in card.badges:
            rendered = await self._resolve_badge(badge)
            if rendered:
                badges.append(rendered)

        return RenderedHeading(
            heading=card.heading,
            icon=icon,
            badges=badges,
        )

    async def _resolve_auto_entities(self, card: AutoEntitiesCardConfig) -> RenderedAutoEntities:
        """Resolve auto-entities card by evaluating filter rules."""
        tiles: list[RenderedTile] = []

        if card.card.type in ("custom:map-card", "logbook"):
            return RenderedAutoEntities(tiles=tiles)

        matched_entities: list[tuple[str, dict[str, Any]]] = []

        for rule in card.filter.include:
            if rule.entity_id and not rule.domain:
                entity_id = rule.entity_id
                if entity_id not in self.state_cache:
                    await self.fetch_all_states({entity_id})
                if entity_id in self.state_cache:
                    matched_entities.append((entity_id, rule.options))
                continue

            if not rule.domain:
                continue

            if rule.integration:
                continue

            domain_entities = await self.search_entities(domain=rule.domain)
            include_label_entities = (
                await self.get_entities_with_label(rule.label) if rule.label else None
            )

            for ent in domain_entities:
                entity_id = ent["entity_id"]
                state = ent["state"]

                if entity_id in [m[0] for m in matched_entities]:
                    continue

                if include_label_entities is not None and entity_id not in include_label_entities:
                    continue

                skip = False
                if rule.not_:
                    for cond in rule.not_.or_:
                        if cond.state is not None and state == cond.state:
                            skip = True
                            break
                        if cond.label is not None:
                            label_entities = await self.get_entities_with_label(cond.label)
                            if entity_id in label_entities:
                                skip = True
                                break

                if skip:
                    continue

                attr_match = True
                ent_attrs = ent.get("attributes", {})
                for attr_name, attr_val in rule.attributes.items():
                    ent_attr = str(ent_attrs.get(attr_name, "")).lower()
                    expected = str(attr_val).lower()
                    if ent_attr != expected:
                        attr_match = False
                        break
                if not attr_match:
                    continue

                matched_entities.append((entity_id, rule.options))
                self.state_cache[entity_id] = CachedEntityState(
                    state=ent["state"],
                    name=ent["name"],
                    icon=ent.get("icon", ""),
                )

        seen: set[str] = set()
        unique_entities: list[tuple[str, dict[str, Any]]] = []
        for entity_id, options in matched_entities:
            if entity_id not in seen:
                seen.add(entity_id)
                unique_entities.append((entity_id, options))

        for entity_id, options in unique_entities:
            cached = self.state_cache.get(entity_id)
            state = cached.state if cached else ""
            if state in ("unavailable", "unknown", ""):
                continue

            opt_name = options.get("name", "").strip()
            cached_name = cached.name if cached else ""
            fallback_name = entity_id.split(".")[-1].replace("_", " ").title()
            name = opt_name if opt_name else cached_name or fallback_name
            icon_str = options.get("icon", "") or (cached.icon if cached else "")
            icon = self._make_icon(icon_str, entity_id)
            formatted = self._format_state(entity_id, state)

            tiles.append(
                RenderedTile(
                    entity_id=entity_id,
                    name=name,
                    state=formatted,
                    icon=icon,
                )
            )

        return RenderedAutoEntities(tiles=tiles)

    async def _resolve_logbook(
        self, card: LogbookCardConfig, max_entries: int = 5
    ) -> RenderedLogbook:
        """Resolve a logbook card into a RenderedLogbook model."""
        from datetime import UTC, datetime

        entries: list[RenderedLogbookEntry] = []

        target_ids = card.target.entity_id
        entity_ids: list[str] = [target_ids] if isinstance(target_ids, str) else list(target_ids)
        if not entity_ids:
            entity_ids = [card.entities] if isinstance(card.entities, str) else list(card.entities)

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

            cached = self.state_cache.get(entity_id)
            icon_str = cached.icon if cached else ""
            icon = self._make_icon(icon_str, entity_id)

            entries.append(
                RenderedLogbookEntry(
                    entity_id=entity_id,
                    name=name,
                    state=formatted,
                    time_ago=time_str,
                    icon=icon,
                )
            )

        return RenderedLogbook(entries=entries)

    async def _resolve_weather(self, card: WeatherCardConfig) -> RenderedWeather | None:
        """Resolve a weather-forecast card into a RenderedWeather model."""
        entity_id = card.entity
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

        cached = self.state_cache.get(entity_id)
        icon_str = cached.icon if cached else ""
        icon = self._make_icon(icon_str, entity_id)

        return RenderedWeather(
            entity_id=entity_id,
            condition=condition,
            raw_condition=state,
            temperature=temp_str,
            icon=icon,
        )

    async def _resolve_card(self, card: CardConfig) -> list[RenderedSectionItem]:
        """Resolve a single card into RenderedSectionItem(s)."""
        if not self.check_visibility(card.visibility):
            return []

        if isinstance(card, TileCardConfig):
            tile = self._resolve_tile(card)
            return [tile] if tile else []
        elif isinstance(card, HeadingCardConfig):
            heading = await self._resolve_heading(card)
            return [heading] if heading else []
        elif isinstance(card, AutoEntitiesCardConfig):
            auto = await self._resolve_auto_entities(card)
            return [auto] if auto.tiles else []
        elif isinstance(card, LogbookCardConfig):
            logbook = await self._resolve_logbook(card)
            return [logbook] if logbook.entries else []
        elif isinstance(card, WeatherCardConfig):
            weather = await self._resolve_weather(card)
            return [weather] if weather else []

        return []

    async def _resolve_section(self, section: SectionConfig) -> RenderedSection:
        """Resolve a section into a RenderedSection model.

        Implements the pending heading pattern: headings with only text (no badges)
        are deferred until non-heading content follows. A blank line (RenderedSpacing)
        is inserted before headings that have subsequent content.
        """
        if not self.check_visibility(section.visibility):
            return RenderedSection()

        items: list[RenderedSectionItem] = []
        pending_heading: RenderedHeading | None = None

        for card in section.cards:
            if isinstance(card, HeadingCardConfig) and card.heading:
                resolved_heading = await self._resolve_heading(card)
                if resolved_heading:
                    if pending_heading:
                        # Previous heading had no content — emit it now
                        items.append(RenderedSpacing())
                        items.append(pending_heading)
                        pending_heading = None
                    if resolved_heading.badges:
                        # Heading with badges — emit immediately
                        items.append(RenderedSpacing())
                        items.append(resolved_heading)
                    else:
                        # Heading without badges — defer
                        pending_heading = resolved_heading
                continue

            card_items = await self._resolve_card(card)

            if card_items and pending_heading:
                items.append(RenderedSpacing())
                items.append(pending_heading)
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
            raw = yaml.safe_load(f)

        if not raw:
            raise ValueError(f"Could not parse view file: {view_path}")

        view_config = ViewConfig.model_validate(raw)

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
        self.extract_entities(raw, entities)
        await self.fetch_all_states(entities)

        # Resolve header
        icon = self._make_icon(view_config.icon)

        # Resolve badges
        badges: list[RenderedBadge] = []
        for badge_config in view_config.badges:
            rendered = await self._resolve_badge(badge_config)
            if rendered:
                badges.append(rendered)

        # Resolve sections
        sections: list[RenderedSection] = []
        for section_config in view_config.sections:
            resolved = await self._resolve_section(section_config)
            if resolved.items:
                sections.append(resolved)

        return RenderedView(
            title=view_config.title,
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

        Emoji with FE0F variation selectors render as 2 cells wide in
        most terminals but cell_len() reports them as 1. We correct for
        this so all icons align consistently.
        """
        width = cell_len(emoji)
        if "\ufe0f" in emoji and width < 2:
            width = 2
        padding = max(0, target_width - width)
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

            if not text.plain.strip():
                return None
            return text

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

"""Home Assistant WebSocket and HTTP client."""

import contextlib
from typing import Any

import aiohttp
import httpx
import logfire


class AuthenticationFailed(Exception):
    """Authentication failed."""


class ConnectionFailed(Exception):
    """Connection failed."""


class NotConnected(Exception):
    """Not connected to Home Assistant."""


__all__ = [
    "AuthenticationFailed",
    "ConnectionFailed",
    "HAClient",
    "NotConnected",
]


class HAClient:
    """Home Assistant client with WebSocket and HTTP support."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self._ws_session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._msg_id = 0
        self._ha_version: str | None = None

    @logfire.instrument("Connecting to Home Assistant")
    async def connect(self) -> None:
        """Connect to Home Assistant via WebSocket."""
        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"

        self._ws_session = aiohttp.ClientSession()
        try:
            self._ws = await self._ws_session.ws_connect(ws_url)

            # Receive auth_required
            msg = await self._ws.receive_json()
            if msg.get("type") != "auth_required":
                raise ConnectionFailed(f"Unexpected message: {msg}")
            self._ha_version = msg.get("ha_version")
            logfire.info("Connected to Home Assistant {ha_version}", ha_version=self._ha_version)

            # Send authentication
            await self._ws.send_json({"type": "auth", "access_token": self.token})

            # Receive auth result
            msg = await self._ws.receive_json()
            if msg.get("type") == "auth_invalid":
                raise AuthenticationFailed(msg.get("message", "Authentication failed"))
            if msg.get("type") != "auth_ok":
                raise ConnectionFailed(f"Unexpected auth response: {msg}")

        except aiohttp.ClientError as e:
            await self._cleanup_ws()
            logfire.error("WebSocket connection failed: {error}", error=str(e))
            raise ConnectionFailed(str(e)) from e

    async def _cleanup_ws(self) -> None:
        """Clean up WebSocket resources."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._ws_session:
            await self._ws_session.close()
            self._ws_session = None

    async def disconnect(self) -> None:
        """Disconnect from Home Assistant."""
        await self._cleanup_ws()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def http(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._http_client

    async def send_command(self, command_type: str, **kwargs: Any) -> Any:
        """Send a WebSocket command and return the result."""
        if not self._ws:
            raise NotConnected("Not connected to Home Assistant")

        self._msg_id += 1
        msg_id = self._msg_id

        with logfire.span(
            "WebSocket: {command_type}", command_type=command_type, request=kwargs
        ) as span:
            await self._ws.send_json({"id": msg_id, "type": command_type, **kwargs})

            # Wait for response with matching ID
            while True:
                response = await self._ws.receive_json()
                if response.get("id") == msg_id:
                    if not response.get("success", True):
                        error = response.get("error", {})
                        code = error.get("code", "error")
                        msg = error.get("message", "Unknown error")
                        logfire.warning(
                            "WebSocket command failed: {code}: {msg}", code=code, msg=msg
                        )
                        raise Exception(f"{code}: {msg}")
                    result = response.get("result")
                    span.set_attribute("response", result)
                    return result
                # Skip events and other messages

    @logfire.instrument("Call service: {domain}.{service}")
    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
    ) -> Any:
        """Call a Home Assistant service."""
        kwargs: dict[str, Any] = {"domain": domain, "service": service}
        if service_data:
            kwargs["service_data"] = service_data
        if target:
            kwargs["target"] = target
        return await self.send_command("call_service", **kwargs)

    # --- Dashboard (Lovelace) Commands ---

    async def get_dashboards(self) -> list[dict[str, Any]]:
        """List all dashboards."""
        result = await self.send_command("lovelace/dashboards/list")
        return result if isinstance(result, list) else []

    async def get_dashboard_config(self, url_path: str | None = None) -> dict[str, Any]:
        """Get dashboard configuration."""
        kwargs = {}
        if url_path is not None:
            kwargs["url_path"] = url_path
        result = await self.send_command("lovelace/config", **kwargs)
        return result if isinstance(result, dict) else {}

    async def save_dashboard_config(
        self, config: dict[str, Any], url_path: str | None = None
    ) -> None:
        """Save dashboard configuration."""
        kwargs: dict[str, Any] = {"config": config}
        if url_path is not None:
            kwargs["url_path"] = url_path
        await self.send_command("lovelace/config/save", **kwargs)

    async def create_dashboard(
        self,
        url_path: str,
        title: str,
        icon: str | None = None,
        show_in_sidebar: bool = True,
        require_admin: bool = False,
    ) -> None:
        """Create a new dashboard."""
        kwargs: dict[str, Any] = {
            "url_path": url_path,
            "title": title,
            "show_in_sidebar": show_in_sidebar,
            "require_admin": require_admin,
            "mode": "storage",  # UI-managed dashboard
        }
        if icon:
            kwargs["icon"] = icon
        await self.send_command("lovelace/dashboards/create", **kwargs)

    async def update_dashboard(
        self,
        dashboard_id: str,
        title: str | None = None,
        icon: str | None = None,
        show_in_sidebar: bool | None = None,
        require_admin: bool | None = None,
    ) -> None:
        """Update dashboard metadata."""
        kwargs: dict[str, Any] = {"dashboard_id": dashboard_id}
        if title is not None:
            kwargs["title"] = title
        if icon is not None:
            kwargs["icon"] = icon
        if show_in_sidebar is not None:
            kwargs["show_in_sidebar"] = show_in_sidebar
        if require_admin is not None:
            kwargs["require_admin"] = require_admin
        await self.send_command("lovelace/dashboards/update", **kwargs)

    async def delete_dashboard(self, dashboard_id: str) -> None:
        """Delete a dashboard."""
        await self.send_command("lovelace/dashboards/delete", dashboard_id=dashboard_id)

    # --- Automation Commands ---

    @logfire.instrument("Get automations")
    async def get_automations(self) -> list[dict[str, Any]]:
        """Get all automations via REST API."""
        response = await self.http.get("/api/states")
        response.raise_for_status()
        states = response.json()
        return [s for s in states if s["entity_id"].startswith("automation.")]

    @logfire.instrument("Get automation config: {automation_id}")
    async def get_automation_config(self, automation_id: str) -> dict[str, Any]:
        """Get automation configuration."""
        response = await self.http.get(f"/api/config/automation/config/{automation_id}")
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    @logfire.instrument("Save automation config: {automation_id}")
    async def save_automation_config(self, automation_id: str, config: dict[str, Any]) -> None:
        """Save automation configuration."""
        response = await self.http.post(
            f"/api/config/automation/config/{automation_id}",
            json=config,
        )
        response.raise_for_status()

    @logfire.instrument("Delete automation: {automation_id}")
    async def delete_automation(self, automation_id: str) -> None:
        """Delete an automation."""
        response = await self.http.delete(f"/api/config/automation/config/{automation_id}")
        response.raise_for_status()

    async def reload_automations(self) -> None:
        """Reload automations."""
        await self.call_service("automation", "reload")

    # --- Script Commands ---

    @logfire.instrument("Get scripts")
    async def get_scripts(self) -> list[dict[str, Any]]:
        """Get all scripts via states."""
        response = await self.http.get("/api/states")
        response.raise_for_status()
        states = response.json()
        return [s for s in states if s["entity_id"].startswith("script.")]

    @logfire.instrument("Get script config: {script_id}")
    async def get_script_config(self, script_id: str) -> dict[str, Any]:
        """Get script configuration."""
        response = await self.http.get(f"/api/config/script/config/{script_id}")
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    @logfire.instrument("Save script config: {script_id}")
    async def save_script_config(self, script_id: str, config: dict[str, Any]) -> None:
        """Save script configuration."""
        response = await self.http.post(
            f"/api/config/script/config/{script_id}",
            json=config,
        )
        response.raise_for_status()

    @logfire.instrument("Delete script: {script_id}")
    async def delete_script(self, script_id: str) -> None:
        """Delete a script."""
        response = await self.http.delete(f"/api/config/script/config/{script_id}")
        response.raise_for_status()

    async def reload_scripts(self) -> None:
        """Reload scripts."""
        await self.call_service("script", "reload")

    # --- Scene Commands ---

    @logfire.instrument("Get scenes")
    async def get_scenes(self) -> list[dict[str, Any]]:
        """Get all scenes via states."""
        response = await self.http.get("/api/states")
        response.raise_for_status()
        states = response.json()
        return [s for s in states if s["entity_id"].startswith("scene.")]

    @logfire.instrument("Get scene config: {scene_id}")
    async def get_scene_config(self, scene_id: str) -> dict[str, Any]:
        """Get scene configuration."""
        response = await self.http.get(f"/api/config/scene/config/{scene_id}")
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    @logfire.instrument("Save scene config: {scene_id}")
    async def save_scene_config(self, scene_id: str, config: dict[str, Any]) -> None:
        """Save scene configuration."""
        response = await self.http.post(
            f"/api/config/scene/config/{scene_id}",
            json=config,
        )
        response.raise_for_status()

    @logfire.instrument("Delete scene: {scene_id}")
    async def delete_scene(self, scene_id: str) -> None:
        """Delete a scene."""
        response = await self.http.delete(f"/api/config/scene/config/{scene_id}")
        response.raise_for_status()

    async def reload_scenes(self) -> None:
        """Reload scenes."""
        await self.call_service("scene", "reload")

    # --- Helper Commands (via WebSocket) ---

    async def _get_helpers(self, helper_type: str) -> list[dict[str, Any]]:
        """Get all helpers of a specific type."""
        result = await self.send_command(f"{helper_type}/list")
        return result if isinstance(result, list) else []

    async def _create_helper(self, helper_type: str, config: dict[str, Any]) -> None:
        """Create a helper."""
        await self.send_command(f"{helper_type}/create", **config)

    async def _update_helper(
        self, helper_type: str, helper_id: str, config: dict[str, Any]
    ) -> None:
        """Update a helper."""
        config_copy = {k: v for k, v in config.items() if k != "id"}
        await self.send_command(
            f"{helper_type}/update", **{f"{helper_type}_id": helper_id, **config_copy}
        )

    async def _delete_helper(self, helper_type: str, helper_id: str) -> None:
        """Delete a helper."""
        await self.send_command(f"{helper_type}/delete", **{f"{helper_type}_id": helper_id})

    # Input Boolean
    async def get_input_booleans(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_boolean")

    async def create_input_boolean(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_boolean", config)

    async def update_input_boolean(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_boolean", helper_id, config)

    async def delete_input_boolean(self, helper_id: str) -> None:
        await self._delete_helper("input_boolean", helper_id)

    # Input Number
    async def get_input_numbers(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_number")

    async def create_input_number(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_number", config)

    async def update_input_number(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_number", helper_id, config)

    async def delete_input_number(self, helper_id: str) -> None:
        await self._delete_helper("input_number", helper_id)

    # Input Select
    async def get_input_selects(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_select")

    async def create_input_select(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_select", config)

    async def update_input_select(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_select", helper_id, config)

    async def delete_input_select(self, helper_id: str) -> None:
        await self._delete_helper("input_select", helper_id)

    # Input Text
    async def get_input_texts(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_text")

    async def create_input_text(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_text", config)

    async def update_input_text(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_text", helper_id, config)

    async def delete_input_text(self, helper_id: str) -> None:
        await self._delete_helper("input_text", helper_id)

    # Input Datetime
    async def get_input_datetimes(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_datetime")

    async def create_input_datetime(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_datetime", config)

    async def update_input_datetime(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_datetime", helper_id, config)

    async def delete_input_datetime(self, helper_id: str) -> None:
        await self._delete_helper("input_datetime", helper_id)

    # Input Button
    async def get_input_buttons(self) -> list[dict[str, Any]]:
        return await self._get_helpers("input_button")

    async def create_input_button(self, config: dict[str, Any]) -> None:
        await self._create_helper("input_button", config)

    async def update_input_button(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("input_button", helper_id, config)

    async def delete_input_button(self, helper_id: str) -> None:
        await self._delete_helper("input_button", helper_id)

    # Timer
    async def get_timers(self) -> list[dict[str, Any]]:
        return await self._get_helpers("timer")

    async def create_timer(self, config: dict[str, Any]) -> None:
        await self._create_helper("timer", config)

    async def update_timer(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("timer", helper_id, config)

    async def delete_timer(self, helper_id: str) -> None:
        await self._delete_helper("timer", helper_id)

    # Schedule
    async def get_schedules(self) -> list[dict[str, Any]]:
        return await self._get_helpers("schedule")

    async def create_schedule(self, config: dict[str, Any]) -> None:
        await self._create_helper("schedule", config)

    async def update_schedule(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("schedule", helper_id, config)

    async def delete_schedule(self, helper_id: str) -> None:
        await self._delete_helper("schedule", helper_id)

    # Counter
    async def get_counters(self) -> list[dict[str, Any]]:
        return await self._get_helpers("counter")

    async def create_counter(self, config: dict[str, Any]) -> None:
        await self._create_helper("counter", config)

    async def update_counter(self, helper_id: str, config: dict[str, Any]) -> None:
        await self._update_helper("counter", helper_id, config)

    async def delete_counter(self, helper_id: str) -> None:
        await self._delete_helper("counter", helper_id)

    async def reload_helpers(self) -> None:
        """Reload all helper integrations."""
        for domain in [
            "input_boolean",
            "input_number",
            "input_select",
            "input_text",
            "input_datetime",
            "input_button",
            "timer",
            "schedule",
            "counter",
        ]:
            with contextlib.suppress(Exception):
                await self.call_service(domain, "reload")

    # --- Config Entry-based Helpers (template, group) ---

    @logfire.instrument("Get config entries: {domain}")
    async def get_config_entries(self, domain: str | None = None) -> list[dict[str, Any]]:
        """Get all config entries, optionally filtered by domain."""
        entries = await self.send_command("config_entries/get")
        if domain:
            entries = [e for e in entries if e.get("domain") == domain]
        return entries if isinstance(entries, list) else []

    @logfire.instrument("Get config entry options: {entry_id}")
    async def get_config_entry_options(self, entry_id: str) -> dict[str, Any]:
        """Get config entry options by creating and aborting an options flow.

        Returns the configuration data extracted from the options flow schema.
        """
        # Create an options flow to get the current configuration
        response = await self.http.post(
            "/api/config/config_entries/options/flow",
            json={"handler": entry_id, "show_advanced_options": True},
        )
        response.raise_for_status()
        flow_data = response.json()

        # Extract configuration from data_schema suggested_values
        config: dict[str, Any] = {}
        for field in flow_data.get("data_schema", []):
            field_name = field.get("name")
            if field_name and "description" in field:
                suggested = field["description"].get("suggested_value")
                if suggested is not None:
                    config[field_name] = suggested
            # Handle expandable fields (like advanced_options)
            if field.get("type") == "expandable":
                for subfield in field.get("schema", []):
                    subfield_name = subfield.get("name")
                    if subfield_name and "description" in subfield:
                        suggested = subfield["description"].get("suggested_value")
                        if suggested is not None:
                            config[subfield_name] = suggested

        # Clean up the flow
        if "flow_id" in flow_data:
            await self.http.delete(
                f"/api/config/config_entries/options/flow/{flow_data['flow_id']}"
            )

        return {
            "entry_id": entry_id,
            "step_id": flow_data.get("step_id"),  # The entity type (sensor, binary_sensor, etc.)
            **config,
        }

    @logfire.instrument("Delete config entry: {entry_id}")
    async def delete_config_entry(self, entry_id: str) -> None:
        """Delete a config entry."""
        response = await self.http.delete(f"/api/config/config_entries/entry/{entry_id}")
        response.raise_for_status()

    @logfire.instrument("Create config entry: {domain}")
    async def create_config_entry(
        self,
        domain: str,
        config: dict[str, Any],
        menu_step: str | None = None,
    ) -> str:
        """Create a config entry via config flow.

        Args:
            domain: The integration domain (e.g., 'template', 'group')
            config: The configuration data for the entry
            menu_step: For domains with a menu (like template), the entity type to create

        Returns:
            The entry_id of the created config entry
        """
        # Start the config flow
        response = await self.http.post(
            "/api/config/config_entries/flow",
            json={"handler": domain, "show_advanced_options": True},
        )
        response.raise_for_status()
        flow_data = response.json()
        flow_id = flow_data["flow_id"]

        try:
            # Handle menu step if needed (e.g., template entity type selection)
            if flow_data.get("type") == "menu" and menu_step:
                response = await self.http.post(
                    f"/api/config/config_entries/flow/{flow_id}",
                    json={"next_step_id": menu_step},
                )
                response.raise_for_status()
                flow_data = response.json()

            # Submit the form data
            # Filter out internal fields (but keep "name" - it's required for creation)
            form_data = {
                k: v
                for k, v in config.items()
                if k not in ("entry_id", "step_id") and v is not None
            }

            response = await self.http.post(
                f"/api/config/config_entries/flow/{flow_id}",
                json=form_data,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("type") == "create_entry":
                entry_id = result["result"]["entry_id"]
                logfire.info("Created config entry {entry_id}", entry_id=entry_id)
                return entry_id
            elif result.get("errors"):
                logfire.warning("Config flow errors: {errors}", errors=result["errors"])
                raise ValueError(f"Config flow errors: {result['errors']}")
            else:
                logfire.warning("Unexpected flow result: {result}", result=result)
                raise ValueError(f"Unexpected flow result: {result}")

        except Exception:
            # Clean up the flow on error
            with contextlib.suppress(Exception):
                await self.http.delete(f"/api/config/config_entries/flow/{flow_id}")
            raise

    @logfire.instrument("Update config entry: {entry_id}")
    async def update_config_entry(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a config entry via options flow.

        Args:
            entry_id: The config entry ID to update
            config: The new configuration data
        """
        # Start the options flow
        response = await self.http.post(
            "/api/config/config_entries/options/flow",
            json={"handler": entry_id, "show_advanced_options": True},
        )
        response.raise_for_status()
        flow_data = response.json()
        flow_id = flow_data["flow_id"]

        try:
            # Filter out internal fields (name is excluded because options flows
            # don't handle name changes - name is set during creation as entry title)
            form_data = {
                k: v
                for k, v in config.items()
                if k not in ("entry_id", "step_id", "name") and v is not None
            }

            # Submit the form data
            response = await self.http.post(
                f"/api/config/config_entries/options/flow/{flow_id}",
                json=form_data,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("errors"):
                logfire.warning("Options flow errors: {errors}", errors=result["errors"])
                raise ValueError(f"Options flow errors: {result['errors']}")

        except Exception:
            # Clean up the flow on error
            with contextlib.suppress(Exception):
                await self.http.delete(f"/api/config/config_entries/options/flow/{flow_id}")
            raise

    # Template Helpers
    async def get_template_helpers(self) -> list[dict[str, Any]]:
        """Get all template helpers with their configurations."""
        entries = await self.get_config_entries("template")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                # Skip entries that can't be read
                pass
        return result

    async def create_template_helper(self, entity_type: str, config: dict[str, Any]) -> str:
        """Create a template helper.

        Args:
            entity_type: The entity type (sensor, binary_sensor, switch, etc.)
            config: The configuration data

        Returns:
            The entry_id of the created config entry
        """
        return await self.create_config_entry("template", config, menu_step=entity_type)

    async def update_template_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a template helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_template_helper(self, entry_id: str) -> None:
        """Delete a template helper."""
        await self.delete_config_entry(entry_id)

    # Group Helpers
    async def get_group_helpers(self) -> list[dict[str, Any]]:
        """Get all group helpers with their configurations."""
        entries = await self.get_config_entries("group")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                # Skip entries that can't be read
                pass
        return result

    async def create_group_helper(self, entity_type: str, config: dict[str, Any]) -> str:
        """Create a group helper.

        Args:
            entity_type: The entity type (binary_sensor, sensor, light, etc.)
            config: The configuration data

        Returns:
            The entry_id of the created config entry
        """
        return await self.create_config_entry("group", config, menu_step=entity_type)

    async def update_group_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a group helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_group_helper(self, entry_id: str) -> None:
        """Delete a group helper."""
        await self.delete_config_entry(entry_id)

    # Integration Helpers (Riemann sum integral)
    async def get_integration_helpers(self) -> list[dict[str, Any]]:
        """Get all integration helpers with their configurations."""
        entries = await self.get_config_entries("integration")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                pass
        return result

    async def create_integration_helper(self, config: dict[str, Any]) -> str:
        """Create an integration helper."""
        return await self.create_config_entry("integration", config)

    async def update_integration_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update an integration helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_integration_helper(self, entry_id: str) -> None:
        """Delete an integration helper."""
        await self.delete_config_entry(entry_id)

    # Utility Meter Helpers
    async def get_utility_meter_helpers(self) -> list[dict[str, Any]]:
        """Get all utility meter helpers with their configurations."""
        entries = await self.get_config_entries("utility_meter")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                pass
        return result

    async def create_utility_meter_helper(self, config: dict[str, Any]) -> str:
        """Create a utility meter helper."""
        return await self.create_config_entry("utility_meter", config)

    async def update_utility_meter_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a utility meter helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_utility_meter_helper(self, entry_id: str) -> None:
        """Delete a utility meter helper."""
        await self.delete_config_entry(entry_id)

    # Threshold Helpers
    async def get_threshold_helpers(self) -> list[dict[str, Any]]:
        """Get all threshold helpers with their configurations."""
        entries = await self.get_config_entries("threshold")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                pass
        return result

    async def create_threshold_helper(self, config: dict[str, Any]) -> str:
        """Create a threshold helper."""
        return await self.create_config_entry("threshold", config)

    async def update_threshold_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a threshold helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_threshold_helper(self, entry_id: str) -> None:
        """Delete a threshold helper."""
        await self.delete_config_entry(entry_id)

    # Time of Day (TOD) Helpers
    async def get_tod_helpers(self) -> list[dict[str, Any]]:
        """Get all time of day helpers with their configurations."""
        entries = await self.get_config_entries("tod")
        result = []
        for entry in entries:
            try:
                config = await self.get_config_entry_options(entry["entry_id"])
                config["name"] = entry.get("title", "")
                result.append(config)
            except Exception:
                pass
        return result

    async def create_tod_helper(self, config: dict[str, Any]) -> str:
        """Create a time of day helper."""
        return await self.create_config_entry("tod", config)

    async def update_tod_helper(self, entry_id: str, config: dict[str, Any]) -> None:
        """Update a time of day helper."""
        await self.update_config_entry(entry_id, config)

    async def delete_tod_helper(self, entry_id: str) -> None:
        """Delete a time of day helper."""
        await self.delete_config_entry(entry_id)

    # --- Utility Methods ---

    @logfire.instrument("Check HA config")
    async def check_config(self) -> dict[str, Any]:
        """Check Home Assistant configuration validity."""
        response = await self.http.post("/api/config/core/check_config")
        response.raise_for_status()
        return response.json()

    @logfire.instrument("Get HA config")
    async def get_config(self) -> dict[str, Any]:
        """Get Home Assistant configuration."""
        response = await self.http.get("/api/config")
        response.raise_for_status()
        return response.json()

    @logfire.instrument("Render template")
    async def render_template(self, template: str) -> str:
        """Render a Jinja2 template using Home Assistant."""
        response = await self.http.post(
            "/api/template",
            json={"template": template},
        )
        response.raise_for_status()
        return response.text

    @logfire.instrument("Validate template")
    async def validate_template(self, template: str) -> tuple[bool, str]:
        """Validate a Jinja2 template."""
        try:
            result = await self.render_template(template)
            return True, result
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, "response"):
                with contextlib.suppress(Exception):
                    error_msg = e.response.text  # type: ignore
            return False, error_msg

    async def __aenter__(self) -> "HAClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

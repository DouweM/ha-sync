"""CLI interface for ha-sync."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import logfire
import typer
from rich.console import Console
from rich.table import Table

from ha_sync import __version__
from ha_sync.client import HAClient
from ha_sync.config import SyncConfig, get_config
from ha_sync.sync import (
    AutomationSyncer,
    DashboardSyncer,
    GroupSyncer,
    HelperSyncer,
    SceneSyncer,
    ScriptSyncer,
    TemplateSyncer,
)
from ha_sync.sync.base import BaseSyncer, DiffItem
from ha_sync.sync.config_entries import (
    CONFIG_ENTRY_HELPER_DOMAINS,
    ConfigEntrySyncer,
    discover_helper_domains,
)
from ha_sync.utils import (
    MANAGED_FOLDERS,
    dump_yaml,
    git_stash,
    git_stash_pop,
    is_git_repo,
)

# Configure logfire (must be after imports to ensure proper instrumentation)
logfire.configure(service_name="ha-sync", send_to_logfire="if-token-present", console=False)
logfire.instrument_httpx(capture_all=True)

app = typer.Typer(
    name="ha-sync",
    help="Sync Home Assistant UI config to/from local YAML files.",
    no_args_is_help=True,
)
console = Console()


# WebSocket-based helper types (under helpers/)
WEBSOCKET_HELPER_TYPES = {
    "input_boolean",
    "input_number",
    "input_select",
    "input_text",
    "input_datetime",
    "input_button",
    "timer",
    "schedule",
    "counter",
}


@dataclass
class SyncerSpec:
    """Specification for a syncer with optional file filter."""

    syncer_class: type[BaseSyncer]
    file_filter: Path | None = None
    # For ConfigEntrySyncer, we need to know the domain
    domain: str | None = None


def resolve_path_to_syncers(
    path: str | None,
    config: SyncConfig,
    discovered_domains: set[str] | None = None,
) -> list[SyncerSpec]:
    """Resolve a path argument to syncer specifications.

    Args:
        path: File path or directory path (e.g., "automations/", "helpers/template/sensor/")
        config: Sync configuration
        discovered_domains: Pre-discovered config entry helper domains

    Returns:
        List of SyncerSpec with syncer class and optional file filter
    """
    if path is None:
        # No path = all syncers
        specs: list[SyncerSpec] = [
            SyncerSpec(DashboardSyncer),
            SyncerSpec(AutomationSyncer),
            SyncerSpec(ScriptSyncer),
            SyncerSpec(SceneSyncer),
            SyncerSpec(HelperSyncer),
            SyncerSpec(TemplateSyncer),
            SyncerSpec(GroupSyncer),
        ]
        # Add config entry syncers for discovered domains
        domains = discovered_domains or CONFIG_ENTRY_HELPER_DOMAINS
        for domain in sorted(domains):
            specs.append(SyncerSpec(ConfigEntrySyncer, domain=domain))
        return specs

    # Normalize path (remove trailing slashes, handle relative paths)
    path_obj = Path(path.rstrip("/"))
    parts = path_obj.parts

    if not parts:
        # Empty path = all syncers
        return resolve_path_to_syncers(None, config, discovered_domains)

    top_level = parts[0]

    # Map top-level directories to syncers
    if top_level == "dashboards":
        file_filter = path_obj if len(parts) > 1 else None
        return [SyncerSpec(DashboardSyncer, file_filter=file_filter)]

    elif top_level == "automations":
        file_filter = path_obj if len(parts) > 1 else None
        return [SyncerSpec(AutomationSyncer, file_filter=file_filter)]

    elif top_level == "scripts":
        file_filter = path_obj if len(parts) > 1 else None
        return [SyncerSpec(ScriptSyncer, file_filter=file_filter)]

    elif top_level == "scenes":
        file_filter = path_obj if len(parts) > 1 else None
        return [SyncerSpec(SceneSyncer, file_filter=file_filter)]

    elif top_level == "helpers":
        if len(parts) == 1:
            # helpers/ = all helper syncers
            specs = [
                SyncerSpec(HelperSyncer),
                SyncerSpec(TemplateSyncer),
                SyncerSpec(GroupSyncer),
            ]
            domains = discovered_domains or CONFIG_ENTRY_HELPER_DOMAINS
            for domain in sorted(domains):
                specs.append(SyncerSpec(ConfigEntrySyncer, domain=domain))
            return specs

        helper_type = parts[1]

        # WebSocket-based helpers (input_*, timer, counter, schedule)
        if helper_type in WEBSOCKET_HELPER_TYPES:
            file_filter = path_obj if len(parts) > 2 else None
            return [SyncerSpec(HelperSyncer, file_filter=file_filter)]

        # Template helpers
        elif helper_type == "template":
            file_filter = path_obj if len(parts) > 2 else None
            return [SyncerSpec(TemplateSyncer, file_filter=file_filter)]

        # Group helpers
        elif helper_type == "group":
            file_filter = path_obj if len(parts) > 2 else None
            return [SyncerSpec(GroupSyncer, file_filter=file_filter)]

        # Config entry helpers (integration, utility_meter, threshold, tod, etc.)
        else:
            file_filter = path_obj if len(parts) > 2 else None
            return [SyncerSpec(ConfigEntrySyncer, file_filter=file_filter, domain=helper_type)]

    else:
        # Unknown path - try to be helpful
        console.print(f"[red]Unknown path:[/red] {path}")
        console.print(
            "[dim]Valid paths: dashboards/, automations/, scripts/, scenes/, helpers/[/dim]"
        )
        raise typer.Exit(1)


def create_syncers_from_specs(
    specs: list[SyncerSpec],
    client: HAClient,
    config: SyncConfig,
) -> list[tuple[BaseSyncer, Path | None]]:
    """Create syncer instances from specs.

    Returns:
        List of (syncer, file_filter) tuples
    """
    result: list[tuple[BaseSyncer, Path | None]] = []
    for spec in specs:
        if spec.syncer_class == ConfigEntrySyncer:
            syncer = ConfigEntrySyncer(client, config, spec.domain or "")
        else:
            syncer = spec.syncer_class(client, config)
        result.append((syncer, spec.file_filter))
    return result


async def get_syncers_for_path(
    client: HAClient,
    config: SyncConfig,
    path: str | None,
) -> list[tuple[BaseSyncer, Path | None]]:
    """Get syncers for a path, auto-discovering config entry helper domains.

    Returns:
        List of (syncer, file_filter) tuples
    """
    # Discover helper domains if needed
    discovered: set[str] | None = None
    if path is None or path.rstrip("/") == "helpers":
        discovered = await discover_helper_domains(client)

    specs = resolve_path_to_syncers(path, config, discovered)
    return create_syncers_from_specs(specs, client, config)


async def get_syncers_for_paths(
    client: HAClient,
    config: SyncConfig,
    paths: list[str] | None,
) -> list[tuple[BaseSyncer, list[Path] | None]]:
    """Get syncers for multiple paths, grouping file filters by syncer.

    Returns:
        List of (syncer, file_filters) tuples where file_filters is None if no filtering needed
    """
    if paths is None or len(paths) == 0:
        # No paths = all syncers, no filtering
        single_result = await get_syncers_for_path(client, config, None)
        return [(syncer, None) for syncer, _ in single_result]

    # Discover helper domains if any path needs it
    discovered: set[str] | None = None
    if any(p is None or p.rstrip("/") == "helpers" for p in paths):
        discovered = await discover_helper_domains(client)

    # Collect all specs and group by syncer key
    from collections import defaultdict

    # Key: (syncer_class, domain) -> list of file_filters
    syncer_filters: dict[tuple[type[BaseSyncer], str | None], list[Path]] = defaultdict(list)
    syncer_has_no_filter: set[tuple[type[BaseSyncer], str | None]] = set()

    for path in paths:
        specs = resolve_path_to_syncers(path, config, discovered)
        for spec in specs:
            key = (spec.syncer_class, spec.domain)
            if spec.file_filter:
                syncer_filters[key].append(spec.file_filter)
            else:
                # This syncer was requested without a filter (e.g., "automations/")
                syncer_has_no_filter.add(key)

    # Build result: for each syncer, use filters only if ALL requests had filters
    result: list[tuple[BaseSyncer, list[Path] | None]] = []
    seen_keys: set[tuple[type[BaseSyncer], str | None]] = set()

    for key in list(syncer_filters.keys()) + list(syncer_has_no_filter):
        if key in seen_keys:
            continue
        seen_keys.add(key)

        syncer_class, domain = key
        if syncer_class == ConfigEntrySyncer:
            syncer = ConfigEntrySyncer(client, config, domain or "")
        else:
            syncer = syncer_class(client, config)

        # If this syncer was ever requested without a filter, don't filter
        if key in syncer_has_no_filter:
            result.append((syncer, None))
        else:
            result.append((syncer, syncer_filters[key]))

    return result


@app.command()
def init() -> None:
    """Initialize ha-sync directory structure and check configuration."""
    with logfire.span("ha-sync init"):
        config = get_config()

        # Create directory structure
        config.ensure_dirs()
        console.print(
            "[green]Created[/green] directory structure (dashboards/, automations/, etc.)"
        )

        # Check .env configuration
        if config.url:
            console.print(f"[green]HA_URL found in .env:[/green] {config.url}")
        else:
            console.print("[yellow]HA_URL not set in .env[/yellow]")

        if config.token:
            console.print("[green]HA_TOKEN found in .env[/green]")
        else:
            console.print("[yellow]HA_TOKEN not set in .env[/yellow]")

        if not config.url or not config.token:
            console.print()
            console.print("[dim]Add HA_URL and HA_TOKEN to a .env file in this directory[/dim]")


@app.command()
def status() -> None:
    """Show connection status and sync state."""
    with logfire.span("ha-sync status"):
        config = get_config()

        table = Table(title="Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value")

        table.add_row("HA URL", config.url or "[red]Not set[/red]")
        table.add_row("HA Token", "[green]Set[/green]" if config.token else "[red]Not set[/red]")

        console.print(table)

        # Try to connect
        if config.url and config.token:
            console.print()
            console.print("[dim]Testing connection...[/dim]")
            try:
                asyncio.run(_test_connection(config))
                console.print("[green]Connected successfully[/green]")
            except Exception as e:
                console.print(f"[red]Connection failed:[/red] {e}")
        else:
            console.print()
            console.print("[dim]Set HA_URL and HA_TOKEN in .env to enable connection[/dim]")


async def _test_connection(config: SyncConfig) -> None:
    """Test connection to Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        await client.get_config()


@app.command()
def validate(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to validate (e.g., automations/, helpers/template/)"),
    ] = None,
    check_templates: Annotated[
        bool,
        typer.Option("--check-templates", "-t", help="Validate Jinja2 templates against HA"),
    ] = False,
    check_config: Annotated[
        bool,
        typer.Option("--check-config", "-c", help="Check HA config validity"),
    ] = False,
    diff_only: Annotated[
        bool,
        typer.Option(
            "--diff-only/--all-templates",
            "-d/-a",
            help="Only check templates from changed files (default) or all templates",
        ),
    ] = True,
) -> None:
    """Validate local YAML files for errors."""
    with logfire.span("ha-sync validate", paths=paths):
        _validate_impl(paths, check_templates, check_config, diff_only)


def _validate_impl(
    paths: list[str] | None,
    check_templates: bool,
    check_config: bool,
    diff_only: bool,
) -> None:
    """Implementation of validate command."""

    from ha_sync.utils import load_yaml, relative_path

    config = get_config()
    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    templates_to_check: list[tuple[str, str, str]] = []  # (file, path, template)
    files_checked = 0

    # Resolve paths to determine what to validate
    all_specs: list[SyncerSpec] = []
    all_file_filters: list[Path] = []
    for path in paths or [None]:
        specs = resolve_path_to_syncers(path, config, None)
        all_specs.extend(specs)
        for spec in specs:
            if spec.file_filter:
                all_file_filters.append(spec.file_filter)
    # Deduplicate syncer classes
    syncer_classes = {spec.syncer_class for spec in all_specs}
    # Use file filters only if all paths had specific filters
    file_filters = all_file_filters if all_file_filters else None

    # Get changed files if diff_only mode
    changed_files: set[str] = set()
    if check_templates and diff_only and config.url and config.token:
        console.print("[dim]Getting diff to find changed files...[/dim]")
        diff_items = asyncio.run(_get_diff_items(config, paths))
        for item in diff_items:
            # Collect file paths from changed items
            if item.status in ("added", "modified", "renamed") and item.file_path:
                changed_files.add(item.file_path)

    def validate_yaml_file(file_path: Path, required_fields: list[str] | None = None) -> None:
        """Validate a single YAML file."""
        nonlocal files_checked
        files_checked += 1

        rel_path = relative_path(file_path)

        try:
            data = load_yaml(file_path)
            if data is None:
                warnings.append((rel_path, "Empty file"))
                return
            if not isinstance(data, dict):
                errors.append((rel_path, "Root must be a dictionary"))
                return

            # Check required fields
            if required_fields:
                for field in required_fields:
                    if field not in data:
                        errors.append((rel_path, f"Missing required field: '{field}'"))

            # Check for Jinja2 templates and validate syntax
            collect_templates(data, rel_path)

        except Exception as e:
            errors.append((rel_path, f"YAML parse error: {e}"))

    def collect_templates(data: dict, rel_path: str, path: str = "") -> None:
        """Recursively collect Jinja2 templates and do basic syntax check."""
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, str) and ("{{" in value or "{%" in value):
                # Basic Jinja2 syntax check
                if value.count("{{") != value.count("}}"):
                    errors.append((rel_path, f"Unbalanced {{{{ }}}} in {current_path}"))
                elif value.count("{%") != value.count("%}"):
                    errors.append((rel_path, f"Unbalanced {{% %}} in {current_path}"))
                else:
                    # Collect for remote validation
                    templates_to_check.append((rel_path, current_path, value))
            elif isinstance(value, dict):
                collect_templates(value, rel_path, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        collect_templates(item, rel_path, f"{current_path}[{i}]")
                    elif isinstance(item, str) and ("{{" in item or "{%" in item):
                        if item.count("{{") != item.count("}}"):
                            errors.append(
                                (rel_path, f"Unbalanced {{{{ }}}} in {current_path}[{i}]")
                            )
                        elif item.count("{%") != item.count("%}"):
                            errors.append((rel_path, f"Unbalanced {{% %}} in {current_path}[{i}]"))
                        else:
                            location = f"{current_path}[{i}]"
                            templates_to_check.append((rel_path, location, item))

    console.print("[bold]Validating local files...[/bold]\n")

    def should_validate_file(file_path: Path) -> bool:
        """Check if file matches any of the filters."""
        if file_filters is None:
            return True
        # Check if file path matches any filter (is under the filter path or matches it)
        for file_filter in file_filters:
            try:
                file_path.relative_to(file_filter)
                return True
            except ValueError:
                if str(file_path) == str(file_filter) or str(file_path).endswith(str(file_filter)):
                    return True
        return False

    # Validate automations
    if AutomationSyncer in syncer_classes:
        for yaml_file in config.automations_path.glob("*.yaml"):
            if should_validate_file(yaml_file):
                validate_yaml_file(yaml_file, required_fields=["id", "alias"])

    # Validate scripts
    if ScriptSyncer in syncer_classes:
        for yaml_file in config.scripts_path.glob("*.yaml"):
            if should_validate_file(yaml_file):
                validate_yaml_file(yaml_file)

    # Validate scenes
    if SceneSyncer in syncer_classes:
        for yaml_file in config.scenes_path.glob("*.yaml"):
            if should_validate_file(yaml_file):
                validate_yaml_file(yaml_file, required_fields=["id"])

    # Validate dashboards
    if DashboardSyncer in syncer_classes:
        for dashboard_dir in config.dashboards_path.iterdir():
            if dashboard_dir.is_dir():
                for yaml_file in dashboard_dir.glob("*.yaml"):
                    if should_validate_file(yaml_file):
                        validate_yaml_file(yaml_file)

    # Validate helpers (WebSocket-based)
    if HelperSyncer in syncer_classes:
        helper_types = [
            "input_boolean",
            "input_number",
            "input_select",
            "input_text",
            "input_datetime",
            "input_button",
            "timer",
            "schedule",
            "counter",
        ]
        for helper_type in helper_types:
            helper_path = config.helpers_path / helper_type
            if helper_path.exists():
                for yaml_file in helper_path.glob("*.yaml"):
                    if should_validate_file(yaml_file):
                        validate_yaml_file(yaml_file, required_fields=["id", "name"])

    # Validate template helpers (now under helpers/template/)
    if TemplateSyncer in syncer_classes:
        template_path = config.helpers_path / "template"
        if template_path.exists():
            for subtype_dir in template_path.iterdir():
                if subtype_dir.is_dir():
                    for yaml_file in subtype_dir.glob("*.yaml"):
                        if should_validate_file(yaml_file):
                            # entry_id is optional for new files (generated by HA on push)
                            validate_yaml_file(yaml_file, required_fields=["name"])

    # Validate group helpers (now under helpers/group/)
    if GroupSyncer in syncer_classes:
        group_path = config.helpers_path / "group"
        if group_path.exists():
            for subtype_dir in group_path.iterdir():
                if subtype_dir.is_dir():
                    for yaml_file in subtype_dir.glob("*.yaml"):
                        if should_validate_file(yaml_file):
                            # entry_id is optional for new files (generated by HA on push)
                            validate_yaml_file(yaml_file, required_fields=["name"])

    # Report local validation results
    if errors:
        console.print("[red]Local validation errors:[/red]")
        for file_path, error in errors:
            console.print(f"  [red]✗[/red] {file_path}: {error}")
        console.print()

    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for file_path, warning in warnings:
            console.print(f"  [yellow]![/yellow] {file_path}: {warning}")
        console.print()

    # Validate templates against HA if requested
    template_errors: list[tuple[str, str]] = []
    if check_templates and templates_to_check:
        if not config.url or not config.token:
            console.print("[yellow]Skipping template validation (no HA connection)[/yellow]")
        else:
            # Filter to only changed files if diff_only mode
            if diff_only and changed_files:

                def _file_in_changed(file_path: str) -> bool:
                    """Check if file is in or under any changed path."""
                    for changed in changed_files:
                        if file_path == changed or file_path.startswith(changed + "/"):
                            return True
                    return False

                filtered = [t for t in templates_to_check if _file_in_changed(t[0])]
                if not filtered:
                    console.print("[dim]No templates in changed files[/dim]")
                else:
                    console.print(
                        f"[dim]Checking {len(filtered)} templates "
                        f"(filtered from {len(templates_to_check)} total)[/dim]"
                    )
                templates_to_check = filtered

            if templates_to_check:
                count = len(templates_to_check)
                console.print(f"[dim]Validating {count} templates against HA...[/dim]")
                template_errors = asyncio.run(_validate_templates(config, templates_to_check))
            if template_errors:
                console.print("[red]Template errors:[/red]")
                for location, error in template_errors:
                    console.print(f"  [red]✗[/red] {location}: {error}")
                console.print()
            else:
                console.print(f"[green]✓[/green] All {len(templates_to_check)} templates valid")

    # Check HA config if requested
    if check_config and config.url and config.token:
        console.print("[dim]Checking Home Assistant config...[/dim]")
        try:
            result = asyncio.run(_check_ha_config(config))
            if result.get("result") == "valid":
                console.print("[green]✓[/green] Home Assistant config is valid")
            else:
                errs = result.get("errors", [])
                console.print(f"[red]✗[/red] Home Assistant config errors: {errs}")
        except Exception as e:
            console.print(f"[red]Could not check HA config:[/red] {e}")

    # Summary
    total_errors = len(errors) + len(template_errors)
    console.print(f"\n[bold]Checked {files_checked} files[/bold]")
    if templates_to_check:
        console.print(f"[bold]Found {len(templates_to_check)} templates[/bold]")
    if total_errors:
        console.print(f"[red]{total_errors} error(s)[/red]")
        raise typer.Exit(1)
    elif warnings:
        console.print(f"[yellow]{len(warnings)} warning(s)[/yellow]")
    else:
        console.print("[green]All files valid[/green]")


async def _validate_templates(
    config: SyncConfig, templates: list[tuple[str, str, str]]
) -> list[tuple[str, str]]:
    """Validate templates against Home Assistant.

    Args:
        config: Sync configuration
        templates: List of (file_path, field_path, template_string)

    Returns:
        List of (location, error_message) for invalid templates
    """
    errors: list[tuple[str, str]] = []
    async with HAClient(config.url, config.token) as client:
        for file_path, field_path, template in templates:
            is_valid, result = await client.validate_template(template)
            if not is_valid:
                location = f"{file_path}:{field_path}"
                # Clean up error message
                error = result.replace("\n", " ").strip()
                if len(error) > 100:
                    error = error[:100] + "..."
                errors.append((location, error))
    return errors


async def _check_ha_config(config: SyncConfig) -> dict:
    """Check Home Assistant configuration validity."""
    async with HAClient(config.url, config.token) as client:
        return await client.check_config()


async def _get_diff_items(config: SyncConfig, paths: list[str] | None) -> list[DiffItem]:
    """Get diff items for the specified paths."""
    items: list[DiffItem] = []
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)
        for syncer, file_filters in syncers_with_filters:
            syncer_items = await syncer.diff()
            # Filter items if file_filters is set
            if file_filters:
                syncer_items = [
                    item
                    for item in syncer_items
                    if item.file_path
                    and any(_matches_filter(item.file_path, f) for f in file_filters)
                ]
            items.extend(syncer_items)
    return items


def _matches_filter(file_path: str, file_filter: Path) -> bool:
    """Check if a file path matches the filter.

    Handles these cases:
    1. file_path starts with filter (e.g., filter="automations/", file_path="automations/foo.yaml")
    2. file_path equals filter exactly
    3. filter is a file within file_path directory (e.g., filter="dashboards/welcome/00_oasis.yaml",
       file_path="dashboards/welcome" - filter is under the file_path directory)
    """
    filter_str = str(file_filter)
    file_path_obj = Path(file_path)

    # Direct match or prefix match
    if file_path.startswith(filter_str) or file_path == filter_str:
        return True

    # Check if filter is a file within the file_path directory
    # This handles dashboards where file_path is a directory like "dashboards/welcome"
    # but the user specifies a file like "dashboards/welcome/00_oasis.yaml"
    if file_filter.suffix and not file_path_obj.suffix:
        # filter is a file, file_path is a directory
        return file_filter.parent == file_path_obj

    return False


def _record_file_states(diff_items: list[DiffItem]) -> dict[str, float]:
    """Record the modification times of files in diff_items.

    This is used for staleness detection - we record the state when diff is computed,
    then check if files changed before executing the push.

    Args:
        diff_items: List of diff items to record states for

    Returns:
        Dict mapping file paths to their mtime (modification time)
    """
    states: dict[str, float] = {}
    for item in diff_items:
        if item.file_path:
            file_path = Path(item.file_path)
            if file_path.exists():
                states[item.file_path] = file_path.stat().st_mtime
    return states


def _check_file_staleness(recorded_states: dict[str, float]) -> list[str]:
    """Check if any files have changed since their states were recorded.

    Args:
        recorded_states: Dict mapping file paths to their recorded mtime

    Returns:
        List of file paths that have changed (stale files)
    """
    stale_files: list[str] = []
    for file_path_str, recorded_mtime in recorded_states.items():
        file_path = Path(file_path_str)
        if file_path.exists():
            current_mtime = file_path.stat().st_mtime
            if current_mtime != recorded_mtime:
                stale_files.append(file_path_str)
        else:
            # File was deleted - this is also a change
            stale_files.append(file_path_str)
    return stale_files


def _display_diff_items(items: list[DiffItem], direction: str = "push") -> None:
    """Display diff items with content diffs for modified items.

    Args:
        items: List of diff items to display
        direction: "push" (local -> remote) or "pull" (remote -> local)
    """
    import difflib

    if not items:
        console.print("[dim]No changes[/dim]")
        return

    status_colors = {
        "added": "green",
        "modified": "yellow",
        "deleted": "red",
        "renamed": "blue",
    }

    # For pull, swap the semantics: "added" means remote has it, local doesn't
    # "deleted" means local has it, remote doesn't
    if direction == "pull":
        status_labels = {
            "added": "create",  # Will create locally
            "modified": "update",  # Will update locally
            "deleted": "delete",  # Will delete locally (if --sync-deletions)
            "renamed": "rename",
        }
    else:
        status_labels = {
            "added": "create",  # Will create remotely
            "modified": "update",  # Will update remotely
            "deleted": "delete",  # Will delete remotely (if --sync-deletions)
            "renamed": "rename",
        }

    for item in sorted(items, key=lambda x: (x.status, x.file_path or x.entity_id)):
        color = status_colors.get(item.status, "white")
        label = status_labels.get(item.status, item.status)
        display_path = item.file_path or item.entity_id

        console.print(f"[{color}]{label}[/{color}] {display_path}")

        # Show diff for modified items
        if item.status == "modified" and item.local and item.remote:
            if direction == "pull":
                # Pull: remote -> local, show what local will become
                from_yaml = dump_yaml(item.local).splitlines(keepends=True)
                to_yaml = dump_yaml(item.remote).splitlines(keepends=True)
                from_label, to_label = "local", "remote"
            else:
                # Push: local -> remote, show what remote will become
                from_yaml = dump_yaml(item.remote).splitlines(keepends=True)
                to_yaml = dump_yaml(item.local).splitlines(keepends=True)
                from_label, to_label = "remote", "local"

            diff_lines = list(
                difflib.unified_diff(
                    from_yaml,
                    to_yaml,
                    fromfile=from_label,
                    tofile=to_label,
                    lineterm="",
                )
            )

            if diff_lines:
                for line in diff_lines:
                    line = line.rstrip("\n")
                    if line.startswith("+++") or line.startswith("---"):
                        console.print(f"  [dim]{line}[/dim]")
                    elif line.startswith("@@"):
                        console.print(f"  [cyan]{line}[/cyan]")
                    elif line.startswith("+"):
                        console.print(f"  [green]{line}[/green]")
                    elif line.startswith("-"):
                        console.print(f"  [red]{line}[/red]")
                    else:
                        console.print(f"  [dim]{line}[/dim]")

        # Show content for added items
        elif item.status == "added":
            content = item.remote if direction == "pull" else item.local
            if content:
                content_yaml = dump_yaml(content)
                for line in content_yaml.splitlines():
                    console.print(f"  [green]+{line}[/green]")

        # Show content for deleted items
        elif item.status == "deleted":
            content = item.local if direction == "pull" else item.remote
            if content:
                content_yaml = dump_yaml(content)
                for line in content_yaml.splitlines():
                    console.print(f"  [red]-{line}[/red]")

        console.print()  # Blank line between items


def _ask_confirmation(action: str = "proceed") -> bool:
    """Ask user for confirmation.

    Args:
        action: Description of what will happen (e.g., "proceed", "push changes")

    Returns:
        True if user confirms, False otherwise
    """
    try:
        response = console.input(f"[bold]Do you want to {action}?[/bold] [y/N] ")
        return response.lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False


def _handle_autostash(skip_stash: bool) -> tuple[bool, bool]:
    """Handle git autostash if in a git repo.

    Only stashes changes in ha-sync managed folders (automations, scripts, etc.).

    Args:
        skip_stash: If True, skip stashing entirely

    Returns:
        Tuple of (is_git, stashed) - whether we're in git and whether we stashed
    """
    if skip_stash:
        return False, False

    if not is_git_repo():
        return False, False

    stash_result = git_stash(MANAGED_FOLDERS)
    if stash_result.stashed:
        console.print("[dim]Stashed local changes in managed folders[/dim]")
        return True, True
    return True, False


def _handle_stash_pop(stashed: bool) -> bool:
    """Pop stashed changes and check for conflicts.

    Args:
        stashed: Whether we previously stashed

    Returns:
        True if successful (no conflicts), False if conflicts detected
    """
    if not stashed:
        return True

    pop_result = git_stash_pop()
    if pop_result.success:
        console.print("[dim]Restored stashed changes[/dim]")
        return True

    if pop_result.has_conflicts:
        console.print("[yellow]Conflicts detected after restoring stashed changes.[/yellow]")
        console.print("[yellow]Resolve conflicts before pushing.[/yellow]")
        return False

    console.print(f"[red]Error restoring stash:[/red] {pop_result.message}")
    return False


@app.command()
def pull(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to pull (e.g., automations/, helpers/template/)"),
    ] = None,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Delete local files not in Home Assistant"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation and autostash"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
) -> None:
    """Pull entities from Home Assistant to local files.

    Shows a preview of changes. In a git repo, automatically stashes local changes
    before pull and restores after (no confirmation needed). Outside git, asks for
    confirmation since local changes can't be recovered.
    """
    with logfire.span("ha-sync pull", paths=paths, dry_run=dry_run, yes=yes):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if dry_run:
            console.print("[cyan]Dry run mode - no changes will be made[/cyan]\n")
            asyncio.run(_pull(config, paths, sync_deletions, dry_run=True))
            return

        # Get diff preview
        console.print("[bold]Fetching changes from Home Assistant...[/bold]\n")
        diff_items = asyncio.run(_get_pull_diff(config, paths, sync_deletions))

        if not diff_items:
            console.print("[dim]No changes to pull[/dim]")
            return

        # Show preview
        _display_diff_items(diff_items, direction="pull")

        in_git = is_git_repo()

        if not in_git:
            # Not in git - ask for confirmation since we can't recover overwritten files
            if not yes and not _ask_confirmation("pull these changes"):
                console.print("[dim]Aborted[/dim]")
                raise typer.Exit(0)
            console.print()
            asyncio.run(_pull(config, paths, sync_deletions, dry_run=False))
        else:
            # In git - autostash handles recovery, no confirmation needed
            _, stashed = _handle_autostash(skip_stash=yes)
            console.print()
            asyncio.run(_pull(config, paths, sync_deletions, dry_run=False))
            _handle_stash_pop(stashed)


async def _get_sync_diffs(
    config: SyncConfig,
    paths: list[str] | None,
    sync_deletions: bool,
    in_git: bool,
    has_local_changes: bool,
) -> tuple[list[DiffItem], list[DiffItem], dict[str, dict]]:
    """Get both pull and push diffs efficiently with single API fetch.

    For accurate pull_diff when there are uncommitted changes, we need to
    temporarily stash and compute the diff against clean working tree.

    Returns:
        Tuple of (pull_diff, push_diff, remote_cache)
    """
    push_diff: list[DiffItem] = []
    pull_diff: list[DiffItem] = []

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        # Cache remote data for all syncers (single API fetch per syncer type)
        remote_cache: dict[str, dict] = {}
        for syncer, _ in syncers_with_filters:
            remote_cache[syncer.entity_type] = await syncer.get_remote_entities()

        # Step 1: Compute push_diff (dirty working tree vs remote)
        if has_local_changes:
            for syncer, file_filters in syncers_with_filters:
                remote = remote_cache[syncer.entity_type]
                syncer_items = await syncer.diff(remote=remote)

                # Filter for push: adds, modifies, renames; deletes only if sync_deletions
                push_items = [
                    item
                    for item in syncer_items
                    if item.status in ("renamed", "added", "modified")
                    or (item.status == "deleted" and sync_deletions)
                ]

                if file_filters:
                    push_items = [
                        item
                        for item in push_items
                        if item.file_path
                        and any(_matches_filter(item.file_path, f) for f in file_filters)
                    ]
                push_diff.extend(push_items)

        # Step 2: Stash if needed for accurate pull_diff
        stashed = False
        if in_git and has_local_changes:
            stash_result = git_stash(MANAGED_FOLDERS)
            stashed = stash_result.stashed

        # Step 3: Compute pull_diff (clean working tree vs remote)
        try:
            for syncer, file_filters in syncers_with_filters:
                remote = remote_cache[syncer.entity_type]
                syncer_items = await syncer.diff(remote=remote)

                # For pull, flip the perspective:
                # - "deleted" (remote has, local doesn't) -> "added" (will create locally)
                # - "modified" stays as-is
                # - "added" (local has, remote doesn't) -> "deleted" (will delete if sync_deletions)
                pull_items = []
                for item in syncer_items:
                    if item.status == "deleted":
                        pull_items.append(
                            DiffItem(
                                entity_id=item.entity_id,
                                status="added",
                                local=item.local,
                                remote=item.remote,
                                file_path=item.file_path,
                            )
                        )
                    elif item.status == "modified":
                        pull_items.append(item)
                    elif item.status == "added" and sync_deletions:
                        pull_items.append(
                            DiffItem(
                                entity_id=item.entity_id,
                                status="deleted",
                                local=item.local,
                                remote=item.remote,
                                file_path=item.file_path,
                            )
                        )

                if file_filters:
                    pull_items = [
                        item
                        for item in pull_items
                        if item.file_path
                        and any(_matches_filter(item.file_path, f) for f in file_filters)
                    ]
                pull_diff.extend(pull_items)
        finally:
            # Step 4: Restore stash
            if stashed:
                git_stash_pop()

    return pull_diff, push_diff, remote_cache


async def _get_pull_diff(
    config: SyncConfig, paths: list[str] | None, sync_deletions: bool
) -> list[DiffItem]:
    """Get diff items for pull operation (what remote has that differs from local)."""
    items: list[DiffItem] = []
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)
        for syncer, file_filters in syncers_with_filters:
            syncer_items = await syncer.diff()
            # For pull, we care about:
            # - "deleted" items = remote has something local doesn't (will create locally)
            # - "modified" items = both have it but different (will update locally)
            # - "added" items = local has something remote doesn't (will delete if sync_deletions)
            pull_items = []
            for item in syncer_items:
                if item.status == "deleted":
                    # Remote has it, local doesn't -> will create locally
                    pull_items.append(
                        DiffItem(
                            entity_id=item.entity_id,
                            status="added",  # Flip: it's an "add" from pull perspective
                            local=item.local,
                            remote=item.remote,
                            file_path=item.file_path,
                        )
                    )
                elif item.status == "modified":
                    pull_items.append(item)
                elif item.status == "added" and sync_deletions:
                    # Local has it, remote doesn't -> will delete locally if sync_deletions
                    pull_items.append(
                        DiffItem(
                            entity_id=item.entity_id,
                            status="deleted",  # Flip: it's a "delete" from pull perspective
                            local=item.local,
                            remote=item.remote,
                            file_path=item.file_path,
                        )
                    )

            if file_filters:
                pull_items = [
                    item
                    for item in pull_items
                    if item.file_path
                    and any(_matches_filter(item.file_path, f) for f in file_filters)
                ]
            items.extend(pull_items)
    return items


async def _pull(
    config: SyncConfig,
    paths: list[str] | None,
    sync_deletions: bool,
    dry_run: bool = False,
    remote_cache: dict[str, dict] | None = None,
) -> None:
    """Pull entities from Home Assistant.

    Args:
        remote_cache: Pre-fetched remote entities by entity_type (skips API calls if provided).
    """
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        for syncer, _file_filters in syncers_with_filters:
            console.print(f"\n[bold]Pulling {syncer.entity_type}s...[/bold]")
            # Use cached remote data if available
            remote = remote_cache.get(syncer.entity_type) if remote_cache else None
            result = await syncer.pull(
                sync_deletions=sync_deletions, dry_run=dry_run, remote=remote
            )

            if not result.has_changes:
                console.print("  [dim]No changes[/dim]")
            elif result.has_errors:
                console.print(f"  [yellow]Completed with {len(result.errors)} errors[/yellow]")
            else:
                total = len(result.created) + len(result.updated) + len(result.deleted)
                if dry_run:
                    console.print(f"  [cyan]Would sync {total} entities[/cyan]")
                else:
                    console.print(f"  [green]Synced {total} entities[/green]")


@app.command()
def push(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to push (e.g., automations/, helpers/template/)"),
    ] = None,
    all_items: Annotated[
        bool,
        typer.Option("--all", "-a", help="Push all local items, not just changed ones"),
    ] = False,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Delete remote entities not in local files"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
) -> None:
    """Push local files to Home Assistant.

    By default, shows a preview of changes and asks for confirmation.
    """
    with logfire.span("ha-sync push", paths=paths, all=all_items, dry_run=dry_run, yes=yes):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if dry_run:
            console.print("[cyan]Dry run mode - no changes will be made[/cyan]\n")
            asyncio.run(_push(config, paths, all_items, sync_deletions, dry_run=True))
            return

        # Get diff preview
        console.print("[bold]Comparing local files with Home Assistant...[/bold]\n")
        diff_items = asyncio.run(_get_push_diff(config, paths, all_items, sync_deletions))

        if not diff_items:
            console.print("[dim]No changes to push[/dim]")
            return

        # Record file states for staleness detection
        file_states = _record_file_states(diff_items)

        # Show preview
        _display_diff_items(diff_items, direction="push")

        # Ask for confirmation unless --yes
        if not yes and not _ask_confirmation("push these changes"):
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

        # Check for staleness before executing push
        stale_files = _check_file_staleness(file_states)
        if stale_files:
            console.print("\n[red]Error: Files changed since diff was computed![/red]")
            console.print("Changed files:")
            for file_path in stale_files:
                console.print(f"  - {file_path}")
            console.print("\n[dim]Re-run the command to see the updated diff.[/dim]")
            raise typer.Exit(1)

        # Execute push with pre-computed diff_items to ensure consistency
        console.print()
        asyncio.run(
            _push(config, paths, all_items, sync_deletions, dry_run=False, diff_items=diff_items)
        )


async def _get_push_diff(
    config: SyncConfig, paths: list[str] | None, all_items: bool, sync_deletions: bool
) -> list[DiffItem]:
    """Get diff items for push operation."""
    items: list[DiffItem] = []
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)
        for syncer, file_filters in syncers_with_filters:
            syncer_items = await syncer.diff()

            # Filter based on what push would actually do
            push_items = []
            for item in syncer_items:
                # Include renames, adds, modifies; deletes only if sync_deletions
                include = item.status in ("renamed", "added", "modified")
                include = include or (item.status == "deleted" and sync_deletions)
                if include:
                    push_items.append(item)

            if file_filters:
                push_items = [
                    item
                    for item in push_items
                    if item.file_path
                    and any(_matches_filter(item.file_path, f) for f in file_filters)
                ]
            items.extend(push_items)
    return items


async def _push(
    config: SyncConfig,
    paths: list[str] | None,
    all_items: bool,
    sync_deletions: bool,
    dry_run: bool,
    diff_items: list[DiffItem] | None = None,
) -> None:
    """Push entities to Home Assistant.

    Args:
        diff_items: Pre-computed diff items to use (skips API call if provided).
    """
    # Group diff_items by entity_type if provided
    items_by_type: dict[str, list[DiffItem]] = {}
    if diff_items:
        for item in diff_items:
            items_by_type.setdefault(item.entity_type, []).append(item)

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        for syncer, _file_filters in syncers_with_filters:
            # Get pre-computed items for this syncer's entity type
            syncer_items = items_by_type.get(syncer.entity_type) if diff_items else None

            console.print(f"\n[bold]Pushing {syncer.entity_type}s...[/bold]")
            result = await syncer.push(
                force=all_items,
                sync_deletions=sync_deletions,
                dry_run=dry_run,
                diff_items=syncer_items,
            )

            if not result.has_changes:
                console.print("  [dim]No changes[/dim]")
            elif result.has_errors:
                console.print(f"  [yellow]Completed with {len(result.errors)} errors[/yellow]")
            else:
                total = (
                    len(result.created)
                    + len(result.updated)
                    + len(result.deleted)
                    + len(result.renamed)
                )
                console.print(f"  [green]Synced {total} entities[/green]")


@app.command()
def diff(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to diff (e.g., automations/, helpers/template/)"),
    ] = None,
) -> None:
    """Show differences between local and remote."""
    with logfire.span("ha-sync diff", paths=paths):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_diff(config, paths))


async def _diff(config: SyncConfig, paths: list[str] | None) -> None:
    """Show differences between local and remote."""
    import difflib

    from ha_sync.utils import dump_yaml

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)
        all_items: list[tuple[str, DiffItem]] = []

        for syncer, file_filters in syncers_with_filters:
            items = await syncer.diff()
            # Filter items if file_filters is set
            if file_filters:
                items = [
                    item
                    for item in items
                    if item.file_path
                    and any(_matches_filter(item.file_path, f) for f in file_filters)
                ]
            for item in items:
                all_items.append((syncer.entity_type, item))

        if not all_items:
            console.print("[dim]No differences[/dim]")
            return

        status_colors = {
            "added": "green",
            "modified": "yellow",
            "deleted": "red",
            "renamed": "blue",
        }

        for _entity_type_name, item in sorted(all_items, key=lambda x: (x[1].status, x[0])):
            color = status_colors.get(item.status, "white")
            display_path = item.file_path or item.entity_id

            # Header line
            console.print(f"[{color}]{item.status}[/{color}] {display_path}")

            # Show diff for modified items
            if item.status == "modified" and item.local and item.remote:
                local_yaml = dump_yaml(item.local).splitlines(keepends=True)
                remote_yaml = dump_yaml(item.remote).splitlines(keepends=True)

                diff_lines = list(
                    difflib.unified_diff(
                        remote_yaml,
                        local_yaml,
                        fromfile="remote",
                        tofile="local",
                        lineterm="",
                    )
                )

                if diff_lines:
                    for line in diff_lines:
                        line = line.rstrip("\n")
                        if line.startswith("+++") or line.startswith("---"):
                            console.print(f"[dim]{line}[/dim]")
                        elif line.startswith("@@"):
                            console.print(f"[cyan]{line}[/cyan]")
                        elif line.startswith("+"):
                            console.print(f"[green]{line}[/green]")
                        elif line.startswith("-"):
                            console.print(f"[red]{line}[/red]")
                        else:
                            console.print(f"[dim]{line}[/dim]")

            # Show content for added items
            elif item.status == "added" and item.local:
                local_yaml = dump_yaml(item.local)
                for line in local_yaml.splitlines():
                    console.print(f"[green]+{line}[/green]")

            # Show content for deleted items
            elif item.status == "deleted" and item.remote:
                remote_yaml = dump_yaml(item.remote)
                for line in remote_yaml.splitlines():
                    console.print(f"[red]-{line}[/red]")

            console.print()  # Blank line between items


@app.command()
def template(
    template_str: Annotated[
        str,
        typer.Argument(help="Jinja2 template string to render"),
    ],
) -> None:
    """Test a Jinja2 template against Home Assistant."""
    with logfire.span("ha-sync template"):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_template(config, template_str))


async def _template(config: SyncConfig, template_str: str) -> None:
    """Render a template against Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        is_valid, result = await client.validate_template(template_str)
        if is_valid:
            console.print(result)
        else:
            console.print(f"[red]Template error:[/red] {result}")
            raise typer.Exit(1)


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(help="Search query (matches entity_id and friendly_name)"),
    ],
    domain: Annotated[
        str | None,
        typer.Option("--domain", "-d", help="Filter by domain (e.g., light, switch)"),
    ] = None,
    state: Annotated[
        str | None,
        typer.Option("--state", "-s", help="Filter by current state (e.g., on, off)"),
    ] = None,
) -> None:
    """Search for entities in Home Assistant."""
    with logfire.span("ha-sync search", query=query):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_search(config, query, domain, state))


async def _search(
    config: SyncConfig, query: str, domain: str | None, state_filter: str | None
) -> None:
    """Search for entities in Home Assistant."""
    import fnmatch

    async with HAClient(config.url, config.token) as client:
        all_states = await client.get_all_states()

        # Filter by domain
        if domain:
            all_states = [s for s in all_states if s["entity_id"].startswith(f"{domain}.")]

        # Filter by state
        if state_filter:
            all_states = [s for s in all_states if s.get("state") == state_filter]

        # Filter by query (matches entity_id or friendly_name)
        query_lower = query.lower()
        # Check if query is a glob pattern
        is_glob = "*" in query or "?" in query

        matches = []
        for entity in all_states:
            entity_id = entity["entity_id"]
            friendly_name = entity.get("attributes", {}).get("friendly_name", "")

            if is_glob:
                # Glob pattern matching
                if fnmatch.fnmatch(entity_id.lower(), query_lower) or fnmatch.fnmatch(
                    friendly_name.lower(), query_lower
                ):
                    matches.append(entity)
            else:
                # Substring matching
                if query_lower in entity_id.lower() or query_lower in friendly_name.lower():
                    matches.append(entity)

        if not matches:
            console.print("[dim]No entities found[/dim]")
            return

        # Display results
        table = Table(title=f"Found {len(matches)} entities")
        table.add_column("Entity ID", style="cyan")
        table.add_column("State")
        table.add_column("Name", style="dim")

        for entity in sorted(matches, key=lambda e: e["entity_id"]):
            entity_id = entity["entity_id"]
            state_val = entity.get("state", "")
            friendly_name = entity.get("attributes", {}).get("friendly_name", "")

            # Color state based on value
            if state_val in ("on", "home", "playing", "open"):
                state_display = f"[green]{state_val}[/green]"
            elif state_val in ("off", "not_home", "idle", "closed", "paused"):
                state_display = f"[dim]{state_val}[/dim]"
            elif state_val == "unavailable":
                state_display = f"[red]{state_val}[/red]"
            else:
                state_display = state_val

            table.add_row(entity_id, state_display, friendly_name)

        console.print(table)


@app.command()
def state(
    entity: Annotated[
        str,
        typer.Argument(help="Entity ID (e.g., light.living_room) or file path"),
    ],
) -> None:
    """Get the current state of an entity."""
    with logfire.span("ha-sync state", entity=entity):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_state(config, entity))


async def _state(config: SyncConfig, entity: str) -> None:
    """Get entity state."""
    from ha_sync.utils import load_yaml

    # Detect if input is a file path or entity ID
    is_file_path = "/" in entity or entity.endswith(".yaml")

    entity_id: str | None = None

    if is_file_path:
        # Parse file to extract entity ID
        file_path = Path(entity)
        if not file_path.exists():
            console.print(f"[red]File not found:[/red] {entity}")
            raise typer.Exit(1)

        data = load_yaml(file_path)
        if not data:
            console.print(f"[red]Could not parse file:[/red] {entity}")
            raise typer.Exit(1)

        # Determine entity ID based on file location and content
        parts = file_path.parts

        if "automations" in parts:
            # Automations use "id" field with automation. domain
            auto_id = data.get("id")
            if auto_id:
                entity_id = f"automation.{auto_id}"
        elif "scripts" in parts:
            # Scripts use filename as ID
            entity_id = f"script.{file_path.stem}"
        elif "scenes" in parts:
            # Scenes use "id" field
            scene_id = data.get("id")
            if scene_id:
                entity_id = f"scene.{scene_id}"
        elif "helpers" in parts:
            # Helpers: look for entry_id or id field
            helper_id = data.get("id") or data.get("entry_id")
            if helper_id:
                # Determine domain from path
                if "input_boolean" in parts:
                    entity_id = f"input_boolean.{helper_id}"
                elif "input_number" in parts:
                    entity_id = f"input_number.{helper_id}"
                elif "input_select" in parts:
                    entity_id = f"input_select.{helper_id}"
                elif "input_text" in parts:
                    entity_id = f"input_text.{helper_id}"
                elif "input_datetime" in parts:
                    entity_id = f"input_datetime.{helper_id}"
                elif "input_button" in parts:
                    entity_id = f"input_button.{helper_id}"
                elif "timer" in parts:
                    entity_id = f"timer.{helper_id}"
                elif "counter" in parts:
                    entity_id = f"counter.{helper_id}"
                elif "schedule" in parts:
                    entity_id = f"schedule.{helper_id}"
                # For config entry helpers (template, group, etc.),
                # we need to look up entities by config entry ID
                elif "template" in parts or "group" in parts:
                    entry_id = data.get("entry_id")
                    if entry_id:
                        # Look up entity from registry
                        async with HAClient(config.url, config.token) as client:
                            entities = await client.get_entities_for_config_entry(entry_id)
                            if entities:
                                entity_id = entities[0].get("entity_id")

        if not entity_id:
            console.print(f"[red]Could not determine entity ID from file:[/red] {entity}")
            raise typer.Exit(1)

        console.print(f"[dim]File maps to entity:[/dim] {entity_id}")
    else:
        entity_id = entity

    async with HAClient(config.url, config.token) as client:
        state_data = await client.get_entity_state(entity_id)

        if not state_data:
            console.print(f"[red]Entity not found:[/red] {entity_id}")
            raise typer.Exit(1)

        # Display state info
        console.print(f"[bold]Entity:[/bold] {state_data['entity_id']}")
        console.print(f"[bold]State:[/bold] {state_data.get('state', 'unknown')}")
        console.print(f"[bold]Last Changed:[/bold] {state_data.get('last_changed', 'unknown')}")

        attrs = state_data.get("attributes", {})
        if attrs:
            console.print("\n[bold]Attributes:[/bold]")
            for key, value in sorted(attrs.items()):
                console.print(f"  {key}: {value}")


@app.command()
def sync(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to sync (e.g., automations/, helpers/template/)"),
    ] = None,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Sync deletions in both directions"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation and autostash"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be synced without making changes"),
    ] = False,
) -> None:
    """Bidirectional sync: pull from HA, merge local changes, push back.

    This is the safest way to sync when you have local changes:
    1. Stashes local changes (if git repo)
    2. Pulls latest from Home Assistant
    3. Restores stashed changes (may create conflicts)
    4. If no conflicts, pushes local changes to Home Assistant

    If conflicts are detected after restoring the stash, the command stops
    and asks you to resolve them manually before pushing.
    """
    with logfire.span("ha-sync sync", paths=paths, yes=yes, dry_run=dry_run):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if dry_run:
            console.print("[cyan]Dry run mode - showing what would be synced[/cyan]\n")

        # Check if we're in a git repo
        in_git = is_git_repo()
        if not in_git and not yes and not dry_run:
            console.print(
                "[yellow]Warning:[/yellow] Not in a git repo. "
                "Local changes may be overwritten during pull."
            )
            if not _ask_confirmation("continue anyway"):
                console.print("[dim]Aborted[/dim]")
                raise typer.Exit(0)

        # Quick check: any uncommitted changes in managed folders?
        from ha_sync.utils import git_has_changes

        has_local_changes = git_has_changes(MANAGED_FOLDERS) if in_git else True

        # Fetch all diffs in one API call, computing both push and pull diffs
        # by temporarily stashing if needed
        console.print("[dim]Fetching remote state...[/dim]")
        pull_diff, push_diff, remote_cache = asyncio.run(
            _get_sync_diffs(config, paths, sync_deletions, in_git, has_local_changes)
        )

        # Display remote changes
        console.print("\n[bold]Remote changes (will be pulled):[/bold]\n")
        if pull_diff:
            _display_diff_items(pull_diff, direction="pull")
        else:
            console.print("[dim]No remote changes[/dim]\n")

        # Display local changes
        if has_local_changes:
            console.print("[bold]Your uncommitted changes (will be pushed after merge):[/bold]\n")
            if push_diff:
                _display_diff_items(push_diff, direction="push")
            else:
                console.print("[dim]No local changes[/dim]\n")
        else:
            console.print("[dim]No uncommitted changes[/dim]\n")

        # If nothing to do, exit early
        if not pull_diff and not push_diff:
            console.print("[dim]Everything is in sync[/dim]")
            return

        # Dry run stops here
        if dry_run:
            console.print("[cyan]Dry run complete - no changes made[/cyan]")
            return

        # If only remote changes (no local changes), just pull without confirmation
        if pull_diff and not push_diff:
            console.print("[bold]Pulling from Home Assistant...[/bold]")
            asyncio.run(
                _pull(config, paths, sync_deletions, dry_run=False, remote_cache=remote_cache)
            )
            console.print("\n[green]Sync complete![/green]")
            return

        # Warn about potential conflicts
        if pull_diff and push_diff:
            pull_files = {item.file_path for item in pull_diff if item.file_path}
            push_files = {item.file_path for item in push_diff if item.file_path}
            overlap = pull_files & push_files
            if overlap:
                console.print(
                    f"[yellow]Note:[/yellow] {len(overlap)} file(s) changed on both sides. "
                    "May require conflict resolution.\n"
                )

        # Ask for confirmation when there are local changes to push
        if not yes and not _ask_confirmation("proceed with sync"):
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

        # Step 3: Stash, pull, unstash
        stashed = False
        if in_git and not yes:
            stash_result = git_stash(MANAGED_FOLDERS)
            if stash_result.stashed:
                console.print("[dim]Stashed local changes in managed folders[/dim]")
                stashed = True

        # Execute pull (using cached remote data to avoid re-fetching)
        if pull_diff:
            console.print("\n[bold]Pulling from Home Assistant...[/bold]")
            asyncio.run(
                _pull(config, paths, sync_deletions, dry_run=False, remote_cache=remote_cache)
            )

        # Restore stash
        if stashed:
            pop_result = git_stash_pop()
            if not pop_result.success:
                if pop_result.has_conflicts:
                    console.print("\n[yellow]Conflicts detected![/yellow]")
                    console.print(
                        "Resolve the conflicts in your files, then run "
                        "[cyan]ha-sync push[/cyan] to push your changes."
                    )
                    raise typer.Exit(1)
                else:
                    console.print(f"[red]Error restoring stash:[/red] {pop_result.message}")
                    raise typer.Exit(1)
            console.print("[dim]Restored stashed changes[/dim]")

        # Step 4: Push using pre-computed push_diff (no need to re-fetch)
        # After stash pop without conflicts, our uncommitted changes are restored,
        # so the diff should be the same as what we computed in the preview
        if push_diff:
            changed_paths = list({item.file_path for item in push_diff if item.file_path})
            console.print("\n[bold]Pushing to Home Assistant...[/bold]")
            asyncio.run(
                _push(
                    config,
                    changed_paths,
                    all_items=False,
                    sync_deletions=sync_deletions,
                    dry_run=False,
                    diff_items=push_diff,
                )
            )
        else:
            console.print("[dim]No changes to push[/dim]")

        console.print("\n[green]Sync complete![/green]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"ha-sync version {__version__}")


if __name__ == "__main__":
    app()

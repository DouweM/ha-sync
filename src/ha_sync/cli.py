"""CLI interface for ha-sync."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

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
from ha_sync.sync.three_way import ThreeWayDiffItem, ThreeWayDiffResult, compute_three_way_diff
from ha_sync.utils import (
    dump_yaml,
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


type SyncerDiff = tuple[
    "BaseSyncer", list[ThreeWayDiffItem], list[ThreeWayDiffItem], dict[str, dict]
]


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
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
) -> None:
    """Pull entities from Home Assistant to local files.

    In a git repo, uses three-way diff to only write remote-changed entities,
    leaving local-only changes untouched (no stashing needed).
    Outside git, falls back to two-way diff and asks for confirmation.
    """
    with logfire.span("ha-sync pull", paths=paths, dry_run=dry_run, yes=yes):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        in_git = is_git_repo()

        if in_git:
            # Three-way pull: only writes remote-changed entities
            asyncio.run(
                _pull_three_way(config, paths, sync_deletions, dry_run=dry_run, yes=yes)
            )
        else:
            # Two-way pull: old behavior (confirmation needed)
            if dry_run:
                console.print("[cyan]Dry run mode - no changes will be made[/cyan]\n")
                asyncio.run(_pull(config, paths, sync_deletions, dry_run=True))
                return

            console.print("[bold]Fetching changes from Home Assistant...[/bold]\n")
            diff_items = asyncio.run(_get_pull_diff(config, paths, sync_deletions))

            if not diff_items:
                console.print("[dim]No changes to pull[/dim]")
                return

            _display_diff_items(diff_items, direction="pull")

            if not yes and not _ask_confirmation("pull these changes"):
                console.print("[dim]Aborted[/dim]")
                raise typer.Exit(0)

            console.print()
            asyncio.run(_pull(config, paths, sync_deletions, dry_run=False))


async def _pull_three_way(
    config: SyncConfig,
    paths: list[str] | None,
    sync_deletions: bool,
    dry_run: bool = False,
    yes: bool = False,
) -> None:
    """Three-way pull: only write remote-changed entities, leave local-only alone."""
    if dry_run:
        console.print("[cyan]Dry run mode - no changes will be made[/cyan]\n")

    console.print("[bold]Fetching changes from Home Assistant...[/bold]\n")

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        # First pass: collect all diffs for preview
        syncer_diffs: list[SyncerDiff] = []

        for syncer, file_filters in syncers_with_filters:
            base = syncer.get_base_entities()
            local = syncer.get_local_entities()
            remote = await syncer.get_remote_entities()

            norm_fn = _get_normalize_fn(syncer)
            fp_fn = _get_file_path_fn(syncer)
            tw_result = compute_three_way_diff(
                base, local, remote, syncer.entity_type,
                normalize_fn=norm_fn, file_path_fn=fp_fn,
            )

            # For pull, we care about:
            # - remote_only items (will be pulled)
            # - conflicts (need resolution)
            remote_items = tw_result.remote_only
            conflicts = tw_result.conflicts

            if file_filters:
                remote_items = _filter_three_way_items(remote_items, file_filters, fp_fn)
                conflicts = _filter_three_way_items(conflicts, file_filters, fp_fn)

            if remote_items or conflicts:
                syncer_diffs.append((syncer, remote_items, conflicts, remote))

        if not syncer_diffs:
            console.print("[dim]No changes to pull[/dim]")
            return

        # Show preview
        all_remote = [item for _, remote_items, _, _ in syncer_diffs for item in remote_items]
        all_conflicts = [item for _, _, conflicts, _ in syncer_diffs for item in conflicts]

        if all_remote:
            console.print("[bold]Remote changes (will be pulled):[/bold]\n")
            for item in all_remote:
                _print_three_way_item(item, side="remote")
            console.print()

        if all_conflicts:
            console.print("[bold red]Conflicts (will NOT be pulled):[/bold red]\n")
            for item in all_conflicts:
                _print_three_way_item(item, side="both")
            console.print(
                "\n[yellow]Resolve conflicts with sync --theirs or --ours.[/yellow]\n"
            )

        if dry_run:
            return

        # Ask for confirmation
        if not yes and not _ask_confirmation("pull these changes"):
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

        # Second pass: execute
        for syncer, remote_items, _conflicts, remote in syncer_diffs:
            if not remote_items:
                continue

            console.print(f"\n[bold]Pulling {syncer.entity_type}s...[/bold]")

            # Split into additions/modifications vs deletions
            remote_to_pull = {
                item.entity_id: remote[item.entity_id]
                for item in remote_items
                if item.remote_status != "deleted" and item.entity_id in remote
            }
            remote_deletions = [
                item for item in remote_items
                if item.remote_status == "deleted"
            ]

            if remote_to_pull:
                await syncer.pull(
                    sync_deletions=False,
                    dry_run=False,
                    remote=remote_to_pull,
                )

            # Handle remote deletions: delete local files
            if remote_deletions:
                _delete_local_files(syncer, remote_deletions)


def _delete_local_files(syncer: BaseSyncer, items: list[ThreeWayDiffItem]) -> None:
    """Delete local files for entities that were deleted remotely."""
    from ha_sync.utils import relative_path

    for item in items:
        # Try to find the file from local data (_filename metadata)
        local_data = item.local or item.base
        file_path = None

        if local_data and "_filename" in local_data:
            file_path = syncer.local_path / local_data["_filename"]
        elif item.file_path:
            file_path = Path(item.file_path)
            if not file_path.is_absolute():
                file_path = Path.cwd() / file_path
        else:
            get_filename = getattr(syncer, "get_filename", None)
            if callable(get_filename):
                filename = get_filename(item.entity_id, local_data or {})
                if isinstance(filename, str):
                    file_path = syncer.local_path / filename

        if file_path and file_path.exists():
            rel_path = relative_path(file_path)
            file_path.unlink()
            console.print(f"  [red]Deleted[/red] {rel_path}")


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
    """Show differences between local and remote.

    Uses three-way diff when in a git repo (base=HEAD, local=disk, remote=HA).
    Falls back to two-way diff (local vs remote) when not in git.
    """
    in_git = is_git_repo()

    if in_git:
        await _diff_three_way(config, paths)
    else:
        await _diff_two_way(config, paths)


async def _diff_two_way(config: SyncConfig, paths: list[str] | None) -> None:
    """Two-way diff: local vs remote (fallback when not in git)."""
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)
        all_items: list[tuple[str, DiffItem]] = []

        for syncer, file_filters in syncers_with_filters:
            items = await syncer.diff()
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

        for _entity_type_name, item in sorted(all_items, key=lambda x: (x[1].status, x[0])):
            _print_diff_item(item)


async def _diff_three_way(config: SyncConfig, paths: list[str] | None) -> None:
    """Three-way diff: base (HEAD) vs local (disk) vs remote (HA)."""
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        all_local: list[ThreeWayDiffItem] = []
        all_remote: list[ThreeWayDiffItem] = []
        all_conflicts: list[ThreeWayDiffItem] = []

        for syncer, file_filters in syncers_with_filters:
            base = syncer.get_base_entities()
            local = syncer.get_local_entities()
            remote = await syncer.get_remote_entities()

            # Get normalize and file_path functions from syncer
            norm_fn = _get_normalize_fn(syncer)
            fp_fn = _get_file_path_fn(syncer)

            tw_result = compute_three_way_diff(
                base, local, remote, syncer.entity_type,
                normalize_fn=norm_fn,
                file_path_fn=fp_fn,
            )

            if file_filters:
                tw_result = ThreeWayDiffResult(
                    local_only=_filter_three_way_items(tw_result.local_only, file_filters),
                    remote_only=_filter_three_way_items(tw_result.remote_only, file_filters),
                    conflicts=_filter_three_way_items(tw_result.conflicts, file_filters),
                )

            all_local.extend(tw_result.local_only)
            all_remote.extend(tw_result.remote_only)
            all_conflicts.extend(tw_result.conflicts)

        if not all_local and not all_remote and not all_conflicts:
            console.print("[dim]No differences[/dim]")
            return

        if all_local:
            console.print("[bold]Local changes[/bold] (not yet in HA):\n")
            for item in all_local:
                _print_three_way_item(item, side="local")
            console.print()

        if all_remote:
            console.print("[bold]Remote changes[/bold] (not yet pulled):\n")
            for item in all_remote:
                _print_three_way_item(item, side="remote")
            console.print()

        if all_conflicts:
            console.print("[bold red]Conflicts[/bold red] (changed on both sides):\n")
            for item in all_conflicts:
                _print_three_way_item(item, side="both")
            console.print()


def _get_normalize_fn(
    syncer: BaseSyncer,
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Get a normalize function for a syncer, if available."""
    from ha_sync.sync.automations import AutomationSyncer
    from ha_sync.sync.base import SimpleEntitySyncer
    from ha_sync.sync.dashboards import DashboardSyncer

    if isinstance(syncer, AutomationSyncer):
        from ha_sync.models import Automation

        def norm_auto(data: dict[str, Any]) -> dict[str, Any]:
            clean = {k: v for k, v in data.items() if not k.startswith("_")}
            return Automation.normalize(clean)

        return norm_auto
    elif isinstance(syncer, SimpleEntitySyncer):

        def norm_simple(data: dict[str, Any]) -> dict[str, Any]:
            clean = {k: v for k, v in data.items() if not k.startswith("_")}
            return syncer.normalize(clean)

        return norm_simple
    elif isinstance(syncer, DashboardSyncer):

        def norm_dashboard(data: dict[str, Any]) -> dict[str, Any]:
            if "config" in data:
                return {"config": syncer._normalize_config(data["config"])}
            return data

        return norm_dashboard
    return None


def _get_file_path_fn(syncer: BaseSyncer) -> Callable[[str], str | None] | None:
    """Get a file_path function for a syncer."""
    from ha_sync.utils import relative_path as rel_path

    def fp(entity_id: str) -> str | None:
        return rel_path(syncer.local_path / f"{entity_id}.yaml")

    return fp


def _filter_three_way_items(
    items: list[ThreeWayDiffItem],
    file_filters: list[Path],
    fp_fn: Callable[[str], str | None] | None = None,
) -> list[ThreeWayDiffItem]:
    """Filter three-way diff items by file path filters."""
    filtered = []
    for item in items:
        fp = item.file_path or (fp_fn(item.entity_id) if fp_fn else None)
        if fp and any(_matches_filter(fp, f) for f in file_filters):
            filtered.append(item)
    return filtered


def _print_three_way_item(item: ThreeWayDiffItem, side: str) -> None:
    """Print a three-way diff item."""

    status_colors = {
        "added": "green",
        "modified": "yellow",
        "deleted": "red",
    }

    display_path = item.file_path or item.entity_id

    if side == "local":
        status = item.local_status or "unknown"
        color = status_colors.get(status, "white")
        console.print(f"  [{color}]{status}[/{color}] {display_path}")
        if status == "modified" and item.base and item.local:
            _print_yaml_diff(item.base, item.local, "base", "local")
        elif status == "added" and item.local:
            _print_yaml_content(item.local, "+", "green")
        elif status == "deleted" and item.base:
            _print_yaml_content(item.base, "-", "red")

    elif side == "remote":
        status = item.remote_status or "unknown"
        color = status_colors.get(status, "white")
        console.print(f"  [{color}]{status}[/{color}] {display_path}")
        if status == "modified" and item.base and item.remote:
            _print_yaml_diff(item.base, item.remote, "base", "remote")
        elif status == "added" and item.remote:
            _print_yaml_content(item.remote, "+", "green")
        elif status == "deleted" and item.base:
            _print_yaml_content(item.base, "-", "red")

    elif side == "both":
        console.print(
            f"  [red]conflict[/red] {display_path} "
            f"(local: {item.local_status}, remote: {item.remote_status})"
        )
        if item.local and item.remote:
            _print_yaml_diff(
                item.local, item.remote, "local", "remote"
            )


def _print_diff_item(item: DiffItem) -> None:
    """Print a two-way DiffItem (backward compat)."""
    status_colors = {
        "added": "green",
        "modified": "yellow",
        "deleted": "red",
        "renamed": "blue",
    }
    color = status_colors.get(item.status, "white")
    display_path = item.file_path or item.entity_id

    console.print(f"[{color}]{item.status}[/{color}] {display_path}")

    if item.status == "modified" and item.local and item.remote:
        _print_yaml_diff(item.remote, item.local, "remote", "local")
    elif item.status == "added" and item.local:
        _print_yaml_content(item.local, "+", "green")
    elif item.status == "deleted" and item.remote:
        _print_yaml_content(item.remote, "-", "red")

    console.print()


def _print_yaml_diff(
    from_data: dict[str, Any], to_data: dict[str, Any], from_label: str, to_label: str
) -> None:
    """Print a unified diff between two YAML representations."""
    import difflib

    from_yaml = dump_yaml(from_data).splitlines(keepends=True)
    to_yaml = dump_yaml(to_data).splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(from_yaml, to_yaml, fromfile=from_label, tofile=to_label, lineterm="")
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


def _print_yaml_content(data: dict[str, Any], prefix: str, color: str) -> None:
    """Print YAML content with a prefix on each line."""
    yaml_str = dump_yaml(data)
    for line in yaml_str.splitlines():
        console.print(f"[{color}]{prefix}{line}[/{color}]")


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
        # Use entity registry (fast WebSocket call) instead of /api/states
        all_entities = await client.get_entity_registry_cached()

        # Filter by domain
        if domain:
            all_entities = [
                e for e in all_entities if e["entity_id"].startswith(f"{domain}.")
            ]

        # Filter by query (matches entity_id or name)
        query_lower = query.lower()
        is_glob = "*" in query or "?" in query

        matches = []
        for entity in all_entities:
            entity_id = entity["entity_id"]
            name = entity.get("name") or entity.get("original_name") or ""

            if is_glob:
                if fnmatch.fnmatch(entity_id.lower(), query_lower) or fnmatch.fnmatch(
                    name.lower(), query_lower
                ):
                    matches.append(entity)
            else:
                if query_lower in entity_id.lower() or query_lower in name.lower():
                    matches.append(entity)

        if not matches:
            console.print("[dim]No entities found[/dim]")
            return

        # Fetch states only for matched entities (in parallel)
        async def get_state(entity: dict) -> tuple[dict, dict | None]:
            state = await client.get_entity_state(entity["entity_id"])
            return entity, state

        results = await asyncio.gather(*[get_state(e) for e in matches])

        # Filter by state if requested
        if state_filter:
            results = [
                (e, s) for e, s in results if s and s.get("state") == state_filter
            ]

        if not results:
            console.print("[dim]No entities found[/dim]")
            return

        # Display results
        table = Table(title=f"Found {len(results)} entities")
        table.add_column("Entity ID", style="cyan", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Name", style="dim", no_wrap=True)
        table.add_column("Attrs", style="dim", no_wrap=True, justify="right")

        _HIDDEN_ATTR_KEYS = {"friendly_name", "icon", "entity_picture"}

        for entity, state in sorted(results, key=lambda r: r[0]["entity_id"]):
            entity_id = entity["entity_id"]
            name = entity.get("name") or entity.get("original_name") or ""
            state_val = state.get("state", "") if state else ""
            friendly_name = (
                state.get("attributes", {}).get("friendly_name", "") if state else name
            )
            attr_keys = sorted(
                k
                for k in (state.get("attributes", {}) if state else {})
                if k not in _HIDDEN_ATTR_KEYS
            )

            # Color state based on value
            if state_val in ("on", "home", "playing", "open"):
                state_display = f"[green]{state_val}[/green]"
            elif state_val in ("off", "not_home", "idle", "closed", "paused"):
                state_display = f"[dim]{state_val}[/dim]"
            elif state_val == "unavailable":
                state_display = f"[red]{state_val}[/red]"
            else:
                state_display = state_val

            table.add_row(
                entity_id,
                state_display,
                friendly_name or name,
                str(len(attr_keys)) if attr_keys else "",
            )

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
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be synced without making changes"),
    ] = False,
    theirs: Annotated[
        bool,
        typer.Option("--theirs", help="Resolve conflicts by accepting remote changes"),
    ] = False,
    ours: Annotated[
        bool,
        typer.Option("--ours", help="Resolve conflicts by keeping local changes"),
    ] = False,
) -> None:
    """Bidirectional sync using three-way diff (base=HEAD, local=disk, remote=HA).

    Computes what changed locally vs remotely since last commit:
    - Remote-only changes are pulled (written to disk)
    - Local-only changes are pushed (sent to HA)
    - Conflicts (both sides changed) are shown for resolution

    No git stashing is used. Local changes are never overwritten.
    """
    with logfire.span("ha-sync sync", paths=paths, yes=yes, dry_run=dry_run):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if theirs and ours:
            console.print("[red]Cannot use both --theirs and --ours[/red]")
            raise typer.Exit(1)

        asyncio.run(
            _sync_three_way(config, paths, sync_deletions, dry_run, yes, theirs, ours)
        )


async def _sync_three_way(
    config: SyncConfig,
    paths: list[str] | None,
    sync_deletions: bool,
    dry_run: bool,
    yes: bool,
    theirs: bool,
    ours: bool,
) -> None:
    """Three-way sync: compute diffs, show preview, execute."""
    if dry_run:
        console.print("[cyan]Dry run mode - showing what would be synced[/cyan]\n")

    console.print("[dim]Fetching remote state...[/dim]")

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_paths(client, config, paths)

        # Collect three-way diffs per syncer
        syncer_diffs: list[tuple[BaseSyncer, ThreeWayDiffResult, dict[str, dict]]] = []

        for syncer, file_filters in syncers_with_filters:
            base = syncer.get_base_entities()
            local = syncer.get_local_entities()
            remote = await syncer.get_remote_entities()

            norm_fn = _get_normalize_fn(syncer)
            fp_fn = _get_file_path_fn(syncer)
            tw_result = compute_three_way_diff(
                base, local, remote, syncer.entity_type,
                normalize_fn=norm_fn, file_path_fn=fp_fn,
            )

            # Apply file filters
            if file_filters:
                tw_result = ThreeWayDiffResult(
                    local_only=_filter_three_way_items(tw_result.local_only, file_filters),
                    remote_only=_filter_three_way_items(tw_result.remote_only, file_filters),
                    conflicts=_filter_three_way_items(tw_result.conflicts, file_filters),
                )

            syncer_diffs.append((syncer, tw_result, remote))

        # Display preview
        all_local = [item for _, tw, _ in syncer_diffs for item in tw.local_only]
        all_remote = [item for _, tw, _ in syncer_diffs for item in tw.remote_only]
        all_conflicts = [item for _, tw, _ in syncer_diffs for item in tw.conflicts]

        console.print("\n[bold]Remote changes (will be pulled):[/bold]\n")
        if all_remote:
            for item in all_remote:
                _print_three_way_item(item, side="remote")
        else:
            console.print("[dim]No remote changes[/dim]")

        console.print("\n[bold]Local changes (will be pushed):[/bold]\n")
        if all_local:
            for item in all_local:
                _print_three_way_item(item, side="local")
        else:
            console.print("[dim]No local changes[/dim]")

        if all_conflicts:
            console.print(f"\n[bold red]Conflicts ({len(all_conflicts)}):[/bold red]\n")
            for item in all_conflicts:
                _print_three_way_item(item, side="both")
            if not theirs and not ours:
                console.print(
                    "\n[yellow]Use --theirs to accept remote or --ours to keep local[/yellow]"
                )

        if not all_local and not all_remote and not all_conflicts:
            console.print("\n[dim]Everything is in sync[/dim]")
            return

        # Stop if conflicts and no resolution strategy
        if all_conflicts and not theirs and not ours and not dry_run:
            console.print(
                "\n[red]Cannot sync with unresolved conflicts.[/red] "
                "Use --theirs or --ours to resolve."
            )
            raise typer.Exit(1)

        if dry_run:
            console.print("\n[cyan]Dry run complete - no changes made[/cyan]")
            return

        # Ask for confirmation
        if not yes and not _ask_confirmation("proceed with sync"):
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

        # Execute sync
        for syncer, tw_result, remote in syncer_diffs:
            if not tw_result.has_changes:
                continue

            console.print(f"\n[bold]Syncing {syncer.entity_type}s...[/bold]")

            # Pull remote-only changes (additions + modifications)
            if tw_result.remote_only:
                remote_to_pull = {
                    item.entity_id: remote[item.entity_id]
                    for item in tw_result.remote_only
                    if item.remote_status != "deleted" and item.entity_id in remote
                }
                remote_deletions = [
                    item for item in tw_result.remote_only
                    if item.remote_status == "deleted"
                ]

                if remote_to_pull:
                    await syncer.pull(
                        sync_deletions=False,
                        dry_run=False,
                        remote=remote_to_pull,
                    )
                if remote_deletions:
                    _delete_local_files(syncer, remote_deletions)

            # Push local-only changes
            if tw_result.local_only:
                # Convert ThreeWayDiffItems to DiffItems for push
                push_items = _three_way_to_diff_items(tw_result.local_only, direction="push")
                if push_items:
                    await syncer.push(
                        sync_deletions=sync_deletions,
                        dry_run=False,
                        diff_items=push_items,
                    )

            # Handle conflicts
            if tw_result.conflicts:
                if theirs:
                    # Accept remote: pull conflicted entities (additions + modifications)
                    remote_to_pull = {
                        item.entity_id: remote[item.entity_id]
                        for item in tw_result.conflicts
                        if item.entity_id in remote and item.remote_status != "deleted"
                    }
                    remote_deletions = [
                        item for item in tw_result.conflicts
                        if item.remote_status == "deleted"
                    ]
                    if remote_to_pull:
                        await syncer.pull(
                            sync_deletions=False,
                            dry_run=False,
                            remote=remote_to_pull,
                        )
                    if remote_deletions:
                        _delete_local_files(syncer, remote_deletions)
                elif ours:
                    # Keep local: push local versions
                    push_items = _three_way_to_diff_items(tw_result.conflicts, direction="push")
                    if push_items:
                        await syncer.push(
                            sync_deletions=sync_deletions,
                            dry_run=False,
                            diff_items=push_items,
                        )

        console.print("\n[green]Sync complete![/green]")


def _three_way_to_diff_items(
    items: list[ThreeWayDiffItem], direction: str
) -> list[DiffItem]:
    """Convert ThreeWayDiffItems to DiffItems for push/pull operations."""
    result: list[DiffItem] = []
    for item in items:
        status = item.local_status if direction == "push" else item.remote_status

        if status is None:
            continue

        result.append(DiffItem(
            entity_id=item.entity_id,
            status=status,
            entity_type=item.entity_type,
            local=item.local,
            remote=item.remote,
            file_path=item.file_path,
        ))
    return result


@app.command()
def render(
    view_path: Annotated[
        Path,
        typer.Argument(help="Path to dashboard view YAML file"),
    ],
    user: Annotated[
        str | None,
        typer.Option("--user", "-u", help="View as specific user (e.g., douwe)"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output format: rich (default) or swiftbar"),
    ] = "rich",
) -> None:
    """Render a Lovelace dashboard view as CLI text."""
    with logfire.span("ha-sync render", view_path=str(view_path), user=user, output=output):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_render(config, view_path, user, output))


async def _render(
    config: SyncConfig, view_path: Path, user: str | None, output: str
) -> None:
    """Render a dashboard view."""
    async with HAClient(config.url, config.token) as client:
        if output == "swiftbar":
            from ha_sync.swiftbar import render_view_swiftbar

            await render_view_swiftbar(client, view_path, user)
        else:
            from ha_sync.render import render_view_file

            await render_view_file(client, view_path, user)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"ha-sync version {__version__}")


if __name__ == "__main__":
    app()

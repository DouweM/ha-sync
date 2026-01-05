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
    path: Annotated[
        str | None,
        typer.Argument(help="Path to validate (e.g., automations/, helpers/template/)"),
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
    with logfire.span("ha-sync validate", path=path):
        _validate_impl(path, check_templates, check_config, diff_only)


def _validate_impl(
    path: str | None,
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

    # Resolve path to determine what to validate
    specs = resolve_path_to_syncers(path, config, None)
    syncer_classes = {spec.syncer_class for spec in specs}
    file_filter = specs[0].file_filter if len(specs) == 1 and specs[0].file_filter else None

    # Get changed files if diff_only mode
    changed_files: set[str] = set()
    if check_templates and diff_only and config.url and config.token:
        console.print("[dim]Getting diff to find changed files...[/dim]")
        diff_items = asyncio.run(_get_diff_items(config, path))
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
        """Check if file matches the filter."""
        if file_filter is None:
            return True
        # Check if file path matches the filter (is under the filter path or matches it)
        try:
            file_path.relative_to(file_filter)
            return True
        except ValueError:
            return str(file_path) == str(file_filter) or str(file_path).endswith(str(file_filter))

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
                filtered = [t for t in templates_to_check if t[0] in changed_files]
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


async def _get_diff_items(config: SyncConfig, path: str | None) -> list[DiffItem]:
    """Get diff items for the specified path."""
    items: list[DiffItem] = []
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_path(client, config, path)
        for syncer, file_filter in syncers_with_filters:
            syncer_items = await syncer.diff()
            # Filter items if file_filter is set
            if file_filter:
                syncer_items = [
                    item
                    for item in syncer_items
                    if item.file_path and _matches_filter(item.file_path, file_filter)
                ]
            items.extend(syncer_items)
    return items


def _matches_filter(file_path: str, file_filter: Path) -> bool:
    """Check if a file path matches the filter."""
    filter_str = str(file_filter)
    return file_path.startswith(filter_str) or file_path == filter_str


@app.command()
def pull(
    path: Annotated[
        str | None,
        typer.Argument(help="Path to pull (e.g., automations/, helpers/template/)"),
    ] = None,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Delete local files not in Home Assistant"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
) -> None:
    """Pull entities from Home Assistant to local files."""
    with logfire.span("ha-sync pull", path=path, dry_run=dry_run):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if dry_run:
            console.print("[cyan]Dry run mode - no changes will be made[/cyan]")

        asyncio.run(_pull(config, path, sync_deletions, dry_run))


async def _pull(
    config: SyncConfig, path: str | None, sync_deletions: bool, dry_run: bool = False
) -> None:
    """Pull entities from Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_path(client, config, path)

        for syncer, _file_filter in syncers_with_filters:
            console.print(f"\n[bold]Pulling {syncer.entity_type}s...[/bold]")
            result = await syncer.pull(sync_deletions=sync_deletions, dry_run=dry_run)

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
    path: Annotated[
        str | None,
        typer.Argument(help="Path to push (e.g., automations/, helpers/template/)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Push all local items, not just changed ones"),
    ] = False,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Delete remote entities not in local files"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without making changes"),
    ] = False,
) -> None:
    """Push local files to Home Assistant."""
    with logfire.span("ha-sync push", path=path, force=force, dry_run=dry_run):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        if dry_run:
            console.print("[cyan]Dry run mode - no changes will be made[/cyan]")

        asyncio.run(_push(config, path, force, sync_deletions, dry_run))


async def _push(
    config: SyncConfig,
    path: str | None,
    force: bool,
    sync_deletions: bool,
    dry_run: bool,
) -> None:
    """Push entities to Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_path(client, config, path)

        for syncer, _file_filter in syncers_with_filters:
            console.print(f"\n[bold]Pushing {syncer.entity_type}s...[/bold]")
            result = await syncer.push(force=force, sync_deletions=sync_deletions, dry_run=dry_run)

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
    path: Annotated[
        str | None,
        typer.Argument(help="Path to diff (e.g., automations/, helpers/template/)"),
    ] = None,
) -> None:
    """Show differences between local and remote."""
    with logfire.span("ha-sync diff", path=path):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        asyncio.run(_diff(config, path))


async def _diff(config: SyncConfig, path: str | None) -> None:
    """Show differences between local and remote."""
    import difflib

    from ha_sync.utils import dump_yaml

    async with HAClient(config.url, config.token) as client:
        syncers_with_filters = await get_syncers_for_path(client, config, path)
        all_items: list[tuple[str, DiffItem]] = []

        for syncer, file_filter in syncers_with_filters:
            items = await syncer.diff()
            # Filter items if file_filter is set
            if file_filter:
                items = [
                    item
                    for item in items
                    if item.file_path and _matches_filter(item.file_path, file_filter)
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
def watch(
    path: Annotated[
        str | None,
        typer.Argument(help="Path to watch (e.g., automations/, helpers/template/)"),
    ] = None,
) -> None:
    """Watch local files and push changes automatically."""
    with logfire.span("ha-sync watch", path=path):
        config = get_config()
        if not config.url or not config.token:
            console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
            raise typer.Exit(1)

        console.print("[dim]Watching current directory for changes...[/dim]")
        console.print("[dim]Press Ctrl+C to stop[/dim]")

        try:
            asyncio.run(_watch(config, path))
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped watching[/dim]")


async def _watch(config: SyncConfig, path: str | None) -> None:
    """Watch for file changes and push."""
    from watchfiles import awatch

    watch_path = Path(".")

    async for changes in awatch(watch_path):
        console.print(f"\n[dim]Detected {len(changes)} change(s)[/dim]")

        async with HAClient(config.url, config.token) as client:
            syncers_with_filters = await get_syncers_for_path(client, config, path)

            for syncer, _file_filter in syncers_with_filters:
                # Check if any changed files are in this syncer's path
                syncer_path = syncer.local_path
                relevant = any(str(syncer_path) in str(changed_path) for _, changed_path in changes)
                if relevant:
                    console.print(f"[bold]Pushing {syncer.entity_type}s...[/bold]")
                    await syncer.push()


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
def version() -> None:
    """Show version information."""
    console.print(f"ha-sync version {__version__}")


if __name__ == "__main__":
    app()

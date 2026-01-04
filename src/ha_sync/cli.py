"""CLI interface for ha-sync."""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Annotated

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

app = typer.Typer(
    name="ha-sync",
    help="Sync Home Assistant UI config to/from local YAML files.",
    no_args_is_help=True,
)
console = Console()


# Validation patterns
ENTITY_ID_PATTERN = r"^[a-z0-9_]+$"


class EntityType(str, Enum):
    ALL = "all"
    DASHBOARDS = "dashboards"
    AUTOMATIONS = "automations"
    SCRIPTS = "scripts"
    SCENES = "scenes"
    HELPERS = "helpers"  # Traditional input_* helpers
    TEMPLATES = "templates"
    GROUPS = "groups"
    CONFIG_HELPERS = "config_helpers"  # All config entry-based helpers


def get_syncers(
    client: HAClient,
    config: SyncConfig,
    entity_type: EntityType,
    discovered_domains: set[str] | None = None,
) -> list[BaseSyncer]:
    """Get syncers for the specified entity type.

    Args:
        client: HA client
        config: Sync config
        entity_type: Type of entities to sync
        discovered_domains: Pre-discovered config entry helper domains.
            If None and entity_type is ALL or CONFIG_HELPERS, will use
            all known domains.
    """
    # Core syncers (non-config-entry based)
    core_syncers: list[BaseSyncer] = [
        DashboardSyncer(client, config),
        AutomationSyncer(client, config),
        ScriptSyncer(client, config),
        SceneSyncer(client, config),
        HelperSyncer(client, config),
        TemplateSyncer(client, config),
        GroupSyncer(client, config),
    ]

    type_map: dict[EntityType, type[BaseSyncer]] = {
        EntityType.DASHBOARDS: DashboardSyncer,
        EntityType.AUTOMATIONS: AutomationSyncer,
        EntityType.SCRIPTS: ScriptSyncer,
        EntityType.SCENES: SceneSyncer,
        EntityType.HELPERS: HelperSyncer,
        EntityType.TEMPLATES: TemplateSyncer,
        EntityType.GROUPS: GroupSyncer,
    }

    # Handle specific entity types
    if entity_type in type_map:
        return [type_map[entity_type](client, config)]

    # Get config entry helper syncers
    domains = discovered_domains or CONFIG_ENTRY_HELPER_DOMAINS
    config_entry_syncers: list[BaseSyncer] = [
        ConfigEntrySyncer(client, config, domain) for domain in sorted(domains)
    ]

    if entity_type == EntityType.CONFIG_HELPERS:
        return config_entry_syncers

    # ALL: return core syncers + config entry syncers
    return core_syncers + config_entry_syncers


async def get_syncers_with_discovery(
    client: HAClient, config: SyncConfig, entity_type: EntityType
) -> list[BaseSyncer]:
    """Get syncers, auto-discovering config entry helper domains.

    This discovers which helper domains actually have entries in the HA instance,
    avoiding empty syncs for unused helper types.
    """
    if entity_type in (EntityType.ALL, EntityType.CONFIG_HELPERS):
        # Discover which helper domains have entries
        discovered = await discover_helper_domains(client)
        return get_syncers(client, config, entity_type, discovered)
    return get_syncers(client, config, entity_type)


@app.command()
def init() -> None:
    """Initialize ha-sync directory structure and check configuration."""
    config = get_config()

    # Create directory structure
    config.ensure_dirs()
    console.print("[green]Created[/green] directory structure (dashboards/, automations/, etc.)")

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
    entity_type: Annotated[
        EntityType,
        typer.Argument(help="Type of entities to validate"),
    ] = EntityType.ALL,
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
    import re

    from ha_sync.utils import load_yaml

    config = get_config()
    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    templates_to_check: list[tuple[str, str, str]] = []  # (file, path, template)
    files_checked = 0

    # Get changed files if diff_only mode
    changed_files: set[str] = set()
    if check_templates and diff_only and config.url and config.token:
        console.print("[dim]Getting diff to find changed files...[/dim]")
        diff_items = asyncio.run(_get_diff_items(config, entity_type))
        for item in diff_items:
            # Map entity ID to file path
            if item.status in ("added", "modified", "renamed"):
                changed_files.add(item.entity_id)

    def validate_entity_id(entity_id: str, file_path: Path) -> None:
        """Validate entity ID format."""
        if not re.match(ENTITY_ID_PATTERN, entity_id):
            errors.append((str(file_path), f"Invalid entity ID format: '{entity_id}'"))

    def validate_yaml_file(file_path: Path, required_fields: list[str] | None = None) -> None:
        """Validate a single YAML file."""
        nonlocal files_checked
        files_checked += 1

        try:
            data = load_yaml(file_path)
            if data is None:
                warnings.append((str(file_path), "Empty file"))
                return
            if not isinstance(data, dict):
                errors.append((str(file_path), "Root must be a dictionary"))
                return

            # Check required fields
            if required_fields:
                for field in required_fields:
                    if field not in data:
                        errors.append((str(file_path), f"Missing required field: '{field}'"))

            # Validate entity ID if present
            if "id" in data:
                validate_entity_id(data["id"], file_path)

            # Check for Jinja2 templates and validate syntax
            collect_templates(data, file_path)

        except Exception as e:
            errors.append((str(file_path), f"YAML parse error: {e}"))

    def collect_templates(data: dict, file_path: Path, path: str = "") -> None:
        """Recursively collect Jinja2 templates and do basic syntax check."""
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, str) and ("{{" in value or "{%" in value):
                # Basic Jinja2 syntax check
                if value.count("{{") != value.count("}}"):
                    errors.append((str(file_path), f"Unbalanced {{{{ }}}} in {current_path}"))
                elif value.count("{%") != value.count("%}"):
                    errors.append((str(file_path), f"Unbalanced {{% %}} in {current_path}"))
                else:
                    # Collect for remote validation
                    templates_to_check.append((str(file_path), current_path, value))
            elif isinstance(value, dict):
                collect_templates(value, file_path, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        collect_templates(item, file_path, f"{current_path}[{i}]")
                    elif isinstance(item, str) and ("{{" in item or "{%" in item):
                        if item.count("{{") != item.count("}}"):
                            errors.append(
                                (str(file_path), f"Unbalanced {{{{ }}}} in {current_path}[{i}]")
                            )
                        elif item.count("{%") != item.count("%}"):
                            errors.append(
                                (str(file_path), f"Unbalanced {{% %}} in {current_path}[{i}]")
                            )
                        else:
                            location = f"{current_path}[{i}]"
                            templates_to_check.append((str(file_path), location, item))

    console.print("[bold]Validating local files...[/bold]\n")

    # Validate automations
    if entity_type in (EntityType.ALL, EntityType.AUTOMATIONS):
        for yaml_file in config.automations_path.glob("*.yaml"):
            validate_yaml_file(yaml_file, required_fields=["id", "alias"])

    # Validate scripts
    if entity_type in (EntityType.ALL, EntityType.SCRIPTS):
        for yaml_file in config.scripts_path.glob("*.yaml"):
            validate_yaml_file(yaml_file)

    # Validate scenes
    if entity_type in (EntityType.ALL, EntityType.SCENES):
        for yaml_file in config.scenes_path.glob("*.yaml"):
            validate_yaml_file(yaml_file, required_fields=["id"])

    # Validate dashboards
    if entity_type in (EntityType.ALL, EntityType.DASHBOARDS):
        for dashboard_dir in config.dashboards_path.iterdir():
            if dashboard_dir.is_dir():
                for yaml_file in dashboard_dir.glob("*.yaml"):
                    validate_yaml_file(yaml_file)

    # Validate helpers
    if entity_type in (EntityType.ALL, EntityType.HELPERS):
        helper_types = [
            "input_boolean",
            "input_number",
            "input_select",
            "input_text",
            "input_datetime",
        ]
        for helper_type in helper_types:
            helper_path = config.helpers_path / helper_type
            if helper_path.exists():
                for yaml_file in helper_path.glob("*.yaml"):
                    validate_yaml_file(yaml_file, required_fields=["id", "name"])

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
                filtered = [
                    t for t in templates_to_check
                    if any(entity_id in t[0] for entity_id in changed_files)
                ]
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


async def _get_diff_items(config: SyncConfig, entity_type: EntityType) -> list[DiffItem]:
    """Get diff items for the specified entity type."""
    items: list[DiffItem] = []
    async with HAClient(config.url, config.token) as client:
        syncers = await get_syncers_with_discovery(client, config, entity_type)
        for syncer in syncers:
            items.extend(await syncer.diff())
    return items


@app.command()
def pull(
    entity_type: Annotated[
        EntityType,
        typer.Argument(help="Type of entities to pull"),
    ] = EntityType.ALL,
    sync_deletions: Annotated[
        bool,
        typer.Option("--sync-deletions", help="Delete local files not in Home Assistant"),
    ] = False,
) -> None:
    """Pull entities from Home Assistant to local files."""
    config = get_config()
    if not config.url or not config.token:
        console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
        raise typer.Exit(1)

    asyncio.run(_pull(config, entity_type, sync_deletions))


async def _pull(config: SyncConfig, entity_type: EntityType, sync_deletions: bool) -> None:
    """Pull entities from Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        syncers = await get_syncers_with_discovery(client, config, entity_type)

        for syncer in syncers:
            console.print(f"\n[bold]Pulling {syncer.entity_type}s...[/bold]")
            result = await syncer.pull(sync_deletions=sync_deletions)

            if not result.has_changes:
                console.print("  [dim]No changes[/dim]")
            elif result.has_errors:
                console.print(f"  [yellow]Completed with {len(result.errors)} errors[/yellow]")
            else:
                total = len(result.created) + len(result.updated) + len(result.deleted)
                console.print(f"  [green]Synced {total} entities[/green]")


@app.command()
def push(
    entity_type: Annotated[
        EntityType,
        typer.Argument(help="Type of entities to push"),
    ] = EntityType.ALL,
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
    config = get_config()
    if not config.url or not config.token:
        console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
        raise typer.Exit(1)

    if dry_run:
        console.print("[cyan]Dry run mode - no changes will be made[/cyan]")

    asyncio.run(_push(config, entity_type, force, sync_deletions, dry_run))


async def _push(
    config: SyncConfig,
    entity_type: EntityType,
    force: bool,
    sync_deletions: bool,
    dry_run: bool,
) -> None:
    """Push entities to Home Assistant."""
    async with HAClient(config.url, config.token) as client:
        syncers = await get_syncers_with_discovery(client, config, entity_type)

        for syncer in syncers:
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
    entity_type: Annotated[
        EntityType,
        typer.Argument(help="Type of entities to diff"),
    ] = EntityType.ALL,
) -> None:
    """Show differences between local and remote."""
    config = get_config()
    if not config.url or not config.token:
        console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
        raise typer.Exit(1)

    asyncio.run(_diff(config, entity_type))


async def _diff(config: SyncConfig, entity_type: EntityType) -> None:
    """Show differences between local and remote."""
    import difflib

    from ha_sync.utils import dump_yaml

    async with HAClient(config.url, config.token) as client:
        syncers = await get_syncers_with_discovery(client, config, entity_type)
        all_items: list[tuple[str, DiffItem]] = []

        for syncer in syncers:
            items = await syncer.diff()
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

        for entity_type_name, item in sorted(all_items, key=lambda x: (x[1].status, x[0])):
            color = status_colors.get(item.status, "white")

            # Header line
            if item.status == "renamed":
                console.print(
                    f"[{color}]{item.status}[/{color}] "
                    f"[bold]{entity_type_name}[/bold]: {item.entity_id} -> {item.new_id}"
                )
            else:
                console.print(
                    f"[{color}]{item.status}[/{color}] "
                    f"[bold]{entity_type_name}[/bold]: {item.entity_id}"
                )

            # Show diff for modified items
            if item.status == "modified" and item.local and item.remote:
                local_yaml = dump_yaml(item.local).splitlines(keepends=True)
                remote_yaml = dump_yaml(item.remote).splitlines(keepends=True)

                diff_lines = list(difflib.unified_diff(
                    remote_yaml,
                    local_yaml,
                    fromfile="remote",
                    tofile="local",
                    lineterm="",
                ))

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
    entity_type: Annotated[
        EntityType,
        typer.Argument(help="Type of entities to watch"),
    ] = EntityType.ALL,
) -> None:
    """Watch local files and push changes automatically."""
    config = get_config()
    if not config.url or not config.token:
        console.print("[red]Missing HA_URL or HA_TOKEN.[/red] Set them in .env file.")
        raise typer.Exit(1)

    console.print("[dim]Watching current directory for changes...[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        asyncio.run(_watch(config, entity_type))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching[/dim]")


async def _watch(config: SyncConfig, entity_type: EntityType) -> None:
    """Watch for file changes and push."""
    from watchfiles import awatch

    watch_path = Path(".")

    async for changes in awatch(watch_path):
        console.print(f"\n[dim]Detected {len(changes)} change(s)[/dim]")

        async with HAClient(config.url, config.token) as client:
            syncers = await get_syncers_with_discovery(client, config, entity_type)

            for syncer in syncers:
                # Check if any changed files are in this syncer's path
                syncer_path = syncer.local_path
                relevant = any(str(syncer_path) in str(path) for _, path in changes)
                if relevant:
                    console.print(f"[bold]Pushing {syncer.entity_type}s...[/bold]")
                    await syncer.push()


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"ha-sync version {__version__}")


if __name__ == "__main__":
    app()

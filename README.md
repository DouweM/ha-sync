# ha-sync

Sync Home Assistant UI configuration to local YAML files and back.

Manage your dashboards, automations, scripts, scenes, and helpers as code. Pull from Home Assistant, edit locally with your favorite editor or agent and push changes back.

## Features

- **Bidirectional sync**: Pull from Home Assistant, push local changes back, or use `sync` for smart merging
- **Git-aware**: Auto-stashes local changes before pull, restores after - safe to run anytime
- **Diff view**: See exactly what changed between local and remote before syncing
- **Validation**: Check YAML syntax and Jinja2 templates before pushing
- **Multiple entity types**: Dashboards, automations, scripts, scenes, and all helper types

### Supported Entity Types

| Type | Description |
|------|-------------|
| Dashboards | Lovelace dashboards (split into view files) |
| Automations | Automation rules |
| Scripts | Script sequences |
| Scenes | Scene configurations |
| Helpers | Input helpers (boolean, number, select, text, datetime, button) |
| Helpers | Timer, counter, schedule helpers |
| Helpers | Template sensors, binary sensors, switches |
| Helpers | Group sensors, binary sensors, lights |
| Helpers | Utility meters, integrations, thresholds, time of day |

## Installation

```bash
# Install with uv (recommended)
uv tool install ha-sync

# Or with pip
pip install ha-sync
```

### From source

```bash
git clone https://github.com/DouweM/ha-sync.git
cd ha-sync
uv sync
```

## Configuration

Create a `.env` file in your sync directory:

```bash
# Home Assistant URL
HA_URL=http://homeassistant.local:8123

# Long-lived access token from Home Assistant
# Create at: Settings > User > Long-lived access tokens
HA_TOKEN=your_token_here
```

Or run the setup script:

```bash
./setup-env.sh
```

## Quick Start

```bash
# Initialize directory structure
ha-sync init

# Check connection
ha-sync status

# Pull everything from Home Assistant
ha-sync pull

# Make changes to your YAML files...

# See what changed
ha-sync diff

# Push changes back
ha-sync push
```

## Usage

### sync (Recommended)

Bidirectional sync: pulls remote changes, merges with local changes, pushes the result.

```bash
# Sync everything
ha-sync sync

# Sync specific paths
ha-sync sync automations/
ha-sync sync automations/ scripts/
```

The sync command:
- Shows remote and local changes before doing anything
- In git repos, stashes local changes, pulls, then restores
- Detects merge conflicts and stops for manual resolution
- Only asks for confirmation when pushing local changes

### pull

Pull entities from Home Assistant to local YAML files.

```bash
ha-sync pull                      # Pull all
ha-sync pull automations/         # Pull specific entity types
ha-sync pull automations/turn-on-light.yaml # Pull a specific entity

ha-sync pull --sync-deletions     # Delete local files not in HA
ha-sync pull --dry-run            # Preview without changes
```

### push

Push local YAML files to Home Assistant.

```bash
ha-sync push                      # Push changed files
ha-sync push automations/         # Push specific entity types
ha-sync push automations/turn-on-light.yaml # Push a specific entity
ha-sync push --all                # Push all files, not just changed

ha-sync push --sync-deletions     # Delete remote entities not locally
ha-sync push --dry-run            # Preview without changes
```

Always shows a preview and asks for confirmation.

### diff

Show differences between local and remote.

```bash
ha-sync diff                      # Diff all
ha-sync diff automations/         # Diff specific entity types
ha-sync diff automations/turn-on-light.yaml # Diff a specific entity
```

### validate

Validate local YAML files.

```bash
ha-sync validate                  # Basic YAML validation
ha-sync validate automations/         # Validate specific entity types
ha-sync validate automations/turn-on-light.yaml # Validate a specific entity

ha-sync validate --check-templates    # Also validate Jinja2 templates against HA
ha-sync validate --check-config   # Check HA config validity
```

### Other Commands

```bash
ha-sync template "{{ states('sensor.temperature') }}"  # Test a template
ha-sync search light              # Search for entities
ha-sync state light.living_room   # Get entity state
ha-sync status                    # Show connection status
```

## Directory Structure

After `ha-sync init`, your directory looks like:

```
.
├── automations/              # Automation YAML files
├── scripts/                  # Script YAML files
├── scenes/                   # Scene YAML files
├── dashboards/               # Dashboard directories
│   └── <dashboard-name>/     # Each dashboard gets a directory
│       ├── _meta.yaml        # Dashboard metadata
│       └── 00_<view>.yaml    # View files (prefixed for ordering)
└── helpers/                  # All helper entities
    ├── input_boolean/        # Input boolean helpers
    ├── input_number/         # Input number helpers
    ├── input_select/         # Input select helpers
    ├── input_text/           # Input text helpers
    ├── input_datetime/       # Input datetime helpers
    ├── input_button/         # Input button helpers
    ├── timer/                # Timer helpers
    ├── counter/              # Counter helpers
    ├── schedule/             # Schedule helpers
    ├── template/             # Template helpers
    │   ├── sensor/           # Template sensors
    │   ├── binary_sensor/    # Template binary sensors
    │   └── switch/           # Template switches
    ├── group/                # Group helpers
    │   ├── sensor/           # Group sensors
    │   ├── binary_sensor/    # Group binary sensors
    │   └── light/            # Group lights
    ├── utility_meter/        # Utility meter helpers
    ├── integration/          # Integration (Riemann sum) helpers
    ├── threshold/            # Threshold helpers
    └── tod/                  # Time of Day helpers
```

## Workflow Tips

### Git Integration

ha-sync works great with git. A typical workflow:

```bash
# Start fresh
git checkout main
git pull

# Get latest from Home Assistant
ha-sync pull
git add -A && git commit -m "Pull from HA"

# Make your changes...

# Review and push
ha-sync diff
ha-sync push

# Commit the final state
git add -A && git commit -m "Update automations"
```

### Using sync for Day-to-Day

The `sync` command handles the common case where you've made changes both locally and in the HA UI:

```bash
ha-sync sync
```

This pulls remote changes first, then pushes your local changes. If the same file was modified in both places, git's stash mechanism will detect the conflict.

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Type checking
uv run pyright

# Linting
uv run ruff check src/
uv run ruff format src/
```

## License

MIT - see [LICENSE](LICENSE) for details.

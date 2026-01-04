# ha-sync

Sync Home Assistant UI configuration (dashboards, automations, helpers, etc.) to/from local YAML files.

## Features

- **Bidirectional sync**: Pull from Home Assistant to local files, or push local changes back
- **Multiple entity types**: Dashboards, automations, scripts, scenes, helpers, templates, groups
- **Config entry helpers**: Utility meters, integrations, thresholds, generic thermostats, and more
- **Diff view**: See exactly what changed between local and remote
- **Validation**: Check YAML syntax and Jinja2 templates before pushing
- **Watch mode**: Automatically push changes when files are modified

## Installation

```bash
# Clone the repository
git clone https://github.com/DouweM/ha-ui-yaml-sync.git
cd ha-ui-yaml-sync

# Install dependencies with uv
uv sync
```

## Configuration

Create a `.env` file in the project directory:

```bash
# Home Assistant URL
HA_URL=http://homeassistant.local:8123

# Long-lived access token from Home Assistant
# Create at: Settings > User > Long-lived access tokens
HA_TOKEN=your_token_here
```

## Usage

### Initialize

Create the directory structure and verify configuration:

```bash
uv run ha-sync init
```

### Check Status

View connection status and configuration:

```bash
uv run ha-sync status
```

### Pull

Pull entities from Home Assistant to local YAML files:

```bash
# Pull all entity types
uv run ha-sync pull

# Pull specific type
uv run ha-sync pull automations
uv run ha-sync pull dashboards
uv run ha-sync pull helpers

# Delete local files not in Home Assistant
uv run ha-sync pull --sync-deletions
```

### Push

Push local YAML files to Home Assistant:

```bash
# Push all entity types
uv run ha-sync push

# Push specific type
uv run ha-sync push automations

# Dry run (show what would change)
uv run ha-sync push --dry-run

# Force push all items (not just changed)
uv run ha-sync push --force

# Delete remote entities not in local files
uv run ha-sync push --sync-deletions
```

### Diff

Show differences between local and remote:

```bash
uv run ha-sync diff
uv run ha-sync diff automations
```

### Validate

Validate local YAML files:

```bash
# Basic validation
uv run ha-sync validate

# Also validate Jinja2 templates against HA
uv run ha-sync validate --check-templates

# Check HA config validity
uv run ha-sync validate --check-config
```

### Watch

Watch for file changes and automatically push:

```bash
uv run ha-sync watch
```

## Entity Types

| Type | Description |
|------|-------------|
| `all` | All entity types (default) |
| `dashboards` | Lovelace dashboards |
| `automations` | Automation rules |
| `scripts` | Script sequences |
| `scenes` | Scene configurations |
| `helpers` | Input helpers (boolean, number, select, text, datetime, button, timer, counter, schedule) |
| `templates` | Template sensors, binary sensors, switches |
| `groups` | Entity groups (binary sensors, sensors, lights, etc.) |
| `config_helpers` | Config entry-based helpers (utility meters, integrations, thresholds, etc.) |

## Directory Structure

After running `ha-sync init`, the following directory structure is created:

```
.
├── automations/              # Automation YAML files
├── scripts/                  # Script YAML files
├── scenes/                   # Scene YAML files
├── dashboards/               # Dashboard directories
│   └── <dashboard-name>/     # Each dashboard gets a directory
│       ├── _meta.yaml        # Dashboard metadata (title, icon, etc.)
│       └── 00_<view-name>.yaml # View files (prefixed for ordering)
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

MIT

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom component (HACS integration) for ConnectLife smart appliances. Polls the ConnectLife cloud API every 60 seconds and exposes appliances as HA entities across 8 platforms: binary_sensor, climate, humidifier, number, sensor, select, switch, water_heater.

## Commands

```bash
# Install dependencies (uses uv, not pip)
uv sync

# Validate data dictionary YAML files against JSON schema
uv run python -m scripts.validate_mappings

# Regenerate strings.json from data dictionaries
uv run python -m scripts.gen_strings

# Run API library tests (in the connectlife submodule)
python -m pytest connectlife/connectlife/tests/

# Run the test server for local development
python -m connectlife.test_server -d dumps  # from the connectlife/ submodule directory

# Type check
uv run pyright

# CI runs hassfest only (no linter/formatter/type checker configured)
```

## Architecture

### Data Flow

1. **Config flow** (`config_flow.py`) — user provides credentials, validated via `ConnectLifeApi.authenticate()`
2. **Entry setup** (`__init__.py`) — creates `ConnectLifeApi`, calls `login()` (4-step OAuth2 via Gigya), initializes `ConnectLifeCoordinator`
3. **Coordinator** (`coordinator.py`) — subclass of `DataUpdateCoordinator`, polls `api.get_appliances()` every 60s, returns `dict[str, ConnectLifeAppliance]` keyed by device_id
4. **Platform setup** — each platform iterates appliances, loads data dictionaries, creates entities for properties that match the platform
5. **Entity updates** — coordinator notifies entities via `_handle_coordinator_update()` → `update_state()` → `async_write_ha_state()`
6. **Commands** — entity actions call `async_update_device()` on base entity → `coordinator.async_update_device()` → `api.update_appliance()`

### Data Dictionary System (the core abstraction)

YAML files in `custom_components/connectlife/data_dictionaries/` define how API properties map to HA entities. This is the most important part of the codebase.

- **Default type mapping**: `{device_type_code}.yaml` (e.g., `009.yaml` for air conditioners)
- **Feature override**: `{device_type_code}-{device_feature_code}.yaml` (e.g., `009-105.yaml`)
- Feature files overlay the default — properties in the feature file replace same-named properties from the type file
- Unmapped properties become hidden sensor entities with `state_class: measurement`
- Parsed by `Dictionaries` class (`dictionaries.py`) with a class-level cache

Each property maps to exactly one platform. Platform type is determined by `hasattr()` on the `Property` object — only the attribute for the assigned platform is set during `__init__`.

### Entity Creation Pattern

All per-property platforms (sensor, binary_sensor, number, select, switch) follow the same pattern:

```python
for appliance in coordinator.data.values():
    dictionary = Dictionaries.get_dictionary(appliance)
    for s in appliance.status_list:
        if is_entity(Platform.XXX, dictionary.properties[s], appliance.status_list[s]):
            # create entity
```

Device-level platforms (climate, humidifier, water_heater) create one entity per appliance when any property has that platform type.

### Key Design Decisions

- **Unique ID format**: `{device_id}-{property_name}` (or `{device_id}-climate` etc. for device-level entities)
- **Beep disable**: When configured per-device in options, `t_beep: 0` is injected into every command (`entity.py:async_update_device`)
- **Command vs property**: Select and switch support separate `command` property names with optional `adjust` offset for devices where the write property differs from the status property
- **`is_entity()` utility** (`utils.py`): gates entity creation — checks platform match, not disabled, and not in unavailable state

### connectlife Submodule

Git submodule at `connectlife/` — the API library published to PyPI as `connectlife`. Contains `ConnectLifeApi` (OAuth2 client), `ConnectLifeAppliance` (data model), and a test server (`dumps/test_server.py`).

## Adding New Device Mappings

1. Generate skeleton: `python -m connectlife.dump --username <user> --password <pass> --format dd`
2. Create/edit YAML in `data_dictionaries/` (see `data_dictionaries/README.md` for full schema docs)
3. Validate: `uv run python -m scripts.validate_mappings`
4. Generate strings: `uv run python -m scripts.gen_strings`
5. Translation keys must be lowercase; YAML booleans (`true`, `false`, `on`, `off`, `yes`, `no`) must be quoted in option values
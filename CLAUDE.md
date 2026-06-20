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

# Regenerate strings.json and en.json from data dictionaries, sort all translations
uv run python -m scripts.gen_strings

# Sort all translation files (without regenerating strings)
uv run python -m scripts.sort_translations

# Run the test server for local development
uv run python -m connectlife.test_server -d <dumps_dir>

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

For the YAML schema and authoring guidance, see:
- `custom_components/connectlife/data_dictionaries/README.md` — user-facing field docs (all types, `command`/`adjust`, presets, units, translations)
- `custom_components/connectlife/data_dictionaries/properties-schema.json` — authoritative JSON schema

Code-level details not in those files:
- Parsed by `Dictionaries` class (`dictionaries.py`) with a class-level cache.
- Each property maps to exactly one platform. Platform type is determined by `hasattr()` on the `Property` object — only the attribute for the assigned platform is set during `__init__`.

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

### Statistics (daily energy/water) sensors

A second coordinator, `ConnectLifeStatisticsCoordinator` (`coordinator.py`), runs alongside the main
one and powers the daily energy/water consumption sensors. These are **not** derived from
`status_list`; they come from separate ConnectLife cloud statistics endpoints.

- **Opt-in via the data dictionary**: a top-level `statistics` block (`source` +
  per-sensor boolean flags `daily_energy_kwh` / `daily_water_consumption`) selects the endpoint
  and which sensors to create. Parsed in `dictionaries.py` onto `Dictionary.statistics_source` /
  `Dictionary.statistics_sensors`. Both flags default to off — explicit `true` is required.
- **Registry** (`statistics_sources.py`): maps each `source` (`air_duct_energy` for air
  conditioners, `energy_consumption_curve` for other appliances) to its endpoint fetch and its
  `StatisticsSensorDef`s. `enabled_sensors(source, flags)` returns only the explicitly-enabled
  sensor defs.
- **Lifecycle**: `__init__.py` creates the energy coordinator only if at least one appliance has
  an enabled statistics sensor (otherwise it would poll nothing); stored under
  `hass.data[DOMAIN][f"{entry_id}_statistics"]`. It polls every `STATISTICS_UPDATE_INTERVAL` (10 minutes),
  storing `dict[device_id, EnergyResult | None]`. On `LifeConnectAuthError` it stops the cycle
  (no per-appliance re-login storm).
- **Sensors** (`ConnectLifeStatisticsSensor` in `sensor.py`): generic, configured from a
  `StatisticsSensorDef`; unique ID `{device_id}-{sensor.key}`. Unlike status entities they are
  **not** gated on offline state — cloud-side statistics remain available while the device is offline.

### Key Design Decisions

- **Unique ID format**: `{device_id}-{property_name}` (or `{device_id}-climate` etc. for device-level entities)
- **Beep disable**: When configured per-device in options, `t_beep: 0` is injected into every command (`entity.py:async_update_device`)
- **`is_entity()` utility** (`utils.py`): gates entity creation — checks platform match, not disabled, and not in unavailable state

### connectlife API Library

The API library is published to PyPI as `connectlife` and developed in a separate repo: https://github.com/oyvindwe/connectlife. Contains `ConnectLifeApi` (OAuth2 client), `ConnectLifeAppliance` (data model), and a test server.

## Adding New Device Mappings

See `custom_components/connectlife/data_dictionaries/README.md` for the authoring workflow (skeleton generation, tips, translation strings). After editing YAML, run `uv run python -m scripts.validate_mappings` and `uv run python -m scripts.gen_strings`.
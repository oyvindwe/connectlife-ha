# AGENTS.md

Guidance for AI coding agents (and human contributors) working in this
repository. Claude Code loads this file via `CLAUDE.md`, which imports it.

## Project Overview

Home Assistant custom component (HACS integration) for ConnectLife smart appliances. Gets status pushes from the ConnectLife cloud over a WebSocket (polling every 60 seconds when push is off or disconnected) and exposes appliances as HA entities across 8 platforms: binary_sensor, climate, humidifier, number, sensor, select, switch, water_heater.

## Commands

```bash
# Install dependencies (uses uv, not pip)
uv sync

# Validate mapping YAML files against JSON schema
uv run python -m scripts.validate_mappings

# Regenerate strings.json and en.json from the mappings, sort all translations
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
2. **Entry setup** (`__init__.py`) — creates `ConnectLifeApi`, calls `login()` (4-step OAuth2 via Gigya), initializes `ConnectLifeCoordinator`, and — only if at least one appliance enables a statistics sensor — also a `ConnectLifeStatisticsCoordinator` (stored under `hass.data[DOMAIN][f"{entry_id}_statistics"]`)
3. **Coordinators** (`coordinator.py`) — two `DataUpdateCoordinator` subclasses run side by side:
   - `ConnectLifeCoordinator` — the main coordinator; polls `api.get_appliances()` every 60s (every 15 min while push updates are connected; see `push.py`), returns `dict[str, ConnectLifeAppliance]` keyed by device_id. Drives all status-derived entities.
   - `ConnectLifeStatisticsCoordinator` — polls the cloud statistics endpoints every `STATISTICS_UPDATE_INTERVAL` (10 min) for the daily energy/water sensors; returns `dict[device_id, EnergyResult | None]`. See [Statistics](#statistics-daily-energywater-sensors) below.
4. **Platform setup** — each platform iterates appliances, loads device mappings, creates entities for properties that match the platform
5. **Entity updates** — coordinator notifies entities via `_handle_coordinator_update()` → `update_state()` → `async_write_ha_state()`
6. **Commands** — entity actions call `async_update_device()` on base entity → `coordinator.async_update_device()` → `api.update_appliance()`

### Device Mapping System (the core abstraction)

YAML files in `custom_components/connectlife/mappings/` define how API properties map to HA entities. This is the most important part of the codebase.

For the YAML schema and authoring guidance, see:
- `custom_components/connectlife/mappings/README.md` — user-facing field docs (all types, `command`/`adjust`, presets, units, translations)
- `custom_components/connectlife/mappings/properties-schema.json` — authoritative JSON schema

Code-level details not in those files:
- Parsed by the `DeviceMappings` class (`device_mappings.py`) with a class-level cache.
- Each property maps to exactly one platform. Platform type is determined by `hasattr()` on the `Property` object — only the attribute for the assigned platform is set during `__init__`.

### Entity Creation Pattern

All per-property platforms (sensor, binary_sensor, number, select, switch) follow the same pattern:

```python
for appliance in coordinator.data.values():
    mapping = DeviceMappings.get_mapping(appliance)
    for s in appliance.status_list:
        if has_platform(Platform.XXX, mapping.properties[s]):
            # create entity
```

Device-level platforms (climate, humidifier, water_heater) create one entity per appliance when any property has that platform type.

### Statistics (daily energy/water) sensors

A second coordinator, `ConnectLifeStatisticsCoordinator` (`coordinator.py`), runs alongside the main
one and powers the daily energy/water consumption sensors. These are **not** derived from
`status_list`; they come from separate ConnectLife cloud statistics endpoints.

- **Opt-in via the device mapping**: a top-level `statistics` block (`source` +
  per-sensor boolean flags `daily_energy_kwh` / `daily_water_consumption`) selects the endpoint
  and which sensors to create. Parsed in `device_mappings.py` onto `DeviceMapping.statistics_source` /
  `DeviceMapping.statistics_sensors`. Both flags default to off — explicit `true` is required.
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
- **`has_platform()` utility** (`utils.py`): gates entity creation — the property has the platform's block (`hasattr`) and is not `disable`d. (The per-property `unavailable` sentinel is applied at runtime via the entity's `available` / `_is_value_unavailable()`, not at creation time.)

### connectlife API Library

The API library is published to PyPI as `connectlife` and developed in a separate repo: https://github.com/oyvindwe/connectlife. Contains `ConnectLifeApi` (OAuth2 client), `ConnectLifeAppliance` (data model), and a test server.

## Adding New Device Mappings

See `custom_components/connectlife/mappings/README.md` for the authoring workflow (skeleton generation, tips, translation strings). After editing YAML, run `uv run python -m scripts.validate_mappings` and `uv run python -m scripts.gen_strings`.

Mappings are data, validated by `validate_mappings` (schema) and PR review — don't add unit tests asserting a specific mapping's *content*.

### Reviewing mappings

- Check every new or changed mapping against the ConnectLife property list of its feature code: read-only (`R`)
  properties must not get a writable platform (switch, select, number, writable climate target) unless a separate
  `command` property is written (look for one in the list: e.g. `SET_…` on refrigerators, `…_setting` next to
  `…_setting_status` on dishwashers), and option values and limits should match `propertyValueList`, `lowerLimit`
  and `upperLimit`. `uv run python -m scripts.check_property_list <diagnostics.json>` reports both
  (`--feature <type>-<feature>` for a list from `connectlife.dump`).
- The list is in the diagnostics (`property_list`). If no diagnostics are attached, or they're from before 0.49.0,
  fetch it: it's keyed by type and feature code only, so any account works
  (`python -m connectlife.dump --query property-list --device-type-code <t> --device-feature-code <f>`).
- When the list and observed device data disagree (e.g. a value the device reports that isn't in the list), trust the
  device and note it in a comment in the mapping.
- The lists aren't perfect: they can have typos, miss values the device reports, and use inconsistent formats
  (full-width punctuation, notes in Chinese, e.g. that values from 5 up are a drying time). Check each finding
  against the device instead of following the list blindly.

## Versioning

Classify changes (major, minor, patch; what counts as breaking) per
[Versioning and breaking changes](CONTRIBUTING.md#versioning-and-breaking-changes).
Branches, betas and release branches: see [Branches and releases](CONTRIBUTING.md#branches-and-releases).

## Git and pull requests

- **Don't amend, drop, or squash commits on an open PR.** Once a branch has an
  open pull request, only add new commits — never rewrite its history with
  `git commit --amend`, `git rebase`, `git reset`, or a force-push. Rewriting a
  pushed PR branch loses review context and can leave CI running against a stale
  merge ref.
- Don't `git push` until the user explicitly asks for it.

## Issues

- When a comment asks the reporter for something (diagnostics, a test, an answer), add the
  `waiting for reporter` label. Don't add it when we owe the next step.
- When a comment tells the reporter a fix is released and asks them to confirm it, add
  `awaiting confirmation` instead.
- `.github/workflows/stale.yaml` pings issues with either label after 4 weeks without activity
  (and adds `stale`), and closes them 4 weeks later: `waiting for reporter` as not planned,
  `awaiting confirmation` as completed. `.github/workflows/reporter-replied.yaml` removes the
  labels when the issue's author comments.
- Close other issues only when a merged fix covers them.

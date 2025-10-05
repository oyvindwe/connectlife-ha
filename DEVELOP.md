# Developing `connectlife-ha`

## Prerequisites

1. `uv`: https://docs.astral.sh/uv/getting-started/installation/
2. Home Assistant development environment: https://developers.home-assistant.io/docs/development_environment

Install the custom component in your Home Assistant development environment
(assuming your configuration directory is `config`):
```bash
home_assistant_repo=<local home-assistant repo>
connectlife_ha_repo=<local connectlife-ha repo>
cd ${home_assistant_repo}
mkdir -p config/custom_components
cd config/custom_components
ln -s ${connectlife_ha_repo}>/custom_componnents/connectlife .
```

Install dev dependencies (in `connectlife-ha` repo):
```bash
uv sync
```

## Generate `strings.json` 

This will add strings for new properties.

```bash
uv run python -m scripts.gen_strings
```

## Validate mapping files

```bash
uv run python -m scripts.validate_mappings
```

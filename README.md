# ConnectLife

ConnectLife integration for Home Assistant

## Installation

You can install using HACS or download.

### HACS
If you have HACS installed, add this repository (`oyvindwe/connectlife-ha`) as a custom repository of type "Integration".

See https://hacs.xyz/docs/faq/custom_repositories/ 

### Download

Download the `connectlife` directory and place in your `<config>/custom_components/`.

After installing, you need to restart Home Assistant.

Finally, add "ConnectLife" as an integration in the UI, and provide the username and password for your ConnectLife account.

You device and all their status values should show up.

## Supported devices

Any unknown device will show up as sensors with names based on their properties. As there are a lot of exposed
sensors, all unknown sensors are hidden by default. Access the device or entity list to view sensors and change
visibility.

### Known devices

| Device name  | Device type     | Device type code | Device feature code | Data dictionary                                                                           |
|--------------|-----------------|------------------|---------------------|-------------------------------------------------------------------------------------------|
|              | Dehumidifier    | 007              | 400                 | [Completed](custom_components/connectlife/data_dictionaries/007-400.yaml)                 |
|              | Air conditioner | 009              | 109                 | [In progress](custom_components/connectlife/data_dictionaries/009-109.yaml)               |
| W-DW50/60-22 | Dishwasher      | 015              | 000                 | [Most properties completed](custom_components/connectlife/data_dictionaries/015-000.yaml) |

Please, please, please contribute PRs with [data dictionaries](custom_components/connectlife/data_dictionaries) for your devices!

## Issues

### Climate entities

Please ignore the following warning in the log:
```
Entity None (<class 'custom_components.connectlife.climate.ConnectLifeClimate'>) implements HVACMode(s): auto, off and therefore implicitly supports the turn_on/turn_off methods without setting the proper ClimateEntityFeature. Please report it to the author of the 'connectlife' custom integration
```

Missing features:
- Preset modes (e.g. eco)
- Setting HVAC mode except to off/auto
- Min/max temperatures

### Experimental service to set property values (sensors only)

Entity service `connectlife.set_value` can be used to set values. Use with caution, as there is **no** validation
if property is writeable, or that the value is legal to set.

1. The service can be accessed from Developer tools -> Services in HomeAssistant UI.
2. Search for service name "ConnectLife: Set value"
3. As target, select entity, and enter a ConnectLife sensor entity id.

### Login

Note that users at least in Russia and China can't log in using this integration. See discussion in
https://github.com/bilan/connectlife-api-connector/issues/25

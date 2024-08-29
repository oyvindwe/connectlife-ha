# ConnectLife

ConnectLife integration for Home Assistant

[![BuyMeCoffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/oyvindwev)

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

## Supported ConncetLife devices

Any unknown device will show up as sensors with names based on their properties. As there are a lot of exposed
sensors, all unknown sensors are hidden by default. Access the device or entity list to view sensors and change
visibility.

### Known devices

| Device name  | Device type     | Device type code | Device feature code | Data dictionary                                                                           |
|--------------|-----------------|------------------|---------------------|-------------------------------------------------------------------------------------------|
| AP10TW1RLR-N | Air conditioner | 006              | 200                 | [Completed](custom_components/connectlife/data_dictionaries/006-200.yaml)                 |
|              | Air conditioner | 006              | 201                 | [Completed](custom_components/connectlife/data_dictionaries/006-201.yaml)                 |
|              | Dehumidifier    | 007              | 400                 | [Completed](custom_components/connectlife/data_dictionaries/007-400.yaml)                 |
|              | Dehumidifier    | 007              | 406                 | [Completed](custom_components/connectlife/data_dictionaries/007-406.yaml)                 |
|              | Air conditioner | 009              | 100                 | [Under testing](custom_components/connectlife/data_dictionaries/009-100.yaml)             |
|              | Air conditioner | 009              | 104                 | [Completed](custom_components/connectlife/data_dictionaries/009-104.yaml)                 |
|              | Air conditioner | 009              | 106                 | [Completed](custom_components/connectlife/data_dictionaries/009-106.yaml)                 |
|              | Air conditioner | 009              | 109                 | [Completed](custom_components/connectlife/data_dictionaries/009-109.yaml)                 |
|              | Air conditioner | 009              | 117                 | [Under testing](custom_components/connectlife/data_dictionaries/009-117.yaml)             |
|              | Air conditioner | 009              | 128                 | [Completed](custom_components/connectlife/data_dictionaries/009-128.yaml)                 |
|              | Air conditioner | 009              | 129                 | [Completed](custom_components/connectlife/data_dictionaries/009-129.yaml)                 |
| W-DW50/60-22 | Dishwasher      | 015              | 000                 | [Most properties completed](custom_components/connectlife/data_dictionaries/015-000.yaml) |
|              | Heat pump       | 016              | 502                 | [Completed](custom_components/connectlife/data_dictionaries/016-502.yaml)                 |
|              | Induction hob   | 020              | 63c45b513e1a4bf7    | [Completed](custom_components/connectlife/data_dictionaries/020-63c45b513e1a4bf7.yaml)    |
|              | Refrigerator    | 026              | 1b0610z0049j        | [Completed](custom_components/connectlife/data_dictionaries/026-1b0610z0049j.yaml)        |
| DPNA83W      | Tumble dryer    | 032              | 000                 | [Completed](custom_components/connectlife/data_dictionaries/032-000.yaml)                 |

Please, please, please contribute PRs with [data dictionaries](custom_components/connectlife/data_dictionaries) for your devices!

## Supported Home Assistant entities

ConnectLife properties can be mapped to any of these entity types:

- [Binary sensor](https://developers.home-assistant.io/docs/core/entity/binary-sensor)
- [Climate](https://developers.home-assistant.io/docs/core/entity/climate)
- [Humidifier](https://developers.home-assistant.io/docs/core/entity/humidifier)
- [Number](https://developers.home-assistant.io/docs/core/entity/number)
- [Select](https://developers.home-assistant.io/docs/core/entity/select)
- [Sensor](https://developers.home-assistant.io/docs/core/entity/sensor)
- [Switch](https://developers.home-assistant.io/docs/core/entity/switch)
- [Water heater](https://developers.home-assistant.io/docs/core/entity/water-heater)

## Disable beeping

Some devices will beep on every configuration change. To disable this, go to the
[ConnectLife integration](https://my.home-assistant.io/redirect/integration/?domain=connectlife)
and click "Configure" → "Configure a device" and select the device you want to disable beeping for. 

## Service to set property values on sensors

Entity service `connectlife.set_value` can be used to set values. Use with caution, as there is **no** validation
if property is writeable or that the value is legal to set.

1. The service can be accessed from [Developer tools - Services](https://my.home-assistant.io/redirect/developer_services/).
2. Search for service name "ConnectLife: Set value"
3. Select entity as target.
4. Enter value
5. Call service.

It is possible to guard against `set_value` by setting `readonly: true` in the data dictionary on the sensor, e.g.
```yaml
  - property: f_status 
    sensor:
      read_only: true
```

## Issues

### Climate entities

Please ignore the following warning in the log:
```
Entity None (<class 'custom_components.connectlife.climate.ConnectLifeClimate'>) implements HVACMode(s): auto, off and therefore implicitly supports the turn_on/turn_off methods without setting the proper ClimateEntityFeature. Please report it to the author of the 'connectlife' custom integration
```

Missing features:
- Setting target_temperature_high/target_temperature_low

### Heat pump entities
 
Missing features:
- Setting state except to off/one defined state
- Setting target_temperature_high/target_temperature_low

### Login

Note that users at least in Russia and China can't log in using this integration. See discussion in
https://github.com/bilan/connectlife-api-connector/issues/25

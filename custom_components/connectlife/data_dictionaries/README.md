# Data dictionaries

Data dictionaries for known appliances are located in this directory. Appliances without data dictionary will be still
be loaded, but with a warning in the log. Their properties will all be mapped to [sensor](#type-sensor) entities,
with `hidden` set to `true` and `state_class` set to `measurement` (to enable
[long-term statistics](https://developers.home-assistant.io/docs/core/entity/sensor/#long-term-statistics)).

## Create your own mapping file

To map you device, create a file with the name `<deviceTypeCode>-<deviceFeatureCode>.yaml` in this directory. When done,
or if you need help with the mapping, please open a PR on GitHub with the file!

The file contains two top level items:
- `device_type`: string
- `properties`: list of [`Property`](#property)

To make a property visible by default, just add the property to the list. Note that properties you do not map are still
mapped to [sensor](#type-sensor) entities, but _without_ `state_class`. This is done as some devices supports a lot
of properties, which will take up processing time and storage. Makes sure to include all properties of interest when
mapping a device!

Each property is mapped to _one_ entity or _one_ target property.

If you change the type of mapping, the old entity or state attribute will change to unavailable in Home Assistant.

If you change unit or state class for sensors, you will need to fix the history in Home Assistant -> Developer Tools
-> Statistics.

You need to restart Home Assistant to load mapping changes.

### Mapping tips and tricks:

- Inspect the existing mappings files in this directory.
- Change settings in the ConnectLife app while monitoring value changes in Home Assistant. Take a note of which
  property is changes, what the value is, and what the button or action is named in the ConnectLife app.
- Be aware that `true`, `false`, `yes`, `no`, `on`, and `off` are all interpreted as boolean values in YAML,
  and must be quoted (e.g. `"off"`) to be interpreted as a string, e.g. in option lists. Note that some options
  expects boolean (unquoted) values.
- Validate your mapping file with the [JSON schema](properties-schema.json).
- Remember to add translation strings.

## Property

| Item            | Type                               | Description                                                                                                                                    |
|-----------------|------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `property`      | string                             | Name of status/property.                                                                                                                       |
| `hide`          | `true`, `false`                    | If Home Assistant should initially hide the sensor entity for this property. Defaults to `false`, but it set to `true` for unknown properties. |
| `icon`          | `mdi:eye`, etc.                    | Icon to use for the entity.                                                                                                                    |
| `binary_sensor` | [BinarySensor](#type-binarysensor) | Create a binary sensor of the property.                                                                                                        |
| `climate`       | [Climate](#type-climate)           | Map the property to a climate entity for the device.                                                                                           |
| `humidifier`    | [Humidifier](#type-humidifier)     | Map the property to a humidifier entity for the device.                                                                                        |
| `number`        | [Number](#type-number)             | Create a number entity of the property.                                                                                                        |
| `select`        | [Select](#type-select)             | Create a selector of the property.                                                                                                             |
| `sensor`        | [Sensor](#type-sensor)             | Create a sensor of the property. This is the default.                                                                                          |
| `switch`        | [Switch](#type-switch)             | Create a switch of the property.                                                                                                               |
| `water_heater`  | [WaterHeater](#type-waterheater)   | Map the property to a water heater entity for the device.                                                                                      |

If an entity mapping is not given, the property is mapped to a sensor entity.

It is not necessary to include items with empty values. A [JSON schema](properties-schema.json) is provided so data dictionaries can be
validated.

## Type `BinarySensor`

Domain `binary_sensor` can be used for read only properties where `0` is not available, `1` is off, and `2` is on. Both
`0`and `1` is mapped to off.

| Item           | Type                     | Description                                                                                                                                                           |
|----------------|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `device_class` | `power`, `problem`, etc. | For domain `binary_sensor`, name of any [BinarySensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/binary-sensor#available-device-classes). | 


## Type `Climate`:

Domain `climate` can be used to map the property to a target property in a climate entity. If at least one property has
type `climate`, a climate entity is created for the appliance.

| Item            | Type                                               | Description                                                                                                                                                                                                                                                                                                       |
|-----------------|----------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `target`        | string                                             | Any  of these [climate entity](https://developers.home-assistant.io/docs/core/entity/climate#properties) attributes: `current_humidity`, `fan_mode`, `hvac_action`, `hvac_mode`, `swing_mode`, `current_temperature`, `target_humidity`, `target_temperature`, `temperature_unit`, or the special target `is_on`. |
| `options`       | dictionary of integer to string                    | Required for `fan_mode`, `hvac_action`, `hvac_mode`, `swing_mode`, and `temperature_unit`.                                                                                                                                                                                                                        |
| `unknown_value` | integer                                            | The value used by the API to signal unknown value.                                                                                                                                                                                                                                                                |
| `min_value`     | [IntegerOrTemperature](#type-integerortemperature) | Minimum allowed value. Supported for `target_humidity` (integer) and `target_temperature` (temperature).                                                                                                                                                                                                          |
| `max_value`     | [IntegerOrTemperature](#type-integerortemperature) | Maximum allowed value. Supported for `target_humidity` (integer) and `target_temperature` (temperature).                                                                                                                                                                                                          |

`temperature_unit` defaults to Celsius.

`hvac_mode` can only be mapped to [pre-defined modes](https://developers.home-assistant.io/docs/core/entity/climate#hvac-modes).

`hvac_action` can only be mapped to [pre-defined actions](https://developers.home-assistant.io/docs/core/entity/climate#hvac-action).
If a value does not have a sensible mapping, leave it out to set `hvac_action` to `None` for that value, or consider
mapping to a sensor `enum` instead.

For `fan_mode` and `swing_mode`, remember to add options [translation strings](#translation-strings).

Not yet supported target properties:
- `preset_mode`
- `target_temperature_high`
- `target_temperature_low`

## Type `Humidifier`:

Domain `humidifier` can be used to map the property to a target property in a humidifier entity. If at least one property has
type `humidifier`, a humidifier entity is created for the appliance.

| Item           | Type                            | Description                                                                                                                                                                                  |
|----------------|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `target`       | string                          | Any  of these [humidifier entity](https://developers.home-assistant.io/docs/core/entity/humidifier#properties) attributes: `action`, `is_on`, `current_humidity`, `target_humidity`, `mode`. |
| `options`      | dictionary of integer to string | Required for `action` and `mode`.                                                                                                                                                            |
| `device_class` | string                          | Name of any [HumidifierDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/humidifier#available-device-classes).                                                         |                                                                                                                         

It is sufficient to set `device_class` on one property. The value of the first encountered property is used.

`action` can only be mapped to [pre-defined actions](https://developers.home-assistant.io/docs/core/entity/humidifier/#action).
If a value does not have a sensible mapping, leave it out to set `action` to `None` for that value, or consider mapping
to a sensor `enum` instead.

For `mode`, remember to add options to [translation strings](#translation-strings).

## Type `Number`

Number entities can be set by the user.

| Item            | Type                                | Description                                                                                                                   |
|-----------------|-------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `min_value`     | integer                             | Minimum value.                                                                                                                |
| `max_value`     | integer                             | Maximum value.                                                                                                                |
| `device_class`  | `duration`, `energy`, `water`, etc. | Name of any [NumberDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/number/#available-device-classes). | 
| `unit`          | `min`, `°C`, `°F`, etc.             | Required if `device_class` is set, except not allowed when `device_class` is `aqi` or `ph`.                                   |

## Type `Select`

| Item       | Type                            | Description |
|------------|---------------------------------|-------------|
| `options`  | dictionary of integer to string | Required.   |

Remember to add options to [translation strings](#translation-strings).

## Type `Sensor`

Sensor entities are usually read-only, but this integration provides a `set_value` service that can be applied on 
the `sensor.connectlife` entities, unless the sensor is set to `read_only: true`.

| Item            | Type                                       | Description                                                                                                                                                                                    |
|-----------------|--------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `read_only`     | `true`, `false`                            | If this property is known to be read-only (prevents `set_value` service).                                                                                                                      |
| `state_class`   | `measurement`, `total`, `total_increasing` | Name of any [SensorStateClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes). For integer properties. Not allowed when `device_class` is `enum`. |
| `device_class`  | `duration`, `energy`, `water`, etc.        | Name of any [SensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes).                                                                  | 
| `unit`          | `min`, `kWh`, `L`, etc.                    | Required if `device_class` is set, except not allowed when `device_class` is `aqi`, `ph` or `enum`.                                                                                            |
| `options`       | dictionary of integer to string            | Required if `device_class` is set to `enum`.                                                                                                                                                   |
| `unknown_value` | integer                                    | The value used by the API to signal unknown value.                                                                                                                                             |

For device class `enum`, remember to add options to [translation strings](#translation-strings).

## Type `Switch`

| Item  | Type    | Description               |
|-------|---------|---------------------------|
| `off` | integer | Off value. Defaults to 0. |
| `on`  | integer | On value. Defaults to 1.  |

## Type `WaterHeater`:

Domain `water_heater` can be used to map the property to a target property in a water heater entity. If at least one property has
type `water_heater`, a water heater entity is created for the appliance.

| Item            | Type                                               | Description                                                                                                                                                                                                                   |
|-----------------|----------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `target`        | string                                             | Any  of these [water heater entity](https://developers.home-assistant.io/docs/core/entity/water-heater#properties) attributes: `current_operation`, `current_temperature`, `state`, `target_temperature`, `temperature_unit`. |
| `options`       | dictionary of integer to string or boolean         | Required for `current_operation`, `is_away_mode_on`, state`, and `temperature_unit`.                                                                                                                                          |
| `unknown_value` | integer                                            | The value used by the API to signal unknown value.                                                                                                                                                                            |
| `min_value`     | [IntegerOrTemperature](#type-integerortemperature) | Minimum allowed value. Supported for `target_temperature` (temperature).                                                                                                                                                      |
| `max_value`     | [IntegerOrTemperature](#type-integerortemperature) | Maximum allowed value. Supported for `target_temperature` (temperature).                                                                                                                                                      |

`temperature_unit` defaults to Celsius.

`state` can only be mapped to [pre-defined state](https://developers.home-assistant.io/docs/core/entity/water-heater#states).

`options` for `is_away_mode_on` is a map of integer to boolean.

For `current_operation`, remember to add options [translation strings](#translation-strings).

Not yet supported target properties:
- `target_temperature_high`
- `target_temperature_low`

## Type `IntegerOrTemperature`

Either just a numeric value, or values in Celsius and/or Fahrenheit.

```yaml
min_value: 10
```
or
```yaml
min_value:
  celsius: 0
  fahrenheit: 32
```

# Translation strings

By default, sensor entities are named by replacing `_` with ` ` in the property name. However, the property name is also
the translation key for the property, so it is possible to add a different English entity name as well as provide
translations by adding the property to [strings.json](../strings.json), and then to any [translations](../translations)
files.

For example, given the following data dictionary:
```yaml
properties:
  - property: Door_status
    sensor:
      device_class: enum
      options:
        0: not_available
        1: closed
        2: open
```

This goes into  [strings.json](../strings.json) and  [en.json](../translations/en.json),
```json
{
  "entity": {
    "sensor": {
      "Door_status": {
        "name": "Door",
        "state": {
          "not_available": "Unavailable",
          "closed": "Closed",
          "open": "Open"
        }
      }
    }
  }
}
```

Climate and humidifier modes must be registered as `state_attributes`.  

For example, given the following data dictionary:
```yaml
properties:
  - property: t_fan_speed
    climate:
      target: fan_mode
      options:
        0: auto
        5: low
        6: medium_low
        7: medium
        8: medium_high
        9: high
```

Strings not in [Home Assistant Core](https://github.com/home-assistant/core/blob/dev/homeassistant/components/climate/strings.json) goes in [strings.json](../strings.json) and  [en.json](../translations/en.json):
```json
{
  "entity": {
    "climate": {
      "connectlife": {
        "state_attributes": {
          "fan_mode": {
            "state": {
              "medium_low": "Medium low",
              "medium_high": "Medium high"
            }
          }
        }
      }
    }
  }
}
```

**If your appliance is missing, please make a PR to contribute it!**

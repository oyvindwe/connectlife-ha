# Data dictionaries

Data dictionaries for known appliances are located in this directory. Appliances without data dictionary will be still
be loaded, but with a warning in the log. Also, all unknown properties are mapped to hidden status entities.

To make a property visible by default, just add the property to the list (without setting `hide`).

File name: `<deviceTypeCode>-<deviceFeatureCode>.yaml`

The file contains two top level items:
- `device_type`: string
- `properties`: list of [`Property`](#property)

## Property

| Item            | Type                               | Description                                                                                       |
|-----------------|------------------------------------|---------------------------------------------------------------------------------------------------|
| `property`      | string                             | Name of status/property.                                                                          |
| `hide`          | `true`, `false`                    | If Home Assistant should initially hide the sensor entity for this property. Defaults to `false`. |
| `icon`          | `mdi:eye`, etc.                    | Icon to use for the entity.                                                                       |
| `binary_sensor` | [BinarySensor](#type-binarysensor) | Create a binary sensor of the property.                                                           |
| `climate`       | [Climate](#type-climate)           | Map the property to a climate entity for the device.                                              |
| `humidifier`    | [Humidifier](#type-humidifier)     | Map the property to a humidifier entity for the device.                                           |
| `select`        | [Select](#type-select)             | Create a selector of the property.                                                                |
| `sensor`        | [Sensor](#type-sensor)             | Create a sensor of the property. This is the default.                                             |
| `switch`        | [Switch](#type-switch)             | Create a Switch of the property.                                                                  |

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

| Item            | Type                            | Description                                                                                                                                                                                                                                                                                                       |
|-----------------|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `target`        | string                          | Any  of these [climate entity](https://developers.home-assistant.io/docs/core/entity/climate#properties) attributes: `current_humidity`, `fan_mode`, `hvac_action`, `hvac_mode`, `swing_mode`, `current_temperature`, `target_humidity`, `target_temperature`, `temperature_unit`, or the special target `is_on`. |
| `options`       | dictionary of integer to string | Required for `fan_mode`, `hvac_action`, `hvac_mode`, `swing_mode`, and `temperature_unit`.                                                                                                                                                                                                                        |
| `unknown_value` | integer                         | The value used by the API to signal unknown value.                                                                                                                                                                                                                                                                |

`temperature_unit` defaults to Celsius.

`hvac_mode` can only be mapped to [pre-defined modes](https://developers.home-assistant.io/docs/core/entity/climate#hvac-modes).

`hvac_action` can only be mapped to [pre-defined actions](https://developers.home-assistant.io/docs/core/entity/climate#hvac-action).
If a value does not have a sensible mapping, leave it out to set `hvac_action` to `None` for that value, or consider
mapping to a sensor `enum` instead.

For `fan_mode` and `swing_mode`, remember to add [translation strings](#translation-strings).

## Type `Humidifier`:

Domain `humidifier` can be used to map the property to a target property in a humidifier entity. If at least one property has
type `humidifier`, a humidifier entity is created for the appliance.

| Item           | Type                            | Description                                                                                                                                                                                  |
|----------------|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `target`       | string                          | Any  of these [humidifier entity](https://developers.home-assistant.io/docs/core/entity/humidifier#properties) attributes: `action`, `is_on`, `current_humidity`, `target_humidity`, `mode`. |
| `options`      | dictionary of integer to string | Required for `action` and `mode`.                                                                                                                                                             |
| `device_class` | string                          | Name of any [HumidifierDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/humidifier#available-device-classes).                                                         |                                                                                                                         

It is sufficient to set `device_class` on one property. The value of the first encountered property is used.

`action` can only be mapped to [pre-defined actions](https://developers.home-assistant.io/docs/core/entity/humidifier/#action).
If a value does not have a sensible mapping, leave it out to set `action` to `None` for that value, or consider mapping
to a sensor `enum` instead.

For mode, remember to add [translation strings](#translation-strings).

## Type `Select`

| Item       | Type                            | Description |
|------------|---------------------------------|-------------|
| `options`  | dictionary of integer to string | Required.   |

Remember to add options to [translation strings](#translation-strings).

## Type `Sensor`

| Item            | Type                                       | Description                                                                                                                                                                                                               |
|-----------------|--------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `unknown_value` | integer                                    | The value used by the API to signal unknown value.                                                                                                                                                                        |
| `max_value`     | integer                                    | Maximum value (checked when setting property).                                                                                                                                                                            |
| `writable`      | `true`, `false`                            | If this property is writable (do not set if unknown). Only applies to `sensor`.                                                                                                                                           |
| `state_class`   | `measurement`, `total`, `total_increasing` | Name of any [SensorStateClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes). For integer properties, defaults to `measurement`. Not allowed when `device_class` is `enum`. |
| `device_class`  | `duration`, `energy`, `water`, etc.        | Name of any [SensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes).                                                                                             | 
| `unit`          | `min`, `kWh`, `L`, etc.                    | Required if `device_class` is set, except not allowed when `device_class` is `ph` or `enum`.                                                                                                                              |
| `options`       | dictionary of integer to string            | Required if `device_class` is set to `enum`.                                                                                                                                                                              |

For enum options, remember to add [translation strings](#translation-strings).

## Type `Switch`

| Item  | Type    | Description               |
|-------|---------|---------------------------|
| `off` | integer | Off value. Defaults to 0. |
| `on`  | integer | On value. Defaults to 1.  |

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

*If your appliance is missing, please make a PR to contribute it!*

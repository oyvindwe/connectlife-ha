Data dictionaries for known appliances are located in this directory.

Appliances without data dictionary will be still be loaded.

File name: `<deviceTypeCode>-<deviceFeatureCode>.yaml`

List of `properties` with the following items:

| Item            | Type            | Description                                                                                       |
|-----------------|-----------------|---------------------------------------------------------------------------------------------------|
| `property`      | string          | Name of status/property.                                                                          |
| `hide`          | `true`, `false` | If Home Assistant should initially hide the sensor entity for this property. Defaults to `false`. |
| `icon`          | `mdi:eye`, etc. | Icon to use for the entity.                                                                       |
| `sensor`        | Sensor          | Create a sensor of the property. This is the default.                                             |
| `binary_sensor` | BinarySensor    | Create a binary sensor of the property.                                                           |


Type `Sensor`

| Item            | Type                                       | Description                                                                                                                                                                                                               |
|-----------------|--------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `unknown_value` | integer                                    | The value used by the API to signal unknown value.                                                                                                                                                                        |
| `max_value`     | integer                                    | Maximum value (checked when setting property).                                                                                                                                                                            |
| `writable`      | `true`, `false`                            | If this property is writable (do not set if unknown). Only applies to `sensor`.                                                                                                                                           |
| `state_class`   | `measurement`, `total`, `total_increasing` | Name of any [SensorStateClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes). For integer properties, defaults to `measurement`. Not allowed when `device_class` is `enum`. |
| `device_class`  | `duration`, `energy`, `water`, etc.        | Name of any [SensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes).                                                                                             | 
| `unit`          | `min`, `kWh`, `L`, etc.                    | Required if `device_class` is set, except not allowed when `device_class` is `ph` or `enum`.                                                                                                                              |
| `options`       | dictionary of integer to string            | Required if `device_class` is set to `enum`.                                                                                                                                                                              |

Type `BinarySensor`

| Item           | Type                     | Description                                                                                                                                                           |
|----------------|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `device_class` | `power`, `problem`, etc. | For domain `binary_sensor`, name of any [BinarySensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/binary-sensor#available-device-classes). | 


Domain `binary_sensor` can be used for read only properties where `0` is not available, `1` is off, and `2` is on. Both
`0`and `1` is mapped to off.

If none of `sensor` or `binary_sensor` is provided, the property is treated like `sensor`. It is not necessary to
include items with empty values. A [JSON schema](properties-schema.json) is provided so data dictionaries can be
validated.

By default, sensor entities are named by replacing `_` with ` ` in the property name. However, the property name is also
the translation key for the property, so it is possible to add a different English entity name as well as provide
translations by adding the property to [strings.json](../strings.json), and then to any [translations](../translations)
files.

Options for device class `enum` should always be added.

For example, given the following data dictionary:
```yaml
properties:
  - property: t_fan_speed
    sensor:
      device_class: enum
      options:
        0: low
        1: high
        2: auto
```

This goes into  [strings.json](../strings.json) and  [en.json](../translations/en.json),
```json
{
  "entity": {
    "sensor": {
      "t_fan_speed": {
        "name": "Fan speed",
        "state": {
          "low": "Low",
          "high": "High",
          "auto": "Auto"
        }
      }
    }
  }
}
```

*If your appliance is missing, please make a PR to contribute it!*

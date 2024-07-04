Data dictionaries for known appliances are located in this directory.

Appliances without data dictionary will be still be loaded.

File name: `<deviceTypeCode>-<deviceFeatureCode>.yaml`

List of `properties` with the following items:
| Item           | Type                                       | Description                                                                                      |
|----------------|--------------------------------------------|--------------------------------------------------------------------------------------------------|
|`property`      | string                                     | Name of status/property.                                                                         |
|`unknown_value` | integer                                    | The value used by the API to signal unknown value.                                               |
|`max_value`     | integer                                    | Maxium value (checked when setting property)                                                     |
|`writable`      | `true`, `false`                            | If this property is writable (leave blank if unknown)                                            |
|`state_class`   | `measurement`, `total`, `total_increasing` | Name of any [SensorStateClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes). For integer properties, defaults to `measurement`.     |
|`device_class`  | `duration`, `energy`, `water`, etc.        | Name of any [SensorDeviceClass enum](https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes)                                                        | 
|`unit`          | `min`, `kWh`, `L`, etc.                    | Required if `device_class` is set.                                                               |
|`hide`          | `true`, `false`                            | If Home Assistant should initially hide the sensor entity for this property. Defaults to `false`.|

If your appliance is missing, please make a PR to contribute it!

Future improvement: support `enum` device class for integer properties that are not measurements. 

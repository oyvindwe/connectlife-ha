# ConnectLife

ConnectLife integration for Home Assistant

[![BuyMeCoffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/oyvindwev)

## Installation

You can install using HACS or download.

### HACS

If you have HACS installed use the button below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=oyvindwe&repository=connectlife-ha&category=integration)


### Download

Download the `connectlife` directory and place in your `<config>/custom_components/`.

After installing, you need to restart Home Assistant.

Finally, add "ConnectLife" as an integration in the UI, and choose how to sign in (see [Login](#login)):
- **Sign in on the ConnectLife website**, also with a Google, Apple, Facebook or Microsoft account.
- **Enter username and password** of your ConnectLife account. Users in Russia/CIS who sign in with the
  ConnectLife.TRIR app must use this option and enable the experimental "TRIR" option.

Your devices and all their properties should show up.

## Supported ConnectLife devices

See [DEVICES.md](DEVICES.md) for the full list of supported devices.

### Default device types

Default mapping files are provided for the following device types:

| Device type              | Device type code                                                |
|--------------------------|-----------------------------------------------------------------|
| Portable air conditioner | [006](custom_components/connectlife/data_dictionaries/006.yaml) |
| Dehumidifier             | [007](custom_components/connectlife/data_dictionaries/007.yaml) |
| Window air conditioner   | [008](custom_components/connectlife/data_dictionaries/008.yaml) |
| Air conditioner          | [009](custom_components/connectlife/data_dictionaries/009.yaml) |
| Hood                     | [012](custom_components/connectlife/data_dictionaries/012.yaml) |
| Oven                     | [013](custom_components/connectlife/data_dictionaries/013.yaml) |
| Dishwasher               | [015](custom_components/connectlife/data_dictionaries/015.yaml) |
| Heat pump                | [016](custom_components/connectlife/data_dictionaries/016.yaml) |
| Induction hob            | [020](custom_components/connectlife/data_dictionaries/020.yaml) |
| Oven                     | [023](custom_components/connectlife/data_dictionaries/023.yaml) |
| Washing machine          | [025](custom_components/connectlife/data_dictionaries/025.yaml) |
| Refrigerator             | [026](custom_components/connectlife/data_dictionaries/026.yaml) |
| Washing machine          | [027](custom_components/connectlife/data_dictionaries/027.yaml) |
| Tumble dryer             | [030](custom_components/connectlife/data_dictionaries/030.yaml) |
| Tumble dryer             | [032](custom_components/connectlife/data_dictionaries/032.yaml) |
| Wine cooler              | [034](custom_components/connectlife/data_dictionaries/034.yaml) |

Any devices of these types will use the default mapping file, but it may not be fully functional until a
feature-specific mapping file is provided.

Any unmapped properties will show up as sensors with names based on their properties. As there are a lot of exposed
properties, all unknown entities are disabled by default. Access the device or entity list to view sensors and enable.

Please contribute PRs with [mapping files](custom_components/connectlife/data_dictionaries) for your devices!

## Disable beeping

Some devices will beep on every configuration change. To disable this, go to the
[ConnectLife integration](https://my.home-assistant.io/redirect/integration/?domain=connectlife)
and click "Configure" → "Configure a device" and select the device you want to disable beeping for. 

## Expose offline state

By default, when a device goes offline all of its entities become unavailable in Home Assistant. If you would
rather keep the entities showing their last known values, go to the
[ConnectLife integration](https://my.home-assistant.io/redirect/integration/?domain=connectlife)
and click "Configure" → "Configure a device", select the device, and enable "Expose offline state".

This adds a `connectivity` binary sensor (a diagnostic entity) reporting whether the device is online, and stops
the device's other entities from going unavailable while it is offline — they keep their last reported values
until the device comes back online.

## Swing mode control

Some devices report more than one property that can drive the climate card's swing mode (for example, both a
multi-position swing angle and a simple on/off swing). The integration normally picks one automatically, but a
few devices advertise a control they don't actually honour — e.g. the swing angle options appear but only make
the unit beep, while the on/off swing is what works.

If the swing control on the climate card doesn't work, go to the
[ConnectLife integration](https://my.home-assistant.io/redirect/integration/?domain=connectlife)
and click "Configure" → "Configure a device", select the device, and set "Swing mode control" to the property
your hardware actually responds to (leave it on "auto" to keep the automatic choice). This option only appears
for devices that expose more than one swing property.

## Daily energy and water consumption sensors

For supported device types, the integration exposes a **daily energy** sensor (kWh) and, for
wet appliances such as dishwashers and washing machines, a **daily water consumption** sensor (L).
Air conditioners report energy via the cloud `air_duct_energy` endpoint; other appliances
(dishwashers, washing machines, dryers, ovens, …) report energy — and where applicable water —
via the `energyConsumptionCurve` endpoint.

No configuration is needed: these sensors are created automatically for device types whose mapping
opts in (see the `statistics` block in the
[data dictionary docs](custom_components/connectlife/data_dictionaries/README.md#statistics)).
The statistics are fetched from a separate cloud endpoint, polled every 10 minutes, and — unlike
the regular status entities — they stay available even while the appliance is offline.

## Action to set property values on sensors

Entity action `connectlife.set_value` can be used to set values. Use with caution, as there is **no** validation
if property is writeable or that the value is legal to set.

1. The action can be accessed from [Settings → Tools → Actions](https://my.home-assistant.io/redirect/developer_services/).
2. Search for action name "ConnectLife: Set value"
3. Select entity as target.
4. Enter value
5. Perform action.

It is possible to guard against `set_value` by setting `read_only: true` in the data dictionary on the sensor, e.g.
```yaml
  - property: f_status 
    sensor:
      read_only: true
```

## Polling delay

The integration polls the ConnectLife API every 60 seconds to avoid overloading the API and risking being banned. When a command is sent from Home Assistant, only the properties included in that command are updated immediately in the HA UI. Any side effects on other properties (e.g., turning on an AC may also change fan mode or current temperature) will not appear until the next poll. Changes made outside Home Assistant (e.g., from the ConnectLife mobile app or physical device controls) may also take up to 60 seconds to appear.

## Troubleshooting

When reporting an issue with a device, please attach its diagnostics: go to the device page and click **Download
diagnostics** in the Device info card. The file contains the device type and feature code, the raw status values,
which properties are not mapped, what ConnectLife reports about the device (the settings it supports, its firmware
versions, its programs and their options, the faults it can report, its property list and today's hourly energy use),
and the last energy statistics. Device IDs, names and rooms are left out.

### Climate entities

Missing features:
- Setting `target_temperature_high`/`target_temperature_low`

### Heat pump entities
 
Missing features:
- Setting state except to off/one defined state
- Setting `target_temperature_high`/`target_temperature_low`

### Login

There are two ways to sign in:

- **Sign in on the ConnectLife website.** Home Assistant opens the ConnectLife login page, where you can sign in
  with your ConnectLife password or with Google, Apple, Facebook or Microsoft, and accept updated Terms &
  Conditions. Home Assistant doesn't store your password. This requires
  [My Home Assistant](https://www.home-assistant.io/integrations/my/), which is part of the default configuration.
  So far this has only been tested with accounts in Europe; please report how it works for you elsewhere.
- **Enter username and password** of a ConnectLife account. The password is stored in Home Assistant.

Users in China can't sign in using this integration. Users in Russia/CIS who use the ConnectLife.TRIR app must
enter username and password and enable the experimental "TRIR" option (see
https://github.com/oyvindwe/connectlife-ha/issues/267). See also the earlier discussion in
https://github.com/bilan/connectlife-api-connector/issues/25

Each ConnectLife account can only be added once. To change how an existing entry signs in, open it and select
**⋮** → **Reconfigure**. Alternatively, disable the existing entry, add a new one and then delete the old one. As the
devices are the same, entity IDs, names and history are kept.

### Password works in the app but not in Home Assistant

If login fails with "Invalid authentication" and the log shows `Code: 403042 … invalid loginID or password`, although
the same password works in the ConnectLife app, the password may be longer than the app accepts or contain special
characters it doesn't allow. The app may silently cut off or change such a password, so Home Assistant sends a
different one. Set a new, shorter password in the app (e.g. at most 20 characters, with letters, digits and common
special characters) and use that.

### Updated Terms & Conditions

ConnectLife periodically updates their Terms & Conditions. When this happens, the integration may stop working
with errors like `Account Pending Registration` or `Missing required fields for registration`, or devices may
silently become unavailable. Home Assistant shows this as the repair issue
**Accept updated ConnectLife Terms & Conditions**. The integration retries every 15 minutes until the terms are
accepted; select **Submit** in the repair to retry right away.

If you sign in on the ConnectLife website, select **⋮** → **Reconfigure** on the entry and sign in again; the login
page should ask you to accept the new terms.

With username and password, you need to accept the new Terms & Conditions in the ConnectLife mobile app:

1. Open the ConnectLife mobile app
2. Go to Settings and **change the app language to English**
3. **Force close the app** (not just background it)
4. **Reopen the app** — the Terms & Conditions acceptance screen should appear
5. **Accept the new Terms & Conditions**
6. In Home Assistant, **reload the ConnectLife integration**
7. You can change the app language back afterward — the acceptance persists

The language change is needed because updated Terms & Conditions are often only available in English initially.
The app skips the acceptance prompt if the translated version for your language doesn't exist yet, but the
backend still requires acceptance.

## Contributing

See [DEVELOPMENT.md](DEVELOPMENT.md).

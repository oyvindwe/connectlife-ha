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

Finally add "ConnectLife" as an integration in the UI, and provide the username and password for your ConnectLife account.

You appliances and all their status values should show up.

## Issues

### Missing data dictionaries

Please contribute PR with [data dictionary](custom_components/connectlife/data_dictionaries) for your device!

### Experimental service to set property values

Entity service `connectlife.set_value` can be used to set values. Use with caution, as there is **no** validation
if property is writeable, or that the value is legal to set.

1. The service can be accessed from Developer tools -> Services in HomeAssistant UI.
2. Search for service name "ConnectLife: Set value"
3. As target, select entity, and enter a ConnectLife sensor entity id.

### Login

Note that users at least in Russia and China can't log in using this integration. See discussion in
https://github.com/bilan/connectlife-api-connector/issues/25

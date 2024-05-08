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

You appliances and all their status values should show up. So far it is not possible to control any appliance. 

Note that probably only European users can log in using this integration. See discussion in
https://github.com/bilan/connectlife-api-connector/issues/25

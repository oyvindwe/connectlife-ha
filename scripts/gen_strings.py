import json
from os import listdir
from os.path import isfile, join

import yaml


def main(basedir):
    with open(f'{basedir}/strings.json', 'r') as f:
        strings = json.load(f)
    device_dir = f'{basedir}/data_dictionaries'
    filenames = list(filter(lambda f: f[-5:] == ".yaml", [f for f in listdir(device_dir) if isfile(join(device_dir, f))]))
    for filename in filenames:
        print(f"Generating strings from {filename}")
        with (open(f'{basedir}/data_dictionaries/{filename}') as f):
            appliance = yaml.safe_load(f)
        for property in appliance["properties"]:
            if "climate" in property:
                if property["climate"]["target"] == "fan_mode":
                    for option in property["climate"]["options"].values():
                        if (
                                option not in ["off", "on", "auto", "low", "medium", "high", "top", "middle", "focus", "diffuse"]
                                and option not in strings["entity"]["climate"]["connectlife"]["state_attributes"]["fan_mode"]["state"]
                            ):
                            if include_option(option, filename):
                                strings["entity"]["climate"]["connectlife"]["state_attributes"]["fan_mode"]["state"][option] = pretty(option)
                elif property["climate"]["target"] == "swing_mode":
                    for option in property["climate"]["options"].values():
                        if (
                                option not in ["off", "on", "both", "vertical", "horizontal"]
                                and option not in strings["entity"]["climate"]["connectlife"]["state_attributes"]["swing_mode"]["state"]
                            ):
                            if include_option(option, filename):
                                strings["entity"]["climate"]["connectlife"]["state_attributes"]["swing_mode"]["state"][option] = pretty(option)
            elif "humidifier" in property and property["humidifier"]["target"] == "mode":
                for option in property["humidifier"]["options"].values():
                    if (
                            option not in ["humidifying", "drying", "idle", "off"]
                            and option not in strings["entity"]["humidifier"]["connectlife"]["state_attributes"]["mode"]["state"]
                    ):
                        if include_option(option, filename):
                            strings["entity"]["humidifier"]["connectlife"]["state_attributes"]["state"][option] = pretty(option)
            else:
                if "disable" in property and property["disable"]:
                    continue
                for entity_type in ["binary_sensor", "switch", "number", "sensor", "select"]:
                    if entity_type in property:
                        if entity_type not in strings["entity"]:
                            strings["entity"][entity_type] = {}
                        name = property["property"]
                        key = name.lower().replace(" ", "_")
                        if key not in strings["entity"][entity_type]:
                            strings["entity"][entity_type][key] = {"name": pretty(name)}
                        if (
                                (
                                        (
                                                entity_type == "sensor"
                                                and entity_type in property
                                                and "device_class" in property[entity_type]
                                                and property[entity_type]["device_class"] == "enum")
                                        or entity_type == "select"
                                )
                                and "options" in property[entity_type]
                        ):
                            for option in property[entity_type]["options"].values():
                                if option in ["off", "on"]:
                                    continue
                                if not "state" in strings["entity"][entity_type][key]:
                                    strings["entity"][entity_type][key]["state"] = {}
                                if not option in strings["entity"][entity_type][key]["state"]:
                                    if include_option(option, filename):
                                        strings["entity"][entity_type][key]["state"][option] = pretty(option)
                            if "state" in strings["entity"][entity_type][key] and not strings["entity"][entity_type][key]["state"]:
                                del(strings["entity"][entity_type][key]["state"])

        if "climate" in appliance:
            if "presets" in appliance["climate"]:
                for preset in appliance["climate"]["presets"]:
                    preset = preset["preset"]
                    if (
                            preset not in ["eco", "away", "boost", "comfort", "home", "sleep", "activity"]
                            and preset not in strings["entity"]["climate"]["connectlife"]["state_attributes"]["preset_mode"]["state"]
                    ):
                        if include_option(preset, filename):
                            strings["entity"]["climate"]["connectlife"]["state_attributes"]["preset_mode"]["state"][preset] = pretty(preset)

    for (k, v) in strings["entity"].items():
        strings["entity"][k] = dict(sorted(v.items()))

    json.dump(strings, open(f'{basedir}/strings.json', 'w'), indent=2)

def is_number(s: str) -> bool:
    try:
        float(s.replace('%', 'e-2'))
        return True
    except ValueError:
        return False

def include_option(option: str, filename: str) -> bool:
    if type(option) != str:
        print(f"Values must be strings: {option} in {filename}")
        exit(1)
    if is_number(option) or "mmol/L" in option:
        return False
    if option != option.lower():
        print(f"Values should be lowercase: {option} in {filename}")
        exit(1)
    return True


def pretty(name: str) -> str:
    return name.replace("_", " ").capitalize();


if __name__ == "__main__":
    main("custom_components/connectlife")

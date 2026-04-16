import argparse
import json
import re
import urllib.request
from os import listdir
from os.path import isfile, join

import yaml

from scripts import check_translations, sort_translations

HA_STRINGS_URL = "https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/strings.json"


def main(basedir):
    ha_strings = load_ha_strings()
    with open(f'{basedir}/strings.json', 'r') as f:
        strings = json.load(f)
    valid_properties = {"sensor": {"daily_energy_kwh"}}
    valid_options = {}

    device_dir = f'{basedir}/data_dictionaries'
    filenames = list(filter(lambda f: f[-5:] == ".yaml", [f for f in listdir(device_dir) if isfile(join(device_dir, f))]))
    for filename in filenames:
        print(f"Generating strings from {filename}")
        with (open(f'{basedir}/data_dictionaries/{filename}') as f):
            appliance = yaml.safe_load(f)
        if appliance is not None:
            if "properties" in appliance and appliance["properties"] is not None:
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
                        elif property["climate"]["target"] == "swing_horizontal_mode":
                            for option in property["climate"]["options"].values():
                                if (
                                        option not in ["off", "auto", "fullrange"]
                                        and option not in strings["entity"]["climate"]["connectlife"]["state_attributes"]["swing_horizontal_mode"]["state"]
                                    ):
                                    if include_option(option, filename):
                                        strings["entity"]["climate"]["connectlife"]["state_attributes"]["swing_horizontal_mode"]["state"][option] = pretty(option)
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
                        key = to_key(property["property"])
                        if not any(entity_type in property for entity_type in ["binary_sensor", "climate", "humidifier", "number", "select", "sensor", "switch", "water_heater"]):
                            valid_properties.setdefault("sensor", set()).add(key)
                            name = property["property"]
                            if "sensor" not in strings["entity"]:
                                strings["entity"]["sensor"] = {}
                            if key not in strings["entity"]["sensor"]:
                                strings["entity"]["sensor"][key] = {"name": pretty(name)}
                            elif "name" not in strings["entity"]["sensor"][key]:
                                strings["entity"]["sensor"][key]["name"] = pretty(name)
                        for entity_type in ["binary_sensor", "switch", "number", "sensor", "select"]:
                            if entity_type in property:
                                if entity_type not in strings["entity"]:
                                    strings["entity"][entity_type] = {}
                                name = property["property"]
                                key = to_key(name)
                                if key not in strings["entity"][entity_type]:
                                    strings["entity"][entity_type][key] = {"name": pretty(name)}
                                elif "name" not in strings["entity"][entity_type][key]:
                                    strings["entity"][entity_type][key]["name"] = pretty(name)
                                valid_properties.setdefault(entity_type, set()).add(key)
                                if (
                                        property[entity_type] is not None
                                        and "options" in property[entity_type]
                                        and property[entity_type]["options"] is not None
                                ):
                                    for option in property[entity_type]["options"].values():
                                        valid_options.setdefault((entity_type, key), set()).add(option)
                                if (
                                        (
                                                (
                                                        entity_type == "sensor"
                                                        and entity_type in property
                                                        and property[entity_type] is not None
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

    for entity_type in ["binary_sensor", "switch", "number", "sensor", "select"]:
        if entity_type not in strings["entity"]:
            continue
        valid = valid_properties.get(entity_type, set())
        for key in list(strings["entity"][entity_type]):
            if key not in valid:
                print(f"Removing stale {entity_type}.{key}")
                del strings["entity"][entity_type][key]
            elif "state" in strings["entity"][entity_type][key]:
                valid_opts = valid_options.get((entity_type, key), set())
                for option in list(strings["entity"][entity_type][key]["state"]):
                    if option not in valid_opts:
                        print(f"Removing stale {entity_type}.{key}.state.{option}")
                        del strings["entity"][entity_type][key]["state"][option]
                if not strings["entity"][entity_type][key]["state"]:
                    del strings["entity"][entity_type][key]["state"]

    for (k, v) in strings["entity"].items():
        strings["entity"][k] = dict(sorted(v.items()))

    with open(f'{basedir}/strings.json', 'w') as f:
        json.dump(strings, f, indent=2, sort_keys=True)
        f.write("\n")

    en = expand_keys(strings, ha_strings)
    with open(f'{basedir}/translations/en.json', 'w') as f:
        json.dump(en, f, indent=2, sort_keys=True)
        f.write("\n")

    prune_translations(basedir, en)
    sort_translations.main(basedir)

def prune_translations(basedir, reference):
    translations_dir = f'{basedir}/translations'
    for filename in sorted(listdir(translations_dir)):
        if filename.endswith('.json') and filename != 'en.json':
            filepath = join(translations_dir, filename)
            with open(filepath, 'r') as f:
                trans = json.load(f)
            pruned = prune_keys(trans, reference)
            with open(filepath, 'w') as f:
                json.dump(pruned, f, indent=2, ensure_ascii=True, sort_keys=True)
                f.write("\n")


def prune_keys(obj, reference):
    if not isinstance(obj, dict) or not isinstance(reference, dict):
        return obj
    return {k: prune_keys(v, reference[k]) for k, v in obj.items() if k in reference}


def load_ha_strings():
    print(f"Fetching HA strings from {HA_STRINGS_URL}")
    try:
        with urllib.request.urlopen(HA_STRINGS_URL, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print(f"Failed to fetch HA strings: {e}")
        exit(1)


def resolve_key(ha_strings, key):
    """Resolve a key like 'common::config_flow::data::username' against HA strings."""
    parts = key.split("::")
    obj = ha_strings
    for part in parts:
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def expand_keys(obj, ha_strings):
    if isinstance(obj, dict):
        return {k: expand_keys(v, ha_strings) for k, v in obj.items()}
    if isinstance(obj, str) and obj.startswith("[%key:") and obj.endswith("%]"):
        key = obj[6:-2]
        value = resolve_key(ha_strings, key)
        if value is None:
            print(f"Unknown HA common string: {key}")
            exit(1)
        return value
    return obj


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


def to_key(name: str) -> str:
    return re.sub(r'_+', '_', name.strip().lower().replace(" ", "_"))


def pretty(name: str) -> str:
    # Split camelCase: "AirDryFlag" -> "Air Dry Flag"
    name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    # Split acronyms from words: "APPControl" -> "APP Control"
    name = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', name)
    # Split letters from digits: "compartment1" -> "compartment 1", "1add" -> "1 add"
    name = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', name)
    name = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', name)
    return re.sub(r' +', ' ', name.replace("_", " ")).strip().capitalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-missing", nargs="?", const="", default=None,
                        metavar="LANG", help="show missing translation keys (optionally for a specific language, e.g. nl)")
    args = parser.parse_args()
    basedir = "custom_components/connectlife"
    main(basedir)
    if args.show_missing is not None:
        check_translations.main(basedir, lang=args.show_missing)

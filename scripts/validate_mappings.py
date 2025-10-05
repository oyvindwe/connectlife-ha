import pprint
from os import listdir
from os.path import isfile, join

from jschon import create_catalog, JSON, JSONSchema
import yaml

def my_construct_mapping(self, node, deep=False):
    data = self.construct_mapping_org(node, deep)
    return {(str(key) if isinstance(key, int) else key): data[key] for key in data}

def main(basedir):
    yaml.SafeLoader.construct_mapping_org = yaml.SafeLoader.construct_mapping
    yaml.SafeLoader.construct_mapping = my_construct_mapping

    device_dir = f"{basedir}/data_dictionaries"
    create_catalog("2020-12")
    schema_file = f"{device_dir}/properties-schema.json"
    schema = JSONSchema.loadf(schema_file)
    schema.validate()

    filenames = list(filter(lambda f: f[-5:] == ".yaml", [f for f in listdir(device_dir) if isfile(join(device_dir, f))]))
    filenames.sort()
    for filename in filenames:
        print(f"Validating {filename}")
        with open(f"{device_dir}/{filename}", "r") as f:
            mappings_yaml = yaml.safe_load(f)
        if mappings_yaml is None:
            print("Empty mapping file")
        else:
            mappings_json = JSON(mappings_yaml)
            result = schema.evaluate(mappings_json)
            if not result.valid:
                pprint.pp(result.output("basic")["errors"])

if __name__ == "__main__":
    main("custom_components/connectlife")

import json
from os import listdir
from os.path import join


def main(basedir):
    translations_dir = f'{basedir}/translations'
    for filename in sorted(listdir(translations_dir)):
        if filename.endswith('.json'):
            sort_json(join(translations_dir, filename))


def sort_json(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main("custom_components/connectlife")

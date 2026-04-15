import argparse
import json
from os import listdir
from os.path import join


def main(basedir, lang=""):
    with open(join(basedir, 'translations', 'en.json'), 'r') as f:
        reference = json.load(f)
    translations_dir = join(basedir, 'translations')
    ref_keys = leaf_keys(reference)
    found_missing = False
    for filename in sorted(listdir(translations_dir)):
        if filename.endswith('.json') and filename != 'en.json' and (not lang or filename == f'{lang}.json'):
            with open(join(translations_dir, filename), 'r') as f:
                trans = json.load(f)
            trans_keys = leaf_keys(trans)
            missing = sorted(ref_keys - trans_keys)
            if missing:
                found_missing = True
                print(f"\n{len(missing)} missing keys in {filename}:")
                for key in missing:
                    print(f"  {key}")
            else:
                print(f"\nNo missing keys in {filename}")
    if not found_missing:
        print("\nAll translation files are complete.")


def leaf_keys(obj, prefix=""):
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys |= leaf_keys(v, f"{prefix}.{k}" if prefix else k)
    else:
        keys.add(prefix)
    return keys


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("lang", nargs="?", default="",
                        help="language code to check (e.g. nl), or omit for all")
    args = parser.parse_args()
    main("custom_components/connectlife", lang=args.lang)

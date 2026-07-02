#!/usr/bin/env python3
"""Extract the list of English strings that need translating for a language.

For the given language, finds every key present in en.json but missing from
<lang>.json, then emits the DISTINCT English strings that don't already have a
translation elsewhere in the file (those are reused automatically at merge
time). Each entry carries up to 3 example key paths as context, so short or
ambiguous labels ("Sl", "Mid", "1000 RPM") can be disambiguated.

Output: local/i18n/<lang>_todo.json  ->  [{"en": ..., "ctx": [key, ...]}, ...]

Usage:  python3 .../extract_todo.py <lang>
Run from the repository root.
"""
import json
import os
import sys
from collections import defaultdict

BASE = "custom_components/connectlife/translations"
OUT_DIR = "local/i18n"


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = obj
    return out


def main(lang):
    en = flatten(json.load(open(f"{BASE}/en.json")))
    target = flatten(json.load(open(f"{BASE}/{lang}.json")))

    val_to_keys = defaultdict(list)
    for k, v in en.items():
        val_to_keys[v].append(k)

    # English strings already translated somewhere in the target file -> reused at merge.
    known = {en[k] for k in target if k in en}

    missing_keys = [k for k in en if k not in target]
    need = sorted({en[k] for k in missing_keys if en[k] not in known},
                  key=lambda s: (len(s), s))

    items = [{"en": v, "ctx": val_to_keys[v][:3]} for v in need]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = f"{OUT_DIR}/{lang}_todo.json"
    json.dump(items, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"[{lang}] {len(missing_keys)} missing keys -> {len(items)} distinct strings to translate")
    print(f"        wrote {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: extract_todo.py <lang>")
    main(sys.argv[1])
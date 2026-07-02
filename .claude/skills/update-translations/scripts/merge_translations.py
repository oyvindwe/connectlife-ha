#!/usr/bin/env python3
"""Merge a translation map into a language file, filling every missing key.

Reads local/i18n/<lang>_translations.json  ->  {english_string: translation}
For every key present in en.json but missing from <lang>.json, fills it from
the map, or reuses an existing in-file translation of the same English string.

Refuses to write unless every missing key is filled AND every filled value has
the same {placeholders} as its English source. Writes ASCII-escaped + sorted
(match with `uv run python -m scripts.sort_translations`).

Usage:  python3 .../merge_translations.py <lang> [--check]
Run from the repository root.
"""
import json
import os
import re
import sys

BASE = "custom_components/connectlife/translations"
MAP_DIR = "local/i18n"
PLACEHOLDER = re.compile(r"\{[^}]+\}")


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = obj
    return out


def set_path(root, dotted, value):
    cur = root
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def main(lang, check):
    en = json.load(open(f"{BASE}/en.json"))
    target = json.load(open(f"{BASE}/{lang}.json"))
    en_flat = flatten(en)
    tgt_flat = flatten(target)

    known = {}
    for k, v in tgt_flat.items():
        if k in en_flat:
            known.setdefault(en_flat[k], v)

    map_path = f"{MAP_DIR}/{lang}_translations.json"
    tmap = json.load(open(map_path)) if os.path.exists(map_path) else {}

    missing = [k for k in en_flat if k not in tgt_flat]
    filled = reused = 0
    unfilled, ph_mismatch = [], []
    for k in missing:
        en_val = en_flat[k]
        if tmap.get(en_val) not in (None, ""):
            tr, src = tmap[en_val], "map"
        elif en_val in known:
            tr, src = known[en_val], "reuse"
        else:
            unfilled.append((k, en_val))
            continue
        if sorted(PLACEHOLDER.findall(str(en_val))) != sorted(PLACEHOLDER.findall(str(tr))):
            ph_mismatch.append((k, en_val, tr))
            continue
        if not check:
            set_path(target, k, tr)
        filled += 1
        reused += src == "reuse"

    print(f"[{lang}] missing={len(missing)} filled={filled} (reused={reused}) "
          f"unfilled={len(unfilled)} placeholder_mismatch={len(ph_mismatch)}")
    for k, e, t in ph_mismatch[:20]:
        print(f"  PLACEHOLDER MISMATCH {k}\n    en: {e!r}\n    tr: {t!r}")
    for k, e in unfilled[:30]:
        print(f"  UNFILLED {k}  <=  {e!r}")

    if check:
        return
    if unfilled or ph_mismatch:
        print("  NOT WRITTEN — resolve unfilled/placeholder issues first.")
        sys.exit(1)
    json.dump(target, open(f"{BASE}/{lang}.json", "w"), ensure_ascii=True, indent=2, sort_keys=True)
    open(f"{BASE}/{lang}.json", "a").write("\n")
    print(f"  WROTE {BASE}/{lang}.json  (run: uv run python -m scripts.sort_translations)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: merge_translations.py <lang> [--check]")
    main(args[0], "--check" in sys.argv)
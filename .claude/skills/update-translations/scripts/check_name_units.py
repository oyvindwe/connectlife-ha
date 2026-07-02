#!/usr/bin/env python3
"""Check consistency between time-unit words in entity names and units in the mapping.

Reports two problems across all language files:

  A. REDUNDANT  — a property has device_class: duration + a unit in the mapping,
     but its translated name still contains a unit word ("in minutes", "used
     hours", "(minuten)", leading "Horas de ..."). Home Assistant already
     renders the unit; drop the word from the name.

  B. UNIT ONLY IN NAME — a name contains a unit word but the property has NO
     unit in its sensor/number block. Either set the unit in the data dictionary
     (preferred, so HA renders it) or the name is the only place the unit shows.

Unit detection is word-boundary based and per-language, and deliberately skips
ambiguous short tokens: Norwegian "timer" (= hours OR timer) and bare Dutch
"uur"/Italian "ore" are only matched when clearly separate tokens.

Usage:  python3 .../check_name_units.py
Run from the repository root. Exit code 1 if any REDUNDANT issue is found.
"""
import glob
import json
import re
import sys

import yaml

DD = "custom_components/connectlife/data_dictionaries"
TR = "custom_components/connectlife/translations"
LANGS = ["en", "de", "es", "fr", "it", "nl", "no"]

# Property/state keys whose name legitimately keeps a unit word (would collide otherwise).
KEEP = {"set_time_hour", "set_time_minutes"}

DET = {
    "en": r"\b(minutes?|hours?|seconds?)\b",
    "de": r"\b(Minuten?|Stunden?|Sekunden?)\b",
    "es": r"\b(minutos?|horas?|segundos?)\b",
    "fr": r"\b(minutes?|heures?|secondes?)\b",
    "it": r"\b(minuti|minuto|ore|ora|secondi|secondo)\b",
    "nl": r"\b(minuten|minuut|uren|uur|seconden|seconde)\b",
    "no": r"\b(minutter|minutt|sekunder|sekund)\b",  # 'timer' (=hours) intentionally excluded
}


def build_property_map():
    pm = {}  # key -> (kind, device_class, unit)
    for path in sorted(glob.glob(f"{DD}/*.yaml")):
        try:
            doc = yaml.safe_load(open(path))
        except Exception:
            continue
        if not doc or not doc.get("properties"):
            continue
        for p in doc["properties"]:
            if not isinstance(p, dict):
                continue
            key = (p.get("translation_key") or p.get("property", "")).lower()
            for kind in ("sensor", "number"):
                blk = p.get(kind)
                if isinstance(blk, dict):
                    pm.setdefault(key, (kind, blk.get("device_class"), blk.get("unit")))
    return pm


def name_of(data, kind, key):
    return (((data.get("entity", {}) or {}).get(kind, {}) or {}).get(key, {}) or {}).get("name")


def main():
    pm = build_property_map()
    files = {l: json.load(open(f"{TR}/{l}.json")) for l in LANGS}

    redundant, unit_only = [], []
    for lang in LANGS:
        rx = re.compile(DET[lang], re.I)
        for key, (kind, dc, unit) in pm.items():
            if key in KEEP:
                continue
            n = name_of(files[lang], kind, key)
            if not isinstance(n, str) or not rx.search(n):
                continue
            (redundant if unit else unit_only).append((lang, key, dc, unit, n))

    print(f"A. REDUNDANT unit word in a name that already has a mapping unit: {len(redundant)}")
    for lang, key, dc, unit, n in redundant:
        print(f"   [{lang}] {key} (unit={unit}): {n!r}")
    print(f"\nB. Unit word in a name but NO unit set in the mapping: {len(unit_only)}")
    for lang, key, dc, unit, n in unit_only:
        print(f"   [{lang}] {key} (device_class={dc}): {n!r}")

    if redundant:
        print("\nFix A: strip the unit word from these names (unit is rendered from the mapping).")
        sys.exit(1)
    print("\nOK: no redundant unit words in unit-backed names.")


if __name__ == "__main__":
    main()
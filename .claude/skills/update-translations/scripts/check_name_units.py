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

By default this audits the entire committed corpus, which re-reports findings
that have shipped for releases. Pass --base <git-ref> to scope the report to
findings this change *newly introduces*: the same check is run against the tree
at <git-ref> and any finding already present there (pre-existing) is dropped.
This catches both ways a redundancy appears — a name gaining a unit word, or a
mapping gaining a unit — since it diffs the resulting findings, not just names.

Usage:
  python3 .../check_name_units.py                 # full audit (all languages)
  python3 .../check_name_units.py --base v0.45.0   # only findings new since a release
  python3 .../check_name_units.py --base origin/main  # only findings new on this branch
Run from the repository root. Exit code 1 if any *reported* REDUNDANT issue is
found (i.e. new ones only when --base is given).
"""
import argparse
import glob
import json
import re
import subprocess
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


def git_show(ref, path):
    """Return the bytes of `path` at `ref`, or None if it did not exist there."""
    r = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
    )
    return r.stdout if r.returncode == 0 else None


def build_property_map(read):
    """read(path) -> raw bytes/str or None. Builds key -> (kind, device_class, unit)."""
    pm = {}
    for path in sorted(glob.glob(f"{DD}/*.yaml")):
        raw = read(path)
        if raw is None:
            continue
        try:
            doc = yaml.safe_load(raw)
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


def load_lang_files(read):
    files = {}
    for l in LANGS:
        raw = read(f"{TR}/{l}.json")
        files[l] = json.loads(raw) if raw is not None else {}
    return files


def name_of(data, kind, key):
    return (((data.get("entity", {}) or {}).get(kind, {}) or {}).get(key, {}) or {}).get("name")


def collect_findings(pm, files):
    """Return {(lang, key, category): (dc, unit, name)} for every unit-word hit.

    category is "A" (redundant: mapping has a unit) or "B" (unit word, no mapping unit).
    """
    out = {}
    for lang in LANGS:
        rx = re.compile(DET[lang], re.I)
        for key, (kind, dc, unit) in pm.items():
            if key in KEEP:
                continue
            n = name_of(files[lang], kind, key)
            if not isinstance(n, str) or not rx.search(n):
                continue
            out[(lang, key, "A" if unit else "B")] = (dc, unit, n)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        metavar="GIT_REF",
        help="only report findings not already present at this ref "
        "(e.g. a release tag or origin/main); omit for a full audit",
    )
    args = ap.parse_args()

    current = collect_findings(
        build_property_map(lambda p: open(p, "rb").read()),
        load_lang_files(lambda p: open(p, "rb").read()),
    )

    baseline = {}
    if args.base:
        if git_show(args.base, "custom_components/connectlife/manifest.json") is None:
            sys.exit(f"error: git ref {args.base!r} not found (fetch it or check the name)")
        baseline = collect_findings(
            build_property_map(lambda p: git_show(args.base, p)),
            load_lang_files(lambda p: git_show(args.base, p)),
        )

    # Scope to findings this change introduces: drop any already present at base.
    new = {k: v for k, v in current.items() if k not in baseline}
    redundant = sorted([(l, key, *new[(l, key, c)]) for (l, key, c) in new if c == "A"])
    unit_only = sorted([(l, key, *new[(l, key, c)]) for (l, key, c) in new if c == "B"])

    scope = f" new since {args.base}" if args.base else ""
    print(f"A. REDUNDANT unit word in a name that already has a mapping unit{scope}: {len(redundant)}")
    for lang, key, dc, unit, n in redundant:
        print(f"   [{lang}] {key} (unit={unit}): {n!r}")
    print(f"\nB. Unit word in a name but NO unit set in the mapping{scope}: {len(unit_only)}")
    for lang, key, dc, unit, n in unit_only:
        print(f"   [{lang}] {key} (device_class={dc}): {n!r}")

    if redundant:
        print("\nFix A: strip the unit word from these names (unit is rendered from the mapping).")
        sys.exit(1)
    print(f"\nOK: no redundant unit words in unit-backed names{scope}.")


if __name__ == "__main__":
    main()
---
name: update-translations
description: Fill missing translation keys in the ConnectLife language files using appliance-specific terminology, keep time units in the data dictionary (not baked into entity names), verify, and open one PR per language. Use when a language file is missing keys or when unit words need cleaning out of names.
argument-hint: [lang ...]
disable-model-invocation: true
allowed-tools: Bash(uv *) Bash(git *) Bash(gh *) Bash(python3 *)
---

Add or fix translations for this ConnectLife Home Assistant integration.

Read [CONVENTIONS.md](CONVENTIONS.md) first — it holds the locked terminology and formatting rules. Scripts live in [scripts/](scripts/); optional multi-agent workflow templates in [workflows/](workflows/).

`$ARGUMENTS` is an optional space-separated list of language codes (`de es fr it nl no`); default to all non-English languages.

## Workflow

1. **Find what's missing.**
   ```bash
   uv run python -m scripts.check_translations [lang]
   ```
   `en.json` is the reference; it is generated from the data dictionaries by `scripts.gen_strings` (which only *adds* missing keys and never overwrites existing text). Never invent keys — only fill keys that `check_translations` reports.

2. **Extract the work list with context.**
   ```bash
   python3 .claude/skills/update-translations/scripts/extract_todo.py <lang>   # -> local/i18n/<lang>_todo.json
   ```
   Emits each distinct missing English string plus the key path(s) it appears under (needed to disambiguate short labels like `Sl`, `Mid`, `1000 RPM`).

3. **Translate** per [CONVENTIONS.md](CONVENTIONS.md), using the committed term glossary [glossary.json](glossary.json) (extend it from `local/manuals/` and public user manuals — see CONVENTIONS). Produce `local/i18n/<lang>_translations.json` (a transient work file) as a flat `{english_string: translation}` map.
   - Small sets: translate inline.
   - Large sets (hundreds+): use the multi-agent workflow in [workflows/translate.js](workflows/translate.js) (requires explicit opt-in — see workflows/README). Batch by file, one reviewer per language.

4. **Merge, sort, verify.**
   ```bash
   python3 .claude/skills/update-translations/scripts/merge_translations.py <lang> --check   # dry run
   python3 .claude/skills/update-translations/scripts/merge_translations.py <lang>           # write
   uv run python -m scripts.sort_translations
   uv run python -m scripts.check_translations <lang>        # must report 0 missing
   ```
   `merge_translations.py` fills every missing key, reuses existing in-file translations for repeated English strings, and refuses to write if any `{placeholder}` parity check fails or any key is unfilled.

5. **Keep units in the mapping, not in names.** If an entity name bakes in a time unit (`… in minutes`, `… used hours`, `(minuten)`, leading `Horas de …`), set `device_class: duration` + `unit` on the property's `sensor`/`number` block in the data dictionary and drop the unit word from the name in every language. Then verify both directions:
   ```bash
   python3 .claude/skills/update-translations/scripts/check_name_units.py    # names vs mapping units, both ways
   ```

6. **Open one PR per language.** Branch `add-<lang>-translations`; commit only that language's file; keep the PR description functional (see CONVENTIONS). Don't push until the user asks.

## Guardrails

- Never rename property or state **keys** — they map to API property names / device codes. Only edit display text.
- Write JSON with `ensure_ascii=True` and always run `scripts.sort_translations` after (repo files are ASCII-escaped and sorted).
- Don't add unit tests asserting a mapping's content — mappings are validated by `scripts.validate_mappings` and PR review.
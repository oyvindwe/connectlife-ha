# Translation conventions

Locked rules for translating ConnectLife entity names, states, and UI strings. The goal is text that reads like it was written for a real appliance in that language, consistent with what the integration already ships.

## Sourcing terminology

- Use the **standard consumer-appliance term** a native speaker sees on a real control panel or in the manual — not a literal dictionary translation. E.g. Cotton → *Baumwolle / Coton / Cotone / Algodón / Katoen*; Spin → *Schleudern / Essorage / Centrifuga*.
- **Public user manuals are an allowed source** (published Hisense/Gorenje/ASKO/Winix PDFs; the gitignored copies in `local/manuals/`). Multilingual EU manuals list the same label in several languages side by side — the best source for program/mode names.
- The harvested term glossary is committed alongside this file as `glossary.json`: `[{en, category, de?, es?, fr?, it?, nl?, no?}, …]`. Extend it as you find new appliance terms — record only terms actually printed in a manual; when in doubt, match the term already used elsewhere in the same language file.
- Keep commit and PR text functional — describe what an entity measures or how a label reads. Public user manuals are fine to reference.

## Units

- **Units and measurements belong in the data dictionary, not in the name.** Set the appropriate `device_class` + `unit` on the property's `sensor`/`number` block and Home Assistant renders the unit after the value: duration (`min`/`h`/`s`), humidity (`%`), temperature (`°C`), energy (`kWh`), etc. The entity **name must not repeat the unit** (`… in minutes`, `… used hours`, `(minuten)`, leading `Horas de …`, `%RH`). Such unit/measurement labels are **not** glossary terms — the glossary holds appliance program/mode/option/phase/status/error/setting terminology only.
- **Exception — clock / time-of-day components.** When `hour`/`minute`/`second` names *which component of a time* (not a duration), the word is meaningful and stays: e.g. `Set time hour` + `Set time minutes` (a pair — stripping both would collide), and the Sabbath / Night-mode / `*_start_time_*` / `*_end_time_*` hour and minute fields. These are not durations; don't strip the word, and don't give them a `duration` unit. Likewise `_second` sometimes means the ordinal "2nd item" (e.g. `WashingWizzard_Cloth_stains_second`), not the unit — never treat that as a unit.
- **RPM / spin speed** per language: `de U/min · es rpm · fr tr/min · it giri/min · nl toeren · no o/min`. Never leave English `RPM` in a translated string. (These are state *values* like `1000 U/min`, so they stay in the translations.)
- Leave unchanged: bare numbers (`600`), pure units (`kg`, `ml`), symbols (`%`, `°C`), and brand/feature tokens (`AquaStop`, `DrumClean`, `Eco 40-60`, `AdaptTech`, `Wi-Fi`).

## Formatting

- Preserve exactly: `{curly_placeholders}` (`{device_name}`, `{count}`), HTML entities, markdown (`**bold**`, `\n`, backticks, links), and leading/trailing spaces. `merge_translations.py` enforces placeholder parity.
- Match each language's UI casing (German nouns capitalized; sentence case elsewhere).
- Write JSON `ensure_ascii=True`; run `scripts.sort_translations` after any edit.

## Grammatical form (action vs state)

- A **select** option value (`entity.select.<x>.state.<y>`) is something the user *picks to command* the appliance — prefer the **action / imperative** form for verb-capable labels (`Start`, `Pause`, `Cancel`, `Reset programs to default`).
- **Exception:** value/enumeration selects whose options are quantities or noun-named modes — spin speeds, durations, temperatures, wattages, or modes like `Delay start`/`Delay end` — stay **nouns**.
- A `sensor`/`binary_sensor` state or any `.name` is a **noun/state** describing a condition — descriptive noun form.

## Language notes

- **Norwegian:** `timer` means both *hours* and *timer* — never strip it mechanically. Handle `no` by hand.
- **Dutch/Italian:** don't strip short unit substrings (`uur` inside *temperatuur*, `ore` inside *sensore*) — only remove a unit that is a separate trailing/leading token.

## Garbled English source strings

The English label is `pretty(property_key)`, so a typo'd or run-together **property key** shows up as a garbled English name (`Soil lever`→level, `Quiet model`→mode, `Alarmoven`→missing space). Fix the **display text** in `strings.json` + `en.json` (`gen_strings` preserves existing entries). **Do not rename the key** — it maps to an API property/device code and renaming breaks every language at once.

## Reviewing

- Per-language depth review (fluency + terminology) needs a native-level pass **per language** — one reviewer each, in parallel.
- A single **cross-language** pass is right for *systematic* issues: garbled sources, inconsistent glossary terms, unit/placeholder drift — it sees the same string's translations side by side. See [workflows/review.js](workflows/review.js).
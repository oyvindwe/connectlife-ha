export const meta = {
  name: 'i18n-translate',
  description: 'Translate missing ConnectLife HA strings for one language using a manual-sourced glossary, then verify',
  phases: [
    { title: 'Translate', detail: 'batched translation using locked appliance glossary' },
    { title: 'Verify', detail: 'check placeholder parity, glossary compliance, phrasing' },
  ],
}

const LANG_NAME = {
  de: 'German (Deutsch)', es: 'Spanish (Español, European/Spain)', fr: 'French (Français)',
  it: 'Italian (Italiano)', nl: 'Dutch (Nederlands)', no: 'Norwegian (Bokmål)',
}

// Localized spin-speed unit per language, matching each file's shipped convention.
const RPM_UNIT = { de: 'U/min', es: 'rpm', fr: 'tr/min', it: 'giri/min', nl: 'toeren', no: 'o/min' }

const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { lang, batchPaths, glossaryPath } = A
if (!lang || !Array.isArray(batchPaths) || !batchPaths.length || !glossaryPath) {
  throw new Error(`bad args: lang=${lang} batchPaths=${Array.isArray(batchPaths) ? batchPaths.length : typeof batchPaths} glossaryPath=${glossaryPath}`)
}
const langName = LANG_NAME[lang]

const PAIR_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['translations'],
  properties: { translations: { type: 'array', items: {
    type: 'object', additionalProperties: false, required: ['en', 'tr'],
    properties: { en: { type: 'string' }, tr: { type: 'string' } } } } },
}

const translatePrompt = (path, idx) => `You are a professional localizer translating smart-home appliance UI strings into ${langName} for a Home Assistant integration that exposes ConnectLife appliances (washing machines, tumble dryers, heat-pump dryers, dehumidifiers, air conditioners, ovens/cookers, water heaters).

Read this file: ${path} — a JSON array of {en, ctx}. Translate EVERY item in it. "en" is the English string; "ctx" lists the HA key path(s) where it is used (use it to disambiguate short/ambiguous labels).

Also read the locked glossary at ${glossaryPath} — a JSON array of {en, category, <lang codes>}. This is AUTHORITATIVE appliance terminology sourced from real manuals.

TRANSLATION RULES:
- If an item's English string matches a glossary entry that has a "${lang}" value, you MUST use that exact ${lang} term (preserve its casing/diacritics). Glossary wins over your own judgment.
- Use STANDARD CONSUMER APPLIANCE terminology as printed on real ${langName} appliance control panels and manuals — not literal dictionary translations. E.g. washer programs, AC modes (Cool/Heat/Dry/Fan/Auto), cycle phases (Wash/Rinse/Spin/Dry), options (Prewash/Extra Rinse/Steam), fault descriptions.
- Preserve EXACTLY, unchanged: {curly_braces_placeholders} (e.g. {device_name}, {count}), HTML entities, markdown (**bold**, \\n, backticks, links), leading/trailing spaces, and units/symbols (%, °C, kg, ml, rpm, kWh).
- SPIN SPEED / RPM: render the unit "RPM" (revolutions per minute) as "${RPM_UNIT[lang]}" in ${langName} — e.g. "1000 RPM" -> "1000 ${RPM_UNIT[lang]}", "Motor speed 800 RPM available" uses "800 ${RPM_UNIT[lang]}". Never leave the English "RPM" in a translated phrase.
- A bare number ("5", "600"), a pure unit ("kg", "ml"), or a brand/feature token that appliances leave untranslated (e.g. AquaStop, DrumClean, Eco 40-60, AdaptTech, Wi-Fi) should be returned UNCHANGED.
- ACTION vs STATE (use the "ctx" key path to decide the grammatical form):
    * A "select" option value (ctx like ".select.<x>.state.<y>") is something the USER PICKS TO COMMAND the appliance. If the label is verb-capable, prefer the ACTION / imperative-command form (e.g. "Start", "Pause", "Cancel", "Reset programs to default", "Open steamer water tank door"). This is the common case for selects.
    * EXCEPTION: value/enumeration selects whose options are quantities or noun-named modes — spin speeds ("1000 RPM"), durations/times, temperatures, wattages, or mode names like "Delay start"/"Delay end" — stay as NOUNS/values, not verbs.
    * A "sensor"/"binary_sensor" state or any ".name" label is a NOUN/STATE describing a condition — use the descriptive noun form.
- Keep it concise: UI labels must stay short. Match capitalization conventions of ${langName} UI (e.g. German nouns capitalized; French/Italian/Spanish/Dutch sentence case for most labels).
- Long repair/dialog sentences: translate fully and naturally, keeping every placeholder and markdown intact.

OUTPUT: Return {translations: [{en, tr}, ...]} containing EVERY item from the file, with "en" copied VERBATIM from the input (exact same string) and "tr" the ${langName} translation. Do not add, drop, or merge items.`

const verifyPrompt = (pairsJson, idx) => `You are a senior ${langName} reviewer for smart-home appliance UI strings. Below are English→${langName} translation pairs produced by a translator, plus the authoritative glossary at ${glossaryPath} (read it).

Check each pair and FIX where needed:
- Placeholder/markup parity: the ${langName} text MUST contain exactly the same {placeholders}, HTML entities, \\n, markdown, and units/symbols as the English. If mismatched, fix.
- Glossary compliance: if the English matches a glossary entry with a "${lang}" value, the translation MUST equal that term. Fix if not.
- Terminology: ensure standard ${langName} appliance-panel wording (programs, modes, phases, options, faults). Correct anglicisms or literal mistranslations.
- RPM unit: any "RPM" in a translated phrase MUST be rendered as "${RPM_UNIT[lang]}" (e.g. "1000 ${RPM_UNIT[lang]}"). Fix leftover English "RPM".
- Untranslated tokens: bare numbers, pure units, and brand/feature names (AquaStop, DrumClean, Eco 40-60, Wi-Fi, etc.) must remain unchanged.
- Casing/length appropriate for a UI label.

Return {translations: [{en, tr}, ...]} with the SAME "en" values and corrected (or unchanged) "tr". Keep every item.

PAIRS (JSON):
${pairsJson}`

const results = await pipeline(
  batchPaths,
  (path, _orig, idx) => agent(translatePrompt(path, idx), { label: `${lang} tr #${idx}`, phase: 'Translate', schema: PAIR_SCHEMA }),
  async (res, path, idx) => {
    const pairs = (res && res.translations) || []
    if (!pairs.length) return { translations: [] }
    try {
      const v = await agent(verifyPrompt(JSON.stringify(pairs), idx), { label: `${lang} vf #${idx}`, phase: 'Verify', schema: PAIR_SCHEMA })
      // Fall back to unverified translations if verify came back empty/short.
      if (v && Array.isArray(v.translations) && v.translations.length >= pairs.length * 0.9) return v
      return { translations: pairs }
    } catch (e) {
      return { translations: pairs } // never discard translated work on a verify failure
    }
  },
)

const map = {}
for (const res of results) {
  if (!res || !res.translations) continue
  for (const { en, tr } of res.translations) {
    if (en != null && tr != null) map[en] = tr
  }
}
log(`${lang}: produced ${Object.keys(map).length} translations across ${batchPaths.length} batches`)
return { lang, count: Object.keys(map).length, batches: batchPaths.length, map }

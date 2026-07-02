export const meta = {
  name: 'i18n-review',
  description: 'Review the six translation PRs: per-language fluency/terminology depth + one cross-language pattern pass',
  phases: [
    { title: 'PerLanguage', detail: 'one Opus 4.8 reviewer per language, fluency + terminology' },
    { title: 'CrossLanguage', detail: 'single reviewer over same-English rows to find systematic patterns' },
  ],
}

const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { base, counts, xlangCount } = A
if (!base || !counts || !xlangCount) throw new Error(`bad args: ${JSON.stringify(A)}`)
const glossaryPath = `${base}/glossary.json`
const pad = n => String(n).padStart(2, '0')
const reviewPaths = {}
for (const [lang, n] of Object.entries(counts)) {
  reviewPaths[lang] = Array.from({ length: n }, (_, i) => `${base}/${lang}_rev${pad(i)}.json`)
}
const xlangPaths = Array.from({ length: xlangCount }, (_, i) => `${base}/xlang${pad(i)}.json`)

const LANG_NAME = {
  de: 'German (Deutsch)', es: 'Spanish (Español, Spain)', fr: 'French (Français)',
  it: 'Italian (Italiano)', nl: 'Dutch (Nederlands)', no: 'Norwegian (Bokmål)',
}
const RPM_UNIT = { de: 'U/min', es: 'rpm', fr: 'tr/min', it: 'giri/min', nl: 'toeren', no: 'o/min' }

const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['en', 'current', 'suggested', 'severity', 'reason'],
    properties: {
      en: { type: 'string' },
      current: { type: 'string' },
      suggested: { type: 'string' },
      severity: { type: 'string', description: 'high (wrong/misleading), medium (unnatural/inconsistent), low (nit)' },
      reason: { type: 'string', description: 'one concise sentence' },
    },
  } } },
}

const XFINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['en', 'pattern', 'langs', 'reason'],
    properties: {
      en: { type: 'string' },
      pattern: { type: 'string', description: 'the systematic issue class, e.g. "garbled English source", "RPM unit missing", "glossary term inconsistent", "placeholder drift"' },
      langs: { type: 'string', description: 'comma-separated language codes affected' },
      reason: { type: 'string' },
    },
  } } },
}

const perLangPrompt = (lang, path) => `You are a NATIVE ${LANG_NAME[lang]} speaker and a smart-home appliance domain expert, reviewing machine-produced translations for a Home Assistant integration (ConnectLife appliances: washers, dryers, dehumidifiers, air conditioners, ovens, water heaters).

Read the batch at ${path} — a JSON array of {en, tr} where "en" is the English source and "tr" is the ${LANG_NAME[lang]} translation under review. Also read the authoritative glossary at ${glossaryPath} (array of {en, category, <lang codes>}).

For EACH pair, judge whether "tr" is correct, natural, and uses the terminology a native speaker sees on a real ${LANG_NAME[lang]} appliance. Report ONLY the entries you would change. Skip anything that is already good — do not pad the list.

Flag when:
- The translation is wrong, misleading, or a false friend / literal mistranslation (severity high).
- It's grammatically off, uses non-native/anglicized wording, wrong register, or wrong appliance term (severity medium).
- It contradicts the glossary's ${lang} term for that English string (severity high).
- Casing/spacing/diacritics are wrong for a ${LANG_NAME[lang]} UI label (severity low).
- "RPM" appears untranslated instead of "${RPM_UNIT[lang]}" (severity medium).
Do NOT flag: bare numbers, pure units, or brand/feature tokens (AquaStop, DrumClean, Eco 40-60, Wi-Fi) that legitimately stay unchanged; and do not flag stylistic preferences where the current wording is already idiomatic.

Return {findings: [...]} with en (verbatim), current (the tr as given), suggested (your corrected ${LANG_NAME[lang]} wording), severity, and a one-sentence reason. Empty findings array if the batch is clean.`

const xlangPrompt = (path) => `You are auditing appliance-UI translations across SIX languages at once (de/es/fr/it/nl/no) to find SYSTEMATIC, cross-language PATTERNS — not per-language fluency (other reviewers handle that).

Read the batch at ${path} — a JSON array of rows {en, de?, es?, fr?, it?, nl?, no?}: one English source string and its translation in each language that has it. Also read the glossary at ${glossaryPath}.

Look for issues that recur across languages or reveal a shared root cause:
- GARBLED / NON-ENGLISH SOURCE: the "en" itself is junk or a code (e.g. "Darhcdq", "An creae mux", "PPU RECIPSS", "Slotdry") that most/all languages tried to translate when it should have been left verbatim. Flag so it can be reverted to the English token everywhere.
- GLOSSARY INCONSISTENCY: the same concept rendered with different terms across languages when the glossary implies one standard, or one language deviating from its own glossary term.
- UNIT / FORMAT DRIFT: "RPM" localized in some languages but left English in others; inconsistent handling of %, °C, kg, time formats.
- PLACEHOLDER / MARKUP DRIFT: {placeholders}, HTML entities, or markdown present in en but dropped/added in one or more languages.
- STRUCTURAL DIVERGENCE: same English string translated as an action (verb) in some languages and a noun/state in others, where they should agree.

Report one finding per problematic English row. Return {findings: [...]} with en, pattern (the issue class), langs (comma-separated codes affected), and a one-sentence reason. Empty array if the batch shows no systematic issue. Ignore purely idiomatic per-language wording differences — those are expected and are NOT findings.`

phase('PerLanguage')
const langs = Object.keys(reviewPaths)
const perLang = await parallel(langs.map(lang => async () => {
  const batches = reviewPaths[lang]
  const results = await parallel(batches.map((p, i) => () =>
    agent(perLangPrompt(lang, p), { label: `review:${lang}#${i}`, phase: 'PerLanguage', schema: FINDINGS_SCHEMA })))
  const findings = results.filter(Boolean).flatMap(r => r.findings || [])
  return { lang, findings }
}))

phase('CrossLanguage')
const xResults = await parallel(xlangPaths.map((p, i) => () =>
  agent(xlangPrompt(p), { label: `xlang#${i}`, phase: 'CrossLanguage', schema: XFINDINGS_SCHEMA })))
const xfindings = xResults.filter(Boolean).flatMap(r => r.findings || [])

const perLanguage = {}
for (const r of perLang.filter(Boolean)) {
  const f = r.findings
  perLanguage[r.lang] = {
    total: f.length,
    high: f.filter(x => x.severity === 'high').length,
    medium: f.filter(x => x.severity === 'medium').length,
    low: f.filter(x => x.severity === 'low').length,
    findings: f,
  }
}
log(`per-language findings: ${langs.map(l => `${l}=${perLanguage[l]?.total ?? 0}`).join(' ')}; cross-language patterns: ${xfindings.length}`)
return { perLanguage, crossLanguage: xfindings }

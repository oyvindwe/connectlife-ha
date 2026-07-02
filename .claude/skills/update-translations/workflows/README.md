# Translation workflows (multi-agent)

Reference [Workflow-tool](https://docs.claude.com/claude-code) scripts for translating/reviewing at scale (hundreds of strings across 6 languages). They fan out one agent per batch/language and require **explicit multi-agent opt-in** — only run them when the user asks. For small jobs, translate inline instead.

Both read the committed `../glossary.json` and the transient work files under `local/i18n/`.

## `translate.js`
Per language: batches the work list, translates each batch against the glossary + CONVENTIONS, then a verification pass. A failed verify falls back to the raw translation (never discards work).

Prep, then launch with the Workflow tool:
```bash
# 1. extract todo, split into batch files of ~80
python3 .claude/skills/update-translations/scripts/extract_todo.py <lang>
python3 - <<'PY'
import json,os
lang="<lang>"; d=json.load(open(f"local/i18n/{lang}_todo.json")); os.makedirs("local/i18n",exist_ok=True)
paths=[]
for i in range(0,len(d),80):
    p=f"local/i18n/{lang}_b{i//80:02d}.json"; json.dump(d[i:i+80],open(p,"w"),ensure_ascii=False); paths.append(p)
print(json.dumps(paths))
PY
```
Then `Workflow({scriptPath: ".../workflows/translate.js", args: {lang, glossaryPath: "<abs .../glossary.json>", batchPaths: [...]}})`. It returns `{lang, map}`; write the map to `local/i18n/<lang>_translations.json` and run `merge_translations.py`.

## `review.js`
Per-language depth reviewers (fluency/terminology) **plus** one cross-language pass for systematic issues (garbled sources, glossary drift, unit/placeholder drift). Returns structured findings, most-severe first. Args: `{base, counts: {lang: n_batches}, xlangCount}` — see the script header.

> These are templates, not turnkey: adjust batch sizes and paths for the job. The authoritative rules they enforce live in [../CONVENTIONS.md](../CONVENTIONS.md).
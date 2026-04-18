---
name: release-notes
description: Generate release notes for a new version by analyzing commits since the last git tag. Groups changes into categorized sections with contributor attribution.
argument-hint: [version]
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(gh *)
---

Generate release notes for this ConnectLife Home Assistant integration release.

## Steps

1. Determine the version to release:
   - If `$ARGUMENTS` is provided, use that as the version
   - Otherwise, read the version from `custom_components/connectlife/manifest.json`

2. Find the previous release tag:
   ```
   git describe --tags --abbrev=0 HEAD
   ```
   If HEAD is already tagged, use `git describe --tags --abbrev=0 HEAD^` to find the previous tag.

3. Get all commits since that tag:
   ```
   git log <previous_tag>..HEAD --pretty=format:"%H %s" --reverse
   ```

4. For each commit, inspect the commit message. Extract:
   - PR number (from `(#123)` in the message)
   - Author (from `git log --format="%an" -1 <hash>` and `git log --format="%ae" -1 <hash>`)
   - For PR commits, get the GitHub username: `gh pr view <number> --json author --jq '.author.login'`

5. Categorize each commit into sections based on its content:
   - **New devices** — commits that add new device mappings (new YAML files in `data_dictionaries/`)
   - **Improvements to existing devices** — commits that update existing device mappings
   - **Bug fixes** — commits with "fix" in the message
   - **Breaking changes** — commits that change existing entity behavior, rename entities, change defaults, or remove properties
   - **General improvements** — code changes, new features, dependency updates
   - **Translation improvements** — translation additions or fixes
   - **Documentation improvements** — README, docs changes
   - Skip commits that are just version bumps

6. For device mapping commits, identify which device types and feature codes were added/changed by looking at the files modified:
   ```
   git diff-tree --no-commit-id --name-only -r <hash>
   ```

7. Come up with a cool release name.

8. Format the release notes following this template. Do NOT include a `v` prefix on the version in the title line.

```markdown
<version> <release name>

## Highlights

<2-4 bullet summary of the most notable changes in this release>
- Do NOT include PR references (#123) or contributor mentions in Highlights — those belong in the detail sections below.

## New devices

- <device_type_code>-<device_feature_code> (<model name if known>) #PR by @contributor
- ...

## Improvements to existing devices

- <device_type_code or device_type_code-feature_code>: <description of change> #PR by @contributor
- ...

## Bug fixes

- <description> #PR by @contributor
- ...

## Breaking changes

- <description of what changed and what users need to do> #PR
- ...

## General improvements

- <description> #PR by @contributor
- ...

## Translation improvements

- <description> #PR by @contributor
- ...

## Contributors

The following have contributed to changes in this release — thank you very much!
<list of @contributor mentions, excluding the repo owner @oyvindwe>

**Full Changelog**: https://github.com/oyvindwe/connectlife-ha/compare/<previous_tag>...v<version>
```

## Rules

- Omit any section that has no entries
- Use `#123` format for PR references (short form, not full URLs)
- Use `@username` format for GitHub contributors
- The repo owner @oyvindwe should not be listed in the Contributors section
- For device mappings, include the device type code and feature code in backticks (e.g., `025-1wj100404v0w`)
- If a model name is known (from the PR title or commit message), include it in parentheses
- Quote property names and field names in backticks (e.g., `DelayEndTime`, `state_class`)
- Keep descriptions concise — one line per item
- The Highlights section should give a quick overview: count of new devices, key fixes, notable features
- Always read the PR body (via `gh pr view <num> --json body --jq '.body'`)
- When a PR body calls out a breaking change is experimental, note that in the entry (e.g., "breaking changes ...")
- When a PR body calls out that a change is experimental, speculative, or untested for certain models/devices, note that in the entry (e.g., "experimental for ...")
- Present the final release notes as a single markdown code block so it can be easily copied

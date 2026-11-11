---
name: draft-release-notes
description: Generate release notes for a new version by analyzing commits since the last git tag. Groups changes into categorized sections with contributor attribution.
argument-hint: [version]
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
   - For a **beta** (`X.Y.ZbN`, see [Branches and releases](../../../CONTRIBUTING.md#branches-and-releases)) after
     `b1`, the previous tag is the previous beta: the notes list only what changed since then.
   - For `b1` and for a **stable** release, the previous tag is the previous stable release: skip beta tags
     (`git describe --tags --abbrev=0 --exclude '*b*' HEAD`), so a stable release lists everything since the last
     stable release, including what its betas had.

3. Get all commits since that tag:
   ```
   git log <previous_tag>..HEAD --pretty=format:"%H %s" --reverse
   ```

4. For each commit, inspect the commit message. Extract:
   - PR number (from `(#123)` in the message)
   - Author (from `git log --format="%an" -1 <hash>` and `git log --format="%ae" -1 <hash>`)
   - For PR commits, get the GitHub username: `gh pr view <number> --json author --jq '.author.login'`

5. Categorize each commit into sections based on its content:
   - **New devices** — commits that add new device mappings (new YAML files in `mappings/`)
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

7. Come up with a cool release name that hasn't been used before. List the earlier names with
   `gh release list --limit 300 --json name --jq '.[].name'` (older titles start with the version, e.g.
   "0.47.0 Fine Print"), and pick one that doesn't match any of them, ignoring case.
   - **Betas** are named after their final release, with the beta number: "<final name> bN" (e.g. "Opening Night b1"
     for `1.0.0b1`). Pick the final name at `b1`; later betas and the stable release reuse it (the stable release
     without the suffix). Find it from the earlier betas of the same version in the release list.

8. Format the release notes following this template. The first line is the release title: the release name only,
   without the version. HACS already shows the tag in front of it ("v0.52.0 - <release name>").
   For a beta, put this right after the title, before Highlights (link the previous beta's notes from `b2` on):

   > **This is a beta of X.Y.Z.** <It includes breaking changes (see below).> To get it, turn on the integration's
   > **Pre-release** switch: an entity on the ConnectLife device under the Marketplace (or HACS) integration,
   > disabled by default, so enable the entity first. Please report problems in an issue and mention the beta.
   > <From b2: Changes since bN-1; see the [bN-1 notes](<link>) for the rest.>

```markdown
<release name>

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
- Omit the Highlights section for patch releases (`x.y.Z` with Z > 0): with only a few entries it repeats them
- Always read the PR body (via `gh pr view <num> --json body --jq '.body'`)
- When a PR body calls out a breaking change is experimental, note that in the entry (e.g., "breaking changes ...")
- When a PR body calls out that a change is experimental, speculative, or untested for certain models/devices, note that in the entry (e.g., "experimental for ...")
- Present the final release notes as a single markdown code block so it can be easily copied

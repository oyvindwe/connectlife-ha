---
name: bump-version
description: Bump the integration version, create a branch, commit, push, and open a PR.
argument-hint: <version>
allowed-tools: Read Edit Bash(git *) Bash(gh *) Bash(uv sync)
---

Bump the version of this ConnectLife Home Assistant integration.

## Steps

1. Determine the new version:
   - If `$ARGUMENTS` is provided, it must be a valid semver version (e.g., `0.31.0`). Use it as the new version.
   - If not provided, determine the next version via semver by analyzing commits since the last release:
     1. Read the current version from `custom_components/connectlife/manifest.json`.
     2. List commits since the last version bump:
        ```
        git log --oneline "$(git log --grep='^Version ' -n 1 --format=%H)..HEAD"
        ```
        (Falls back to `git log --oneline -n 20` if no prior version commit is found.)
     3. Classify the bump based on the commit subjects and diffs. **Note:** this project is on `0.x.y`, where per semver the public API is considered unstable — breaking changes do **not** trigger a `1.0.0` release on their own, they bump MINOR. Reserve a MAJOR bump for a deliberate, user-driven `1.0.0` graduation.
        - **MAJOR** (`X.0.0`): only when the user explicitly asks to graduate to `1.0.0` (or beyond). Do not infer this from commit contents alone while on `0.x.y`.
        - **MINOR** (`0.X.0`): new functionality **or** breaking changes — new device mappings/registrations, new properties, new platforms, new entities, additive API changes, removed/renamed entities or options, incompatible config flow changes, minimum HA version raised.
        - **PATCH** (`0.0.X`): backwards-compatible fixes only — bug fixes, translation-only changes, doc/readme tweaks, internal refactors with no user-visible change.
        When in doubt between MINOR and PATCH, pick MINOR.
     4. Compute the next version and show the user: the current version, the classification (major/minor/patch) with a one-line justification referencing the commits, and the proposed new version. Ask for confirmation before proceeding.

2. Verify the working tree is clean:
   ```
   git status --porcelain
   ```
   If there are uncommitted changes, stop and tell the user.

3. Make sure main is up to date:
   ```
   git checkout main
   git pull
   ```

4. Create a version branch:
   ```
   git checkout -b version/<new_version>
   ```

5. Update the version in these files:
   - `custom_components/connectlife/manifest.json` — the `"version"` field
   - `pyproject.toml` — the `version` field

6. Run `uv sync` to update `uv.lock`.

7. Stage and commit:
   ```
   git add custom_components/connectlife/manifest.json pyproject.toml uv.lock
   git commit -m "Version <new_version>"
   ```

8. Push and create PR:
   ```
   git push -u origin version/<new_version>
   gh pr create --title "Version <new_version>" --body "Bump version to <new_version>"
   ```

9. Report the PR URL to the user.

---
name: bump-version
description: Bump the integration version, create a branch, commit, push, and open a PR.
argument-hint: <version>
allowed-tools: Read Edit Bash(git *) Bash(gh *) Bash(uv sync)
---

Bump the version of this ConnectLife Home Assistant integration.

## Steps

1. Determine the new version:
   - `$ARGUMENTS` is required and must be a valid semver version (e.g., `0.31.0`)
   - If not provided, read the current version from `custom_components/connectlife/manifest.json` and ask the user what the new version should be

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
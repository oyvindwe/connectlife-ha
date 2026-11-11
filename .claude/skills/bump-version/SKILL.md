---
name: bump-version
description: Bump the integration version, create a branch, commit, push, and open a PR.
argument-hint: <version>
allowed-tools: Read Edit Bash(git *) Bash(gh *) Bash(uv sync)
---

Bump the version of this ConnectLife Home Assistant integration.

## Steps

1. Determine the new version:
   - If `$ARGUMENTS` is provided, it must be a version like `0.31.0`, or a beta like `1.0.0b1` (see
     [Branches and releases](../../../CONTRIBUTING.md#branches-and-releases)). Use it as the new version.
   - Base branch: `main`, unless the user names a release branch (`release/X.Y`) or a feature branch with its own
     betas. Use that branch wherever these steps say `main`.
   - If not provided, determine the next version via semver by analyzing commits since the last release:
     1. Read the current version from `custom_components/connectlife/manifest.json`.
     2. List commits since the last version bump:
        ```
        git log --oneline "$(git log --grep='^Version ' -n 1 --format=%H)..HEAD"
        ```
        (Falls back to `git log --oneline -n 20` if no prior version commit is found.)
     3. Classify the bump based on the commit subjects and diffs. What counts as breaking is defined in [CONTRIBUTING.md](../../../CONTRIBUTING.md#versioning-and-breaking-changes): removing or changing something that works. Removing or fixing entities that were wrong or never had valid data is not breaking.
        - **MAJOR** (`X.0.0`): on `1.x` and later, breaking changes. On `0.x.y`, only when the user explicitly asks to graduate to `1.0.0`; don't infer it from commit contents.
        - **MINOR** (`0.X.0` / `1.X.0`): new functionality — new device mappings/registrations, new properties, new platforms, new entities, additive API changes, minimum HA version raised. On `0.x.y`, also breaking changes.
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
   gh pr create --base <base branch> --title "Version <new_version>" --body "Bump version to <new_version>"
   ```

9. Report the PR URL to the user.

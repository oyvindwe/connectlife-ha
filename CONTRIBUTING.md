# Contributing

Contributions are welcome, especially mappings for devices that aren't fully supported yet.

- **Device mappings:** see the [mapping docs](custom_components/connectlife/mappings/README.md), and
  [DEVICES.md](DEVICES.md) for the devices that already have one. Attach the device's diagnostics (device page →
  **Download diagnostics**) to the pull request or the linked issue.
- **Translations:** see [Providing translations](DEVELOPMENT.md#providing-translations).
- **Development setup, checks and testing a pull request:** see [DEVELOPMENT.md](DEVELOPMENT.md).

Pull requests are merged with squash. Please describe what the change does and how it was tested; the pull request
template has a checklist.

## Versioning and breaking changes

Versions follow [semver](https://semver.org):
- **Major** for breaking changes. Before 1.0.0, breaking changes come in minor versions, as semver allows for
  `0.x`, with a line in the release notes.
- **Minor** for new features, new device mappings and raising the minimum Home Assistant version (we support the
  releases from the last 12 months; HACS and the Marketplace don't offer releases an installation can't run).
- **Patch** for fixes.

A change is breaking when it removes or changes something that **works** and that users rely on:
- Removing a working control or entity, or changing its platform (e.g. a working select becomes buttons).
- Changing an entity's unique ID, so its entity ID and history are lost.
- Removing or renaming an action or one of its fields, or a config or device option.

Not breaking, but listed in the release notes with what users need to do:
- Fixing something that was wrong or never had valid data: removing or disabling entities that were always 0, empty
  or unavailable; correcting inverted states, options, units, device classes or state classes. This includes fixes
  that make Home Assistant raise a statistics repair.
- New entities, options and actions.
- Changing an entity's display name (the entity ID stays).
- Changing defaults that only apply to new entities (`hide`, `optional`, `entity_category`).

Deprecation: before a major that removes something, keep it working for at least one minor release where possible,
with a log warning or repair issue that says what to use instead.

## Branches and releases

- **`main` is the next release.** Pull requests target `main`. A release bumps the version in a `Version X.Y.Z`
  pull request, then tags `vX.Y.Z` on `main` and publishes a GitHub release.
- **Betas** (`X.Y.ZbN`, e.g. `1.0.0b1`) are also tagged on `main`, as GitHub pre-releases. Use them for releases
  with breaking or risky changes, so users can try them first. The Marketplace (and HACS) offers pre-releases only
  to users who turn on the integration's **Pre-release** switch (an entity on its Marketplace or HACS device,
  disabled by default). Fixes go out as `b2`, `b3`, …; the stable release follows on `main`.
  A beta is titled after its final release, with the beta number (e.g. "Opening Night b1" for `1.0.0b1`); its
  notes list what changed since the previous beta, and the stable release's notes everything since the last stable
  release.
- **While a beta of `main` is out**, merge only what should ship in that release: fixes and new device mappings,
  no new breaking changes. Hold other pull requests until the stable release.
- **Release branches only when needed**: to fix the current stable release while `main` holds changes that must not
  ship yet (e.g. during a beta), branch `release/X.Y` from the `vX.Y.Z` tag, merge the fix there, tag `vX.Y.Z+1` on
  that branch, and merge the fix into `main` too.
- **Experimental features** live on a feature branch with their own betas, numbered after the next minor release
  (e.g. `1.1.0b1` while `main` heads for `1.0.0`), so the Marketplace keeps their testers on the feature through
  the next stable release. To give testers that release's fixes, merge `main` into the feature branch and tag a new
  beta. Once the feature is proven, it's merged into `main` and ships with the next release.

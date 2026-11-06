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

From 1.0.0, versions follow semver:
- **Major** for breaking changes.
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

Before 1.0.0, breaking changes are released in minor versions, with a line in the release notes.

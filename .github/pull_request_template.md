Describe what this changes and why. For device mappings, include the device type and feature
code (e.g. `015-dishwasher-60.3`) and the model.

Fixes #

## Testing

- [ ] Tested on a device (model: )

## Checklist

- [ ] I have searched open pull requests, and found none covering this
- [ ] Mapping changes: attached device diagnostics (device page → **Download diagnostics**), or they are
      attached to the linked issue
- [ ] Mapping changes: ran `uv run python -m scripts.validate_mappings`
- [ ] Mapping or translation changes: ran `uv run python -m scripts.gen_strings`
- [ ] New devices: added the model to `DEVICES.md`

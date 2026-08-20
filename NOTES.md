# Chromebook Toggle Tool - Development Notes

## Status

- Small Python/tkinter application, standard library only, packaged as a
  standalone Windows one-folder build via `Build-EXE.bat`.
- Disables or re-enables ChromeOS devices in Google Workspace through GAM7,
  by individual serial entry, CSV file, or Google Sheet.
- 76 automated unit tests (`python -m unittest discover -v`), covering
  every module except the tkinter GUI itself (manual/scripted smoke-tested
  instead, since assert-based tests have little value against widget code).
- Every GAM command this tool builds was checked directly against GAM7's own
  command reference (`GamCommands.txt`) and, for the parts that could only
  be confirmed by watching real output, against a live GAM7 install - not
  assumed from memory or general documentation.

## Roadmap / ideas

- Preserve partial lookup results if one device in a large batch returns
  malformed data, instead of failing the whole batch (currently a
  deliberate tradeoff - see the comment above `parse_lookup_json` in
  `device_lookup.py`).
- A shared/network copy of the local audit log, for organizations where
  the people running this tool do have shared-folder access (currently
  local-only by design for the tool's original use case).
- A pre-action review table for Google Sheet mode (currently Sheet mode
  reads the sheet directly at execution time, so there is no local list to
  preview beforehand without reading the sheet a second way first).

## Known limitations

- Only Disable and Re-enable actions are supported - no deprovisioning.
- Google Sheet mode's header column must be spelled exactly `Serial`
  (case-sensitive); CSV files are more forgiving (`Serial` or
  `SerialNumber`, any case), since the tool reads and re-normalizes those
  locally before handing them to GAM.
- No organizational-unit/campus restriction is enforced by the tool itself
  - it relies entirely on the operator's own Google Workspace permissions.
- If a single line of a multi-device GAM lookup response is malformed, the
  whole lookup call fails rather than returning partial results (see
  Roadmap above).
- Two runs completed within the same second will overwrite each other's
  local log file (unlikely in practice, since this is a human-driven,
  click-through-a-review-screen tool, not something run in a loop).

## Contributing

Issues and pull requests are welcome. The codebase is split into small,
single-responsibility modules under `chromebook_toggle/` (config, serial
list parsing, Google Sheet URL parsing, GAM command building, JSON
response parsing, review/result orchestration, logging, and the GUI) with
a matching test file per module. Please keep it dependency-free (standard
library only) so it stays easy to build and audit, and keep new logic
covered by real `unittest` tests rather than manual verification alone.

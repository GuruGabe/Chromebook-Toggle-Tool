# Chromebook Toggle Tool - Development Notes

## Status (v1.4)

- Small Python/tkinter application, standard library only, packaged with
  PyInstaller for Windows, macOS and Linux.
- Disables, re-enables and (opt-in) deprovisions ChromeOS devices in Google
  Workspace through GAM7, by individual serial entry, CSV file, or Google
  Sheet.
- Deprovision is hidden unless `allow_deprovision = true` in `settings.ini`
  (also set by the Windows installer's tick-box or `/ALLOWDEPROV=1`). It is
  permanent, so it needs a reason, a red review screen and a typed
  confirmation word; Sheet mode (no preview) shows the sheet URL and warns.
- Self-updater (`updater.py`, `update_apply.py`, `update_flow.py`,
  `update_posix.py`, `update_ui.py`): checks GitHub releases once a day,
  refuses any download whose SHA-256 is not published in the release notes,
  swaps the install safely with rollback, keeps `settings.ini`, `Logs` and
  `state.ini`. No PowerShell involved (EDR-friendly).
- Installers: Inno Setup (`installer/chromebooktoggle.iss`), macOS .dmg
  (`installer/build-macos-dmg.sh`), Linux .deb/.rpm
  (`installer/build-linux-packages.sh`). GitHub Actions
  (`.github/workflows/`) run the tests on every push and build every release
  asset; see `docs/RELEASING.md`.
- 246 automated unit tests (`python -m unittest discover -s tests -t .`),
  covering every module except the tkinter GUI itself. The updater tests use
  a small local stand-in for GitHub (`tests/helpers.py`) - no real network.
- Every GAM command this tool builds was checked directly against GAM7's own
  command reference (`GamCommands.txt`) and, for the parts that could only
  be confirmed by watching real output, against a live GAM7 install - not
  assumed from memory or general documentation.

## What has NOT been verified on real systems

- The macOS and Linux installers/update scripts are built only by CI. The
  Linux update script is tested with a real bash; the macOS one is only
  syntax-checked off a Mac.
- Deprovision has never been run against a real device by the author (it is
  irreversible). Test it on a device you are happy to lose.

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

- Deprovision cannot be undone, and Google Sheet mode cannot preview it.
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
- Versions 1.3 and earlier have no updater; people install 1.4 by hand once.
- Linux .deb/.rpm installs cannot update silently (root-owned `/opt`); the
  app shows the `sudo` command instead.

## Contributing

Issues and pull requests are welcome. The codebase is split into small,
single-responsibility modules under `chromebook_toggle/` (config, serial
list parsing, Google Sheet URL parsing, GAM command building, JSON
response parsing, review/result orchestration, logging, install-location
logic, the self-updater, and the GUI) with
a matching test file per module. Please keep it dependency-free (standard
library only) so it stays easy to build and audit, and keep new logic
covered by real `unittest` tests rather than manual verification alone.

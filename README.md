# Chromebook Toggle Tool

**A point-and-click app (Windows, macOS, Linux) for disabling, re-enabling
or - when IT switches it on - deprovisioning ChromeOS devices in Google
Workspace, for people who don't want to touch a command line.**

It's a small front end for [GAM7](https://github.com/GAM-team/GAM) - pick an
action (Disable or Re-enable, plus Deprovision if IT has turned it on), give
it a list of devices (type/paste serial numbers, a CSV file, or a Google
Sheet), review exactly what's about to happen, confirm, and get a results
screen that shows what actually changed - verified by looking the device up
again afterward, not just trusted from GAM's exit code.

It ships with ready-made installers for each system and **updates itself**
(see [Updating](#updating)).

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Dependencies](https://img.shields.io/badge/dependencies-none%20(standard%20library)-brightgreen)

---

## Why this exists

[GAM](https://github.com/GAM-team/GAM/wiki) can disable or re-enable a
Chromebook in Google Workspace in one command - but it's a command-line
tool, and not everyone who needs to do this (front-desk staff processing a
returned device, a librarian handling a lost-and-found cart) is comfortable
with a terminal, or should need GAM installed and authorized under their
own account to do one specific, everyday task.

This tool wraps that one task in a normal window: pick devices, pick an
action, see a review screen, confirm, done. It never asks the person
running it to type a GAM command or know GAM exists.

> [!IMPORTANT]
> **This tool does not replace GAM - it drives it.** GAM7 must already be
> installed and authorized on the machine this runs on. This tool stores no
> Google credentials of its own; it only shells out to your existing,
> already-authorized `gam.exe`.

---

## What it actually does

- **Three ways to give it a device list:**
  - Type or paste serial numbers, one per line.
  - Point it at a CSV file with a `Serial` or `SerialNumber` column
    (either name, any capitalization).
  - Paste a Google Sheet URL (the sheet's column header must be spelled
    exactly `Serial`, and the sheet must be shared with the Google account
    configured in `settings.ini`).
- **Reviews before it acts.** For individual/CSV input, it looks up every
  device's current status first and shows a table of what will happen -
  including devices that don't exist or are already in the target state,
  which get skipped with a reason, not silently processed.
- **Verifies its own results.** After running the action, it looks each
  device up again and compares before/after status - "success" in the
  results screen means the change was actually confirmed, not just that
  GAM didn't return an error.
- **Logs locally.** Every run writes a timestamped CSV to a `Logs\` folder
  next to the app (no device passwords or user PII beyond the serial
  number and its Workspace-assigned annotated fields).

- **Deprovision (off by default).** Deprovisioning permanently removes a
  device from your Google Workspace management and **cannot be undone**, so
  the option is hidden until IT turns it on (see
  [Turning on Deprovision](#turning-on-deprovision)). When it is on, you
  choose a reason (retiring the device, replacing it with the same or a
  different model, or an upgrade transfer), see a red warning on the review
  screen, and must type the word `DEPROVISION` before the button works. In
  Google Sheet mode there is no preview, so the confirmation shows the sheet's
  address and warns about that loudly.
- **Updates itself.** The app checks GitHub once a day for a newer release
  and offers to install it. Nothing is installed unless the download matches
  the SHA-256 checksum published in the release notes.

Disable, Re-enable and Deprovision are the only actions - this is
intentionally a small, single-purpose tool, not a general GAM front end. (If
you want that, see [GAMGUI](https://github.com/GuruGabe/GAM-GUI-Overlay).)

---

## Get it running

### Step 1 - Set up GAM (one time, required)

This tool needs GAM7 installed and authorized against your Google
Workspace first. Follow GAM's own guide:
**[How to install GAM7](https://github.com/GAM-team/GAM/wiki/How-to-Install-GAM7)**.
You'll need Google Workspace admin rights to authorize it once.

> Not sure GAM is working? Open a terminal and run `gam version` and
> `gam info domain`. If those show your domain, you're ready.

### Step 2 - Get the app

Prebuilt (no Python required). Go to the **[Releases](../../releases)** page
of this repository and download the file for your system (`X.Y` is the
version number):

| System | Installer (recommended) | Portable |
|--------|-------------------------|----------|
| Windows | `ChromebookToggle-X.Y-Setup.exe` | `ChromebookToggle-X.Y-Windows.zip` |
| macOS | `ChromebookToggle-X.Y.dmg` (drag the app to Applications) | `ChromebookToggle-X.Y-macOS.zip` |
| Linux (Debian/Ubuntu) | `chromebooktoggle_X.Y_amd64.deb` | `ChromebookToggle-X.Y-Linux.tar.gz` |
| Linux (Fedora/RHEL) | `chromebooktoggle-X.Y-1.x86_64.rpm` | `ChromebookToggle-X.Y-Linux.tar.gz` |

**Windows installer:** run `Setup.exe`. It asks whether to install for all
users (needs administrator approval) or just you (no approval needed), adds a
Start Menu entry and an optional desktop shortcut, and shows up in Windows'
*Installed apps* list so it can be uninstalled normally. Your `settings.ini`
is never overwritten by an upgrade.

**Windows portable zip:** unzip it and keep the whole `ChromebookToggle`
folder together (the `.exe` needs the `_internal` folder next to it).

**Installing without clicking through the wizard (IT)** - the Windows
installer takes the usual Inno Setup switches plus a few of its own:

```bat
ChromebookToggle-X.Y-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS ^
    /GAMPATH="C:\GAM7\gam.exe" /SHEETEMAIL="gam-admin@your-domain.example" /ALLOWDEPROV=1
```

`/GAMPATH`, `/SHEETEMAIL` and `/ALLOWDEPROV=1` write the matching
`settings.ini` values; leave a switch off and that setting is left exactly as
it is. `/CURRENTUSER` installs for just the person running it.

**Settings:** edit `settings.ini` in the app's folder. (A Windows Setup.exe
install keeps it in the install folder; the Linux .deb/.rpm keeps it at
`/opt/ChromebookToggle/settings.ini`. On macOS the app is signed, so editing a
file inside it would break the signature - instead create
`~/Library/Application Support/ChromebookToggle/settings.ini` and the app
uses that.)

- `gam_path` - update if `gam.exe` isn't at `C:\GAM7\gam.exe`.
- `sheet_acting_email` - **required if you'll use Google Sheet input.**
  It ships set to the placeholder `gam-admin@example.com`, which is not
  a real account and will not work as-is. Change it to a real Google
  Workspace account in your own domain that GAM is authorized to act
  as - every Google Sheet you want to read must be shared with that
  same account (see [What it actually does](#what-it-actually-does)).
  Individual-entry and CSV input don't use this value at all, so you
  can skip this if you'll only ever use those two modes.
- `allow_deprovision` - `false` by default; see
  [Turning on Deprovision](#turning-on-deprovision).
- `check_for_updates` - `true` by default; set `false` to stop the daily
  update check (you can still use **Help -> Check for updates now**).

**Starting it:** open it from the Start Menu / desktop shortcut (installer),
double-click `ChromebookToggle.exe` (portable zip), or open the app from
Applications (macOS) or your applications menu / `chromebooktoggle` (Linux).
The apps are not code-signed with a paid certificate, so Windows may warn
about an unrecognized publisher (choose **More info -> Run anyway**) and macOS
asks you to approve the app once (see [macOS Gatekeeper](#macos-gatekeeper)).

Prefer to build it yourself? See [Running and building from source](#running-and-building-from-source-windows-macos-linux).

### Step 3 - First launch

The app checks that `gam.exe` is reachable at startup and tells you clearly
if it isn't, rather than letting you attempt a lookup that will just fail.
Try Individual mode with one real serial number first, confirm the review
screen shows accurate data, and cancel out before confirming anything - a
safe way to check everything is wired up correctly before running a real
action.

---

## Turning on Deprovision

Deprovisioning **permanently** takes a device out of your Google Workspace
management. It cannot be undone from this tool (or from Google's console), so
the option does not appear at all until someone with access to the computer
turns it on. Any one of these works:

- **Installer:** tick *Allow the PERMANENT Deprovision action* in the Windows
  Setup wizard, or run Setup silently with `/ALLOWDEPROV=1`.
- **Any install:** open `settings.ini` and set `allow_deprovision = true`.
  Set it back to `false` to hide the option again.

With it on, the main window gains a third choice. Deprovision always asks for
a reason, which GAM records in Google:

| Reason shown in the window | GAM action word |
|----------------------------|-----------------|
| Retiring the device | `deprovision_retiring_device` |
| Replacing it with the same model | `deprovision_same_model_replace` |
| Replacing it with a different model | `deprovision_different_model_replace` |
| Upgrade transfer | `deprovision_upgrade_transfer` |

Safeguards: the review screen is red and says the action is permanent; the
confirm button only works after you type `DEPROVISION`; devices that are
already deprovisioned are skipped; each device is verified afterward like any
other action. In Google Sheet mode there is no per-device preview (GAM reads
the sheet at the moment you confirm), so the confirmation shows the sheet's
address and you must type the word to continue - **check the sheet first.**

Because it cannot be undone, test Deprovision on a device you are happy to
lose, not on one in service.

---

## Updating

The app asks GitHub for the newest release once a day (and any time you choose
**Help -> Check for updates now**). If there is one, it shows what changed and
asks before doing anything. It then:

1. downloads the file for *your kind of install* (Setup.exe, portable zip,
   macOS zip, Linux tar.gz or package),
2. refuses to continue unless the download's SHA-256 equals the one published in
   that release's notes (a release without a published checksum is never
   installed),
3. closes itself, swaps in the new version - keeping your `settings.ini`, the
   `Logs` folder and your other files, and putting the old version back if
   anything goes wrong - and starts the new version.

How each kind of install updates:

| Install | What happens |
|---------|--------------|
| Windows, per-user Setup.exe or portable zip | Updates fully by itself. |
| Windows, all-users Setup.exe (Program Files) | Runs the new Setup.exe silently; Windows asks for administrator approval once. |
| macOS .app | Replaced with the new, signature-checked app. |
| Linux portable tar.gz | Files replaced in place. |
| Linux .deb / .rpm | The package is downloaded and checked, then the app shows the one `sudo` command that installs it (a normal user cannot write to `/opt`). |
| Run from source | Does not update itself; use `git pull`. |

The update check only talks to GitHub. To turn it off, set
`check_for_updates = false` in `settings.ini`. Versions 1.3 and earlier have no
updater, so install 1.4 or newer by hand once.

---

## Safety notes (please read)

- **It can do whatever the configured GAM identity can do.** This tool has
  no permission model of its own - whoever can run it can disable/re-enable
  any device that identity has rights to. Google Workspace's own
  organizational-unit permissions are what should actually scope this, not
  the tool.
- **Deprovision is permanent** and hidden unless IT turns it on; read
  [Turning on Deprovision](#turning-on-deprovision) first.
- **You always see a review screen before anything changes** for
  Individual/CSV input. Google Sheet mode has no per-device preview (GAM
  reads the sheet directly at the moment you confirm) - double-check the
  sheet's contents before confirming.
- **Results are independently verified**, not just assumed from GAM's exit
  code - see [What it actually does](#what-it-actually-does) above.
- **Test with one device first** when setting this up in a new
  environment, the same way you would test any new admin tool.

---

## Running and building from source (Windows, macOS, Linux)

This tool is standard-library-only Python (tkinter), so it runs on all
three platforms. You still need GAM7 installed and authorized on whichever
machine actually runs it (see [Get it running](#get-it-running) above) -
that part is Windows/macOS/Linux-agnostic too, since GAM7 itself is
cross-platform.

### Run without building (simplest)

Requires Python 3.10+ **with tkinter**:

- **Windows** - tkinter is included with the python.org installer:
  ```bat
  py ChromebookToggle.py
  ```
- **macOS** - the python.org installer includes tkinter. If you use
  Homebrew Python, add it first with `brew install python-tk`:
  ```bash
  python3 ChromebookToggle.py
  ```
- **Linux** - install tkinter from your package manager, then run it:
  ```bash
  # Debian/Ubuntu:
  sudo apt install python3 python3-tk
  # Fedora/RHEL:
  sudo dnf install python3 python3-tkinter
  # Arch:
  sudo pacman -S tk
  python3 ChromebookToggle.py
  ```

Run the test suite the same way on any platform:

```bash
python -m unittest discover -v
```

### Build a standalone app (PyInstaller)

Install PyInstaller once: `pip install pyinstaller` (or `pip3 install ...`).

- **Windows:**
  ```bat
  Build-EXE.bat
  ```
- **macOS / Linux:**
  ```bash
  chmod +x build-app.sh
  ./build-app.sh
  ```

Both scripts run `extract_tcl.py`, then PyInstaller in one-folder mode,
then copy `settings.ini` directly beside the built executable. The result
is `dist/ChromebookToggle/` - copy the whole folder and keep it together
(on macOS you also get a `dist/ChromebookToggle.app` bundle). Run
`dist/ChromebookToggle/ChromebookToggle` (or the `.app`).

Prefer the raw PyInstaller command?

```bash
# Python 3.13 or earlier (Tcl/Tk 8.6): no extract step needed.
pyinstaller --onedir --windowed --name ChromebookToggle ChromebookToggle.py

# Python 3.14+ (Tcl/Tk 9): extract the Tcl data first, then bundle it.
python3 extract_tcl.py
pyinstaller --onedir --windowed --name ChromebookToggle \
    --add-data "build_res/_tcl_data:_tcl_data" \
    --add-data "build_res/_tk_data:_tk_data" \
    ChromebookToggle.py
```

macOS/Linux use a colon (`:`) in `--add-data`; Windows uses a semicolon
(`;`). Either way, copy `settings.ini` next to the built executable
afterward - it isn't bundled automatically by design (see
[Project files](#project-files)).

### Build the installers yourself

The installers are built from the one-folder app above:

- **Windows Setup.exe** - install [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  (`winget install JRSoftware.InnoSetup`), run `Build-EXE.bat`, then from the
  repository folder:
  ```bat
  iscc /DMyAppVersion=1.4 installer\chromebooktoggle.iss
  ```
  This writes `ChromebookToggle-1.4-Setup.exe` in the repository folder. Use the
  number in `chromebook_toggle/version.py`.
- **macOS .dmg** - after `./build-app.sh`: `bash installer/build-macos-dmg.sh 1.4`
  (stamps the version, re-signs the app ad-hoc, verifies it, writes the .dmg).
- **Linux .deb and .rpm** - after `./build-app.sh`, with
  [fpm](https://fpm.readthedocs.io/) installed (`gem install fpm`):
  `bash installer/build-linux-packages.sh 1.4`.

Releases are normally built by GitHub Actions on all three systems at once -
see [docs/RELEASING.md](docs/RELEASING.md).

### Why the extract step, and why it drops `.enc` files

Tcl/Tk 9 stores its script library inside the Tcl shared library as a
virtual zip filesystem, which PyInstaller doesn't bundle on its own -
without this step the app crashes at startup with `Tcl data directory
_tcl_data not found`. `extract_tcl.py` also deletes the loose
`encoding/*.enc` tables after extracting everything else, since some
endpoint security products block files with the `.enc` extension outright
(it resembles ransomware-encrypted output) - Tcl keeps its own internal
copies of those same tables and falls back to them automatically when the
loose files are absent. On Python 3.13 or earlier you can skip this step
entirely.

### macOS Gatekeeper

The app is signed "ad-hoc" (free) rather than with a paid Apple Developer
certificate, so macOS says it cannot verify it the first time. Approve it once:
right-click the app and choose **Open** (then **Open** again), or go to
**System Settings -> Privacy & Security** and click **Open Anyway**. Or clear
the quarantine flag from a terminal:

```bash
xattr -dr com.apple.quarantine /Applications/ChromebookToggle.app
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "gam.exe was not found at: ..." on startup | GAM7 isn't installed at the path configured in `settings.ini`, or the network path its own config depends on is unreachable. |
| CSV rejected with a column-header error | The file needs a column named `Serial` or `SerialNumber` (any capitalization) in its header row. |
| Google Sheet fails to read | Confirm the sheet is shared with the account set as `sheet_acting_email` in `settings.ini`, and that its header row has a column named exactly `Serial`. |
| No Deprovision choice in the window | Deprovision is off by default. See [Turning on Deprovision](#turning-on-deprovision). |
| "cannot update itself" | The copy is run from source, or sits in a folder the app is not allowed to change. Download the new release from the Releases page. |
| "no published checksum" when updating | The release notes lack a `SHA-256 (<file>):` line for your file, so the app will not install it. Download it by hand from the Releases page. |
| "Windows protected your PC" on launch | The app isn't code-signed. Click **More info -> Run anyway**. |
| `Tcl data directory _tcl_data not found` (building yourself) | Run `extract_tcl.py` before PyInstaller, or just use `Build-EXE.bat`. |

---

## Project files

| File | Purpose |
|------|---------|
| `ChromebookToggle.py` | Entry point - creates the Tk root and launches the GUI |
| `chromebook_toggle/` | The application: settings, serial/CSV/Sheet-URL parsing, GAM command building, response parsing, review/result logic, logging, the self-updater, and the GUI |
| `tests/` | Unit tests, one file per module (`python -m unittest discover -v`) |
| `extract_tcl.py` | Build helper: bundles Tcl/Tk data for Python 3.14+, drops `.enc` files |
| `Build-EXE.bat` | One-command build (Windows) |
| `installer/` | Inno Setup script (Windows), `.dmg` and `.deb`/`.rpm` build scripts, release-notes helper |
| `.github/workflows/` | Tests on every push, and the release build that makes all installers |
| `docs/RELEASING.md` | How a release is made |
| `build-app.sh` | One-command build (macOS / Linux) |
| `settings.ini` | Runtime config (`gam_path`, `sheet_acting_email`, `allow_deprovision`, `check_for_updates`) - edit after deployment, no rebuild needed |
| `README.txt` | Full plain-English reference and troubleshooting |
| `CHANGELOG.txt` | Version history |
| `NOTES.md` | This file - status, roadmap, known limitations |

---

## Contributing

Issues and pull requests are welcome. Each module under `chromebook_toggle/`
has one clear responsibility and its own test file - please keep new logic
covered by real `unittest` tests, and keep the app dependency-free
(standard library only) so it stays easy to build and audit.

## License and disclaimer

Created by Gabriel Clifton, built with Claude. Licensed under the
[Apache License 2.0](LICENSE).

This tool runs real administrative commands against a live Google
Workspace through GAM. Review the review screen before confirming any
action, and test against a single device first in a new environment.
Provided **as-is, without warranty**. This is an independent project and
is **not affiliated with or endorsed by** the GAM project or Google.

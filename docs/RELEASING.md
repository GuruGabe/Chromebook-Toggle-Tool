# How a release is made

A release is a GitHub release plus seven files. GitHub Actions builds all of
them (Windows, macOS and Linux each build on their own machine), and publishes
the SHA-256 of every file in the release notes. **The in-app updater will not
install a file whose checksum is not in the notes**, so the last job matters.

| File | Built on | Used by |
|------|----------|---------|
| `ChromebookToggle-X.Y-Setup.exe` | Windows | Windows installer; also what Setup-installed copies update with |
| `ChromebookToggle-X.Y-Windows.zip` | Windows | Portable Windows copy and its updates |
| `ChromebookToggle-X.Y.dmg` | macOS | Drag-to-Applications installer |
| `ChromebookToggle-X.Y-macOS.zip` | macOS | macOS in-app updates |
| `ChromebookToggle-X.Y-Linux.tar.gz` | Linux | Portable Linux copy and its updates |
| `chromebooktoggle_X.Y_amd64.deb` | Linux | Debian/Ubuntu package |
| `chromebooktoggle-X.Y-1.x86_64.rpm` | Linux | Fedora/RHEL package |

(`X.Y` has no leading `v`; the Git tag does: tag `v1.4`, files `...-1.4-...`.)
Do not rename these files - `chromebook_toggle/updater.py` (`asset_name`)
looks for exactly these names.

## Steps

1. **Bump the version** in `chromebook_toggle/version.py` (`APP_VERSION`).
2. **Add a CHANGELOG entry** at the bottom of `CHANGELOG.txt`, headed
   `MM-DD-YYYY - vX.Y Short title`. It becomes the release notes. A unit test
   fails if the newest entry and `APP_VERSION` disagree.
3. **Run the tests** locally: `python -m unittest discover -s tests -t .`
   (the `Tests` workflow also runs on every push).
4. **Commit and push** to `main`; wait for the `Tests` workflow to go green.
5. **Run the release build:** GitHub > *Actions* > *Build installers* >
   *Run workflow* > enter the tag (`v1.4`).
   - It stops at once if the tag and `APP_VERSION` differ.
   - If the release does not exist it is created from that CHANGELOG entry,
     tagged at the commit the workflow ran on. If it already exists, its notes
     are left alone and the files are (re)attached.
   - The last job downloads all seven files, writes a
     `## Checksums (SHA-256)` block with one `SHA-256 (<file>):` line per file
     into the notes (replacing an older block if you re-run), and fails if it
     does not find exactly seven files.
6. **Check the release page:** seven files attached, checksums in the notes.
7. **Try the updater** from the previous version on at least one machine
   (Help > Check for updates now). This is the real proof that the file names
   and checksums line up.

## Things to know

- **Re-running is safe.** Files are uploaded with `--clobber` and the checksum
  block is rewritten, so you can re-run after fixing a failed OS job.
- **A hand-edited release** that loses the `SHA-256` lines cannot be installed
  by the updater (people see "no published checksum"). Re-run the workflow to
  put them back.
- **The macOS app is signed ad-hoc, not notarized** (no paid Apple account is
  used). `installer/build-macos-dmg.sh` re-signs after stamping the version,
  because a changed Info.plist with an old signature is what macOS calls
  "damaged".
- **Windows Inno Setup AppId** (`installer/chromebooktoggle.iss`) must never
  change, or upgrades will install side by side instead of replacing.
- **Python version** for builds is set in the workflow (`3.14`). Python 3.14+
  uses Tcl/Tk 9, which is why `extract_tcl.py` runs before PyInstaller.
- **Nothing here needs a secret.** The workflow uses the automatic
  `GITHUB_TOKEN` only.

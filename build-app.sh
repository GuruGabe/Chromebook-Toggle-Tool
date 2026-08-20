#!/usr/bin/env bash
# =============================================================================
# build-app.sh - build the Chromebook Toggle Tool as a one-folder app on
# macOS / Linux. The macOS/Linux counterpart to Build-EXE.bat. Result:
# dist/ChromebookToggle/ (run the ChromebookToggle executable inside it; on
# macOS you also get dist/ChromebookToggle.app).
#
# Why the extract step:
#   Python 3.14 uses Tcl/Tk 9, which keeps its script library inside the Tcl
#   shared library as a virtual zip filesystem. PyInstaller does not bundle it,
#   so the app would crash at startup with "Tcl data directory _tcl_data not
#   found". extract_tcl.py pulls that library out to disk (and drops the .enc
#   encoding tables, which some endpoint security blocks) so it can be bundled
#   with --add-data. On Python 3.13 or earlier this step is harmless.
#
# Requirements:
#   - Python 3.10+ WITH tkinter
#       Debian/Ubuntu: sudo apt install python3 python3-tk
#       Fedora/RHEL:   sudo dnf install python3 python3-tkinter
#       Arch:          sudo pacman -S tk
#       macOS:         python.org Python includes tkinter; Homebrew Python needs
#                      'brew install python-tk'
#   - PyInstaller:  pip install pyinstaller
# =============================================================================
set -e

# Work from this script's own folder so relative paths are predictable.
cd "$(dirname "$0")"

# Pick an interpreter (prefer python3).
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
    echo "Python 3 was not found on PATH."
    exit 1
fi

# Verify PyInstaller is available.
if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is not installed. Run:  $PY -m pip install pyinstaller"
    exit 1
fi

# Step 1: extract the Tcl/Tk libraries so they can be bundled.
echo "Extracting Tcl/Tk libraries..."
"$PY" extract_tcl.py

# Step 2: build one-folder, bundling the extracted Tcl/Tk data.
#   (macOS/Linux use a ':' separator in --add-data; Windows uses ';'.)
#   -y overwrites a previous dist/ build without prompting, so re-running
#   this script after a code change doesn't require manually deleting dist/
#   first (PyInstaller otherwise hard-errors "output directory is not empty"
#   when run non-interactively).
"$PY" -m PyInstaller --onedir --windowed -y --name ChromebookToggle \
    --add-data "build_res/_tcl_data:_tcl_data" \
    --add-data "build_res/_tk_data:_tk_data" \
    ChromebookToggle.py

# Step 3: copy the default settings.ini so it lands directly beside the
# executable (NOT inside _internal/) - this is the file you edit per
# deployment (gam_path, sheet_acting_email) without rebuilding, so it needs
# to be immediately visible, not buried among PyInstaller's support files.
echo "Copying default settings.ini next to the executable..."
cp settings.ini dist/ChromebookToggle/settings.ini

# On macOS, PyInstaller --windowed also produces a proper .app bundle whose
# real executable lives inside Contents/MacOS/ rather than at dist/App/App -
# copy settings.ini there too so the app finds it however it's launched
# (double-clicked as a .app, or run directly from dist/ChromebookToggle/).
if [ -d "dist/ChromebookToggle.app/Contents/MacOS" ]; then
    cp settings.ini "dist/ChromebookToggle.app/Contents/MacOS/settings.ini"
fi

echo
echo "Build complete: dist/ChromebookToggle/"
echo "Run the ChromebookToggle executable inside that folder (keep the folder"
echo "together, and settings.ini next to it)."
echo "On macOS you can also open dist/ChromebookToggle.app (right-click ->"
echo "Open the first time, since the app is not code-signed)."

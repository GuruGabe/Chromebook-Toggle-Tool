# ChromebookToggle.py
#
# Script:   ChromebookToggle.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Entry point for the Chromebook Toggle Tool. Creates the Tk root window
#   and launches ChromebookToggleApp (chromebook_toggle/gui.py). This is
#   the file PyInstaller packages as the EXE for deployment to district
#   PCs - kept deliberately tiny (window
#   setup only) so all of the tool's real logic stays in the tested
#   chromebook_toggle package, not in the one file that only ever runs as
#   a packaged EXE.
#
# Usage:
#   python ChromebookToggle.py
#
# Requirements:
#   Python 3 with tkinter (stdlib - already present in a normal python.org
#   install), and GAM7 installed locally with its oauth2 config already
#   set up (see README.txt). No admin rights are required to run this
#   script itself; GAM's own commands may require whatever rights GAM's
#   Workspace admin account already has.
#
# Notes:
#   settings.ini and the Logs folder are both resolved relative to this
#   file's own location (not the current working directory), so the tool
#   behaves the same whether it is launched by double-click, from a
#   shortcut, or from a shell in some other folder.

import os
import sys
import tkinter as tk

from chromebook_toggle.gui import ChromebookToggleApp, APP_TITLE

# Resolve this tool's "home" folder so settings.ini and Logs\ are found in
# the same place whether running from source or as a packaged EXE.
#   - Frozen (PyInstaller-built EXE): sys.frozen is set by the bootloader,
#     and sys.executable is the path to ChromebookToggle.exe itself. Using
#     __file__ here would resolve to the temp/_internal extraction folder
#     instead of the folder the admin actually copied the EXE into, which
#     is NOT where Build-EXE.bat places settings.ini (it copies settings.ini
#     next to the EXE, not into _internal\). sys.executable is the correct,
#     standard way to find "where the EXE lives" once frozen.
#   - Not frozen (running ChromebookToggle.py directly with python.exe):
#     fall back to this script's own folder, same as before.
if getattr(sys, "frozen", False):
    _HERE = os.path.dirname(sys.executable)
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))

# Shipped default settings.ini lives next to this script (and next to the
# packaged EXE after a PyInstaller build - Build-EXE.bat copies it there
# directly, so it stays visible instead of buried inside _internal\).
_SETTINGS_PATH = os.path.join(_HERE, "settings.ini")

# Logs\ is created at runtime on first write (logging_util.write_log() uses
# os.makedirs(..., exist_ok=True)) - this tool does not need to create it
# up front here.
_LOG_DIR = os.path.join(_HERE, "Logs")


def main():
    # Build the Tk root window that the whole app lives inside.
    root = tk.Tk()
    root.title(APP_TITLE)
    # Starting size chosen to comfortably fit the review/results tables
    # without the admin having to resize the window on first launch; the
    # window remains resizable (tk.Tk()'s default) if a bigger view of a
    # long device list is needed.
    root.geometry("700x520")

    # ChromebookToggleApp is a tk.Frame subclass that packs itself into
    # root and builds its own first screen - see chromebook_toggle/gui.py.
    ChromebookToggleApp(root, settings_path=_SETTINGS_PATH, log_dir=_LOG_DIR)

    # Hands control to Tk's event loop - blocks here until the window is
    # closed, dispatching button clicks, the after() calls the background
    # threads schedule, etc.
    root.mainloop()


if __name__ == "__main__":
    main()

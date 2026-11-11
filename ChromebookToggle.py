# ChromebookToggle.py
#
# Script:   ChromebookToggle.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 11-10-2026
# Version:  1.6
#
# Purpose:
#   Entry point for the Chromebook Toggle Tool. Creates the Tk root window
#   and launches ChromebookToggleApp (chromebook_toggle/gui.py). This is
#   the file PyInstaller packages as the EXE - kept deliberately tiny so all
#   of the tool's real logic stays in the tested chromebook_toggle package.
#
#   It also has a second, window-less job: when the self-updater hands an
#   update over, the NEW copy of this program is started with
#   --apply-update (see chromebook_toggle/update_apply.py). In that mode it
#   waits for the old copy to close, swaps the files in, restarts the app,
#   and never opens a window of its own.
#
# Usage:
#   python ChromebookToggle.py
#   ChromebookToggle.exe                       (the built app)
#   ChromebookToggle.exe --apply-update ...    (only ever run by the updater)
#
# Requirements:
#   Python 3 with tkinter (stdlib - already present in a normal python.org
#   install), and GAM7 installed locally with its oauth2 config already
#   set up (see README.txt). No admin rights are required to run this
#   script itself; GAM's own commands may require whatever rights GAM's
#   Workspace admin account already has.
#
# Notes:
#   WHERE THINGS LIVE. settings.ini is read from the folder this program
#   lives in. The Logs folder and the small state file go next to it when
#   that folder is writable, otherwise to the signed-in person's own
#   application-data folder (a standard user cannot write to Program Files).
#   chromebook_toggle/paths.py makes that decision and is unit-tested.

import sys


def main():
    # Update-apply mode comes first and imports nothing graphical: it runs
    # from a temporary folder, has no window, and must be as small and
    # predictable as possible.
    if "--apply-update" in sys.argv:
        from chromebook_toggle import update_apply
        return update_apply.apply_update_main(sys.argv[1:])

    # Administrator switches for the permanent Deprovision action
    # (--set-deprovision on|off|clear, --deprovision-status). Also windowless:
    # they change a machine-wide setting and exit (see policy.py).
    from chromebook_toggle import policy
    if policy.is_policy_command(sys.argv):
        return policy.cli_main(sys.argv, say=policy.make_say(), elevate=policy.elevate_windows)

    import tkinter as tk

    from chromebook_toggle import paths, update_apply, version
    from chromebook_toggle.gui import APP_TITLE, ChromebookToggleApp

    # Tidy up work folders left behind by earlier updates (a finished update
    # cannot delete the folder its own program ran from). Purely housekeeping:
    # a failure here must never stop the app starting.
    try:
        update_apply.cleanup_old_work_dirs()
    except Exception:
        pass

    # Where settings.ini, the Logs folder and the state file are. When run
    # from source, "the app folder" is the folder this script is in.
    locations = paths.resolve(paths.app_dir(script_file=__file__))

    # Build the Tk root window that the whole app lives inside.
    root = tk.Tk()
    # The version in the title bar makes "which version are you on?" a
    # question that answers itself in a support call.
    root.title(APP_TITLE + " " + version.APP_VERSION)
    # Starting size chosen to comfortably fit the review/results tables
    # without the admin having to resize the window on first launch; the
    # window remains resizable (tk.Tk()'s default) if a bigger view of a
    # long device list is needed.
    root.geometry("700x540")

    # ChromebookToggleApp is a tk.Frame subclass that packs itself into
    # root and builds its own first screen - see chromebook_toggle/gui.py.
    ChromebookToggleApp(root, locations)

    # Hands control to Tk's event loop - blocks here until the window is
    # closed, dispatching button clicks, the after() calls the background
    # threads schedule, etc.
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

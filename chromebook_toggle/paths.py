# chromebook_toggle/paths.py
#
# Script:   paths.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   Decides WHERE the app keeps its files, so the same code works whether it
#   is run from source, copied to a folder (portable), or installed by the
#   Setup.exe / .dmg / .deb / .rpm into a protected location such as
#   C:\Program Files.
#
#     settings.ini  - always read from the folder the app lives in. An
#                     administrator edits it; the app never needs to write it.
#     Logs\         - the audit logs. Written next to the app when that
#                     folder is writable (portable copy, per-user install),
#                     otherwise to the signed-in person's own application
#                     data folder, because a standard user cannot write to
#                     Program Files and the log would silently fail.
#     state.ini     - tiny per-person notes (when updates were last checked).
#                     Lives beside the Logs folder.
#
# Notes:
#   Pure functions: nothing here touches the screen or the network, and the
#   system, environment and "is this folder writable" test can all be
#   passed in, so tests\test_paths.py can check every case on any OS.

import collections
import os
import sys
import tempfile

# File and folder names, spelled once.
SETTINGS_FILENAME = "settings.ini"
STATE_FILENAME = "state.ini"
LOGS_DIRNAME = "Logs"
APP_DATA_NAME = "ChromebookToggle"

# Everything the rest of the app needs to know about where things are.
Locations = collections.namedtuple(
    "Locations", "app_dir settings_path data_dir log_dir state_path")


def app_dir(frozen=None, executable=None, script_file=None):
    # The folder the app lives in.
    #   Frozen (a PyInstaller build): sys.executable is the real
    #     ChromebookToggle.exe, so its folder is where the person installed
    #     or copied the app. __file__ would point into the temporary
    #     "_internal" extraction area instead, which is not where
    #     settings.ini is.
    #   Not frozen (python ChromebookToggle.py): the entry script's folder.
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    if frozen:
        return os.path.dirname(os.path.abspath(executable or sys.executable))
    return os.path.dirname(os.path.abspath(script_file or sys.argv[0]))


def is_writable(folder):
    # True if a file can actually be created in this folder right now. Tried
    # for real (instead of asking os.access) because on Windows os.access
    # reports "writable" for folders UAC will in fact refuse, such as
    # Program Files. The probe file is removed again immediately; a folder
    # that does not exist counts as not writable.
    if not os.path.isdir(folder):
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".ctt-write-test-"):
            pass
        return True
    except OSError:
        return False


def user_data_dir(system=None, env=None, home=None):
    # The signed-in person's own place for app data, following each OS's
    # convention. Used only when the app's own folder is not writable.
    system = system or sys.platform
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    if system.startswith("win"):
        base = env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    elif system == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_DATA_NAME)


def in_app_bundle(app_folder, system=None):
    # True on macOS when the app's folder is inside a ChromebookToggle.app
    # bundle (.../X.app/Contents/MacOS). Anything written into a signed bundle
    # breaks its code signature, and on Apple Silicon a broken signature means
    # the app will not launch at all - so nothing may be written there.
    system = system or sys.platform
    if system != "darwin":
        return False
    # Split on BOTH kinds of slash so the answer does not depend on which OS
    # is asking (the unit tests check macOS-style paths from Windows).
    parts = app_folder.replace("\\", "/").split("/")
    return any(part.endswith(".app") for part in parts[:-1])


def resolve(app_folder, writable=is_writable, fallback_dir=None, system=None, file_exists=os.path.isfile):
    # Works out every location from the app's own folder. 'writable',
    # 'fallback_dir', 'system' and 'file_exists' exist so tests can simulate
    # a read-only install or a macOS bundle without needing one.
    user_dir = fallback_dir or user_data_dir(system)
    bundle = in_app_bundle(app_folder, system)
    # Logs and state go beside the app when that is safe, otherwise to the
    # person's own folder.
    if bundle or not writable(app_folder):
        data = user_dir
    else:
        data = app_folder
    # settings.ini is read from the app's folder - the administrator's copy.
    # The one exception is a macOS bundle, where editing a file inside the
    # signed app would break it, so there the person's own copy (in their
    # Application Support folder) is used when it exists. This override is
    # deliberately NOT offered on Windows or Linux: there, an installed
    # settings.ini is the administrator's control (for example whether the
    # permanent Deprovision action is available), and a per-person override
    # file would let anyone bypass it.
    settings = os.path.join(app_folder, SETTINGS_FILENAME)
    if bundle:
        personal = os.path.join(user_dir, SETTINGS_FILENAME)
        if file_exists(personal):
            settings = personal
    return Locations(
        app_dir=app_folder,
        settings_path=settings,
        data_dir=data,
        log_dir=os.path.join(data, LOGS_DIRNAME),
        state_path=os.path.join(data, STATE_FILENAME),
    )

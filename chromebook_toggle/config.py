# chromebook_toggle/config.py
#
# Script:   config.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-07-2026
# Modified: 08-10-2026
# Version:  1.2
#
# Purpose:
#   Loads and saves the Chromebook Toggle Tool's settings.ini. Holds the two
#   values that can legitimately differ per deployed PC or change over time
#   without needing a rebuild: where gam.exe lives, and which Workspace
#   identity to read Google Sheets through.
#
# Notes:
#   If settings.ini is missing, malformed (bad INI syntax), or contains
#   non-ASCII bytes (e.g. a Notepad-added BOM or a hand-edited smart quote),
#   sane defaults are used instead of crashing - this covers first run on a
#   freshly-deployed PC as well as a settings.ini damaged after the fact.
#   save_settings() raises RuntimeError with a clear message (instead of a
#   raw OSError or UnicodeEncodeError/traceback) if the file cannot be
#   written, including when a value to be saved contains a non-ASCII
#   character.

import configparser
import os

# Default gam.exe path - matches the existing GAMGUI/district-standard install
# location. Each deployed PC gets its own local GAM7 install per the design.
DEFAULT_GAM_PATH = r"C:\GAM7\gam.exe"

# The Workspace identity GAM already uses for its oauth2 config, per Gabe -
# used as the "acting" account when reading a Google Sheet via gam's
# gsheet: source, since Drive access is per-user, not domain-global.
DEFAULT_SHEET_ACTING_EMAIL = "gam-admin@example.com"

_SECTION = "Settings"


def load_settings(settings_path):
    # Start from defaults so a missing or partially-filled-in settings.ini
    # still produces a fully usable settings dict. This dict is what gets
    # returned if the file is missing, unreadable, or corrupt - the tool
    # must still start up rather than crash on a bad settings.ini.
    settings = {
        "gam_path": DEFAULT_GAM_PATH,
        "sheet_acting_email": DEFAULT_SHEET_ACTING_EMAIL,
    }

    # First-run-on-a-fresh-PC case: no settings.ini has been created yet.
    # This is expected, not an error, so just hand back the defaults.
    if not os.path.isfile(settings_path):
        return settings

    parser = configparser.ConfigParser()
    try:
        # parser.read() can fail two different ways on a hand-edited or
        # Notepad-saved file:
        #   - configparser.Error (and subclasses like MissingSectionHeaderError,
        #     DuplicateOptionError) if the INI syntax itself is broken, e.g. a
        #     duplicate "gam_path=" line or a stray bracket.
        #   - UnicodeDecodeError if the file contains any non-ASCII byte, e.g.
        #     a UTF-8 BOM that Notepad adds by default on save, or a smart
        #     quote/em-dash pasted in during a manual edit.
        # Either way we fall back to defaults below rather than letting the
        # whole tool crash on startup because of one bad settings file.
        parser.read(settings_path, encoding="ascii")
    except (configparser.Error, UnicodeDecodeError):
        # Malformed or non-ASCII settings.ini - treat it the same as a
        # missing file and hand back the defaults already built above.
        return settings

    if parser.has_section(_SECTION):
        # Read each key independently with its own fallback so a
        # partially-filled-in settings.ini (e.g. only gam_path was ever set,
        # sheet_acting_email was never added) still yields a usable value
        # for the key that IS missing, instead of only working when both
        # keys are present.
        settings["gam_path"] = parser.get(_SECTION, "gam_path", fallback=DEFAULT_GAM_PATH)
        settings["sheet_acting_email"] = parser.get(
            _SECTION, "sheet_acting_email", fallback=DEFAULT_SHEET_ACTING_EMAIL
        )
    # If the [Settings] section itself is absent (e.g. someone hand-edited
    # the file down to nothing but comments), settings stays at the
    # all-defaults dict built at the top of the function.
    return settings


def save_settings(settings_path, settings):
    # Build the in-memory config structure from the caller's settings dict.
    # Any key the caller did not supply falls back to the module default so
    # save_settings() never writes a blank/missing value to disk.
    parser = configparser.ConfigParser()
    parser[_SECTION] = {
        "gam_path": settings.get("gam_path", DEFAULT_GAM_PATH),
        "sheet_acting_email": settings.get("sheet_acting_email", DEFAULT_SHEET_ACTING_EMAIL),
    }

    try:
        # Write the file. This can fail two different ways:
        #   - OSError (and subclasses like FileNotFoundError, PermissionError)
        #     if the target directory does not exist, or the file/folder is
        #     read-only/locked (e.g. by another instance of the tool, or
        #     antivirus).
        #   - UnicodeEncodeError (a subclass of UnicodeError, which is itself
        #     a subclass of ValueError, NOT OSError) if any value being saved
        #     contains a non-ASCII character - e.g. an accented name typed
        #     into sheet_acting_email, or a smart quote pasted into gam_path.
        #     encoding="ascii" makes write() raise on the first such
        #     character rather than silently mangling it.
        with open(settings_path, "w", encoding="ascii") as settings_file:
            parser.write(settings_file)
    except (OSError, UnicodeError) as write_error:
        # Do not let a raw, uncommented OSError/UnicodeEncodeError/traceback
        # bubble up to whatever UI eventually calls this (a future
        # settings-editing screen). Re-raise as a clear, specific error so
        # the caller can show the IT admin a real explanation instead of a
        # stack trace, regardless of which of the two failure modes above
        # occurred. "from write_error" keeps the original exception chained
        # for anyone reading a full traceback/log later.
        raise RuntimeError(
            "Could not save settings to '{0}': {1}".format(settings_path, write_error)
        ) from write_error

# chromebook_toggle/config.py
#
# Script:   config.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-07-2026
# Modified: 11-10-2026
# Version:  1.3
#
# Purpose:
#   Loads and saves the Chromebook Toggle Tool's settings.ini. Holds the
#   values that can legitimately differ per deployed PC or change over time
#   without needing a rebuild:
#     gam_path            - where gam.exe lives
#     sheet_acting_email  - which Workspace identity reads Google Sheets
#     allow_deprovision   - whether the (permanent) Deprovision action is
#                           offered at all. OFF by default: an administrator
#                           turns it on for the PCs that should have it.
#     check_for_updates   - whether the app looks for a newer release by
#                           itself at startup (at most once a day)
#     update_repo         - the GitHub owner/repo that publishes releases
#     update_api_base     - the GitHub API address (only ever changed for a
#                           mirror or for testing; must be https, or http to
#                           this same PC)
#
# Notes:
#   Version 1.3 added the last four settings. An older settings.ini that
#   does not have them keeps working: every missing key gets its default.
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

from . import version

# Default gam.exe path - matches the existing GAMGUI/district-standard install
# location. Each deployed PC gets its own local GAM7 install per the design.
DEFAULT_GAM_PATH = r"C:\GAM7\gam.exe"

# The Workspace identity GAM already uses for its oauth2 config, per Gabe -
# used as the "acting" account when reading a Google Sheet via gam's
# gsheet: source, since Drive access is per-user, not domain-global.
DEFAULT_SHEET_ACTING_EMAIL = "gam-admin@example.com"

# Deprovisioning cannot be undone, so it is hidden unless an administrator
# deliberately switches it on (settings.ini, the installer's checkbox, or
# the installer's /ALLOWDEPROV=1 switch).
DEFAULT_ALLOW_DEPROVISION = False

# The header GAM gives the serial-number column when it downloads ChromeOS
# devices to a Sheet or CSV. Google Sheet mode needs the sheet's header to
# match this exactly; the window lets a person type a different one.
DEFAULT_SERIAL_COLUMN = "serialNumber"

# Looking for a newer release at startup is on by default; a locked-down PC
# can switch it off.
DEFAULT_CHECK_FOR_UPDATES = True

# Where releases come from.
DEFAULT_UPDATE_REPO = version.DEFAULT_UPDATE_REPO
DEFAULT_UPDATE_API_BASE = "https://api.github.com"

_SECTION = "Settings"

# Spellings of true/false that configparser (and a person editing the file in
# Notepad) might use.
_TRUE_WORDS = ("1", "yes", "true", "on")
_FALSE_WORDS = ("0", "no", "false", "off")


def default_settings():
    # A fresh copy of every setting at its default. A function (not a shared
    # dict) so no caller can accidentally change the defaults for everyone.
    return {
        "gam_path": DEFAULT_GAM_PATH,
        "sheet_acting_email": DEFAULT_SHEET_ACTING_EMAIL,
        "allow_deprovision": DEFAULT_ALLOW_DEPROVISION,
        "serial_column": DEFAULT_SERIAL_COLUMN,
        "check_for_updates": DEFAULT_CHECK_FOR_UPDATES,
        "update_repo": DEFAULT_UPDATE_REPO,
        "update_api_base": DEFAULT_UPDATE_API_BASE,
    }


def _read_bool(parser, key, default):
    # One yes/no setting. A missing key, or a value that is not recognisably
    # yes or no, gives the default - for allow_deprovision that means a typo
    # such as "ture" leaves the dangerous action OFF.
    raw = parser.get(_SECTION, key, fallback=None)
    if raw is None:
        return default
    word = raw.strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return default


def _read_text(parser, key, default):
    # One text setting; an empty value falls back to the default.
    raw = parser.get(_SECTION, key, fallback=default)
    return raw.strip() or default


def load_settings(settings_path):
    # Start from defaults so a missing or partially-filled-in settings.ini
    # still produces a fully usable settings dict. This dict is what gets
    # returned if the file is missing, unreadable, or corrupt - the tool
    # must still start up rather than crash on a bad settings.ini.
    settings = default_settings()

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
        settings["allow_deprovision"] = _read_bool(
            parser, "allow_deprovision", DEFAULT_ALLOW_DEPROVISION)
        settings["check_for_updates"] = _read_bool(
            parser, "check_for_updates", DEFAULT_CHECK_FOR_UPDATES)
        settings["serial_column"] = _read_text(parser, "serial_column", DEFAULT_SERIAL_COLUMN)
        settings["update_repo"] = _read_text(parser, "update_repo", DEFAULT_UPDATE_REPO)
        settings["update_api_base"] = _read_text(
            parser, "update_api_base", DEFAULT_UPDATE_API_BASE)
    # If the [Settings] section itself is absent (e.g. someone hand-edited
    # the file down to nothing but comments), settings stays at the
    # all-defaults dict built at the top of the function.
    return settings


def save_settings(settings_path, settings):
    # Build the in-memory config structure from the caller's settings dict.
    # Any key the caller did not supply falls back to the module default so
    # save_settings() never writes a blank/missing value to disk.
    parser = configparser.ConfigParser()
    # Start from the defaults and lay the caller's values over them, writing
    # yes/no settings as the words "true"/"false" so the file stays readable
    # by a person.
    merged = default_settings()
    merged.update(settings)
    parser[_SECTION] = {
        "gam_path": str(merged["gam_path"]),
        "sheet_acting_email": str(merged["sheet_acting_email"]),
        "allow_deprovision": "true" if merged["allow_deprovision"] else "false",
        "serial_column": str(merged["serial_column"]),
        "check_for_updates": "true" if merged["check_for_updates"] else "false",
        "update_repo": str(merged["update_repo"]),
        "update_api_base": str(merged["update_api_base"]),
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

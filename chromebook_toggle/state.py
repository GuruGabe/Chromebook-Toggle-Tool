# chromebook_toggle/state.py
#
# Script:   state.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   Remembers one small thing per person between runs: when the app last
#   checked for an update, so the automatic check at startup happens at most
#   once a day instead of on every launch. Kept apart from settings.ini on
#   purpose - settings.ini is an administrator's file that the app only
#   reads, while this is the app's own scratch note and is rewritten freely.
#
# Notes:
#   Nothing in this module may ever stop the app from starting. A missing,
#   unreadable or unwritable state file simply means "no check recorded", so
#   every function swallows its own file errors and falls back safely. The
#   worst outcome is one extra update check, never a crash.

import configparser
import os
import time

_SECTION = "State"
_KEY_LAST_CHECK = "last_update_check"

# How long to wait between automatic checks.
CHECK_INTERVAL_SECONDS = 24 * 60 * 60


def load_last_check(path):
    # Seconds-since-1970 of the last automatic check, or 0 if there is none
    # (no file, unreadable file, or a value that is not a number).
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="ascii")
        return int(parser.get(_SECTION, _KEY_LAST_CHECK, fallback="0"))
    except (OSError, UnicodeError, configparser.Error, ValueError):
        return 0


def save_last_check(path, when=None):
    # Records "checked now". Returns True if it was saved. A failure (for
    # example a read-only folder) is reported by the False return and is not
    # an error - see the module Notes.
    parser = configparser.ConfigParser()
    parser[_SECTION] = {_KEY_LAST_CHECK: str(int(time.time() if when is None else when))}
    try:
        # The person's own app-data folder may not exist yet on a first run.
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="ascii") as handle:
            parser.write(handle)
        return True
    except (OSError, UnicodeError):
        return False


def check_is_due(last_check, now=None, interval=CHECK_INTERVAL_SECONDS):
    # True when enough time has passed since last_check. A recorded time in
    # the FUTURE (the PC clock was changed) also counts as due, so a wrong
    # clock cannot switch update checks off forever.
    now = time.time() if now is None else now
    # 0 (or less) is how load_last_check() says "never checked" - always due.
    if last_check <= 0:
        return True
    if last_check > now:
        return True
    return (now - last_check) >= interval

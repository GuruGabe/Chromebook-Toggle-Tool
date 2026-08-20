# chromebook_toggle/gam_calls.py
#
# Script:   gam_calls.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Thin "CALLER OBLIGATION" wrappers around the five backend calls that
#   gui.py's background-thread code (Task 8) makes into gam_runner.py,
#   device_lookup.py, workflow.py, logging_util.py, and serials.py. Each of
#   those five modules documents, in its own header, that it deliberately
#   lets one specific exception type escape uncaught, and places an
#   obligation on whichever code calls it from a background thread to
#   catch it (see each function's own comment below for exactly which
#   module/exception it is guarding). This module exists so that logic -
#   "call one backend function, catch exactly the one documented exception
#   it can raise, return (value, error_message) instead of letting
#   anything escape" - can be unit-tested the same way every other backend
#   module in this project already is (see tests\test_gam_calls.py),
#   rather than being trapped inside gui.py, the one file in this project
#   that opted out of assert-based automated testing (tkinter widget
#   assertions provide little real confidence - see gui.py's own header).
#
# Notes:
#   Every function here takes its dependencies (gam_path, log_dir, etc.) as
#   plain parameters, not as attributes read off a GUI object - this
#   module has zero tkinter dependency, which is exactly what makes it
#   testable with plain unittest + mock.patch the same way
#   tests\test_gam_runner.py already mocks subprocess.run.
#
#   Each function returns a (value, error_message) tuple: on success,
#   value is whatever the wrapped backend function returned and
#   error_message is None; on the documented failure, value is None and
#   error_message is a plain string ready to show the IT admin directly
#   (e.g. via messagebox.showerror in gui.py). Callers only ever need to
#   check "if error_message:" - never a try/except - which is the whole
#   point: nothing from the five wrapped calls can escape uncaught and
#   silently kill a background thread (see gam_runner.py's, workflow.py's,
#   logging_util.py's, and serials.py's own CALLER OBLIGATION notes for
#   why an uncaught exception there is dangerous).

import subprocess

from . import device_lookup, gam_runner, logging_util, serials, workflow


def run_gam_or_none(gam_path, args):
    # Wraps gam_runner.run_gam(), which deliberately lets
    # subprocess.TimeoutExpired and OSError propagate raw (see
    # gam_runner.py's own CALLER OBLIGATION note).
    try:
        return gam_runner.run_gam(gam_path, args), None
    except subprocess.TimeoutExpired:
        return None, (
            "gam.exe did not finish in time. It may still be running in "
            "the background - check Task Manager before trying again, "
            "since the device(s) involved may or may not have actually "
            "been changed."
        )
    except OSError as os_error:
        return None, "Could not run gam.exe: " + str(os_error)


def parse_lookup_or_none(raw_text):
    # Wraps device_lookup.parse_lookup_json(), which raises ValueError on
    # any malformed input.
    try:
        return device_lookup.parse_lookup_json(raw_text), None
    except ValueError as value_error:
        return None, "Could not understand gam's device lookup output: " + str(value_error)


def build_review_or_none(serial_list, looked_up, action):
    # Wraps workflow.build_review(), which deliberately lets KeyError
    # propagate raw for an unrecognized action (see workflow.py's own
    # CALLER OBLIGATION note). This should never actually trigger in
    # gui.py, since action only ever comes from that file's own two radio
    # buttons ("disable"/"reenable"), but the module requires callers to
    # guard it anyway.
    try:
        return workflow.build_review(serial_list, looked_up, action), None
    except KeyError as key_error:
        return None, "Internal error: unrecognized action " + str(key_error)


def build_results_or_none(review_rows, post_looked_up, action):
    # Same reasoning as build_review_or_none() above, for
    # workflow.build_results().
    try:
        return workflow.build_results(review_rows, post_looked_up, action), None
    except KeyError as key_error:
        return None, "Internal error: unrecognized action " + str(key_error)


def write_log_or_warning(log_dir, action, results):
    # Wraps logging_util.write_log(), which deliberately lets OSError and
    # UnicodeError (e.g. UnicodeEncodeError) propagate raw. Per
    # logging_util.py's own CALLER OBLIGATION note, a failed log write
    # happens AFTER the real gam action already ran, so gui.py is expected
    # to report this as a softer warning about the log specifically -
    # never as if the disable/reenable action itself failed.
    try:
        return logging_util.write_log(log_dir, action, results), None
    except (OSError, UnicodeError) as log_error:
        return None, str(log_error)


def write_temp_csv_or_none(serial_list):
    # Wraps serials.write_temp_serial_csv(), which raises ValueError if a
    # serial cannot be written to the ascii-encoded temp file (see
    # serials.py's own CALLER OBLIGATION note).
    try:
        return serials.write_temp_serial_csv(serial_list), None
    except ValueError as value_error:
        return None, str(value_error)

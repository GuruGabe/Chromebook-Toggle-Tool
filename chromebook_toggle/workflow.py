# chromebook_toggle/workflow.py
#
# Script:   workflow.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Turns a resolved serial list + a pre-action lookup into the review
#   screen's rows (what will happen, and what will be skipped and why), and
#   turns a post-action lookup into the results screen's rows. This is
#   where "success" is decided - by comparing before/after device status,
#   not by parsing gam's mutating-command text output (that output format
#   has never been live-tested, since mutating/disable-enable tests are
#   deliberately reserved for a human to run, not automation). This module
#   never calls gam.exe itself and never reads/writes a file - it only
#   turns dicts that gam_runner.py/device_lookup.py already produced into
#   the row shapes the GUI displays.
#
# Notes:
#   ERROR-HANDLING DESIGN for the "action" parameter used by both functions
#   below: action is NOT free-text or otherwise untrusted input. Per the
#   design (see gui.py, a later task), it only ever comes from exactly one
#   of the GUI's two action radio buttons, whose values are the literal
#   strings "disable" and "reenable" - the same two keys
#   device_lookup.ACTION_TARGET_STATUS defines (confirmed by reading that
#   module directly, not assumed). There is no code path anywhere in this
#   tool's design where a user can type or paste an arbitrary "action"
#   value. That makes an unrecognized action a programming mistake (a
#   typo'd literal, or a future caller/task passing the wrong string) -
#   not a data-quality problem coming from gam, a CSV, a pasted list, or a
#   Google Sheet, all of which ARE untrusted and are the cases serials.py
#   and device_lookup.py deliberately normalize into ValueError (see their
#   own Notes for that reasoning). Wrapping this in a try/except here and
#   re-raising a friendlier exception would only hide a bug behind a
#   plausible-looking error message and risk it being silently caught
#   somewhere upstream instead of being fixed at the source. So, matching
#   gam_runner.py's precedent of leaving specific-enough exceptions
#   (subprocess.TimeoutExpired, OSError) to propagate raw rather than
#   wrapping them, ACTION_TARGET_STATUS[action] below is left to raise its
#   own KeyError untouched - it already reports the exact bad value
#   (KeyError: 'not_a_real_action'), which is more useful for tracking down
#   a coding mistake than any message this module could substitute. This is
#   deliberately the opposite call from device_lookup.py's parse_lookup_json()
#   and serials.py's read_csv_serials(), which DO wrap their raw exceptions -
#   those two are boundary functions reading external/untrusted input, and
#   this one is not.
#
#   CALLER OBLIGATION (matching gam_runner.py's own CALLER OBLIGATION note):
#   per the design (see gui.py, a later task), build_review() and
#   build_results() - like every other call into this tool's backend
#   modules - are expected to be invoked from a background thread so the
#   GUI window does not freeze. Python's default behavior for an exception
#   that escapes a background thread (threading.excepthook) is to print a
#   traceback to stderr and otherwise do nothing - the thread just ends,
#   and nobody sees that stderr output on a deployed EXE. So even though
#   the KeyError from an unrecognized action is deliberately left
#   unwrapped here (see above), any call site invoking these functions off
#   the main thread MUST wrap that call in its own try/except KeyError (or
#   a broader except) and surface the failure (e.g. via a messagebox) -
#   otherwise a coding mistake in the action string would silently hang
#   the GUI on a "Working..." screen forever, in direct violation of the
#   district's "never let a script silently fail" rule. This module only
#   promises that it will not hide the KeyError by catching it first; not
#   catching it downstream is the calling code's responsibility.

from dataclasses import dataclass

from .device_lookup import ACTION_TARGET_STATUS


@dataclass
class ReviewRow:
    # One row of the review/confirm screen (Task 8), one per requested
    # serial - regardless of whether that serial will actually be sent to
    # gam or skipped.
    serial: str
    found: bool  # True if gam's lookup returned anything for this serial
    current_status: str | None  # status from the lookup, or None if not found
    will_process: bool  # True if this row should be included in the gam action
    skip_reason: str | None  # explains why will_process is False, else None


@dataclass
class ResultRow:
    # One row of the results screen (Task 8) / audit log (Task 7), one per
    # row that was actually processed (will_process was True at review time).
    serial: str
    previous_status: str | None  # status at review time, before the action ran
    new_status: str | None  # status from the post-action lookup
    success: bool  # True if new_status matches the action's target status


def build_review(serial_list, looked_up, action):
    # ACTION_TARGET_STATUS[action] - deliberately NOT guarded with .get()
    # or a try/except; see the ERROR-HANDLING DESIGN note above this
    # module's Notes section for the full reasoning (action is a trusted,
    # GUI-controlled value, so an unrecognized one is a programming
    # mistake that should fail loudly and immediately, not be papered
    # over).
    target_status = ACTION_TARGET_STATUS[action]

    # ASSUMPTION, not enforced here: every serial in serial_list and every
    # key in looked_up is already upper-cased, matching serials.py's own
    # normalization (parse_multiline_serials/read_csv_serials both
    # upper-case) and device_lookup.py's parse_lookup_json(), which
    # upper-cases every key it stores. If a future caller ever passed in a
    # serial list that was not already upper-cased, matching entries would
    # silently be treated as "not found" instead of raising - this
    # function does no case-normalization of its own, matching the pattern
    # of documenting (rather than re-enforcing) an upstream contract, per
    # gam_runner.py's build_lookup_args() comment on its own
    # non-empty-list assumption.
    rows = []
    for serial in serial_list:
        # looked_up is keyed by serial (device_lookup.parse_lookup_json's
        # output) - a serial with no entry means gam's lookup found no
        # device with that serial at all (typo, wrong device, or a serial
        # that is not enrolled in this Workspace).
        info = looked_up.get(serial)
        if info is None:
            rows.append(ReviewRow(
                serial=serial,
                found=False,
                current_status=None,
                will_process=False,
                skip_reason="Serial not found in Google Workspace",
            ))
            # Nothing further to check for a device that was never found -
            # move on to the next serial rather than falling through into
            # the status comparison below, which assumes info is a dict.
            continue

        # .get("status", "") rather than info["status"]: matches
        # device_lookup.parse_lookup_json()'s own choice to degrade a
        # missing field to an empty string instead of raising, so a device
        # entry that is missing "status" for some reason does not crash
        # this function - it will simply never equal target_status below
        # and fall through to "will process", which is the safer default
        # (a human reviews it on the review screen before anything is
        # actually sent to gam).
        current_status = info.get("status", "")
        if current_status == target_status:
            # Already in the state this action would produce - re-running
            # the action would be a no-op gam call at best, so skip it and
            # tell the reviewer why, rather than silently including it.
            rows.append(ReviewRow(
                serial=serial,
                found=True,
                current_status=current_status,
                will_process=False,
                skip_reason="Already " + target_status,
            ))
            continue

        # Found, and not already in the target state - this is the normal
        # case: include it for processing, with no skip reason.
        rows.append(ReviewRow(
            serial=serial,
            found=True,
            current_status=current_status,
            will_process=True,
            skip_reason=None,
        ))
    return rows


def build_results(review_rows, post_looked_up, action):
    # Same deliberate no-guard choice as build_review() above - see the
    # ERROR-HANDLING DESIGN note above this module's Notes section.
    target_status = ACTION_TARGET_STATUS[action]

    results = []
    for row in review_rows:
        if not row.will_process:
            # A row that review excluded (not found, or already in the
            # target state) was never sent to gam for this run - it must
            # not appear in the results/audit log, since that would
            # falsely imply this run touched that device.
            continue

        # post_looked_up is a second, post-action lookup dict (same shape
        # as build_review()'s looked_up, from another
        # device_lookup.parse_lookup_json() call made after gam's action
        # ran). A device missing from it here (gam's action lookup somehow
        # did not include it) degrades to new_status=None rather than
        # raising - that is reported as a failure below (None will never
        # equal target_status), which is the safe default: an unverifiable
        # device must never be reported as a success.
        post_info = post_looked_up.get(row.serial)
        new_status = post_info.get("status", "") if post_info is not None else None

        results.append(ResultRow(
            serial=row.serial,
            previous_status=row.current_status,
            new_status=new_status,
            # By design, success is decided purely by
            # comparing the verified post-action status against the
            # action's target status, never by trusting gam's own exit
            # code or stdout text for the mutating command.
            success=(new_status == target_status),
        ))
    return results

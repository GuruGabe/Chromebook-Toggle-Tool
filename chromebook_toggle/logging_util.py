# chromebook_toggle/logging_util.py
#
# Script:   logging_util.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Writes the local audit log for a completed run, per this district's standing
#   logging rule (timestamp, action taken, result). Local-only - no shared
#   network copy, since these users do not have access to most shared
#   folders in some deployments. This
#   module only ever reads fields off ResultRow (Task 6) plus the caller's
#   own log_dir/action strings - it never calls gam.exe and never touches
#   device_lookup.py's raw lookup dicts (which is where a field like
#   annotateduser would come from), so there is no code path here where
#   anything beyond serial/status/result/timestamp could end up in the log.
#
# Notes:
#   PII CHECK: CLAUDE.md's standing logging rule says "Never log passwords,
#   credentials, or PII." The only per-device fields write_log() below ever
#   reads are row.serial, row.previous_status, row.new_status, and
#   row.success (ResultRow's four fields, per workflow.py - confirmed by
#   reading that module directly). A device serial number is a hardware
#   asset tag, not personal information, and a Chromebook's ACTIVE/DISABLED
#   status is likewise not personal information. row.success is a bool,
#   turned into the literal string "SUCCESS"/"FAILED" below - never written
#   as anything else. No name, email, student ID, or other
#   personally-identifying field is read from ResultRow (it does not even
#   have such a field) or written to the CSV.
#
#   ERROR-HANDLING DESIGN: write_log() deliberately does NOT wrap
#   os.makedirs() or the open()/csv.writer() calls in a try/except. Both
#   can fail with OSError (e.g. PermissionError if log_dir is on a
#   read-only/locked path, or a disk-full condition partway through the
#   write) - but OSError is already a specific, clear exception, and this
#   module has no more useful message to substitute for what Python
#   already reports (e.g. "PermissionError: [Errno 13] Permission denied:
#   'C:\\...\\Logs'"). This matches gam_runner.py's run_gam() and
#   workflow.py's build_review()/build_results() precedent: a narrow,
#   already-specific exception is left to propagate raw rather than being
#   wrapped in a less-informative one.
#
#   CALLER OBLIGATION (matching gam_runner.py's and workflow.py's own
#   CALLER OBLIGATION notes): per the design (see gui.py, a later task),
#   write_log() - like every other call into this tool's backend modules -
#   is expected to be invoked from a background thread, after the gam
#   action has already run, so the GUI window does not freeze while the
#   log is written. Python's default behavior for an exception that
#   escapes a background thread (threading.excepthook) is to print a
#   traceback to stderr and otherwise do nothing - the thread just ends,
#   and nobody sees that stderr output on a deployed EXE. So any call site
#   invoking write_log() off the main thread MUST wrap that call in its
#   own try/except OSError and surface the failure (e.g. via a
#   messagebox) - otherwise a permissions problem or a full disk would
#   silently fail to log the run, in direct violation of the district's
#   "never let a script silently fail" rule. This module only promises
#   that it will not hide the OSError by catching it first; not catching
#   it downstream is the calling code's responsibility. Note that this is
#   a slightly softer situation than gam_runner.py's/workflow.py's: by the
#   time write_log() runs, the gam action itself has already completed and
#   the results screen already has the data in memory, so a failed log
#   write should be surfaced as a warning about the LOG, not represented
#   to the admin as if the disable/reenable action itself failed.
#
#   PARTIAL-WRITE SAFEGUARD: a failure (e.g. disk fills up) partway through
#   writing the data rows could in theory leave a truncated CSV file behind
#   (header row present, some/all data rows missing). This module does not
#   add extra machinery (e.g. write-to-temp-file-then-rename) to guard
#   against that. Reasoning: this is a local audit log, not the source of
#   truth for what happened - the GUI's results screen (Task 8) is what the
#   admin actually reviews immediately after a run, and the on-disk gam
#   commands themselves are the actual district record of what changed.
#   IMPORTANT CORRECTION: a truncated file here is NOT self-evidently
#   incomplete - csv.writer() writes whole rows at a time, so a file cut
#   off after N of M rows is syntactically a perfectly valid, shorter CSV
#   with no marker inside the file itself showing it was truncated. Anyone
#   opening it later without independently knowing "this run should have
#   had M rows" would see what looks like a complete short log, not an
#   obviously broken one. The actual safeguard is NOT any property of the
#   file - it is that the OSError propagates out of write_log() at the
#   moment of the failure (per the ERROR-HANDLING DESIGN and CALLER
#   OBLIGATION notes above), so the not-yet-built GUI caller can catch it
#   right then and warn the admin that the log write did not complete,
#   rather than the admin discovering it later from the file alone. Adding
#   atomic-replace machinery here would be extra complexity for a failure
#   mode (disk full mid-write, on a file of at most a few hundred short
#   rows) that is both rare and already surfaced as an error at the source,
#   even though the resulting file itself carries no internal proof of
#   that truncation.
#
#   FILENAME SAFETY: the log filename embeds the action string directly
#   (e.g. "ChromebookToggle_disable_..."). Matching workflow.py's own
#   ERROR-HANDLING DESIGN note on the same "action" parameter: action is
#   NOT free-text or otherwise untrusted input. Per the design (see
#   gui.py, a later task), it only ever comes from exactly one of the
#   GUI's two action radio buttons, whose values are the literal strings
#   "disable" and "reenable" - the same two keys
#   device_lookup.ACTION_TARGET_STATUS defines. There is no code path
#   anywhere in this tool's design where a user can type or paste an
#   arbitrary "action" value that would end up in a filename, so no
#   filename-sanitizing of action is done here - same trust boundary
#   workflow.py already documented for this exact value.

import csv
import datetime
import os


def write_log(log_dir, action, results):
    # os.makedirs(..., exist_ok=True) creates log_dir (and any missing
    # parent folders) if it does not already exist, and does nothing (no
    # error) if it already does - this is what lets the very first run of
    # the tool succeed even before a Logs folder has ever been created.
    # Left unguarded; see the ERROR-HANDLING DESIGN note above this
    # function for why an OSError here is allowed to propagate raw.
    os.makedirs(log_dir, exist_ok=True)

    # One shared timestamp for the whole run (not one per row) - every row
    # in a single write_log() call represents devices processed together
    # in the same gam action, so they share one MM-DD-YYYY_HH-MM-SS
    # timestamp per this district's standing log timestamp format.
    # Using underscores/hyphens only (no colons) keeps the string safe to
    # embed directly in a Windows filename below.
    #
    # ACCEPTED LIMITATION: this timestamp (one-second resolution) is reused
    # for both the filename and every CSV row below, so two write_log()
    # calls landing within the same wall-clock second would produce the
    # same log_path and the second call's open(..., "w") would silently
    # overwrite the first call's file. This is a real gap in theory, but a
    # low-risk one in practice - this tool is driven by a human clicking
    # through a GUI review screen between runs, not by an automated loop
    # capable of firing two runs within the same second - so no
    # higher-resolution timestamp or collision-avoidance logic is added
    # here.
    timestamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")

    # Filename includes the tool name, the action, and the timestamp so
    # multiple runs never collide and an admin can identify a specific
    # log file at a glance without opening it. See the FILENAME SAFETY
    # note above this function for why embedding action directly here is
    # safe (it is a trusted, GUI-controlled value, not user-typed text).
    log_path = os.path.join(log_dir, "ChromebookToggle_" + action + "_" + timestamp + ".csv")

    # encoding="ascii" per CLAUDE.md's "ASCII characters ONLY" rule -
    # device serials and status strings are already ASCII in practice
    # (per device_lookup.py's own field set), so this also acts as a
    # cheap guard: an unexpected non-ASCII value anywhere in results would
    # raise UnicodeEncodeError here rather than silently writing a file
    # that violates the district's ASCII-only standard.
    # newline="" is the standard csv module requirement on Windows - it
    # stops the csv module's own line terminator from being doubled up
    # with the platform's own newline translation.
    with open(log_path, "w", newline="", encoding="ascii") as log_file:
        writer = csv.writer(log_file)

        # Header row - column order here must match the order every data
        # row below appends its values in.
        writer.writerow(["Serial", "Action", "PreviousStatus", "NewStatus", "Result", "Timestamp"])

        for row in results:
            # Turn the ResultRow.success bool into the human-readable text
            # an IT admin scanning the CSV in Excel actually wants to see,
            # rather than a raw True/False.
            result_text = "SUCCESS" if row.success else "FAILED"

            # previous_status/new_status can legitimately be None (see
            # workflow.py's ResultRow and build_results() - e.g. new_status
            # is None if the post-action lookup never found the device).
            # "or ''" turns that into an empty CSV cell instead of writing
            # the literal text "None", which would be confusing to a
            # human reader and is not a valid status value.
            writer.writerow([
                row.serial,
                action,
                row.previous_status or "",
                row.new_status or "",
                result_text,
                timestamp,
            ])

    # Returned so the caller (the GUI, a later task) can show the admin
    # exactly where the log file was written, e.g. in a completion message.
    return log_path

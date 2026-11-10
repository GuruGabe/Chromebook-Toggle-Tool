# chromebook_toggle/gam_runner.py
#
# Script:   gam_runner.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.2
#
# Version 1.1 (08-10-2026): Fixed a confirmed production bug in
#   build_csv_action_args() and build_gsheet_action_args() - both were
#   missing the "cros_sn" prefix on the ~Serial substitution token, which
#   caused every CSV/Sheet-driven disable/reenable action to silently
#   fail against every device (gam interpreted the substituted serial
#   number as a bare Google internal device ID instead, per
#   GamCommands.txt's <CrOSEntity> grammar). Found after Gabe ran a real
#   disable action against 8 real district Chromebooks that all reported
#   FAILED / stayed ACTIVE. See the comment blocks on both functions
#   below for the full root-cause writeup. Also extracted the "cros_sn"
#   literal into the CROS_SN_PREFIX module constant and used it in all
#   three builder functions (including build_lookup_args, which was
#   already correct) so this proven-buggy string can never again drift
#   out of sync between functions via a typo in only one of them.
#
# Version 1.2 (08-10-2026): Code review follow-up. Added explicit
#   encoding="utf-8", errors="replace" to run_gam()'s subprocess.run()
#   call - without it, stdout/stderr decoding fell back to Python's
#   platform-default encoding on Windows, which can raise
#   UnicodeDecodeError (a ValueError subclass, not OSError and not
#   TimeoutExpired) if gam.exe ever emits a byte sequence that codec
#   can't decode - plausible given this district's annotated-user/
#   location CrOS fields can legitimately contain non-ASCII staff/campus
#   names. That third exception type was not covered by this module's
#   CALLER OBLIGATION contract (which only documents TimeoutExpired and
#   OSError), so it could have escaped uncaught on a GUI background
#   thread and hung the "Working..." screen forever - the exact silent-
#   failure mode this module has otherwise been careful to avoid. Fixed
#   by closing off the exception entirely (errors="replace" substitutes
#   undecodable bytes rather than raising) instead of asking every
#   caller to add a third except clause. See run_gam()'s own comment and
#   the CALLER OBLIGATION note below for the updated reasoning.
#
# Purpose:
#   Builds gam.exe argument lists for this tool's two operations (read-only
#   status lookup, and the disable/reenable action) and runs gam.exe via
#   subprocess. Every command shape here is copied from C:\GAM7\GamCommands.txt
#   (v7.47.02), not guessed - see the line references in each function.
#
# Notes:
#   run_gam never raises on a nonzero gam exit code - callers decide what a
#   failure means for their situation (a lookup returning nothing found is
#   not the same kind of failure as gam.exe itself being unreachable, which
#   is what check_gam_available is for).
#
#   run_gam deliberately does NOT wrap the subprocess.run() call in a
#   try/except. Two exception types could realistically come out of it:
#     - subprocess.TimeoutExpired if gam.exe does not finish within
#       timeout_seconds (a big CSV/Sheet batch action taking longer than
#       expected). This is already a specific, well-documented exception
#       (it carries .cmd and .timeout) rather than a raw/uninformative
#       error - wrapping it would only relabel it, not add information.
#       What a timeout MEANS also differs by caller (a stuck lookup vs. a
#       stuck mass-disable are not the same situation to react to), which
#       matches this module's existing "callers decide what a failure
#       means" design for a nonzero exit code. So it is left to propagate
#       to the caller, same as a nonzero exit code is left to the caller
#       to interpret - just via an exception instead of a return value.
#     - OSError (e.g. PermissionError) if gam_path exists as a file but is
#       not actually executable. check_gam_available() is meant to be
#       called first and catches the much more common "gam.exe is not
#       there at all" case, but it only checks existence, not
#       executability, so this narrower case is still technically
#       reachable. It is left unhandled here for the same reason as
#       TimeoutExpired above: OSError is already a clear, specific
#       exception, and this module has no more useful message to add
#       beyond what Python already reports.
#
#   A THIRD exception type was considered and deliberately CLOSED OFF
#   instead of being left to propagate: subprocess.run's text-mode output
#   decoding can raise UnicodeDecodeError (a ValueError subclass, not
#   OSError and not TimeoutExpired) if gam.exe's stdout/stderr bytes are
#   not valid under whatever codec subprocess.run falls back to. Without
#   an explicit encoding=, that fallback is Python's platform-default
#   encoding on Windows, which is not guaranteed to be UTF-8 - and this is
#   not a hypothetical here, since CrOS fields this tool
#   requests (annotateduser, annotatedlocation) can legitimately contain
#   non-ASCII staff/campus names. Unlike TimeoutExpired and OSError above,
#   this exception type was NOT added to the CALLER OBLIGATION contract
#   below - instead run_gam() passes encoding="utf-8", errors="replace"
#   explicitly, which makes UnicodeDecodeError unreachable from this call
#   (undecodable bytes are substituted with U+FFFD instead of raising).
#   This was chosen over "add a third except clause to every caller"
#   because it closes the gap in exactly one place instead of depending on
#   every present and future caller remembering to add it.
#
#   CALLER OBLIGATION: because run_gam() deliberately does not catch
#   subprocess.TimeoutExpired or OSError (see above), every call site that
#   calls run_gam() MUST wrap that call in its own
#   try/except (subprocess.TimeoutExpired, OSError). This is not optional
#   polish - per the design (see gui.py, a later task), every run_gam()
#   call happens on a background thread so the GUI window does not freeze
#   while gam.exe is running. Python's default behavior for an exception
#   that escapes a background thread (threading.excepthook) is to print a
#   traceback to stderr and otherwise do nothing - the thread just ends.
#   Nobody sees that stderr output on a deployed EXE. If a caller does not
#   catch these exceptions itself, the practical result is the GUI stays
#   on a "Working..." screen forever with no error ever shown to the IT
#   admin - a silent failure, in direct violation of the district's
#   standing "never let a script silently fail" rule. Catching and
#   surfacing these two exception types (e.g. via a messagebox) is
#   entirely the calling code's responsibility; this module only promises
#   that it will not hide them by catching them first. (UnicodeDecodeError
#   is deliberately NOT part of this list - see above for why it cannot
#   occur here.)
#
#   This module never talks to a real gam.exe during automated tests -
#   tests\test_gam_runner.py mocks subprocess.run for every test that would
#   otherwise shell out for real (gam.exe operates against a real district
#   Google Workspace tenant).

import os
import subprocess

from . import actions

# GamCommands.txt:2515-2567 <CrOSFieldName> list - these are the fields this
# tool needs to build a review screen and compare before/after status.
# Kept as one module-level constant (rather than repeated inline) so the
# lookup args builder and the tests both reference the exact same field list.
#
# annotatedassetid (NOT annotatedasset) - this exact field name was verified
# against a live "gam info cros" call and GAM's own error message (which
# listed annotatedassetid as a valid choice and rejected annotatedasset), not
# assumed. It is a real, confirmed field name.
LOOKUP_FIELDS = "status,serialnumber,annotatedassetid,annotatedlocation,orgunitpath,annotateduser"

# GamCommands.txt:1096-1098 <CrOSEntity> ::= <CrOSIDList> |
# (cros_sn <SerialNumberList>) | ... - the literal token that tells gam
# "the value that follows is a serial number, not a bare device ID".
#
# Extracted to one module-level constant, used by ALL THREE builder
# functions below (build_lookup_args, build_csv_action_args,
# build_gsheet_action_args), because this exact string was already the
# source of a confirmed production incident: two of those three functions
# (the action builders) were missing it entirely, which silently no-op'd
# a real disable action against 8 real district Chromebooks - see each
# function's own comment for the full writeup. A shared constant means a
# future edit cannot reintroduce that bug via a typo in only one function
# while the others stay correct - there is now exactly one place this
# string is spelled.
CROS_SN_PREFIX = "cros_sn"


def build_lookup_args(serial_list):
    # GamCommands.txt:2584 gam info cros <CrOSEntity> ... formatjson
    # GamCommands.txt:1096-1098 <CrOSEntity> ::= ... | (cros_sn <SerialNumberList>) | ...
    # GamCommands.txt:788 <SerialNumberList> ::= "<SerialNumber>(,<SerialNumber>)*"
    #   - a single gam call can look up many devices at once by joining
    #   their serials with commas, which is why this tool never needs to
    #   run one gam call per device. A scoped cros_sn lookup like this is
    #   used instead of a full-fleet "print cros" specifically because
    #   print cros pulls every device in the whole tenant - on a fleet of
    #   a few thousand devices that took noticeably longer than a targeted
    #   cros_sn lookup of just the serials actually in play.
    #
    #   ASSUMPTION, not enforced here: serial_list is non-empty. This
    #   function does not guard against an empty list - ",".join([]) would
    #   silently build cros_sn "" and only fail later with an uninformative
    #   gam.exe error, rather than a clear Python-side one. serials.py
    #   (Task 2) does NOT itself guarantee a non-empty result (an
    #   all-blank-lines paste or an all-blank CSV column both legitimately
    #   produce []); the emptiness check instead lives at the call site in
    #   gui.py's draft (Task 8) - "if mode != 'sheet' and not serial_list:
    #   warn and return" happens before build_lookup_args() is ever
    #   reached. No validation is added here to avoid duplicating a check
    #   that already exists one layer up, in the one place (the GUI) that
    #   can actually explain "no serials" to the person who typed them in.
    return [
        "info", "cros", CROS_SN_PREFIX, ",".join(serial_list),
        "fields", LOOKUP_FIELDS, "formatjson",
    ]


def build_csv_action_args(csv_path, action):
    # GamCommands.txt:1408-1419 gam csv <CSVLoopContent> gam <GAMArgumentList>
    # ~Serial substitutes the "Serial" column's value from the CSV per row,
    # so this one gam invocation loops the disable/reenable action across
    # every serial in the file without this module having to build a
    # separate command per row.
    #
    # CONFIRMED PRODUCTION BUG (fixed 08-10-2026) - the "cros_sn" prefix
    # below is NOT optional or cosmetic. This function used to emit
    # ["csv", csv_path, "gam", "update", "cros", "~Serial", "action", action]
    # - i.e. the substituted serial went into the <CrOSEntity> position
    # BARE, with no "cros_sn" in front of it.
    #
    # Per GamCommands.txt:1096-1098, <CrOSEntity> ::= <CrOSIDList> |
    # (cros_sn <SerialNumberList>) | ... - a bare/unprefixed value in that
    # position is parsed as a <CrOSIDList> (Google's internal device ID,
    # a UUID-like string), NOT a serial number. Gabe ran a real disable
    # action against 8 real district Chromebooks through this tool with
    # the bare-~Serial version of this function. The GUI reached the
    # Results screen (no error dialog, gam's overall csv-batch process
    # still exited 0) but reported all 8 rows as FAILED, and the devices
    # were still ACTIVE afterward - the action never actually happened.
    #
    # Root cause was confirmed live and read-only (no district device was
    # touched to prove this): running
    #   gam.exe info cros 8CG7890MNO fields status,serialnumber formatjson
    # (bare serial, matching what the old ~Serial substitution produced)
    # returned exit code 50 with "CrOS Device: 8CG7890MNO, Show Info
    # Failed: Does not exist" - gam looked for a device whose internal ID
    # is literally the string "8CG7890MNO" and correctly found none, even
    # though a real device with that SERIAL NUMBER exists (confirmed
    # separately via the correctly-prefixed
    # "gam info cros cros_sn 8CG7890MNO ...", which returns real data).
    # The same bare-value misinterpretation applies to "gam update cros"
    # (this function's actual command), which explains why every row of
    # the CSV-driven disable action silently failed per-device without
    # gam's overall batch exit code ever going nonzero - nothing in this
    # module's own returncode check could have caught it.
    #
    # The fix: insert the literal "cros_sn" token immediately before the
    # "~Serial" substitution token, so gam parses the substituted value as
    # a serial number (per <SerialNumberList> ::= "<SerialNumber>
    # (,<SerialNumber>)*" - a single serial with no comma is a valid
    # one-element list), matching what build_lookup_args() above has
    # always done correctly. Do not remove this prefix again without
    # re-verifying against a live (read-only) gam call first.
    #
    # DEPROVISIONING (added 11-10-2026): for the four deprovision_* actions
    # GAM also requires acknowledge_device_touch_requirement after the
    # action word (GAM wiki, ChromeOS Devices > Deprovisioning: "you must
    # enter acknowledge_device_touch_requirement"). actions.extra_gam_args()
    # supplies it for those actions and nothing for disable/reenable. The
    # "gam csv" loop runs this command once per serial, so each GAM call
    # touches exactly one device and GAM's default max_to_deprov of 1 is
    # never exceeded.
    return [
        "csv", csv_path,
        "gam", "update", "cros", CROS_SN_PREFIX, "~Serial", "action", action,
    ] + list(actions.extra_gam_args(action))


def build_gsheet_action_args(sheet_acting_email, file_id, gid, action):
    # GamCommands.txt:1399-1405 CSVLoopContent accepts (gsheet <UserGoogleSheet>)
    # GamCommands.txt:827-828 <UserGoogleSheet> ::= <EmailAddress> <DriveFileIDEntity> <SheetEntity>
    # GamCommands.txt:1109-1111 <DriveFileIDEntity> accepts bare id:<DriveFileItem>
    # GamCommands.txt:607 <SheetEntity> ::= <String> | id:<Number>  (id:<gid> selects a tab by gid)
    #   - sheet_acting_email is the Workspace identity gam reads the Sheet
    #   as (Drive access is per-user, not domain-global - see config.py's
    #   DEFAULT_SHEET_ACTING_EMAIL). file_id and gid
    #   come from sheet_url.parse_sheet_url() (Task 3), already stripped of
    #   everything except the two IDs gam actually needs, so the "id:"
    #   prefix required by gam's own grammar is added here rather than by
    #   the caller.
    #
    # CONFIRMED PRODUCTION BUG (fixed 08-10-2026) - this function had the
    # exact same bare-~Serial bug as build_csv_action_args() above (see
    # that function's comment block for the full real-world incident: a
    # real disable action run by Gabe against 8 real Chromebooks silently
    # no-op'd, root-caused via a live read-only reproduction). This Sheet-
    # driven action builder was not the one actually run in that incident,
    # but it builds the identical "gam update cros ~Serial action ..."
    # tail via the same substitution mechanism, so it had the identical
    # defect and would have silently failed the same way the first time
    # anyone used the Google Sheet input mode instead of a CSV file. Fixed
    # the same way: "cros_sn" inserted immediately before "~Serial" so gam
    # parses the substituted value as a serial number, not a bare
    # (and therefore misinterpreted-as-device-ID) string.
    #
    # DEPROVISIONING (added 11-10-2026): same acknowledgement flag as
    # build_csv_action_args() above, for the same reason.
    return [
        "csv", "gsheet", sheet_acting_email, "id:" + file_id, "id:" + gid,
        "gam", "update", "cros", CROS_SN_PREFIX, "~Serial", "action", action,
    ] + list(actions.extra_gam_args(action))


def run_gam(gam_path, args, timeout_seconds=180):
    # gam_path is prepended as args[0] so the caller only ever has to think
    # about gam's own arguments (from the build_*_args functions above),
    # never about where gam.exe is installed on this particular PC.
    return subprocess.run(
        [gam_path] + args,
        # capture_output=True + text=True: get gam's stdout/stderr back as
        # decoded strings (not raw bytes) so callers (device_lookup.py's
        # JSON parsing, a later task) can use them directly.
        capture_output=True,
        text=True,
        # encoding="utf-8", errors="replace": WITHOUT this, text=True
        # falls back to Python's platform-default encoding on Windows
        # (not guaranteed UTF-8) to decode gam.exe's stdout/stderr, which
        # can raise UnicodeDecodeError if gam ever emits a byte sequence
        # that codec cannot decode - plausible here since this district's
        # CrOS annotateduser/annotatedlocation fields can legitimately
        # contain non-ASCII staff/campus names. UnicodeDecodeError is a
        # ValueError subclass, NOT OSError and NOT TimeoutExpired, so it
        # was not covered by this module's CALLER OBLIGATION contract
        # (see the module Notes above) and could have escaped uncaught on
        # a GUI background thread, hanging the "Working..." screen
        # forever with no error ever shown - the exact silent-failure
        # mode this module is otherwise careful to avoid. Explicitly
        # forcing UTF-8 with errors="replace" (substitute undecodable
        # bytes with U+FFFD instead of raising) closes off that exception
        # entirely, rather than requiring every caller to add a third
        # except clause on top of TimeoutExpired/OSError.
        encoding="utf-8",
        errors="replace",
        # A batch action against a large CSV/Sheet can legitimately take a
        # while; 180 seconds gives it room without letting a truly hung
        # gam.exe process block the GUI's background thread forever.
        timeout=timeout_seconds,
        # check=False: never raise CalledProcessError on a nonzero exit
        # code. Per this module's Notes above, a nonzero gam.exe exit code
        # is not automatically a "this call failed" signal to every caller
        # (e.g. it means something different for a lookup that found
        # nothing than for an action that could not run at all) - so the
        # caller inspects result.returncode itself and decides.
        check=False,
    )


def check_gam_available(gam_path):
    # Pre-flight check per the design's fail-fast requirement: confirm
    # gam.exe actually exists at the configured path BEFORE the GUI lets
    # anyone attempt a lookup or an action. A missing exe usually means the
    # network-shared config path this PC depends on is unreachable, or GAM
    # was never installed on this particular PC.
    #
    # This is deliberately a plain existence check only (os.path.isfile),
    # nothing more - it does not attempt to run gam.exe (e.g. "gam version")
    # to confirm it actually works, since that would itself be a real
    # subprocess call outside what this narrow pre-flight check is meant to
    # do; a gam.exe that exists but is broken in some other way will still
    # surface clearly the first time run_gam() is actually used.
    if not os.path.isfile(gam_path):
        return False, "gam.exe was not found at: " + gam_path
    return True, "OK"

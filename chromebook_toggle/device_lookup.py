# chromebook_toggle/device_lookup.py
#
# Script:   device_lookup.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.2
#
# Purpose:
#   Parses the JSON text that "gam info cros ... formatjson" prints on
#   stdout into a plain dict keyed by serial number, and defines which
#   device status each of this tool's two actions (disable/reenable) is
#   supposed to produce. This module never calls gam.exe itself - that is
#   gam_runner.py's job (Task 4); this module only turns the text gam
#   already produced into something the rest of the tool can use.
#
# Notes:
#   LIVE VERIFICATION RECORD:
#   The exact JSON key casing formatjson uses was CONFIRMED, not assumed,
#   with one real read-only call against a real district device:
#
#     C:\GAM7\gam.exe info cros cros_sn 5CD1234ABC fields
#         status,serialnumber,orgunitpath,annotatedassetid,
#         annotatedlocation,annotateduser formatjson
#
#   Real output (staff email redacted here - see tests\test_device_lookup.py
#   for the full PII note; the fake "jdoe@example.com" used in that file's
#   fixture is NOT what gam actually printed):
#
#     {"annotatedAssetId": "Building A", "annotatedLocation": "Building A",
#      "annotatedUser": "<real staff email>", "deviceId": "<uuid>",
#      "orgUnitPath": "/Devices/Deprovisioned", "serialNumber": "5CD1234ABC",
#      "status": "DEPROVISIONED"}
#
#   This CONFIRMS: (1) formatjson uses camelCase keys matching the Admin SDK
#   Directory API's chromeosdevices resource - serialNumber, status,
#   orgUnitPath, annotatedAssetId, annotatedLocation, annotatedUser; (2) a
#   single-device lookup returns a bare JSON object, not a one-item array;
#   (3) gam's real output can include keys that were never asked for in the
#   "fields" list (deviceId showed up unrequested) - so this parser must
#   ignore any key it does not recognize instead of treating an extra key
#   as an error.
#
#   MULTI-DEVICE SHAPE - CONFIRMED 08-10-2026 (live re-test after a real
#   failure report): Gabe hit "Extra data: line 2 column 1" every time he
#   pasted multiple serials or used a multi-row CSV. That is because the
#   original guess below (a JSON array for multiple devices) was WRONG.
#   A real read-only call against 3 real district devices -
#
#     C:\GAM7\gam.exe info cros cros_sn 5CD5678DEF,5CD9012GHI,5CD3456JKL
#         fields status,serialnumber,orgunitpath,annotatedassetid,
#         annotatedlocation,annotateduser formatjson
#
#   - printed stdout as NEWLINE-DELIMITED JSON: one complete, independent
#   JSON object per line, NOT a JSON array wrapping all of them (and never
#   an array even for the single-device case - that was already correct).
#   gam's per-device progress logging ("Getting all CrOS Devices...", "Got 1
#   CrOS Device...") was confirmed to go to stderr only, never mixed into
#   stdout, so it does not need to be filtered out of raw_text here.
#   parse_lookup_json() below now parses raw_text line-by-line to match this
#   confirmed shape instead of trying to json.loads() the whole text as one
#   value (which is exactly what produced the "Extra data" error: the old
#   code parsed line 1 as a complete object and then choked on line 2).
#
#   (The error-handling design rationale for parse_lookup_json() itself -
#   why malformed input is normalized to ValueError rather than left to
#   raise whatever raw exception Python would otherwise produce - is kept
#   as a comment directly above that function below, next to the code it
#   explains, rather than repeated up here.)
#
#   KNOWN TRADEOFF (code review, 08-10-2026): one malformed NDJSON line
#   currently fails ValueError for the WHOLE call instead of preserving the
#   other, valid devices' results - deliberately not redesigned as part of
#   this bug fix (would require changing the "value or ValueError" contract
#   this function, gam_calls.py, and gui.py all share), but worth
#   reconsidering if it causes real friction on large batches against
#   a large district fleet (this one was ~4,000 devices).

import json

from . import actions

# GamCommands.txt <CrOSAction> - each action this tool can run maps to the
# device status GAM's own status enum uses for that action's result
# (disable -> DISABLED, reenable -> ACTIVE, every deprovision_* ->
# DEPROVISIONED). The table itself now lives in actions.py, the one place
# that defines the actions, so a new action cannot be added here and
# forgotten there. This name is kept as an alias so workflow.py and the
# existing tests, which have always read device_lookup.ACTION_TARGET_STATUS,
# keep working unchanged.
ACTION_TARGET_STATUS = actions.TARGET_STATUS


# ERROR-HANDLING DESIGN for parse_lookup_json() below: per gam_runner.py's
# CALLER OBLIGATION notes, the normal call path only reaches this function
# after a caller has already confirmed gam's subprocess result had
# returncode == 0 - so in practice raw_text here should always be real
# formatjson output, and a well-formed one at that. However, this function
# does not control that and cannot assume it was followed (e.g. a future
# call site forgets the returncode check, or gam itself prints a plain-text
# error to stdout in some edge case instead of JSON). Unlike gam_runner.py's
# decision to let subprocess.TimeoutExpired and OSError propagate raw
# (those are already specific, well-documented exceptions this module has
# nothing useful to add to), none of the raw exceptions Python would
# otherwise raise here - json.JSONDecodeError on one line, TypeError from a
# non-string raw_text, AttributeError from a line that parses to something
# other than a dict - say by themselves "this was supposed to be gam's
# device lookup output." So, matching the pattern serials.py already
# established for its own external-input boundary functions (CSV reading),
# EVERY malformed-input case below is caught/checked explicitly and
# normalized to ValueError with a message that adds that missing context.
# This gives callers (the GUI, a later task) exactly one exception type to
# catch from this function, regardless of exactly how the input was bad.
#
# ONE-BAD-LINE-AMONG-GOOD-ONES DECISION: per the confirmed NDJSON shape
# above, raw_text can carry results for several devices in one call - one
# line each. If exactly one of those lines is malformed (bad JSON, or valid
# JSON that is not an object), this function raises ValueError for the
# WHOLE call rather than silently dropping just that one line and returning
# results for the rest. Reasoning: a malformed line here is not an expected,
# normal occurrence the way "a requested field was omitted from an
# otherwise-valid object" is (that case is still handled by degrading to ""
# per-field, below) - it means gam's stdout was not the clean formatjson
# output this function contracts to parse, which per the district's "never
# let a script silently fail" rule should surface loudly rather than
# quietly return a partial device list that looks complete to the GUI/
# workflow.py (which cannot tell "this serial was never in the batch" apart
# from "this serial's line failed to parse and was dropped"). The line
# number (1-based, matching what a person would count if they opened the
# text in an editor) is included in the message so the specific bad line
# can actually be found. (See this module's top-of-file Notes block for a
# flagged tradeoff of this fail-whole-batch choice at large fleet scale.)
def parse_lookup_json(raw_text):
    if not isinstance(raw_text, str):
        # json.loads(None) - or any other non-string - raises TypeError,
        # not JSONDecodeError, which would otherwise slip past the
        # try/except below and break the "callers only need to catch
        # ValueError" contract this module promises. Checked explicitly
        # up front rather than relying on json.loads() to fail loudly.
        raise ValueError(
            "Could not parse device lookup output - expected a JSON text "
            "string, got: {0}".format(type(raw_text).__name__)
        )

    if not raw_text.strip():
        # An empty (or whitespace-only) string has no lines to parse, so
        # the loop below would otherwise just fall through and return an
        # empty dict - silently indistinguishable from "gam looked up zero
        # devices" instead of the error this actually is (per gam_runner.py
        # CALLER OBLIGATION notes, this function is only reached after a
        # returncode == 0 check, so empty stdout on a successful run is
        # unexpected and worth surfacing rather than swallowing).
        raise ValueError(
            "Could not parse device lookup output as JSON - gam.exe may "
            "have printed an error instead of the expected formatjson "
            "output: received empty text"
        )

    # NDJSON (newline-delimited JSON) - CONFIRMED shape per this module's
    # Notes above: gam's formatjson prints one complete, independent JSON
    # object per line, for one device as much as for many. Splitting on
    # line breaks and parsing each line on its own (rather than handing the
    # whole multi-line raw_text to a single json.loads() call, which is
    # exactly what produced the real "Extra data: line 2 column 1" error
    # this fix addresses - json.loads() parsed line 1 as one complete value
    # and then had nothing to do with the rest of the text) is what makes
    # this work for any number of devices, including exactly one.
    lines = raw_text.splitlines()

    result = {}
    for line_number, line in enumerate(lines, start=1):
        # A blank line (gam does not appear to print one between device
        # objects, but a trailing newline at the end of stdout is common
        # and str.splitlines() turns that into a final empty-string
        # element) carries no device data and is not a parsing failure -
        # skip it rather than trying to json.loads() an empty string, which
        # would otherwise raise JSONDecodeError over nothing.
        stripped_line = line.strip()
        if not stripped_line:
            continue

        try:
            # Turn this one line of gam's raw stdout text into Python data.
            entry = json.loads(stripped_line)
        except json.JSONDecodeError as parse_error:
            raise ValueError(
                "Could not parse device lookup output as JSON on line {0} "
                "- gam.exe may have printed an error instead of the "
                "expected formatjson output: {1}".format(
                    line_number, parse_error
                )
            ) from parse_error

        if not isinstance(entry, dict):
            # This line was valid JSON, but not a device object (with
            # .get()-able keys like "serialNumber") - e.g. gam printed a
            # lone JSON number, string, or (as in one regression-test case)
            # a JSON array on its own line. Calling entry.get(...) on it
            # below would otherwise raise a raw AttributeError, breaking
            # the "callers only need to catch ValueError" contract
            # documented above. This is not a shape formatjson is
            # documented or observed to ever produce; it is defense-in-
            # depth against a case that should not happen in practice.
            raise ValueError(
                "Unexpected JSON shape from device lookup output on line "
                "{0} - expected a device object, got: {1}".format(
                    line_number, type(entry).__name__
                )
            )

        # Chromebook serials are conventionally upper-alnum, and every
        # other module in this tool (serials.py, workflow.py) keys and
        # compares serials upper-cased - normalizing here too means a
        # lookup result always lines up with the serial list the rest of
        # the tool is already working with, regardless of what case gam
        # itself happened to return.
        # entry.get("serialNumber", "") is NOT enough on its own: the ""
        # default only kicks in when the key is absent entirely. A line
        # with a literal "serialNumber": null (valid JSON, gam has not been
        # observed to produce this but nothing rules it out) makes .get()
        # return None instead, and str(None) is the literal text "None" -
        # which is truthy and would sail past the "if not serial: continue"
        # guard below, storing a phantom "NONE" device key instead of being
        # dropped like a genuinely missing serial. "or \"\"" catches both
        # the missing-key case and the explicit-null case the same way.
        serial = str(entry.get("serialNumber") or "").strip().upper()
        if not serial:
            # A device entry with no serial number at all cannot be keyed
            # or matched back to anything the caller asked for - drop it
            # rather than storing it under the empty string, which no real
            # serial would ever equal.
            continue

        # .get(key, "") on every field (rather than entry[key]) is
        # deliberate: per this module's Notes above, gam's real output can
        # both include unrequested extra keys (ignored automatically here,
        # since only the keys named below are ever read out of entry) and,
        # in principle, omit a requested one (e.g. a narrower "fields" list
        # than this tool's own LOOKUP_FIELDS in some future call site) -
        # either way this function must not raise a KeyError over it, per
        # the district's "never let a script silently fail" rule; a missing
        # value degrades to an empty string instead of blowing up the whole
        # lookup for every other device in the same call.
        result[serial] = {
            "status": entry.get("status", ""),
            "org_unit_path": entry.get("orgUnitPath", ""),
            "annotated_asset_id": entry.get("annotatedAssetId", ""),
            "annotated_location": entry.get("annotatedLocation", ""),
            "annotated_user": entry.get("annotatedUser", ""),
        }
    return result

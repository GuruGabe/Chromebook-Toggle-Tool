# tests/test_device_lookup.py
# ASCII only. Tests device_lookup.parse_lookup_json against fixture JSON
# strings - no real gam.exe call is made here (device_lookup.py never shells
# out itself; that is gam_runner.py's job).
#
# PII NOTE: the single-device fixture below is based on a REAL live
# "gam info cros ... formatjson" call run against a real district device
# (serial 5CD1234ABC) to confirm formatjson's exact JSON key casing before
# this module was written - see device_lookup.py's module Notes for the
# full verification record. The real call's annotatedUser field contained a
# real staff member's email address; that real address is deliberately NOT
# reproduced here. "jdoe@example.com" below is a fake placeholder standing
# in for it, per the district's PII-in-shipped-code rule. Every other field
# in the single-device fixture (serial, status, orgUnitPath,
# annotatedAssetId, annotatedLocation, deviceId) is the real confirmed
# shape/values from that call, since none of those are personal information.
import unittest

from chromebook_toggle import device_lookup

# Real confirmed shape from a live read-only call (single device -> bare
# JSON object, not an array) - see device_lookup.py's module Notes for the
# full command and verification record. deviceId is included on purpose:
# it was NOT one of the fields requested in the live call's "fields" list,
# yet gam's real output included it anyway - this fixture exists to prove
# parse_lookup_json() tolerates an unrequested/unrecognized key rather than
# erroring out on it.
#
# Kept on a SINGLE line (not pretty-printed across multiple lines) on
# purpose: the confirmed real shape (per the NDJSON verification recorded in
# device_lookup.py's module Notes) is one compact JSON object per line, for
# one device exactly as much as for many, and parse_lookup_json() now parses
# raw_text line-by-line - a pretty-printed object spanning several lines
# would not match what gam actually prints and would not parse correctly
# under the current line-based parser.
SAMPLE_SINGLE_DEVICE_JSON = (
    '{"annotatedAssetId": "Building A", "annotatedLocation": "Building A", '
    '"annotatedUser": "jdoe@example.com", '
    '"deviceId": "8b1e6a5e-10a8-46b1-9cb0-1a620c76d0b5", '
    '"orgUnitPath": "/Devices/Deprovisioned", "serialNumber": "5cd1234abc", '
    '"status": "DEPROVISIONED"}'
)

# CONFIRMED SHAPE - NDJSON (newline-delimited JSON): this multi-device
# fixture was updated 08-10-2026 after a real failure report - Gabe pasted
# multiple serials / a multi-row CSV and hit "Extra data: line 2 column 1"
# every time, because the previous version of this fixture (and the parser
# it tested) assumed multiple devices came back as a JSON ARRAY. That
# assumption was wrong. A real read-only call against 3 real district devices
# (see device_lookup.py's module Notes for the full command and record)
# showed gam's real formatjson output is one independent JSON object per
# line, NOT an array. This fixture now mirrors that real shape: three
# lines, each a standalone JSON object, based on the real call's field
# values but with the two real staff email addresses replaced by the fake
# placeholders this project's tests always use (jdoe@example.com /
# asmith@example.com) - see the PII note at the top of this file.
SAMPLE_MULTI_DEVICE_JSON = """
{"annotatedAssetId": "Building A", "annotatedLocation": "Building A", "annotatedUser": "jdoe@example.com", "deviceId": "4c6df89f-6589-48d3-8d0a-76b779c88419", "orgUnitPath": "/Devices/Deprovisioned", "serialNumber": "5CD5678DEF", "status": "DEPROVISIONED"}
{"annotatedAssetId": "Building A Teacher Loaner", "annotatedLocation": "Building A", "annotatedUser": "jdoe@example.com", "deviceId": "2e9b3037-e5b4-4155-9967-13f8bfd9ce91", "orgUnitPath": "/Devices/Inactive", "serialNumber": "5CD9012GHI", "status": "DISABLED"}
{"annotatedAssetId": "Building A", "annotatedLocation": "Building A", "annotatedUser": "asmith@example.com", "deviceId": "4cabc4e9-5443-467f-bc2e-34bfb36e8bf1", "orgUnitPath": "/Devices/Deprovisioned", "serialNumber": "5CD3456JKL", "status": "DEPROVISIONED"}
"""

# Regression fixture: one malformed line among otherwise-valid NDJSON lines.
# Confirms parse_lookup_json()'s ONE-BAD-LINE-AMONG-GOOD-ONES decision (see
# the comment above that function in device_lookup.py) - the whole call
# fails loudly with ValueError rather than silently returning results for
# only the good lines, since a partial result set would look identical to
# "these serials were simply never in the batch" to any caller.
SAMPLE_MULTI_DEVICE_JSON_WITH_ONE_BAD_LINE = """
{"serialNumber": "5CD5678DEF", "status": "DEPROVISIONED", "orgUnitPath": "/Devices/Deprovisioned", "annotatedAssetId": "Building A", "annotatedLocation": "Building A", "annotatedUser": "jdoe@example.com"}
{this is not valid json at all}
{"serialNumber": "5CD3456JKL", "status": "DEPROVISIONED", "orgUnitPath": "/Devices/Deprovisioned", "annotatedAssetId": "Building A", "annotatedLocation": "Building A", "annotatedUser": "asmith@example.com"}
"""


class TestParseLookupJson(unittest.TestCase):

    def test_parses_single_device_object(self):
        # A bare JSON object (one device) must come back as a one-entry
        # dict keyed by the UPPER-CASED serial, with every sub-key renamed
        # to the snake_case names the rest of this tool's modules expect.
        result = device_lookup.parse_lookup_json(SAMPLE_SINGLE_DEVICE_JSON)
        self.assertIn("5CD1234ABC", result)
        entry = result["5CD1234ABC"]
        self.assertEqual(entry["status"], "DEPROVISIONED")
        self.assertEqual(entry["org_unit_path"], "/Devices/Deprovisioned")
        self.assertEqual(entry["annotated_asset_id"], "Building A")
        self.assertEqual(entry["annotated_location"], "Building A")
        self.assertEqual(entry["annotated_user"], "jdoe@example.com")

    def test_parses_multi_device_ndjson(self):
        # Exercises the CONFIRMED real shape: multiple devices come back as
        # newline-delimited JSON (one object per line), not a JSON array.
        # See the fixture's comment above and device_lookup.py's module
        # Notes for the live verification record this replaced the old,
        # wrong, JSON-array fixture with.
        result = device_lookup.parse_lookup_json(SAMPLE_MULTI_DEVICE_JSON)
        self.assertEqual(
            set(result.keys()), {"5CD5678DEF", "5CD9012GHI", "5CD3456JKL"}
        )
        self.assertEqual(result["5CD9012GHI"]["status"], "DISABLED")
        self.assertEqual(
            result["5CD9012GHI"]["org_unit_path"], "/Devices/Inactive"
        )
        self.assertEqual(
            result["5CD3456JKL"]["annotated_user"], "asmith@example.com"
        )

    def test_multi_device_ndjson_with_one_bad_line_raises_value_error(self):
        # Confirms the ONE-BAD-LINE-AMONG-GOOD-ONES error-handling decision
        # documented above parse_lookup_json() in device_lookup.py: one
        # malformed line among otherwise-valid NDJSON lines fails the whole
        # call with ValueError, rather than silently returning results for
        # just the two good lines and dropping the bad one.
        #
        # Also asserts the exception message names the correct 1-based line
        # number (3, not 2) - line 1 of the fixture is the blank line right
        # after the opening triple-quote, line 2 is the first good device,
        # and line 3 is "{this is not valid json at all}", the bad one.
        # Checking assertRaises(ValueError) alone would not catch a future
        # regression that reports the wrong line number, since any
        # ValueError would still make that bare assertion pass.
        with self.assertRaises(ValueError) as raised:
            device_lookup.parse_lookup_json(
                SAMPLE_MULTI_DEVICE_JSON_WITH_ONE_BAD_LINE
            )
        self.assertIn("line 3", str(raised.exception))

    def test_ignores_unexpected_extra_keys_like_deviceid(self):
        # The real live call's output included "deviceId" even though it was
        # never in the requested "fields" list - confirms a stray/unasked-for
        # key does not raise or otherwise break parsing; it is just dropped.
        result = device_lookup.parse_lookup_json(SAMPLE_SINGLE_DEVICE_JSON)
        entry = result["5CD1234ABC"]
        self.assertNotIn("deviceId", entry)
        self.assertNotIn("device_id", entry)

    def test_missing_keys_default_to_empty_string_not_a_crash(self):
        # A device entry that is missing one of the sub-keys this tool
        # normally asks for (e.g. a stripped-down fields= list, or a future
        # GAM version that renames/omits something) must not raise - it
        # should come back as "" for that field, same as .get(key, "") does.
        sparse_json = '{"serialNumber": "ZZZ999"}'
        result = device_lookup.parse_lookup_json(sparse_json)
        entry = result["ZZZ999"]
        self.assertEqual(entry["status"], "")
        self.assertEqual(entry["org_unit_path"], "")
        self.assertEqual(entry["annotated_asset_id"], "")
        self.assertEqual(entry["annotated_location"], "")
        self.assertEqual(entry["annotated_user"], "")

    def test_null_serial_number_is_dropped_not_stored_as_literal_none(self):
        # Regression test for a code-review finding: entry.get("serialNumber",
        # "") only falls back to "" when the key is ABSENT. A line with a
        # literal "serialNumber": null (valid JSON; gam has not been observed
        # to actually produce this, but nothing guarantees it never will) makes
        # .get() return None instead, and the old str(None) code path turned
        # that into the literal text "NONE" after .upper() - a phantom device
        # key that would have sailed right past the "if not serial: continue"
        # guard, since "NONE" is a non-empty, truthy string. Also proves a
        # good line elsewhere in the same NDJSON block is unaffected - the
        # null-serial line is simply dropped, not treated as a parse failure.
        ndjson_with_null_serial = (
            '{"serialNumber": null, "status": "ACTIVE"}\n'
            '{"serialNumber": "ZZZ999", "status": "DISABLED"}'
        )
        result = device_lookup.parse_lookup_json(ndjson_with_null_serial)
        self.assertNotIn("NONE", result)
        self.assertEqual(set(result.keys()), {"ZZZ999"})

    def test_empty_string_raises_value_error(self):
        # Defense-in-depth: per gam_runner.py's CALLER OBLIGATION notes, the
        # normal flow only calls this function after confirming
        # result.returncode == 0, but this function does not control that -
        # if it is ever handed empty/garbage text anyway (e.g. the pre-flight
        # check in a later task is somehow bypassed, or gam prints a plain-
        # text error instead of JSON), an empty string has no lines to parse
        # and would otherwise silently come back as an empty dict rather than
        # surfacing that something is wrong. parse_lookup_json() checks for
        # this explicitly and raises ValueError, matching the same "one
        # exception type the GUI has to catch, with context added" pattern
        # serials.py already established for its own external-input boundary
        # functions.
        with self.assertRaises(ValueError):
            device_lookup.parse_lookup_json("")

    def test_non_json_text_raises_value_error(self):
        # Same reasoning as the empty-string case above, but for a
        # non-empty string that still is not valid JSON on its one line
        # (e.g. gam printed a plain-text error message like "ERROR: not
        # found" to stdout instead of formatjson output).
        with self.assertRaises(ValueError):
            device_lookup.parse_lookup_json("ERROR: 5CD1234ABC, does not exist")

    def test_unexpected_line_json_shape_raises_value_error(self):
        # A line that is valid JSON but not a device object (e.g. a lone
        # JSON number) - not something json.loads() itself rejects, so this
        # has to be checked explicitly per line rather than relying on
        # JSONDecodeError to catch it.
        with self.assertRaises(ValueError):
            device_lookup.parse_lookup_json("42")

    def test_line_that_is_a_json_array_raises_value_error(self):
        # Regression test for a code-review finding against the original
        # (pre-NDJSON) implementation: a JSON array whose elements are not
        # device objects (e.g. plain strings) used to reach entry.get(...)
        # in the per-entry loop and raise a raw, uncaught AttributeError
        # ('str' object has no attribute 'get') instead of the ValueError
        # this module's docstring promises callers only ever have to catch.
        # Under the current line-based parser, a line that parses to a list
        # rather than a device object is caught by the same
        # "not isinstance(entry, dict)" check used for any other wrong-shape
        # line - reproduces the exact input from the original review report,
        # now as a single NDJSON line rather than a whole-input JSON array.
        with self.assertRaises(ValueError):
            device_lookup.parse_lookup_json('["5CD1234ABC", "9XY12345AB"]')

    def test_none_raw_text_raises_value_error_not_type_error(self):
        # Regression test for a code-review finding: json.loads(None) raises
        # TypeError, not json.JSONDecodeError, which would have slipped
        # past the try/except in parse_lookup_json() and broken the "callers
        # only need to catch ValueError" contract. gam_runner's subprocess
        # always yields a str, so this is a low-probability defensive check
        # rather than an expected real-world path, but it is still not
        # allowed to raise something other than ValueError.
        with self.assertRaises(ValueError):
            device_lookup.parse_lookup_json(None)

    def test_action_target_status_mapping(self):
        # GamCommands.txt:2468-2478 - disable/reenable are the only two
        # actions this tool uses; their resulting status values are
        # DISABLED (disable) and ACTIVE (reenable) per the CrOSFieldName
        # status enum.
        self.assertEqual(device_lookup.ACTION_TARGET_STATUS["disable"], "DISABLED")
        self.assertEqual(device_lookup.ACTION_TARGET_STATUS["reenable"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()

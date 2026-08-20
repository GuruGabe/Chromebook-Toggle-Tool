# tests/test_sheet_url.py
#
# Script:   test_sheet_url.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Unit tests for chromebook_toggle/sheet_url.py - covers pulling the
#   Drive file ID and tab (gid) out of a pasted Google Sheets URL: the
#   happy path with both pieces present, the common case where the user
#   never switched tabs (no gid in the URL at all), and the realistic
#   malformed/unexpected shapes a copy-pasted URL can take.
#
# Usage:
#   python -m unittest tests.test_sheet_url -v
#   (run from the Chromebook-Toggle-Tool project root)
#
# Requirements:
#   Python 3.14, stdlib only (unittest, re). No admin rights needed - this
#   module does no file or network I/O, it only parses a string.
#
# Notes:
#   ASCII only. This test file's own bytes are pure ASCII; there is no
#   non-ASCII test data needed here (unlike test_serials.py/test_config.py)
#   since a Google Sheets URL is itself always plain ASCII.

import unittest

from chromebook_toggle import sheet_url


class TestParseSheetUrl(unittest.TestCase):

    def test_extracts_file_id_and_gid(self):
        # The baseline "user clicked a specific tab, then copied the URL"
        # shape: file ID and gid both present, gid attached with "#".
        url = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=123456789"
        file_id, gid = sheet_url.parse_sheet_url(url)
        self.assertEqual(file_id, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "123456789")

    def test_defaults_gid_to_zero_when_absent(self):
        # The other common real shape: the user never switched tabs, so
        # Google never appended a "#gid=" fragment to the URL at all. "0"
        # is the first tab's gid, so this is the correct default rather
        # than an error.
        url = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"
        file_id, gid = sheet_url.parse_sheet_url(url)
        self.assertEqual(file_id, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "0")

    def test_invalid_url_raises_value_error(self):
        # A URL that is not a Google Sheets link at all (e.g. pasted the
        # wrong thing) - no "/spreadsheets/d/" segment present anywhere.
        with self.assertRaises(ValueError):
            sheet_url.parse_sheet_url("https://example.com/not-a-sheet")

    def test_empty_string_raises_value_error(self):
        # Guards the "clicked Toggle before pasting anything" case in the
        # GUI (a later task) - must raise the same clear ValueError as any
        # other non-matching input, not some unrelated crash.
        with self.assertRaises(ValueError):
            sheet_url.parse_sheet_url("")

    def test_missing_file_id_raises_value_error(self):
        # A mangled URL where the "/spreadsheets/d/" segment is present
        # but nothing follows it before the next slash - e.g. a copy-paste
        # that got truncated. Must not match an empty file ID; must raise
        # the same clear ValueError as any other non-matching input.
        with self.assertRaises(ValueError):
            sheet_url.parse_sheet_url("https://docs.google.com/spreadsheets/d//edit#gid=5")

    def test_extracts_gid_with_extra_query_params_before_it(self):
        # The URL Google produces from the "Share > Copy link" button
        # includes extra query params (usp=sharing, and sometimes
        # rtpof/sd from a "copy link to this range" action) between the
        # file ID and the "#gid=" fragment. Those params must not confuse
        # the file-ID or gid extraction.
        url = (
            "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz"
            "/edit?usp=sharing&rtpof=true&sd=true#gid=987654321"
        )
        file_id, gid = sheet_url.parse_sheet_url(url)
        self.assertEqual(file_id, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "987654321")

    def test_bare_query_string_gid_is_ignored_defaults_to_zero(self):
        # Locks in a deliberate design decision (documented in
        # sheet_url.py's module docstring): a bare "?gid=" query parameter
        # is NOT extracted, only "#gid=" (optionally preceded by other
        # query params). This is not a real shape Google produces in the
        # modern URL scheme, so a URL that happens to look like this must
        # fall back to the "0" default rather than picking up "99" - this
        # guards against re-widening _GID_PATTERN to "[#&?]gid=" again,
        # which was tried and reverted once already in this file's
        # history after review found no real-world evidence for it.
        url = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit?gid=99"
        file_id, gid = sheet_url.parse_sheet_url(url)
        self.assertEqual(file_id, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "0")


if __name__ == "__main__":
    unittest.main()

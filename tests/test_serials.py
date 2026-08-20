# tests/test_serials.py
#
# Script:   test_serials.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.1
#
# Purpose:
#   Unit tests for chromebook_toggle/serials.py - covers all three input
#   modes' normalization path: multiline text box entry, CSV file reading
#   (both accepted header spellings, case-insensitive, the missing-column
#   error case, and BOM handling), and the temp CSV writer used to hand
#   Individual-entry mode's serial list to the same gam batch-csv command
#   CSV/Sheet mode uses (including its non-ASCII-serial failure path).
#
# Usage:
#   python -m unittest tests.test_serials -v
#   (run from the Chromebook-Toggle-Tool project root)
#
# Requirements:
#   Python 3.14, stdlib only (unittest, csv, glob, os, tempfile). No admin
#   rights needed - everything runs against temp files/directories, never
#   any real district data.
#
# Notes:
#   ASCII only. Tests chromebook_toggle.serials using tempfile-based temp
#   directories/files so no real CSV or GAM data is touched during the
#   test run. Where a non-ASCII character is needed as test input (see
#   TestWriteTempSerialCsv below), it is built with chr(0xE9) rather than
#   a literal character, so this source file's own bytes stay pure ASCII.

import csv
import glob
import os
import tempfile
import unittest

from chromebook_toggle import serials


class TestParseMultilineSerials(unittest.TestCase):

    def test_splits_strips_and_uppercases(self):
        text = "  abc123  \nDEF456\n\nabc123\n"
        # Blank lines are dropped, whitespace stripped, case normalized to
        # upper (Chromebook serials are conventionally upper-alnum), and
        # exact duplicates removed while keeping first-seen order.
        result = serials.parse_multiline_serials(text)
        self.assertEqual(result, ["ABC123", "DEF456"])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(serials.parse_multiline_serials(""), [])


class TestReadCsvSerials(unittest.TestCase):

    def _write_csv(self, tmp_dir, header, rows):
        path = os.path.join(tmp_dir, "input.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([header])
            for row in rows:
                writer.writerow([row])
        return path

    def test_accepts_serial_header(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = self._write_csv(tmp_dir, "Serial", ["abc123", "DEF456", ""])
            self.assertEqual(serials.read_csv_serials(path), ["ABC123", "DEF456"])

    def test_accepts_serialnumber_header_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = self._write_csv(tmp_dir, "serialnumber", ["xyz789"])
            self.assertEqual(serials.read_csv_serials(path), ["XYZ789"])

    def test_missing_serial_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = self._write_csv(tmp_dir, "AssetTag", ["12345"])
            with self.assertRaises(ValueError):
                serials.read_csv_serials(path)

    def test_missing_file_raises_clear_error(self):
        # Simulates a stale/typo'd path picked in the GUI's file browser
        # (a later task). read_csv_serials() must not let a raw
        # FileNotFoundError/traceback bubble up; it should raise something
        # that names the path so the IT admin knows which file was bad.
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_path = os.path.join(tmp_dir, "does_not_exist.csv")
            with self.assertRaises(ValueError) as raised:
                serials.read_csv_serials(missing_path)
            self.assertIn(missing_path, str(raised.exception))

    def test_empty_file_raises_clear_error(self):
        # A zero-byte file has no header row at all, e.g. someone created a
        # blank placeholder file or a download was interrupted.
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "empty.csv")
            with open(path, "w", encoding="utf-8"):
                pass
            with self.assertRaises(ValueError):
                serials.read_csv_serials(path)

    def test_recognizes_header_with_leading_utf8_bom(self):
        # Simulates the classic "saved as CSV from Excel on Windows" file:
        # Excel writes a UTF-8 byte-order-mark before the header row.
        # encoding="utf-8-sig" on write adds a real BOM (the same 3 bytes
        # Excel writes); read_csv_serials() must still recognize "Serial"
        # as the header rather than seeing a mangled first column name and
        # raising the missing-column ValueError.
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "bom.csv")
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Serial"])
                writer.writerow(["abc123"])
            self.assertEqual(serials.read_csv_serials(path), ["ABC123"])


class TestWriteTempSerialCsv(unittest.TestCase):

    def test_writes_serial_header_and_rows(self):
        path = serials.write_temp_serial_csv(["ABC123", "DEF456"])
        try:
            with open(path, newline="", encoding="ascii") as f:
                reader = csv.reader(f)
                rows = list(reader)
            self.assertEqual(rows, [["Serial"], ["ABC123"], ["DEF456"]])
        finally:
            os.remove(path)

    def test_writes_header_only_for_empty_list(self):
        # An empty serial list is a valid (if pointless) input - e.g. the
        # GUI calls this before validating the list is non-empty. It must
        # produce a well-formed header-only CSV, not crash.
        path = serials.write_temp_serial_csv([])
        try:
            with open(path, newline="", encoding="ascii") as f:
                reader = csv.reader(f)
                rows = list(reader)
            self.assertEqual(rows, [["Serial"]])
        finally:
            os.remove(path)

    def test_raises_value_error_and_removes_orphan_on_non_ascii_serial(self):
        # Simulates a serial that picked up a non-ASCII character somewhere
        # upstream - e.g. pasted from Word/Outlook/a scanned inventory
        # sheet into Individual-entry mode, or read from a hand-edited
        # CSV's Serial column. Built with chr(0xE9) (e-acute, U+00E9)
        # rather than a literal accented character, so this source file's
        # own bytes stay pure ASCII; chr() produces the real character at
        # runtime, so the test value is unchanged. The temp file is opened
        # with encoding="ascii", so writing this value must raise
        # ValueError (not a raw UnicodeEncodeError), mirroring
        # test_config.py's
        # test_save_settings_raises_clear_error_when_value_is_non_ascii.
        non_ascii_serial = "ABC" + chr(0xE9) + "123"

        # Snapshot which chromebook_toggle_* temp files already exist so
        # the assertion below only looks at files this call itself
        # creates - proves the partially-written temp file created before
        # the bad row is hit gets cleaned up rather than orphaned under
        # %TEMP%, per the "no stray temp files on failure" requirement.
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, "chromebook_toggle_*")
        before = set(glob.glob(pattern))

        with self.assertRaises(ValueError):
            serials.write_temp_serial_csv(["ABC123", non_ascii_serial])

        after = set(glob.glob(pattern))
        self.assertEqual(after - before, set())


if __name__ == "__main__":
    unittest.main()

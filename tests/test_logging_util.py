# tests/test_logging_util.py
#
# Tests for chromebook_toggle/logging_util.py (Task 7).
#
# Covers: missing-Logs-dir creation, the full row shape (including the
# Timestamp column), None -> "" defaulting for previous/new status, an
# empty results list producing a header-only file, the encoding="ascii"
# guard actually rejecting a non-ASCII value, os.makedirs() behavior when
# log_dir already exists, and the returned log_path's filename pattern.

import csv
import os
import tempfile
import unittest

from chromebook_toggle import logging_util
from chromebook_toggle.workflow import ResultRow


# Regex for the MM-DD-YYYY_HH-MM-SS timestamp format write_log() uses,
# per this district's standing log timestamp format. Used both to
# check the Timestamp CSV column and the timestamp embedded in the
# filename.
TIMESTAMP_PATTERN = r"\d{2}-\d{2}-\d{4}_\d{2}-\d{2}-\d{2}"


class TestWriteLog(unittest.TestCase):

    def test_creates_log_dir_and_writes_expected_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")  # deliberately does not exist yet
            results = [
                ResultRow("ABC123", "ACTIVE", "DISABLED", True),
                ResultRow("DEF456", "ACTIVE", "ACTIVE", False),
            ]
            log_path = logging_util.write_log(log_dir, "disable", results)

            self.assertTrue(os.path.isfile(log_path))
            with open(log_path, newline="", encoding="ascii") as f:
                rows = list(csv.reader(f))

            self.assertEqual(rows[0], ["Serial", "Action", "PreviousStatus", "NewStatus", "Result", "Timestamp"])
            # Full row including the Timestamp column (index 5) - not
            # sliced to [0:5], so a regression in how the timestamp is
            # written would actually be caught here.
            self.assertEqual(rows[1][0:5], ["ABC123", "disable", "ACTIVE", "DISABLED", "SUCCESS"])
            self.assertRegex(rows[1][5], "^" + TIMESTAMP_PATTERN + "$")
            self.assertEqual(rows[2][0:5], ["DEF456", "disable", "ACTIVE", "ACTIVE", "FAILED"])
            self.assertRegex(rows[2][5], "^" + TIMESTAMP_PATTERN + "$")
            # Both data rows come from the same write_log() call, so per
            # the module's "one shared timestamp for the whole run"
            # comment, they must carry the identical timestamp value.
            self.assertEqual(rows[1][5], rows[2][5])

    def test_none_previous_and_new_status_default_to_empty_string(self):
        # Exercises workflow.py's documented case: new_status (and, in
        # principle, previous_status) can legitimately be None - e.g. a
        # device missing from the post-action lookup. write_log()'s "or
        # ''" is supposed to turn that into an empty CSV cell, never the
        # literal text "None".
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            results = [ResultRow("GHI789", None, None, False)]
            log_path = logging_util.write_log(log_dir, "reenable", results)

            with open(log_path, newline="", encoding="ascii") as f:
                rows = list(csv.reader(f))

            # PreviousStatus and NewStatus (indices 2 and 3) must be empty
            # strings, not the text "None".
            self.assertEqual(rows[1][0:5], ["GHI789", "reenable", "", "", "FAILED"])

    def test_empty_results_list_writes_header_only_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            log_path = logging_util.write_log(log_dir, "disable", [])

            with open(log_path, newline="", encoding="ascii") as f:
                rows = list(csv.reader(f))

            # Only the header row - no data rows - for a run with nothing
            # to report (e.g. every requested serial was skipped at
            # review time).
            self.assertEqual(rows, [["Serial", "Action", "PreviousStatus", "NewStatus", "Result", "Timestamp"]])

    def test_non_ascii_value_raises_unicode_encode_error(self):
        # Per CLAUDE.md's ASCII-only rule, this test uses chr(0xNN) to
        # build the non-ASCII test value rather than a literal non-ASCII
        # character in this source file, keeping the test file itself
        # strict ASCII while still exercising a genuinely non-ASCII
        # runtime value. chr(0xE9) is "e with an acute accent" (e-acute),
        # a character that cannot be encoded as ASCII.
        non_ascii_serial = "ABC" + chr(0xE9) + "123"
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            results = [ResultRow(non_ascii_serial, "ACTIVE", "DISABLED", True)]

            # The encoding="ascii" file handle is expected to reject this
            # value with UnicodeEncodeError at write time - the cheap
            # guard against an unexpected non-ASCII value silently ending
            # up in the log, described in the module's own comment on
            # encoding="ascii".
            with self.assertRaises(UnicodeEncodeError):
                logging_util.write_log(log_dir, "disable", results)

    def test_makedirs_succeeds_when_log_dir_already_exists(self):
        # os.makedirs(..., exist_ok=True) must not raise (and write_log()
        # must still succeed) on a second run against a Logs folder a
        # prior run already created - only the "does not exist yet"
        # branch was covered before this test existed.
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            os.makedirs(log_dir)  # pre-create it before write_log() ever runs
            results = [ResultRow("JKL012", "ACTIVE", "DISABLED", True)]

            log_path = logging_util.write_log(log_dir, "disable", results)

            self.assertTrue(os.path.isfile(log_path))

    def test_log_path_filename_matches_expected_pattern(self):
        # Confirms the actual filename shape
        # (ChromebookToggle_<action>_<timestamp>.csv), not just that some
        # file exists at the returned path.
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            results = [ResultRow("MNO345", "ACTIVE", "DISABLED", True)]

            log_path = logging_util.write_log(log_dir, "reenable", results)

            filename = os.path.basename(log_path)
            self.assertRegex(filename, "^ChromebookToggle_reenable_" + TIMESTAMP_PATTERN + r"\.csv$")
            # The file must actually live inside log_dir, not merely have
            # a plausible-looking name.
            self.assertEqual(os.path.dirname(log_path), log_dir)


if __name__ == "__main__":
    unittest.main()

# tests/test_gam_calls.py
# ASCII only. Tests chromebook_toggle/gam_calls.py (Task 8's "CALLER
# OBLIGATION" wrappers, split out of gui.py specifically so this logic
# could be unit-tested). Each wrapper's job is: call one backend function,
# catch exactly the one exception type that function's own module
# documents as deliberately left uncaught, and return a plain
# (value, error_message) pair instead - never let anything escape.
#
# run_gam_or_none() is tested by mocking chromebook_toggle.gam_runner.
# subprocess.run, the same way tests\test_gam_runner.py already mocks it -
# gam_calls.run_gam_or_none() calls gam_runner.run_gam(), which is the one
# place a real gam.exe call would happen, so subprocess.run is mocked out
# here too rather than ever touching a real gam.exe.
#
# The other five wrappers (parse_lookup_or_none, build_review_or_none,
# build_results_or_none, write_log_or_warning, write_temp_csv_or_none) wrap
# pure functions with no subprocess involved, so their tests simply supply
# input that is known (from Tasks 5-7's own test suites) to succeed or to
# raise the documented exception, and check the wrapper's return shape.

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from chromebook_toggle import gam_calls
from chromebook_toggle.workflow import ReviewRow


class TestRunGamOrNone(unittest.TestCase):

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_success_returns_completed_process_and_no_error(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["fake"], returncode=0, stdout="ok", stderr=""
        )
        result, error = gam_calls.run_gam_or_none(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])
        self.assertIsNone(error)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_timeout_expired_is_caught_and_returns_none_with_message(self, mock_run):
        # gam_runner.run_gam() deliberately lets subprocess.TimeoutExpired
        # propagate raw (see gam_runner.py's own CALLER OBLIGATION note) -
        # this wrapper is what is supposed to catch it instead.
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["fake"], timeout=180)
        result, error = gam_calls.run_gam_or_none(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("did not finish in time", error)

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_oserror_is_caught_and_returns_none_with_message(self, mock_run):
        # Covers the "gam_path exists but is not actually executable" case
        # gam_runner.py's own docstring calls out as still reachable past
        # check_gam_available()'s plain existence check.
        mock_run.side_effect = PermissionError("Access is denied")
        result, error = gam_calls.run_gam_or_none(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("Could not run gam.exe", error)
        self.assertIn("Access is denied", error)


class TestParseLookupOrNone(unittest.TestCase):

    def test_success_returns_parsed_dict_and_no_error(self):
        raw_text = '{"serialNumber": "ABC123", "status": "ACTIVE"}'
        looked_up, error = gam_calls.parse_lookup_or_none(raw_text)
        self.assertIsNone(error)
        self.assertEqual(looked_up["ABC123"]["status"], "ACTIVE")

    def test_malformed_json_is_caught_and_returns_none_with_message(self):
        # device_lookup.parse_lookup_json() raises ValueError on malformed
        # JSON - this happens for real if gam.exe prints a plain-text
        # error to stdout instead of the expected formatjson output.
        looked_up, error = gam_calls.parse_lookup_or_none("gam: error, not JSON at all")
        self.assertIsNone(looked_up)
        self.assertIsNotNone(error)
        self.assertIn("Could not understand gam's device lookup output", error)


class TestBuildReviewOrNone(unittest.TestCase):

    def test_success_returns_review_rows_and_no_error(self):
        looked_up = {"ABC123": {"status": "ACTIVE"}}
        review_rows, error = gam_calls.build_review_or_none(["ABC123"], looked_up, "disable")
        self.assertIsNone(error)
        self.assertEqual(len(review_rows), 1)
        self.assertTrue(review_rows[0].will_process)

    def test_unrecognized_action_keyerror_is_caught_and_returns_none_with_message(self):
        # workflow.build_review() deliberately lets KeyError propagate raw
        # for an unrecognized action (see workflow.py's own CALLER
        # OBLIGATION note) - this should never trigger from gui.py in
        # practice (action only ever comes from its own two radio
        # buttons), but the wrapper must guard it anyway.
        review_rows, error = gam_calls.build_review_or_none(["ABC123"], {}, "not_a_real_action")
        self.assertIsNone(review_rows)
        self.assertIsNotNone(error)
        self.assertIn("unrecognized action", error)


class TestBuildResultsOrNone(unittest.TestCase):

    def test_success_returns_result_rows_and_no_error(self):
        review_rows = [ReviewRow(serial="ABC123", found=True, current_status="ACTIVE", will_process=True, skip_reason=None)]
        post_looked_up = {"ABC123": {"status": "DISABLED"}}
        results, error = gam_calls.build_results_or_none(review_rows, post_looked_up, "disable")
        self.assertIsNone(error)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)

    def test_unrecognized_action_keyerror_is_caught_and_returns_none_with_message(self):
        results, error = gam_calls.build_results_or_none([], {}, "not_a_real_action")
        self.assertIsNone(results)
        self.assertIsNotNone(error)
        self.assertIn("unrecognized action", error)


class TestWriteLogOrWarning(unittest.TestCase):

    def test_success_returns_log_path_and_no_error(self):
        from chromebook_toggle.workflow import ResultRow
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            results = [ResultRow(serial="ABC123", previous_status="ACTIVE", new_status="DISABLED", success=True)]
            log_path, error = gam_calls.write_log_or_warning(log_dir, "disable", results)
            self.assertIsNone(error)
            self.assertTrue(os.path.isfile(log_path))

    def test_oserror_is_caught_and_returns_none_with_message(self):
        # logging_util.write_log() deliberately lets OSError propagate raw
        # (see logging_util.py's own CALLER OBLIGATION note). Using a
        # log_dir path that already exists as a FILE (not a directory)
        # makes os.makedirs(log_dir, exist_ok=True) raise a real OSError
        # (exist_ok only suppresses the error when the existing path is
        # already a directory).
        with tempfile.TemporaryDirectory() as tmp_dir:
            blocking_file_path = os.path.join(tmp_dir, "Logs")
            with open(blocking_file_path, "w", encoding="ascii") as blocking_file:
                blocking_file.write("this is a file, not a directory")

            log_path, error = gam_calls.write_log_or_warning(blocking_file_path, "disable", [])
            self.assertIsNone(log_path)
            self.assertIsNotNone(error)

    def test_unicode_error_is_caught_and_returns_none_with_message(self):
        # logging_util.write_log() opens its CSV with encoding="ascii" and
        # deliberately lets the resulting UnicodeEncodeError propagate raw
        # if any field contains a non-ASCII character. chr(0xE9) is used
        # (rather than a literal non-ASCII character) to keep this test
        # file itself strict ASCII - see test_logging_util.py for the same
        # convention.
        from chromebook_toggle.workflow import ResultRow
        non_ascii_serial = "ABC" + chr(0xE9) + "123"
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = os.path.join(tmp_dir, "Logs")
            results = [ResultRow(serial=non_ascii_serial, previous_status="ACTIVE", new_status="DISABLED", success=True)]

            log_path, error = gam_calls.write_log_or_warning(log_dir, "disable", results)
            self.assertIsNone(log_path)
            self.assertIsNotNone(error)


class TestWriteTempCsvOrNone(unittest.TestCase):

    def test_success_returns_temp_path_and_no_error(self):
        temp_path, error = gam_calls.write_temp_csv_or_none(["ABC123", "DEF456"])
        try:
            self.assertIsNone(error)
            self.assertTrue(os.path.isfile(temp_path))
        finally:
            # Clean up - write_temp_serial_csv() leaves the file behind by
            # design (the caller is responsible for deleting it once gam
            # has run), so this test must not leave it under %TEMP%.
            if temp_path:
                os.remove(temp_path)

    def test_non_ascii_serial_value_error_is_caught_and_returns_none_with_message(self):
        # serials.write_temp_serial_csv() raises ValueError (never a raw
        # UnicodeEncodeError) if a serial cannot be written to the
        # ascii-encoded temp file, and cleans up the partial file itself -
        # see serials.py's own docstring.
        non_ascii_serial = "ABC" + chr(0xE9) + "123"
        temp_path, error = gam_calls.write_temp_csv_or_none([non_ascii_serial])
        self.assertIsNone(temp_path)
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()

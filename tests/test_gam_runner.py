# tests/test_gam_runner.py
# ASCII only. Tests gam_runner's pure argument-list builders directly, and
# mocks subprocess.run for run_gam so no real gam.exe call ever happens
# during an automated test run (gam.exe talks to a real district Google
# Workspace tenant - see the module docstring in gam_runner.py).
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from chromebook_toggle import gam_runner


class TestBuildArgs(unittest.TestCase):

    def test_build_lookup_args_joins_serials_with_commas(self):
        # GamCommands.txt:788 - <SerialNumberList> ::= "<SerialNumber>(,<SerialNumber>)*"
        args = gam_runner.build_lookup_args(["ABC123", "DEF456"])
        self.assertEqual(args, [
            "info", "cros", "cros_sn", "ABC123,DEF456",
            "fields", gam_runner.LOOKUP_FIELDS, "formatjson",
        ])

    def test_build_csv_action_args_includes_cros_sn_prefix_before_serial_token(self):
        # Regression test for a confirmed production bug (fixed
        # 08-10-2026, see gam_runner.py's build_csv_action_args comment
        # block): the "cros_sn" token MUST appear immediately before
        # "~Serial" - without it, gam parses the substituted serial as a
        # bare CrOSIDList (Google internal device ID) instead of a serial
        # number per GamCommands.txt:1096-1098's <CrOSEntity> grammar, and
        # the resulting "gam update cros" call silently fails per-row
        # against every real device (this is exactly what happened to
        # Gabe's real 8-device disable attempt). Do not remove "cros_sn"
        # from this expected list even though it looks redundant next to
        # "~Serial" - it is load-bearing. Named so this specific
        # regression is obvious from a bare test-runner failure list,
        # without needing to open this file.
        #
        # Deliberately asserts against the literal "cros_sn" string, not
        # gam_runner.CROS_SN_PREFIX - a test that compares the module's
        # constant against itself would still pass even if that constant
        # were ever accidentally changed to the wrong value, defeating
        # the whole point of this regression test.
        args = gam_runner.build_csv_action_args(r"C:\temp\serials.csv", "disable")
        self.assertEqual(args, [
            "csv", r"C:\temp\serials.csv",
            "gam", "update", "cros", "cros_sn", "~Serial", "action", "disable",
        ])

    def test_build_gsheet_action_args_includes_cros_sn_prefix_before_serial_token(self):
        # Regression test for the same confirmed production bug as
        # test_build_csv_action_args_includes_cros_sn_prefix_before_serial_token()
        # above (see that test's comment and gam_runner.py's
        # build_gsheet_action_args comment block) - the Sheet-driven
        # action builder had the identical missing-"cros_sn" defect and
        # would silently fail the same way.
        # Same reasoning as the CSV test above: asserts the literal
        # "cros_sn" string, not gam_runner.CROS_SN_PREFIX, so this test
        # still catches the constant itself being set wrong.
        args = gam_runner.build_gsheet_action_args(
            "gam-admin@example.com", "1AbCdEf", "123", "reenable"
        )
        self.assertEqual(args, [
            "csv", "gsheet", "gam-admin@example.com", "id:1AbCdEf", "id:123",
            "gam", "update", "cros", "cros_sn", "~Serial", "action", "reenable",
        ])


class TestRunGam(unittest.TestCase):

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_run_gam_calls_subprocess_with_exe_path_prepended(self, mock_run):
        # This is the ONE place a real gam.exe call would happen, so
        # subprocess.run itself is mocked out - run_gam is exercised without
        # ever touching the real district Google Workspace tenant.
        mock_run.return_value = subprocess.CompletedProcess(
            args=["fake"], returncode=0, stdout="ok", stderr=""
        )
        result = gam_runner.run_gam(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])
        mock_run.assert_called_once_with(
            [r"C:\GAM7\gam.exe", "info", "cros", "cros_sn", "ABC123"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=180, check=False,
        )
        self.assertEqual(result.returncode, 0)

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_run_gam_passes_through_a_caller_supplied_timeout(self, mock_run):
        # Confirms timeout_seconds is not just accepted but actually reaches
        # subprocess.run's timeout= kwarg - the default-only test above
        # would still pass even if run_gam silently ignored a caller's
        # timeout_seconds and hardcoded 180 everywhere, so this needs its
        # own assertion against a non-default value.
        mock_run.return_value = subprocess.CompletedProcess(
            args=["fake"], returncode=0, stdout="ok", stderr=""
        )
        gam_runner.run_gam(
            r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"], timeout_seconds=600
        )
        mock_run.assert_called_once_with(
            [r"C:\GAM7\gam.exe", "info", "cros", "cros_sn", "ABC123"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=600, check=False,
        )

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_run_gam_lets_timeout_expired_propagate(self, mock_run):
        # Regression test locking in the deliberate design decision
        # documented in gam_runner.py's module Notes: run_gam does NOT
        # catch subprocess.TimeoutExpired itself - it is left to propagate
        # to the caller. Without this test, a future edit could silently
        # add a swallowing try/except around subprocess.run and nothing
        # else here would catch that regression.
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gam", timeout=180)
        with self.assertRaises(subprocess.TimeoutExpired):
            gam_runner.run_gam(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])

    @mock.patch("chromebook_toggle.gam_runner.subprocess.run")
    def test_run_gam_lets_os_error_propagate(self, mock_run):
        # Regression test locking in the other half of the same deliberate
        # design decision as test_run_gam_lets_timeout_expired_propagate()
        # above: gam_runner.py's module Notes document run_gam() as NOT
        # catching OSError (e.g. PermissionError, if gam_path exists as a
        # file but is not actually executable) either - it is left to
        # propagate to the caller, same as TimeoutExpired. Only the
        # TimeoutExpired half of that documented contract had a locked-in
        # test before this one; without this test, a future edit could
        # silently add a try/except OSError around subprocess.run and
        # nothing here would catch that regression.
        mock_run.side_effect = PermissionError("Access is denied")
        with self.assertRaises(OSError):
            gam_runner.run_gam(r"C:\GAM7\gam.exe", ["info", "cros", "cros_sn", "ABC123"])


class TestCheckGamAvailable(unittest.TestCase):

    def test_missing_exe_reports_not_ok(self):
        # Deliberately NOT mocked - this only performs a filesystem
        # existence check (os.path.isfile), never a real gam invocation, so
        # it is safe to run for real against a path guaranteed not to exist.
        ok, message = gam_runner.check_gam_available(r"C:\does\not\exist\gam.exe")
        self.assertFalse(ok)
        self.assertIn("not found", message.lower())

    def test_existing_file_reports_ok(self):
        # Also deliberately NOT mocked - a NamedTemporaryFile is a real file
        # on disk (it does not need to actually be gam.exe, or even be
        # executable, since check_gam_available only checks existence via
        # os.path.isfile), so this proves the success path for real without
        # ever invoking anything.
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.close()
        try:
            ok, message = gam_runner.check_gam_available(temp_file.name)
            self.assertTrue(ok)
            self.assertEqual(message, "OK")
        finally:
            os.remove(temp_file.name)


if __name__ == "__main__":
    unittest.main()

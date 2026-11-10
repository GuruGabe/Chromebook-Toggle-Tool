# tests/test_gam_signin.py
#
# Tests for chromebook_toggle/gam_signin.py (the facts behind the GAM sign-in
# window). The sample GAM output below was captured from a real GAM 7.51.00 run
# against an empty config folder, not invented.

import subprocess
import unittest

from chromebook_toggle import gam_signin

# Real: "gam oauth info" with no sign-in (exit 51).
REAL_NO_OAUTH = (
    "Client OAuth2 File: C:\\Temp\\x\\oauth2.txt, Not Shown: Does not exist\n"
    "Created: C:\\Temp\\x\\gamcache\n"
    "Config File: C:\\Temp\\x\\gam.cfg, Initialized\n")

# Real: any normal command with no sign-in (stderr, exit 16).
REAL_NO_CLIENT_ACCESS = (
    "WARNING: Config File: C:\\Temp\\x\\gam.cfg, Section: DEFAULT, Item: oauth2_txt, "
    "Value: C:\\Temp\\x\\oauth2.txt, Not Found\n\nERROR: No Client Access allowed\n")

SIGNED_IN = (
    "Client ID: 123.apps.googleusercontent.com\n"
    "Google Workspace Admin: admin.person@example.com\n"
    "Scopes: 12\n")


class TestOauthState(unittest.TestCase):
    def test_signed_in_returns_admin(self):
        self.assertEqual(gam_signin.oauth_state(0, SIGNED_IN), ("ok", "admin.person@example.com"))

    def test_real_missing_output(self):
        self.assertEqual(gam_signin.oauth_state(51, REAL_NO_OAUTH), ("missing", ""))

    def test_other_problem_reports_first_error_line(self):
        state, detail = gam_signin.oauth_state(1, "something\nERROR: Network is unreachable\n")
        self.assertEqual(state, "error")
        self.assertIn("Network is unreachable", detail)

    def test_empty_output_mentions_exit_code(self):
        state, detail = gam_signin.oauth_state(7, "")
        self.assertEqual((state, detail), ("error", "exit code 7"))


class TestSigninCanFix(unittest.TestCase):
    def test_real_missing_sign_in_is_fixable(self):
        self.assertTrue(gam_signin.signin_can_fix(REAL_NO_CLIENT_ACCESS))
        self.assertTrue(gam_signin.signin_can_fix(REAL_NO_OAUTH))

    def test_expired_sign_in_is_fixable(self):
        self.assertTrue(gam_signin.signin_can_fix("Reauthentication is needed, please run\n\ngam oauth create"))
        self.assertTrue(gam_signin.signin_can_fix("ERROR: invalid_grant: Token has been expired or revoked."))

    def test_wrong_user_is_not_a_sign_in_problem(self):
        self.assertFalse(gam_signin.signin_can_fix("invalid_grant: Invalid email or User ID"))

    def test_ordinary_errors_are_not(self):
        self.assertFalse(gam_signin.signin_can_fix("ERROR: Device not found"))
        self.assertFalse(gam_signin.signin_can_fix(""))
        self.assertFalse(gam_signin.signin_can_fix(None))


class TestCommands(unittest.TestCase):
    def test_update_words(self):
        self.assertEqual(gam_signin.step_argv("update"), ["oauth", "update"])
        self.assertEqual(gam_signin.step_argv("update", "a@example.com"),
                         ["oauth", "update", "admin", "a@example.com"])

    def test_create_words(self):
        self.assertEqual(gam_signin.step_argv("create"), ["oauth", "create"])
        self.assertEqual(gam_signin.step_argv("create", " a@example.com "), ["oauth", "create", "a@example.com"])

    def test_bad_email_and_step_are_refused(self):
        for bad in ("not an email", "a@b", "a b@example.com", "x@example.com; calc"):
            with self.assertRaises(ValueError):
                gam_signin.step_argv("update", bad)
        with self.assertRaises(ValueError):
            gam_signin.step_argv("delete")

    def test_valid_email(self):
        self.assertTrue(gam_signin.valid_email("a.b@example.com"))
        self.assertFalse(gam_signin.valid_email(""))
        self.assertFalse(gam_signin.valid_email("a@@example.com"))

    def test_info_argv(self):
        self.assertEqual(gam_signin.info_argv("C:\\GAM7\\gam.exe"), ["C:\\GAM7\\gam.exe", "oauth", "info"])


class _Done(object):
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class TestCheckSignin(unittest.TestCase):
    def test_reads_status_from_gam(self):
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"], seen["kwargs"] = argv, kwargs
            return _Done(0, SIGNED_IN)

        self.assertEqual(gam_signin.check_signin("gam", run=fake_run), ("ok", "admin.person@example.com"))
        self.assertEqual(seen["argv"], ["gam", "oauth", "info"])
        # Nothing may be typed into it: it must never wait on the keyboard.
        self.assertEqual(seen["kwargs"]["stdin"], subprocess.DEVNULL)

    def test_missing_sign_in(self):
        self.assertEqual(gam_signin.check_signin("gam", run=lambda *a, **k: _Done(51, REAL_NO_OAUTH)), ("missing", ""))

    def test_missing_program_never_raises(self):
        def boom(*a, **k):
            raise FileNotFoundError("no such file")
        state, detail = gam_signin.check_signin("gam", run=boom)
        self.assertEqual(state, "error")
        self.assertIn("Could not run GAM", detail)

    def test_timeout_never_raises(self):
        def slow(*a, **k):
            raise subprocess.TimeoutExpired("gam", 60)
        self.assertEqual(gam_signin.check_signin("gam", run=slow)[0], "error")


class TestWindowsCmdBlocked(unittest.TestCase):
    def test_not_set_means_allowed(self):
        self.assertFalse(gam_signin.windows_cmd_blocked(lambda hive, key, name: None))

    def test_zero_means_allowed(self):
        self.assertFalse(gam_signin.windows_cmd_blocked(lambda hive, key, name: 0))

    def test_policy_one_or_two_in_either_hive_blocks(self):
        self.assertTrue(gam_signin.windows_cmd_blocked(lambda hive, key, name: 1 if hive == "HKCU" else None))
        self.assertTrue(gam_signin.windows_cmd_blocked(lambda hive, key, name: 2 if hive == "HKLM" else None))

    def test_asks_for_the_right_value(self):
        asked = []
        gam_signin.windows_cmd_blocked(lambda hive, key, name: asked.append((hive, key, name)))
        self.assertIn(("HKCU", r"Software\Policies\Microsoft\Windows\System", "DisableCMD"), asked)

    def test_the_real_lookup_does_not_crash(self):
        # Whatever this PC's policy is, reading it must give True or False.
        self.assertIn(gam_signin.windows_cmd_blocked(), (True, False))


class TestLaunchPlan(unittest.TestCase):
    ARGV = ["C:\\GAM7\\gam.exe", "oauth", "update"]

    def test_windows_keeps_a_cmd_window_open(self):
        plan = gam_signin.launch_plan(self.ARGV, "GAM sign-in", "Windows")
        self.assertEqual(plan.command, ["cmd", "/c", "start", "GAM sign-in", "cmd", "/k"] + self.ARGV)
        self.assertTrue(plan.stays_open)
        self.assertEqual(plan.creationflags, 0)

    def test_windows_without_cmd_starts_gam_in_its_own_console(self):
        plan = gam_signin.launch_plan(self.ARGV, "t", "Windows", cmd_blocked=True)
        self.assertEqual(plan.command, self.ARGV)
        self.assertEqual(plan.creationflags, gam_signin.CREATE_NEW_CONSOLE)
        self.assertFalse(plan.stays_open)

    def test_windows_path_with_spaces_avoids_cmd_quoting_traps(self):
        argv = ["C:\\Program Files\\GAM\\gam.exe", "oauth", "update"]
        plan = gam_signin.launch_plan(argv, "t", "Windows")
        self.assertEqual(plan.command, argv)
        self.assertEqual(plan.creationflags, gam_signin.CREATE_NEW_CONSOLE)

    def test_mac_uses_terminal_and_passes_the_config_folder(self):
        plan = gam_signin.launch_plan(["/Users/x/bin/gam7/gam", "oauth", "update"], "t", "Darwin", "/Users/x/cfg")
        self.assertEqual(plan.command[0], "osascript")
        joined = " ".join(plan.command)
        self.assertIn("GAMCFGDIR=/Users/x/cfg", joined)
        self.assertIn("oauth update", joined)

    def test_linux_picks_the_first_terminal_found(self):
        plan = gam_signin.launch_plan(["gam", "oauth", "update"], "t", "Linux", "", which=lambda n: n if n == "konsole" else None)
        self.assertEqual(plan.command[:2], ["konsole", "-e"])
        self.assertIn("read -r -p", plan.command[-1])

    def test_linux_with_no_terminal_is_none(self):
        self.assertIsNone(gam_signin.launch_plan(["gam"], "t", "Linux", "", which=lambda n: None))

    def test_unknown_system_is_none(self):
        self.assertIsNone(gam_signin.launch_plan(["gam"], "t", "Plan9"))

    def test_shell_metacharacters_are_quoted_on_unix(self):
        plan = gam_signin.launch_plan(["gam", "oauth", "create", "a;b@example.com"], "t", "Linux", "", which=lambda n: "xterm")
        self.assertIn("'a;b@example.com'", plan.command[-1])


if __name__ == "__main__":
    unittest.main()

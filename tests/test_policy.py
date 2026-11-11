# tests/test_policy.py
#
# Tests for chromebook_toggle/policy.py (the administrator's way to turn the
# permanent Deprovision action on or off without reinstalling). The registry,
# plist and ini backends are exercised for REAL against throw-away locations,
# never against the machine's real policy.

import os
import shutil
import sys
import tempfile
import unittest
import uuid

from chromebook_toggle import config, policy


class FakeBackend(object):
    # In-memory stand-in with the same get / set / clear methods.
    def __init__(self, value=None, fail=None):
        self.value, self.fail = value, fail

    def get(self):
        return self.value

    def _check(self):
        if self.fail:
            raise self.fail

    def set(self, value):
        self._check()
        self.value = bool(value)

    def clear(self):
        self._check()
        self.value = None


class TestAsBool(unittest.TestCase):
    def test_recognised_values(self):
        for yes in (True, 1, "1", "true", " TRUE ", "yes", "on"):
            self.assertIs(policy._as_bool(yes), True, yes)
        for no in (False, 0, "0", "false", "No", "off"):
            self.assertIs(policy._as_bool(no), False, no)

    def test_anything_else_is_not_a_policy(self):
        for odd in (None, 2, -1, "maybe", "", "tru", 1.0, [], b"1"):
            self.assertIsNone(policy._as_bool(odd), odd)


@unittest.skipUnless(sys.platform.startswith("win"), "Windows registry")
class TestWindowsBackend(unittest.TestCase):
    def setUp(self):
        # A scratch key under the CURRENT USER hive (writable without admin).
        self.path = r"Software\ChromebookToggleTest-" + uuid.uuid4().hex
        self.backend = policy.WindowsBackend("HKCU", self.path)

    def tearDown(self):
        import winreg
        try:
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, self.path, winreg.KEY_WOW64_64KEY, 0)
        except OSError:
            pass

    def test_missing_key_is_no_policy(self):
        self.assertIsNone(self.backend.get())

    def test_set_get_clear(self):
        self.backend.set(True)
        self.assertIs(self.backend.get(), True)
        self.backend.set(False)
        self.assertIs(self.backend.get(), False)
        self.backend.clear()
        self.assertIsNone(self.backend.get())
        self.backend.clear()  # clearing twice is fine

    def test_value_is_a_dword(self):
        import winreg
        self.backend.set(True)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, kind = winreg.QueryValueEx(key, policy.WIN_VALUE)
        self.assertEqual((value, kind), (1, winreg.REG_DWORD))

    def test_a_typo_in_the_registry_is_not_a_yes(self):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.path, 0,
                                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
            winreg.SetValueEx(key, policy.WIN_VALUE, 0, winreg.REG_SZ, "yess")
        self.assertIsNone(self.backend.get())

    def test_the_real_machine_policy_can_be_read(self):
        # Read-only: whatever this PC's policy is, reading never raises.
        self.assertIn(policy.default_backend().get(), (True, False, None))


class TestMacBackend(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = os.path.join(self.folder, "x.plist")
        self.backend = policy.MacBackend(self.path)

    def test_round_trip_and_other_keys_are_kept(self):
        import plistlib
        with open(self.path, "wb") as handle:
            plistlib.dump({"Other": "keep me"}, handle)
        self.assertIsNone(self.backend.get())
        self.backend.set(True)
        self.assertIs(self.backend.get(), True)
        self.backend.set(False)
        self.assertIs(self.backend.get(), False)
        self.backend.clear()
        self.assertIsNone(self.backend.get())
        with open(self.path, "rb") as handle:
            self.assertEqual(plistlib.load(handle), {"Other": "keep me"})

    def test_missing_file_is_no_policy_and_clear_is_harmless(self):
        self.assertIsNone(self.backend.get())
        self.backend.clear()
        self.assertFalse(os.path.exists(self.path))

    def test_garbage_file_is_an_error_not_a_yes(self):
        with open(self.path, "wb") as handle:
            handle.write(b"not a plist at all")
        with self.assertRaises(policy.PolicyError):
            self.backend.get()
        self.assertIsNone(policy.read_policy(self.backend))


class TestLinuxBackend(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = os.path.join(self.folder, "sub", "policy.ini")  # folder does not exist yet
        self.backend = policy.LinuxBackend(self.path)

    def test_round_trip_creates_the_folder(self):
        self.assertIsNone(self.backend.get())
        self.backend.set(True)
        self.assertIs(self.backend.get(), True)
        self.backend.set(False)
        self.assertIs(self.backend.get(), False)
        self.backend.clear()
        self.assertIsNone(self.backend.get())

    def test_hand_written_file_is_understood(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as handle:
            handle.write("[Settings]\nallow_deprovision = yes\n")
        self.assertIs(self.backend.get(), True)


class TestApplyToSettings(unittest.TestCase):
    def test_no_policy_leaves_settings_ini_in_charge(self):
        settings = dict(config.default_settings(), allow_deprovision=True)
        policy.apply_to_settings(settings, FakeBackend(None))
        self.assertTrue(settings["allow_deprovision"])
        self.assertEqual(settings["deprovision_source"], "settings.ini")

    def test_policy_on_overrides_settings_ini_off(self):
        settings = dict(config.default_settings(), allow_deprovision=False)
        policy.apply_to_settings(settings, FakeBackend(True))
        self.assertTrue(settings["allow_deprovision"])
        self.assertEqual(settings["deprovision_source"], "machine policy")

    def test_policy_off_overrides_settings_ini_on(self):
        settings = dict(config.default_settings(), allow_deprovision=True)
        policy.apply_to_settings(settings, FakeBackend(False))
        self.assertFalse(settings["allow_deprovision"])

    def test_a_broken_policy_never_stops_the_app_or_turns_it_on(self):
        class Broken(object):
            def get(self):
                raise RuntimeError("boom")
        settings = dict(config.default_settings())
        policy.apply_to_settings(settings, Broken())
        self.assertFalse(settings["allow_deprovision"])


class TestCli(unittest.TestCase):
    def run_cli(self, args, backend=None, elevate=None):
        said = []
        code = policy.cli_main(["prog"] + args, backend=backend or FakeBackend(), system="linux",
                               say=said.append, elevate=elevate)
        return code, " ".join(said)

    def test_recognises_its_switches(self):
        self.assertTrue(policy.is_policy_command(["prog", "--set-deprovision", "on"]))
        self.assertTrue(policy.is_policy_command(["prog", "--deprovision-status"]))
        self.assertFalse(policy.is_policy_command(["prog"]))
        self.assertFalse(policy.is_policy_command(["prog", "--apply-update"]))

    def test_on_off_clear(self):
        backend = FakeBackend()
        self.assertEqual(self.run_cli(["--set-deprovision", "on"], backend)[0], 0)
        self.assertIs(backend.value, True)
        self.assertEqual(self.run_cli(["--set-deprovision", "OFF"], backend)[0], 0)
        self.assertIs(backend.value, False)
        self.assertEqual(self.run_cli(["--set-deprovision", "clear"], backend)[0], 0)
        self.assertIsNone(backend.value)

    def test_on_says_what_happened(self):
        code, text = self.run_cli(["--set-deprovision", "on"])
        self.assertIn("turned ON", text)
        self.assertIn("next time the program is started", text)

    def test_status(self):
        self.assertIn("ON", self.run_cli(["--deprovision-status"], FakeBackend(True))[1])
        self.assertIn("OFF", self.run_cli(["--deprovision-status"], FakeBackend(False))[1])
        self.assertIn("No machine policy", self.run_cli(["--deprovision-status"], FakeBackend(None))[1])

    def test_bad_arguments_show_usage_and_change_nothing(self):
        backend = FakeBackend(None)
        for args in (["--set-deprovision"], ["--set-deprovision", "maybe"],
                     ["--set-deprovision", "on", "extra"], ["--deprovision-status", "x"]):
            code, text = self.run_cli(args, backend)
            self.assertEqual(code, 1, args)
            self.assertIn("--set-deprovision on", text)
        self.assertIsNone(backend.value)

    def test_without_admin_rights_it_asks_to_elevate(self):
        backend = FakeBackend(fail=policy.PolicyPermissionError("Administrator rights are needed"))
        asked = []
        code, text = self.run_cli(["--set-deprovision", "on"], backend,
                                  elevate=lambda argv: asked.append(argv) or True)
        self.assertEqual(code, 0)
        self.assertEqual(len(asked), 1)

    def test_elevation_refused_explains_and_fails(self):
        backend = FakeBackend(fail=policy.PolicyPermissionError("Administrator rights are needed"))
        code, text = self.run_cli(["--set-deprovision", "on"], backend, elevate=lambda argv: False)
        self.assertEqual(code, 3)
        self.assertIn("administrator", text.lower())

    def test_an_elevated_copy_never_elevates_again(self):
        backend = FakeBackend(fail=policy.PolicyPermissionError("Administrator rights are needed"))
        asked = []
        code, text = self.run_cli(["--set-deprovision", "on", "--elevated"], backend,
                                  elevate=lambda argv: asked.append(argv) or True)
        self.assertEqual(code, 3)
        self.assertEqual(asked, [])

    def test_other_problems_are_reported(self):
        backend = FakeBackend(fail=policy.PolicyError("disk full"))
        code, text = self.run_cli(["--set-deprovision", "on"], backend)
        self.assertEqual(code, 2)
        self.assertIn("disk full", text)

    def test_locations_are_described_per_system(self):
        self.assertIn("HKEY_LOCAL_MACHINE", policy.describe_location("win32"))
        self.assertIn("/Library/Preferences", policy.describe_location("darwin"))
        self.assertIn("/etc/chromebooktoggle", policy.describe_location("linux"))


if __name__ == "__main__":
    unittest.main()

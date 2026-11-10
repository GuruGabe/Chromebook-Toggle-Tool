# tests/test_paths.py
# ASCII only. Tests chromebook_toggle/paths.py - where settings, logs and
# state live. The "is this folder writable" test and the operating system are
# passed in, so every case (portable copy, Program Files install, each OS's
# per-user folder) is checked here on any machine.
import os
import tempfile
import unittest

from chromebook_toggle import paths


class TestAppDir(unittest.TestCase):

    def test_frozen_uses_the_executables_folder(self):
        folder = paths.app_dir(frozen=True, executable=os.path.join("C:\\", "Apps", "ChromebookToggle", "ChromebookToggle.exe"))
        self.assertEqual(os.path.basename(folder), "ChromebookToggle")

    def test_source_run_uses_the_scripts_folder(self):
        folder = paths.app_dir(frozen=False, script_file=os.path.join("C:\\", "src", "tool", "ChromebookToggle.py"))
        self.assertEqual(os.path.basename(folder), "tool")


class TestIsWritable(unittest.TestCase):

    def test_a_normal_folder_is_writable_and_the_probe_file_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(paths.is_writable(folder))
            self.assertEqual(os.listdir(folder), [])

    def test_a_missing_folder_is_not_writable(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(paths.is_writable(os.path.join(folder, "nope")))


class TestUserDataDir(unittest.TestCase):

    def test_windows_uses_localappdata(self):
        folder = paths.user_data_dir("win32", {"LOCALAPPDATA": r"C:\Users\pat\AppData\Local"}, r"C:\Users\pat")
        self.assertEqual(folder, os.path.join(r"C:\Users\pat\AppData\Local", "ChromebookToggle"))

    def test_windows_without_localappdata_falls_back_under_home(self):
        folder = paths.user_data_dir("win32", {}, r"C:\Users\pat")
        self.assertEqual(folder, os.path.join(r"C:\Users\pat", "AppData", "Local", "ChromebookToggle"))

    def test_macos_uses_application_support(self):
        folder = paths.user_data_dir("darwin", {}, "/Users/pat")
        self.assertEqual(folder, os.path.join("/Users/pat", "Library", "Application Support", "ChromebookToggle"))

    def test_linux_honours_xdg_data_home(self):
        folder = paths.user_data_dir("linux", {"XDG_DATA_HOME": "/data/pat"}, "/home/pat")
        self.assertEqual(folder, os.path.join("/data/pat", "ChromebookToggle"))

    def test_linux_defaults_to_local_share(self):
        folder = paths.user_data_dir("linux", {}, "/home/pat")
        self.assertEqual(folder, os.path.join("/home/pat", ".local", "share", "ChromebookToggle"))


class TestResolve(unittest.TestCase):

    def test_writable_app_folder_keeps_logs_and_state_beside_the_app(self):
        # Portable copy / per-user install: everything stays in one folder.
        loc = paths.resolve(os.path.join("C:\\", "Tools", "CT"), writable=lambda folder: True)
        self.assertEqual(loc.settings_path, os.path.join("C:\\", "Tools", "CT", "settings.ini"))
        self.assertEqual(loc.log_dir, os.path.join("C:\\", "Tools", "CT", "Logs"))
        self.assertEqual(loc.state_path, os.path.join("C:\\", "Tools", "CT", "state.ini"))
        self.assertEqual(loc.data_dir, loc.app_dir)

    def test_read_only_app_folder_moves_logs_and_state_to_the_users_folder(self):
        # Program Files install run by a standard user: settings.ini is still
        # read from the app folder, but logs/state must go somewhere writable.
        fallback = os.path.join("C:\\", "Users", "pat", "AppData", "Local", "ChromebookToggle")
        loc = paths.resolve(os.path.join("C:\\", "Program Files", "CT"),
                            writable=lambda folder: False, fallback_dir=fallback)
        self.assertEqual(loc.settings_path, os.path.join("C:\\", "Program Files", "CT", "settings.ini"))
        self.assertEqual(loc.log_dir, os.path.join(fallback, "Logs"))
        self.assertEqual(loc.state_path, os.path.join(fallback, "state.ini"))
        self.assertEqual(loc.data_dir, fallback)


class TestMacAppBundle(unittest.TestCase):
    # Writing inside a signed .app breaks the signature (and on Apple Silicon
    # the app then refuses to launch), so a bundle must never be written to.
    BUNDLE = "/Applications/ChromebookToggle.app/Contents/MacOS"

    def test_detects_a_bundle_only_on_macos(self):
        self.assertTrue(paths.in_app_bundle(self.BUNDLE, "darwin"))
        self.assertFalse(paths.in_app_bundle(self.BUNDLE, "linux"))
        self.assertFalse(paths.in_app_bundle("/opt/ChromebookToggle", "darwin"))

    def test_a_bundle_keeps_logs_and_state_out_even_if_it_looks_writable(self):
        fallback = "/Users/pat/Library/Application Support/ChromebookToggle"
        loc = paths.resolve(self.BUNDLE, writable=lambda folder: True, fallback_dir=fallback,
                            system="darwin", file_exists=lambda p: False)
        self.assertEqual(loc.log_dir, os.path.join(fallback, "Logs"))
        self.assertEqual(loc.state_path, os.path.join(fallback, "state.ini"))

    def test_a_bundle_uses_the_persons_settings_file_when_it_exists(self):
        fallback = "/Users/pat/Library/Application Support/ChromebookToggle"
        personal = os.path.join(fallback, "settings.ini")
        loc = paths.resolve(self.BUNDLE, writable=lambda folder: True, fallback_dir=fallback,
                            system="darwin", file_exists=lambda p: p == personal)
        self.assertEqual(loc.settings_path, personal)

    def test_a_bundle_falls_back_to_the_shipped_settings_without_a_personal_file(self):
        loc = paths.resolve(self.BUNDLE, writable=lambda folder: True,
                            fallback_dir="/x", system="darwin", file_exists=lambda p: False)
        self.assertEqual(loc.settings_path, os.path.join(self.BUNDLE, "settings.ini"))

    def test_no_personal_override_exists_outside_a_bundle(self):
        # On Windows/Linux the installed settings.ini is the administrator's
        # control; a file in the person's own folder must NOT take over.
        fallback = os.path.join("C:\\", "Users", "pat", "AppData", "Local", "ChromebookToggle")
        app = os.path.join("C:\\", "Program Files", "CT")
        loc = paths.resolve(app, writable=lambda folder: False, fallback_dir=fallback,
                            system="win32", file_exists=lambda p: True)
        self.assertEqual(loc.settings_path, os.path.join(app, "settings.ini"))


if __name__ == "__main__":
    unittest.main()

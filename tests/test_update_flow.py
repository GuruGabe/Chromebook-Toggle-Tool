# tests/test_update_flow.py
# ASCII only. Tests chromebook_toggle/update_flow.py end to end: the update
# really is downloaded from a stand-in GitHub on this PC, its checksum really
# is checked, the archive really is unpacked - only the steps that would start
# a real installer or script are replaced by recorders. Covers every kind of
# install plus the ways an update must refuse to proceed.
import hashlib
import io
import os
import tarfile
import tempfile
import unittest
import zipfile

from chromebook_toggle import update_apply, update_flow, updater
from tests import helpers


def _zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def _tar_bytes(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class _FlowCase(unittest.TestCase):

    def setUp(self):
        self.server, self.base = helpers.start_server()
        self.tmp = tempfile.TemporaryDirectory()
        self.work = os.path.join(self.tmp.name, "work")
        os.makedirs(self.work)
        self.log = os.path.join(self.tmp.name, "update.log")
        self.launched = []

    def tearDown(self):
        helpers.stop_server(self.server)
        self.tmp.cleanup()

    def popen(self, args, **kwargs):
        self.launched.append((args, kwargs))

    def plan(self, kind, name, payload, target="TARGET", scope=None, sha=None):
        helpers.FakeGitHub.routes["/dl/" + name] = (200, {}, payload)
        asset = updater.Asset(name, self.base + "/dl/" + name, len(payload))
        digest = sha or hashlib.sha256(payload).hexdigest().upper()
        return updater.UpdatePlan(kind, target, scope, asset, name, digest)

    def run_flow(self, plan, **kwargs):
        return update_flow.perform_install(plan, self.base, self.work, self.log, "9.9",
                                           pid=4242, popen=self.popen, **kwargs)


class TestWindowsPortable(_FlowCase):
    EXE = update_apply.exe_name("win32")

    def _zip(self, with_exe=True):
        entries = [("ChromebookToggle/_internal/lib.dll", b"dll"), ("ChromebookToggle/settings.ini", b"[Settings]")]
        if with_exe:
            entries.append(("ChromebookToggle/" + self.EXE, b"exe"))
        return _zip_bytes(entries)

    def test_download_verify_unpack_then_hand_over_to_the_new_exe(self):
        plan = self.plan(updater.KIND_WINDOWS_PORTABLE, "ChromebookToggle-9.9-Windows.zip", self._zip(), target="C:\\CT")
        outcome = self.run_flow(plan)
        self.assertEqual(outcome, update_flow.Outcome(True, ""))
        new_exe = os.path.join(self.work, "new", "ChromebookToggle", self.EXE)
        self.assertTrue(os.path.isfile(new_exe))
        args, kwargs = self.launched[0]
        self.assertEqual(args, [new_exe, "--apply-update", "--target", "C:\\CT", "--work", self.work,
                                "--pid", "4242", "--log", self.log])

    def test_a_download_that_fails_its_checksum_starts_nothing(self):
        plan = self.plan(updater.KIND_WINDOWS_PORTABLE, "ChromebookToggle-9.9-Windows.zip", self._zip(), sha="00" * 32)
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan)
        self.assertEqual(self.launched, [])
        self.assertFalse(os.path.exists(os.path.join(self.work, "new")))

    def test_an_archive_without_the_exe_starts_nothing(self):
        plan = self.plan(updater.KIND_WINDOWS_PORTABLE, "ChromebookToggle-9.9-Windows.zip", self._zip(with_exe=False))
        with self.assertRaises(updater.UpdateError) as raised:
            self.run_flow(plan)
        self.assertIn("nothing was changed", str(raised.exception))
        self.assertEqual(self.launched, [])

    def test_an_archive_with_an_escaping_path_is_rejected(self):
        payload = _zip_bytes([("ChromebookToggle/" + self.EXE, b"exe"), ("../evil.txt", b"x")])
        plan = self.plan(updater.KIND_WINDOWS_PORTABLE, "ChromebookToggle-9.9-Windows.zip", payload)
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan)
        self.assertEqual(self.launched, [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.txt")))


class TestWindowsSetup(_FlowCase):

    def test_the_new_setup_is_downloaded_verified_and_run_with_the_right_scope(self):
        plan = self.plan(updater.KIND_WINDOWS_SETUP, "ChromebookToggle-9.9-Setup.exe", b"MZ fake installer", scope="machine")
        seen = []
        outcome = self.run_flow(plan, setup_runner=lambda path, scope, log: seen.append((path, scope, log)))
        self.assertTrue(outcome.must_exit)
        path, scope, log = seen[0]
        self.assertEqual((os.path.basename(path), scope, log), ("ChromebookToggle-9.9-Setup.exe", "machine", self.log))
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"MZ fake installer")

    def test_a_declined_administrator_prompt_is_reported_and_the_app_stays_open(self):
        plan = self.plan(updater.KIND_WINDOWS_SETUP, "ChromebookToggle-9.9-Setup.exe", b"x", scope="machine")

        def declined(path, scope, log):
            raise updater.UpdateError("administrator approval was not given")

        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan, setup_runner=declined)

    def test_a_setup_that_fails_its_checksum_is_never_run(self):
        plan = self.plan(updater.KIND_WINDOWS_SETUP, "ChromebookToggle-9.9-Setup.exe", b"x", scope="user", sha="11" * 32)
        seen = []
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan, setup_runner=lambda *a: seen.append(a))
        self.assertEqual(seen, [])


class TestLinux(_FlowCase):

    def test_portable_folder_gets_a_swap_script_started_in_its_own_session(self):
        payload = _tar_bytes([("ChromebookToggle/ChromebookToggle", b"#!/bin/sh\n")])
        plan = self.plan(updater.KIND_LINUX_PORTABLE, "ChromebookToggle-9.9-Linux.tar.gz", payload, target="/opt/CT")
        outcome = self.run_flow(plan)
        self.assertTrue(outcome.must_exit)
        args, kwargs = self.launched[0]
        self.assertEqual(args[0], "/bin/bash")
        self.assertTrue(kwargs["start_new_session"])
        with open(args[1], encoding="utf-8") as handle:
            script = handle.read()
        self.assertIn("PID=4242", script)
        self.assertIn("/opt/CT", script)

    def test_an_archive_without_the_program_starts_nothing(self):
        payload = _tar_bytes([("ChromebookToggle/readme.txt", b"hi")])
        plan = self.plan(updater.KIND_LINUX_PORTABLE, "ChromebookToggle-9.9-Linux.tar.gz", payload)
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan)
        self.assertEqual(self.launched, [])

    def test_a_package_install_downloads_to_downloads_and_shows_the_command(self):
        plan = self.plan(updater.KIND_LINUX_PACKAGE, "chromebooktoggle_9.9_amd64.deb", b"deb bytes")
        downloads = os.path.join(self.tmp.name, "Downloads")
        outcome = self.run_flow(plan, downloads_dir=downloads, package_tool="apt")
        self.assertFalse(outcome.must_exit)
        self.assertIn("sudo apt install", outcome.message)
        self.assertTrue(os.path.isfile(os.path.join(downloads, "chromebooktoggle_9.9_amd64.deb")))
        self.assertEqual(self.launched, [])


class TestMac(_FlowCase):

    class _Result:
        def __init__(self, code):
            self.returncode = code

    def test_the_app_is_unpacked_with_ditto_then_a_script_swaps_it(self):
        plan = self.plan(updater.KIND_MAC_APP, "ChromebookToggle-9.9-macOS.zip", b"zip bytes", target="/Applications/ChromebookToggle.app")
        ran = []

        def fake_ditto(command):
            ran.append(command)
            os.makedirs(os.path.join(command[-1], "ChromebookToggle.app", "Contents"))
            return self._Result(0)

        outcome = self.run_flow(plan, run=fake_ditto)
        self.assertTrue(outcome.must_exit)
        self.assertEqual(ran[0][:3], ["ditto", "-x", "-k"])
        with open(self.launched[0][0][1], encoding="utf-8") as handle:
            self.assertIn("codesign --verify", handle.read())

    def test_a_failed_unpack_changes_nothing(self):
        plan = self.plan(updater.KIND_MAC_APP, "ChromebookToggle-9.9-macOS.zip", b"zip bytes")
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan, run=lambda command: self._Result(1))
        self.assertEqual(self.launched, [])

    def test_an_archive_without_the_app_changes_nothing(self):
        plan = self.plan(updater.KIND_MAC_APP, "ChromebookToggle-9.9-macOS.zip", b"zip bytes")
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan, run=lambda command: self._Result(0))
        self.assertEqual(self.launched, [])


class TestOther(_FlowCase):

    def test_a_kind_with_no_automatic_update_is_an_error_not_a_crash(self):
        plan = self.plan(updater.KIND_UNKNOWN, "x.bin", b"x")
        with self.assertRaises(updater.UpdateError):
            self.run_flow(plan)


if __name__ == "__main__":
    unittest.main()

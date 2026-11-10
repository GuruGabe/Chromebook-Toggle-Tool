# tests/test_update_apply.py
# ASCII only. Tests chromebook_toggle/update_apply.py - swapping the new
# version's files over an install folder. The important promises: settings
# and logs are never touched, files the update does not supply are never
# deleted, and ANY failure puts the old version back exactly as it was.
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from chromebook_toggle import update_apply, updater

EXE = update_apply.exe_name()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as handle:
        handle.write(text)


def _read(path):
    with open(path, encoding="ascii") as handle:
        return handle.read()


def _snapshot(folder):
    # Every file under folder -> its text, so "unchanged" can be asserted.
    found = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            full = os.path.join(root, name)
            found[os.path.relpath(full, folder)] = _read(full)
    return found


class _InstallCase(unittest.TestCase):
    # A fake old install, a fake unpacked new version, and a work folder.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.target = os.path.join(root, "install")
        self.new = os.path.join(root, "new")
        self.work = os.path.join(root, "work")
        os.makedirs(self.work)
        _write(os.path.join(self.target, EXE), "OLD exe")
        _write(os.path.join(self.target, "_internal", "lib.dll"), "OLD dll")
        _write(os.path.join(self.target, "_internal", "stale.dll"), "OLD stale")
        _write(os.path.join(self.target, "settings.ini"), "MY SETTINGS")
        _write(os.path.join(self.target, "state.ini"), "MY STATE")
        _write(os.path.join(self.target, "Logs", "run.csv"), "MY LOG")
        _write(os.path.join(self.target, "notes-from-a-person.txt"), "KEEP ME")
        _write(os.path.join(self.new, EXE), "NEW exe")
        _write(os.path.join(self.new, "_internal", "lib.dll"), "NEW dll")
        _write(os.path.join(self.new, "settings.ini"), "SHIPPED DEFAULT")

    def tearDown(self):
        self.tmp.cleanup()


class TestSwapInstall(_InstallCase):

    def test_the_new_files_replace_the_old_ones(self):
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertEqual(_read(os.path.join(self.target, EXE)), "NEW exe")
        self.assertEqual(_read(os.path.join(self.target, "_internal", "lib.dll")), "NEW dll")

    def test_a_replaced_folder_loses_files_the_new_version_dropped(self):
        # _internal is replaced as a whole, so a DLL the new version no longer
        # ships does not linger and confuse the app.
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertFalse(os.path.exists(os.path.join(self.target, "_internal", "stale.dll")))

    def test_settings_state_and_logs_are_never_touched(self):
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertEqual(_read(os.path.join(self.target, "settings.ini")), "MY SETTINGS")
        self.assertEqual(_read(os.path.join(self.target, "state.ini")), "MY STATE")
        self.assertEqual(_read(os.path.join(self.target, "Logs", "run.csv")), "MY LOG")

    def test_files_the_update_does_not_supply_are_left_alone(self):
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertEqual(_read(os.path.join(self.target, "notes-from-a-person.txt")), "KEEP ME")

    def test_a_first_time_install_gets_the_shipped_settings(self):
        os.remove(os.path.join(self.target, "settings.ini"))
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertEqual(_read(os.path.join(self.target, "settings.ini")), "SHIPPED DEFAULT")

    def test_the_old_versions_are_kept_in_the_backup_until_the_caller_cleans_up(self):
        update_apply.swap_install(self.target, self.new, self.work)
        self.assertEqual(_read(os.path.join(self.work, "old", EXE)), "OLD exe")

    def test_a_failure_while_copying_restores_the_old_version_exactly(self):
        before = _snapshot(self.target)
        real_copy = update_apply._copy_any

        def fail_on_internal(source, destination):
            if os.path.basename(destination) == "_internal":
                raise PermissionError("locked by antivirus")
            return real_copy(source, destination)

        with mock.patch.object(update_apply, "_copy_any", side_effect=fail_on_internal):
            with self.assertRaises(updater.UpdateError) as raised:
                update_apply.swap_install(self.target, self.new, self.work, retries=2, sleep=lambda s: None)
        self.assertIn("previous version was put back", str(raised.exception))
        self.assertEqual(_snapshot(self.target), before)

    def test_a_failure_while_moving_aside_restores_the_old_version_exactly(self):
        before = _snapshot(self.target)
        real_move = update_apply.shutil.move
        calls = {"n": 0}

        def second_move_fails(source, destination):
            calls["n"] += 1
            if calls["n"] == 2:
                raise PermissionError("in use")
            return real_move(source, destination)

        with mock.patch.object(update_apply.shutil, "move", side_effect=second_move_fails):
            with self.assertRaises(updater.UpdateError):
                update_apply.swap_install(self.target, self.new, self.work, retries=1, sleep=lambda s: None)
        self.assertEqual(_snapshot(self.target), before)

    def test_a_brief_lock_is_retried_and_then_succeeds(self):
        real_move = update_apply.shutil.move
        calls = {"n": 0}

        def fails_once(source, destination):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("antivirus is scanning")
            return real_move(source, destination)

        with mock.patch.object(update_apply.shutil, "move", side_effect=fails_once):
            update_apply.swap_install(self.target, self.new, self.work, retries=3, sleep=lambda s: None)
        self.assertEqual(_read(os.path.join(self.target, EXE)), "NEW exe")


class TestRunApply(_InstallCase):

    def _run(self, wait=lambda pid, timeout: True, relaunch=True, **kwargs):
        launched = []
        code = update_apply.run_apply(
            self.target, self.new, self.work, 1234, os.path.join(self.tmp.name, "update.log"),
            relaunch=relaunch, wait=wait,
            popen=lambda args, **kw: launched.append((args, kw)), sleep=lambda s: None, **kwargs)
        return code, launched

    def test_success_installs_restarts_the_app_and_clears_the_backup(self):
        code, launched = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(_read(os.path.join(self.target, EXE)), "NEW exe")
        self.assertEqual(launched[0][0], [os.path.join(self.target, EXE)])
        self.assertFalse(os.path.exists(os.path.join(self.work, "old")))
        self.assertIn("Update installed", _read(os.path.join(self.tmp.name, "update.log")))

    def test_relaunch_can_be_turned_off(self):
        code, launched = self._run(relaunch=False)
        self.assertEqual((code, launched), (0, []))

    def test_if_the_old_app_will_not_close_nothing_is_changed(self):
        before = _snapshot(self.target)
        code, launched = self._run(wait=lambda pid, timeout: False)
        self.assertEqual(code, 2)
        self.assertEqual(_snapshot(self.target), before)
        self.assertEqual(launched, [])

    def test_a_failed_swap_still_restarts_the_old_working_app(self):
        before = _snapshot(self.target)
        with mock.patch.object(update_apply, "swap_install",
                               side_effect=updater.UpdateError("boom")):
            code, launched = self._run()
        self.assertEqual(code, 3)
        self.assertEqual(_snapshot(self.target), before)
        self.assertEqual(len(launched), 1)

    def test_a_target_that_is_not_an_install_is_refused(self):
        os.remove(os.path.join(self.target, EXE))
        code, launched = self._run()
        self.assertEqual((code, launched), (4, []))

    def test_the_new_files_must_contain_the_exe(self):
        os.remove(os.path.join(self.new, EXE))
        self.assertEqual(self._run()[0], 4)

    def test_updating_a_folder_with_itself_is_refused(self):
        code = update_apply.run_apply(self.target, self.target, self.work, 1, None,
                                      wait=lambda p, t: True, popen=lambda *a, **k: None)
        self.assertEqual(code, 4)

    def test_a_work_folder_inside_the_install_is_refused(self):
        inside = os.path.join(self.target, "work")
        os.makedirs(inside)
        code = update_apply.run_apply(self.target, self.new, inside, 1, None,
                                      wait=lambda p, t: True, popen=lambda *a, **k: None)
        self.assertEqual(code, 4)

    def test_a_drive_root_is_refused(self):
        root = os.path.abspath(os.sep)
        code = update_apply.run_apply(root, self.new, self.work, 1, None,
                                      wait=lambda p, t: True, popen=lambda *a, **k: None)
        self.assertEqual(code, 4)


class TestCommandLines(unittest.TestCase):

    def test_apply_arguments(self):
        seen = []
        update_apply.start_apply("N.exe", "T", "W", 77, "L.log", relaunch=False,
                                 popen=lambda args, **kw: seen.append(args))
        self.assertEqual(seen[0], ["N.exe", "--apply-update", "--target", "T", "--work", "W",
                                   "--pid", "77", "--log", "L.log", "--no-relaunch"])

    def test_setup_command_line_quotes_the_path_and_puts_log_quotes_after_the_equals(self):
        line = update_apply.setup_command_line(r"C:\Users\A B\Setup.exe", r"C:\Users\A B\up.log")
        self.assertTrue(line.startswith('"C:\\Users\\A B\\Setup.exe" /VERYSILENT'))
        self.assertIn("/CLOSEAPPLICATIONS", line)
        self.assertIn("/RELAUNCH=1", line)
        self.assertTrue(line.endswith('/LOG="C:\\Users\\A B\\up.log"'))

    def test_missing_apply_arguments_exit_with_the_bad_arguments_code(self):
        self.assertEqual(update_apply.apply_update_main(["--apply-update"]), 4)
        self.assertEqual(update_apply.apply_update_main(
            ["--apply-update", "--target", "T", "--work", "W", "--pid", "notanumber"]), 4)


class TestCleanup(unittest.TestCase):

    def test_old_work_folders_are_removed_and_young_or_unrelated_ones_are_not(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, update_apply.WORK_PREFIX + "old")
            young = os.path.join(root, update_apply.WORK_PREFIX + "young")
            other = os.path.join(root, "someone-elses-folder")
            for folder in (old, young, other):
                os.makedirs(folder)
            long_ago = time.time() - 5 * 3600
            os.utime(old, (long_ago, long_ago))
            os.utime(other, (long_ago, long_ago))
            removed = update_apply.cleanup_old_work_dirs(root)
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(young))
            self.assertTrue(os.path.exists(other))


class TestWaitForPid(unittest.TestCase):
    # Uses REAL processes, so the Windows OpenProcess/WaitForSingleObject
    # path (and the POSIX os.kill path) is actually exercised.

    def test_a_process_that_has_finished_counts_as_gone(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.assertTrue(update_apply.wait_for_pid_exit(child.pid, timeout=5))

    def test_a_process_that_is_still_running_times_out(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            self.assertFalse(update_apply.wait_for_pid_exit(child.pid, timeout=1))
        finally:
            child.kill()
            child.wait()

    def test_it_notices_when_a_running_process_ends(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
        try:
            self.assertTrue(update_apply.wait_for_pid_exit(child.pid, timeout=20))
        finally:
            child.kill()
            child.wait()


if __name__ == "__main__":
    unittest.main()

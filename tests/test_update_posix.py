# tests/test_update_posix.py
# ASCII only. Tests chromebook_toggle/update_posix.py - the macOS/Linux update
# scripts. The scripts are text, so the checks are: the text is right, hostile
# paths are quoted rather than executed, bash accepts the syntax, and (where a
# real bash exists) the Linux script genuinely swaps a scratch folder.
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from chromebook_toggle import update_posix


def _find_bash():
    # A real bash to run the scripts with. On Windows prefer Git's bash (the
    # "bash.exe" on PATH is often the WSL launcher, which sees different
    # paths). None = skip the tests that need one.
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates.append(os.path.join(base, "Git", "bin", "bash.exe"))
    else:
        candidates.append(shutil.which("bash"))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


BASH = _find_bash()


def _bash_path(path):
    # C:\Users\x -> /c/Users/x so Git's bash can use it.
    path = os.path.abspath(path)
    if sys.platform.startswith("win") and len(path) > 1 and path[1] == ":":
        return "/" + path[0].lower() + path[2:].replace("\\", "/")
    return path


class TestPackageHelpers(unittest.TestCase):

    def test_package_commands(self):
        self.assertEqual(update_posix.package_command("apt", "/tmp/a b.deb"), "sudo apt install '/tmp/a b.deb'")
        self.assertEqual(update_posix.package_command("dnf", "/tmp/a.rpm"), "sudo dnf install /tmp/a.rpm")
        self.assertEqual(update_posix.package_command("rpm", "/tmp/a.rpm"), "sudo rpm -U /tmp/a.rpm")

    def test_package_tool_detection_prefers_apt_then_dnf(self):
        self.assertEqual(update_posix.detect_package_tool(lambda t: "/usr/bin/" + t if t in ("apt", "dnf") else None), "apt")
        self.assertEqual(update_posix.detect_package_tool(lambda t: "/usr/bin/" + t if t == "dnf" else None), "dnf")
        self.assertEqual(update_posix.detect_package_tool(lambda t: None), "rpm")


class TestScriptText(unittest.TestCase):

    def test_both_scripts_wait_for_the_app_and_log(self):
        for script in (
                update_posix.mac_update_script(4321, "/Applications/C.app", "/tmp/n/C.app", "/tmp/w", "/tmp/u.log", "1.5"),
                update_posix.linux_update_script(4321, "/opt/C", "/tmp/n/C", "/tmp/w", "/tmp/u.log", "1.5")):
            self.assertTrue(script.startswith("#!/bin/bash"))
            self.assertIn("PID=4321", script)
            self.assertIn("kill -0", script)
            self.assertIn("update cancelled", script)

    def test_the_mac_script_checks_the_signature_before_replacing_anything(self):
        script = update_posix.mac_update_script(1, "/Applications/C.app", "/tmp/n/C.app", "/tmp/w", "/tmp/u.log", "1.5")
        self.assertLess(script.index("codesign --verify"), script.index('mv "$APP" "$APP.old"'))
        self.assertIn("old version restored", script)

    def test_the_linux_script_keeps_settings_state_and_logs(self):
        script = update_posix.linux_update_script(1, "/opt/C", "/tmp/n/C", "/tmp/w", "/tmp/u.log", "1.5")
        self.assertIn("settings.ini|state.ini|Logs", script)

    def test_a_hostile_path_is_quoted_not_executed(self):
        evil = "/tmp/x; touch /tmp/pwned #"
        for script in (
                update_posix.mac_update_script(1, evil, evil, evil, evil, "1.5"),
                update_posix.linux_update_script(1, evil, evil, evil, evil, "1.5")):
            self.assertIn("'" + evil + "'", script)

    def test_pid_must_be_a_number(self):
        with self.assertRaises(ValueError):
            update_posix.linux_update_script("1; rm -rf /", "/o", "/n", "/w", "/l", "1")


@unittest.skipUnless(BASH, "needs a real bash")
class TestScriptsWithBash(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _syntax_ok(self, text):
        path = os.path.join(self.root, "check.sh")
        with open(path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
        result = subprocess.run([BASH, "-n", _bash_path(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_both_scripts_are_valid_bash(self):
        self._syntax_ok(update_posix.mac_update_script(1, "/A/C.app", "/n/C.app", "/w", "/l", "1.5"))
        self._syntax_ok(update_posix.linux_update_script(1, "/opt/C", "/n/C", "/w", "/l", "1.5"))

    def test_the_linux_script_really_swaps_a_folder(self):
        def put(path, text):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="ascii", newline="\n") as handle:
                handle.write(text)

        install = os.path.join(self.root, "install")
        new = os.path.join(self.root, "new")
        work = os.path.join(self.root, "work")
        log = os.path.join(self.root, "update.log")
        marker = os.path.join(self.root, "relaunched.txt")
        put(os.path.join(install, "ChromebookToggle"), "#!/bin/sh\necho OLD\n")
        put(os.path.join(install, "_internal", "old.txt"), "old")
        put(os.path.join(install, "settings.ini"), "MY SETTINGS")
        put(os.path.join(install, "Logs", "run.csv"), "MY LOG")
        put(os.path.join(new, "ChromebookToggle"), "#!/bin/sh\necho RELAUNCHED > " + _bash_path(marker) + "\n")
        # A real extracted program is executable; files written by a test are
        # not (Windows hides the difference, Linux and macOS do not).
        os.chmod(os.path.join(new, "ChromebookToggle"), 0o755)
        put(os.path.join(new, "_internal", "new.txt"), "new")
        put(os.path.join(new, "settings.ini"), "SHIPPED DEFAULT")
        os.makedirs(work)

        # Process 999999 does not exist, so the script's wait loop ends at once.
        script = update_posix.linux_update_script(
            999999, _bash_path(install), _bash_path(new), _bash_path(work), _bash_path(log), "9.9")
        script_path = os.path.join(self.root, "update.sh")
        with open(script_path, "w", encoding="ascii", newline="\n") as handle:
            handle.write(script)
        result = subprocess.run([BASH, _bash_path(script_path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

        with open(os.path.join(install, "ChromebookToggle"), encoding="ascii") as handle:
            self.assertIn("RELAUNCHED", handle.read())
        self.assertTrue(os.path.isfile(os.path.join(install, "_internal", "new.txt")))
        self.assertFalse(os.path.exists(os.path.join(install, "_internal", "old.txt")))
        with open(os.path.join(install, "settings.ini"), encoding="ascii") as handle:
            self.assertEqual(handle.read(), "MY SETTINGS")
        with open(os.path.join(install, "Logs", "run.csv"), encoding="ascii") as handle:
            self.assertEqual(handle.read(), "MY LOG")
        self.assertFalse(os.path.exists(work), "the work folder should be cleaned up")
        with open(log, encoding="ascii") as handle:
            self.assertIn("updated to the new version", handle.read())
        # The script relaunches the app in the background; give it a moment.
        for _ in range(50):
            if os.path.exists(marker):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(marker), "the updated app was not relaunched")


if __name__ == "__main__":
    unittest.main()

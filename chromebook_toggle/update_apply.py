# chromebook_toggle/update_apply.py
#
# Script:   update_apply.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The "put the new version in place" half of the self-updater (updater.py
#   finds and verifies the download). For a portable or per-user Windows copy
#   this works without PowerShell, a batch file or any helper program:
#
#     1. The running (old) app unpacks the verified update into a temporary
#        work folder and starts the NEW ChromebookToggle.exe from there with
#        --apply-update, then exits.
#     2. The new exe waits for the old process to finish (a running program's
#        files cannot be replaced), swaps its own files over the install
#        folder - keeping settings.ini, Logs and state.ini, and putting
#        everything back if any step fails - and starts the updated app.
#
#   A copy installed by Setup.exe is updated by running the new Setup.exe
#   instead (run_setup_update), so the Add/Remove Programs entry stays
#   correct. macOS and Linux use small shell scripts (update_posix.py).
#
# Notes:
#   ONLY WHAT THE NEW RELEASE CONTAINS IS REPLACED. swap_install() moves
#   aside and replaces just the top-level names that exist in the new
#   version (ChromebookToggle.exe, _internal, ...). Any other file a person
#   put in the install folder is left alone, so an update can never delete
#   something it did not put there.
#
#   EVERY STEP CAN FAIL SAFELY. Antivirus or a still-closing process can lock
#   a file for a moment, so each move/copy is retried a few times. If it
#   still fails, everything already moved is put back and an UpdateError
#   says so - the person is left on the old, working version.
#
#   SECURITY: the --apply-update arguments come from the command line, so
#   run_apply() checks them (the target must really be an install of this
#   app, the work folder must be outside it, and the target cannot be a
#   drive root). The update files were already checksum-verified before this
#   code ever runs.

import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import time

from . import updater

# Names inside the install folder that an update must never touch.
PRESERVE = ("settings.ini", "Logs", "state.ini")

# Prefix of the temporary work folders (also used to clean up old ones).
WORK_PREFIX = "ChromebookToggle-update-"

# Process-creation flags (Windows) so the new process outlives this one.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def exe_name(system=None):
    # The program file inside an install folder.
    system = system or sys.platform
    return "ChromebookToggle.exe" if system.startswith("win") else "ChromebookToggle"


def _preserved(name, preserve):
    key = os.path.normcase(name)
    return any(os.path.normcase(p) == key for p in preserve)


def _retry(action, *args, retries=5, sleep=time.sleep):
    # Runs action(*args), retrying if the operating system refuses (a file
    # briefly locked by antivirus, or by a process that is still closing).
    last = None
    for attempt in range(retries):
        try:
            return action(*args)
        except OSError as error:
            last = error
            if attempt < retries - 1:
                sleep(1)
    raise last


def _remove_any(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.lexists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _copy_any(source, destination):
    # Clear anything a previous, interrupted attempt left at the destination
    # first, so a retry starts clean instead of colliding with half a folder.
    _remove_any(destination)
    if os.path.isdir(source):
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def swap_install(target, new_dir, work_dir, preserve=PRESERVE, retries=5, sleep=time.sleep):
    # Replaces the parts of the install folder 'target' that the new version
    # supplies, using the already-unpacked, already-verified files in
    # 'new_dir'. Old versions of the replaced items are kept in
    # work_dir/old until the swap has fully succeeded. Returns the list of
    # names replaced. Raises UpdateError after putting everything back.
    backup = os.path.join(work_dir, "old")
    os.makedirs(backup, exist_ok=True)
    names = [n for n in sorted(os.listdir(new_dir)) if not _preserved(n, preserve)]
    moved = []      # names moved into the backup folder
    copied = []     # paths copied into the install folder

    def roll_back():
        # Remove whatever was copied in, then move the originals back.
        for path in reversed(copied):
            _remove_any(path)
        for name in reversed(moved):
            try:
                _remove_any(os.path.join(target, name))
                shutil.move(os.path.join(backup, name), os.path.join(target, name))
            except OSError:
                pass

    try:
        # Step 1: move the old items aside (only those the new version replaces).
        for name in names:
            source = os.path.join(target, name)
            if os.path.lexists(source):
                _retry(shutil.move, source, os.path.join(backup, name), retries=retries, sleep=sleep)
                moved.append(name)
        # Step 2: copy the new items in.
        for name in names:
            destination = os.path.join(target, name)
            _retry(_copy_any, os.path.join(new_dir, name), destination, retries=retries, sleep=sleep)
            copied.append(destination)
        # A first-time install (no settings.ini yet) gets the shipped default.
        shipped = os.path.join(new_dir, "settings.ini")
        installed = os.path.join(target, "settings.ini")
        if os.path.isfile(shipped) and not os.path.lexists(installed):
            shutil.copy2(shipped, installed)
    except OSError as error:
        roll_back()
        raise updater.UpdateError(
            "The update could not be installed (%s). Your previous version was put back "
            "and is unchanged." % error) from error
    return names


# ---- waiting for the old app to close ------------------------------------------
def wait_for_pid_exit(pid, timeout=90, sleep=time.sleep):
    # Blocks until process 'pid' is gone or 'timeout' seconds pass. Returns
    # True if it is gone. A process that does not exist counts as gone.
    if sys.platform.startswith("win"):
        return _wait_windows(pid, timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        sleep(0.5)
    return False


def _wait_windows(pid, timeout):
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        # Could not open it: normally because it has already exited.
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0
    finally:
        kernel32.CloseHandle(handle)


# ---- starting things -----------------------------------------------------------
def _detached_kwargs():
    # Popen options that let the child keep running after this process exits.
    if sys.platform.startswith("win"):
        return {"creationflags": _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}


def start_apply(new_exe, target, work_dir, pid, log_path, relaunch=True, popen=subprocess.Popen):
    # Called by the OLD app: starts the new exe in apply mode. The caller
    # exits straight afterwards so its files unlock.
    args = [new_exe, "--apply-update", "--target", target, "--work", work_dir,
            "--pid", str(pid), "--log", log_path]
    if not relaunch:
        args.append("--no-relaunch")
    return popen(args, **_detached_kwargs())


def log_line(log_path, text):
    # One timestamped line (MM-DD-YYYY HH:MM:SS); logging problems are ignored
    # (an update must not fail because a log could not be written). Public
    # because the update window logs to the same file.
    if not log_path:
        return
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
        with open(log_path, "a", encoding="ascii", errors="replace") as handle:
            handle.write("[" + stamp + "] " + text + "\n")
    except OSError:
        pass


_log = log_line


def _check_apply_arguments(target, new_dir, work_dir):
    # Raises UpdateError unless the arguments describe a sane update.
    exe = exe_name()
    if not os.path.isfile(os.path.join(target, exe)):
        raise updater.UpdateError("The folder to update does not contain %s." % exe)
    if not os.path.isfile(os.path.join(new_dir, exe)):
        raise updater.UpdateError("The new version's files are missing %s." % exe)
    if updater.same_path(target, new_dir):
        raise updater.UpdateError("The update source and the install folder are the same.")
    drive, rest = os.path.splitdrive(os.path.abspath(target))
    if not rest.strip("\\/"):
        raise updater.UpdateError("Refusing to update a drive's root folder.")
    work_real = os.path.realpath(work_dir)
    target_real = os.path.realpath(target)
    if work_real == target_real or work_real.startswith(target_real + os.sep):
        raise updater.UpdateError("The update work folder must not be inside the install folder.")


def run_apply(target, new_dir, work_dir, pid, log_path=None, relaunch=True,
              wait=wait_for_pid_exit, popen=subprocess.Popen, sleep=time.sleep):
    # The whole apply step, with the process-level parts injectable for
    # tests. Returns a process exit code: 0 updated, 2 the old app would not
    # close (nothing changed), 3 the swap failed (rolled back), 4 bad
    # arguments (nothing changed).
    try:
        _check_apply_arguments(target, new_dir, work_dir)
    except updater.UpdateError as error:
        _log(log_path, "Refused to apply the update: %s" % error)
        return 4
    _log(log_path, "Applying update to %s (waiting for process %s to close)" % (target, pid))
    if pid and not wait(int(pid), 90):
        _log(log_path, "The old app did not close within 90 seconds - nothing was changed.")
        return 2
    code = 0
    try:
        replaced = swap_install(target, new_dir, work_dir, sleep=sleep)
        _log(log_path, "Update installed. Replaced: %s" % ", ".join(replaced))
    except updater.UpdateError as error:
        _log(log_path, "Update FAILED and was rolled back: %s" % error)
        code = 3
    # Whether or not the swap worked, start the app again so the person is
    # never left with nothing on screen.
    if relaunch:
        try:
            popen([os.path.join(target, exe_name())], cwd=target, **_detached_kwargs())
        except OSError as error:
            _log(log_path, "Could not restart the app: %s" % error)
    shutil.rmtree(os.path.join(work_dir, "old"), ignore_errors=True)
    return code


def _argument(argv, flag):
    # The value after 'flag' in argv, or None.
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def apply_update_main(argv):
    # Entry point for "ChromebookToggle.exe --apply-update ...", run by the
    # NEW exe from the temporary work folder. The new files are simply the
    # folder this exe is running from.
    target = _argument(argv, "--target")
    work_dir = _argument(argv, "--work")
    pid = _argument(argv, "--pid")
    log_path = _argument(argv, "--log")
    if not target or not work_dir or not pid or not pid.isdigit():
        _log(log_path, "Missing or invalid --apply-update arguments.")
        return 4
    new_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]))
    relaunch = "--no-relaunch" not in argv
    code = run_apply(os.path.abspath(target), new_dir, os.path.abspath(work_dir), int(pid),
                     log_path, relaunch)
    if code == 3 and "--quiet" not in argv:
        _tell_person("The update could not be installed. Your previous version was put back and "
                     "will start again. Details are in:\n" + (log_path or "(no log)"))
    return code


def _tell_person(message):
    # A plain message box for the rare failure; never raises.
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Chromebook Toggle Tool - update", message)
        root.destroy()
    except Exception:
        pass


# ---- Windows Setup.exe route -----------------------------------------------------
SETUP_SWITCHES = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                  "/CLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/RELAUNCH=1")


def setup_command_line(setup_path, log_path=None):
    # The one command-line string for the silent upgrade. Built by hand
    # (rather than a list) because Inno Setup wants /LOG="path" with the
    # quotes AFTER the equals sign.
    parts = ['"%s"' % setup_path] + list(SETUP_SWITCHES)
    if log_path:
        parts.append('/LOG="%s"' % log_path)
    return " ".join(parts)


def run_setup_update(setup_path, scope, log_path=None, popen=subprocess.Popen):
    # Starts the new Setup.exe silently so it upgrades the existing install in
    # place. 'scope' is "machine" (installed for all users, needs Windows'
    # administrator prompt) or "user" (just this person, no prompt needed).
    # The caller exits right afterwards so the installer can replace the
    # app's files. Raises UpdateError if the administrator prompt is refused.
    if scope == "machine":
        import ctypes
        arguments = " ".join(list(SETUP_SWITCHES) + (['/LOG="%s"' % log_path] if log_path else []))
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup_path, arguments, None, 0)
        if int(result) <= 32:
            raise updater.UpdateError(
                "The update needs administrator approval and it was not given, so nothing was "
                "changed. Ask IT to run the new Setup, or try again and choose Yes at the Windows prompt.")
        return None
    return popen(setup_command_line(setup_path, log_path), **_detached_kwargs())


# ---- housekeeping ------------------------------------------------------------------
def make_work_dir():
    # A fresh private folder under the system temp area for one update.
    return tempfile.mkdtemp(prefix=WORK_PREFIX)


def cleanup_old_work_dirs(temp_root=None, older_than_seconds=2 * 3600, now=None):
    # Removes leftover work folders from earlier updates (the finished update's
    # own folder cannot delete itself while its exe is running, so it is
    # tidied up on a later start). Folders younger than the cutoff are left
    # alone in case an update is in progress. Returns how many were removed.
    temp_root = temp_root or tempfile.gettempdir()
    now = time.time() if now is None else now
    removed = 0
    try:
        entries = os.listdir(temp_root)
    except OSError:
        return 0
    for name in entries:
        if not name.startswith(WORK_PREFIX):
            continue
        path = os.path.join(temp_root, name)
        try:
            if now - os.path.getmtime(path) < older_than_seconds:
                continue
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            removed += 1
    return removed

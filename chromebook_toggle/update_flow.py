# chromebook_toggle/update_flow.py
#
# Script:   update_flow.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The one function that carries out an update once the person has said yes:
#   download the right file, check its SHA-256, unpack it, and start the
#   mechanism that swaps it in (update_apply.py on Windows, the shell scripts
#   in update_posix.py on macOS/Linux, or the new Setup.exe). It returns an
#   Outcome telling the window whether it must close now.
#
# Notes:
#   This module has NO tkinter in it. The window (update_ui.py) only shows
#   progress and messages; everything that could go wrong lives here, where
#   tests\test_update_flow.py runs it end to end against a local stand-in
#   for GitHub with the process-starting parts replaced by recorders.
#   Every failure is an updater.UpdateError (see updater.py), and nothing the
#   running app depends on is touched here - the actual file replacement
#   happens only after the app has closed.

import collections
import os
import subprocess

from . import update_apply, update_posix, updater

# must_exit: the window has to close NOW so the update can replace its files.
# message: text to show the person (empty when there is nothing to say).
Outcome = collections.namedtuple("Outcome", "must_exit message")


def _find_bundle(root):
    # The ChromebookToggle.app folder somewhere under 'root', or None.
    for dirpath, dirnames, _files in os.walk(root):
        for name in dirnames:
            if name == "ChromebookToggle.app":
                return os.path.join(dirpath, name)
    return None


def _launch_script(script_text, work_dir, popen):
    # Writes the swap script and starts it in its own session so it outlives
    # this process.
    path = os.path.join(work_dir, "update.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(script_text)
    os.chmod(path, 0o700)
    popen(["/bin/bash", path], start_new_session=True, stdin=subprocess.DEVNULL,
          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


def perform_install(plan, api_base, work_dir, log_path, app_version, pid=None, progress=None,
                    popen=subprocess.Popen, run=subprocess.run, setup_runner=None,
                    downloads_dir=None, package_tool=None, opener=None):
    # Carries out 'plan' (an updater.UpdatePlan). Raises updater.UpdateError
    # (and nothing else on purpose) if anything fails; the caller shows it.
    # The keyword arguments from 'popen' onward exist so tests can replace the
    # parts that start real processes.
    pid = os.getpid() if pid is None else pid
    kind = plan.kind
    is_package = kind == updater.KIND_LINUX_PACKAGE

    if is_package:
        # A package install needs root, which this app never asks for, so
        # the file goes somewhere the person can find it.
        folder = downloads_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(folder, exist_ok=True)
        destination = os.path.join(folder, plan.asset_name)
    else:
        destination = os.path.join(work_dir, plan.asset_name)

    updater.download_asset(plan.asset, destination, plan.sha256, api_base=api_base,
                           progress=progress, opener=opener)

    if kind == updater.KIND_WINDOWS_SETUP:
        # Upgrade through the installer so Add/Remove Programs stays correct.
        (setup_runner or update_apply.run_setup_update)(destination, plan.scope, log_path)
        return Outcome(True, "")

    if kind == updater.KIND_WINDOWS_PORTABLE:
        new_root = os.path.join(work_dir, "new")
        os.makedirs(new_root, exist_ok=True)
        updater.safe_extract_zip(destination, new_root)
        new_exe = os.path.join(new_root, "ChromebookToggle", update_apply.exe_name("win32"))
        if not os.path.isfile(new_exe):
            raise updater.UpdateError("The update does not contain ChromebookToggle.exe, so nothing was changed.")
        update_apply.start_apply(new_exe, plan.target, work_dir, pid, log_path, popen=popen)
        return Outcome(True, "")

    if kind == updater.KIND_MAC_APP:
        new_root = os.path.join(work_dir, "new")
        os.makedirs(new_root, exist_ok=True)
        # ditto (Apple's own tool) keeps the app's symlinks and signature,
        # which Python's zipfile would not.
        if run(["ditto", "-x", "-k", destination, new_root]).returncode:
            raise updater.UpdateError("The update could not be unpacked, so nothing was changed.")
        new_app = _find_bundle(new_root)
        if not new_app:
            raise updater.UpdateError("The update does not contain ChromebookToggle.app, so nothing was changed.")
        _launch_script(update_posix.mac_update_script(
            pid, plan.target, new_app, work_dir, log_path, app_version), work_dir, popen)
        return Outcome(True, "")

    if kind == updater.KIND_LINUX_PORTABLE:
        new_root = os.path.join(work_dir, "new")
        os.makedirs(new_root, exist_ok=True)
        updater.safe_extract_tar(destination, new_root)
        new_folder = os.path.join(new_root, "ChromebookToggle")
        if not os.path.isfile(os.path.join(new_folder, "ChromebookToggle")):
            raise updater.UpdateError("The update does not contain ChromebookToggle, so nothing was changed.")
        _launch_script(update_posix.linux_update_script(
            pid, plan.target, new_folder, work_dir, log_path, app_version), work_dir, popen)
        return Outcome(True, "")

    if is_package:
        tool = package_tool or update_posix.detect_package_tool()
        command = update_posix.package_command(tool, destination)
        return Outcome(False, (
            "The new version was downloaded and its SHA-256 matches the release notes:\n"
            "%s\n\nThis copy was installed as a package, so installing needs an administrator "
            "password. In a terminal, run:\n\n%s" % (destination, command)))

    raise updater.UpdateError("This copy cannot be updated automatically.")

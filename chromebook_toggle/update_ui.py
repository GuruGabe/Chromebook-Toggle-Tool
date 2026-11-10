# chromebook_toggle/update_ui.py
#
# Script:   update_ui.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The window side of the self-updater: the automatic check at startup, the
#   "Check for updates now" menu item, the "update available - install it?"
#   question, and the progress box while the update downloads. It decides
#   nothing itself - what to download and how to install is all in the
#   Tk-free, unit-tested modules updater.py, update_flow.py and
#   update_apply.py. This class just asks the questions and shows progress.
#
# Notes:
#   NEVER UPDATES WITHOUT A YES. Finding a newer version only ever produces a
#   question; nothing is downloaded until the person answers it.
#
#   NOTHING MAY DIE SILENTLY. Network work runs on a background thread (so
#   the window never freezes), and every such thread catches everything it
#   could raise - UpdateError for the expected problems, plus a last-resort
#   catch-all - and hands the message back to the window. This is the same
#   rule gam_calls.py and gui.py follow for the same reason (an exception in
#   a background thread is otherwise invisible in a built app).
#
#   THREAD RULE: Tk widgets are touched only on the main thread. The worker
#   threads hand results back with root.after(0, ...).
#
#   THE AUTOMATIC CHECK IS QUIET. At startup it says nothing unless there is
#   an update; being offline or rate-limited is logged, not shown. It runs at
#   most once a day, only for the built app (not when run from source), and
#   only if settings.ini has check_for_updates on.

import os
import shutil
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import paths, state, update_apply, update_flow, update_posix, updater, version


class UpdateController:

    def __init__(self, root, settings, locations):
        self.root = root
        self.settings = settings
        self.locations = locations
        # Where update activity is recorded (next to the audit logs).
        self.log_path = os.path.join(locations.log_dir, "update.log")
        self._busy = False
        self._progress_window = None
        self._progress_bar = None
        self._progress_label = None
        self._last_progress_draw = 0.0

    # ---- small helpers ----------------------------------------------------
    def _log(self, text):
        update_apply.log_line(self.log_path, text)

    def _frozen(self):
        return bool(getattr(sys, "frozen", False))

    def _releases_page(self):
        return version.releases_url(self.settings["update_repo"])

    # ---- checking -----------------------------------------------------------
    def auto_check(self):
        # The quiet startup check. Skipped unless this is the built app, the
        # administrator has not switched checking off, and a day has passed.
        if not self._frozen() or not self.settings.get("check_for_updates", True):
            return
        if not state.check_is_due(state.load_last_check(self.locations.state_path)):
            return
        self._start_check(manual=False)

    def check_now(self):
        # Help > Check for updates now: always answers, even "up to date".
        self._start_check(manual=True)

    def _start_check(self, manual):
        if self._busy:
            if manual:
                messagebox.showinfo(version.APP_NAME, "An update is already in progress.")
            return
        self._busy = True
        threading.Thread(target=self._check_worker, args=(manual,), daemon=True).start()

    def _check_worker(self, manual):
        # Background thread: ask GitHub, hand the answer to the window.
        release, error = None, None
        try:
            release = updater.fetch_latest_release(
                self.settings["update_repo"], self.settings["update_api_base"])
        except updater.UpdateError as problem:
            error = str(problem)
        except Exception as problem:  # last resort - see the module Notes
            error = "Unexpected problem while checking: %s" % problem
        self.root.after(0, lambda: self._on_checked(release, error, manual))

    def _on_checked(self, release, error, manual):
        self._busy = False
        # Note that a check was attempted - even a failed one - so a PC that
        # is offline does not retry on every launch.
        state.save_last_check(self.locations.state_path)
        if error:
            self._log("Update check failed: " + error)
            if manual:
                messagebox.showwarning(version.APP_NAME + " - Update check",
                                       "Could not check for updates:\n\n" + error)
            return
        if not updater.is_newer(release.version, version.APP_VERSION):
            self._log("Update check: up to date (%s)." % version.APP_VERSION)
            if manual:
                messagebox.showinfo(version.APP_NAME + " - Update check",
                                    "You are on the latest version (%s)." % version.APP_VERSION)
            return
        self._log("Update available: %s -> %s" % (version.APP_VERSION, release.version))
        self._offer(release)

    # ---- offering and installing ----------------------------------------------
    def _offer(self, release):
        notes = updater.notes_for_display(release.body)
        text = ("A newer version of %s is available.\n\n    Installed: %s\n    Latest:    %s\n\n"
                % (version.APP_NAME, version.APP_VERSION, release.version))
        if notes:
            text += "What's new:\n" + notes + "\n\n"
        text += "Update now? The app will close, update itself, and open again."
        if messagebox.askyesno(version.APP_NAME + " - Update available", text):
            self._begin_install(release)

    def _begin_install(self, release):
        info = updater.detect_install(
            sys.platform, sys.executable, self._frozen(), paths.is_writable,
            updater.windows_registry_install())
        package_tool = (update_posix.detect_package_tool()
                        if info.kind == updater.KIND_LINUX_PACKAGE else None)
        try:
            plan = updater.make_plan(info, release, package_tool)
        except updater.CannotSelfUpdate as reason:
            # Not a failure - this copy just cannot update itself. Explain,
            # and offer the Releases page so it can be done by hand.
            if messagebox.askyesno(version.APP_NAME + " - Update",
                                   str(reason) + "\n\nOpen the Releases page in your browser?"):
                webbrowser.open(self._releases_page())
            return
        except updater.UpdateError as problem:
            messagebox.showerror(version.APP_NAME + " - Update", str(problem))
            return
        self._busy = True
        self._open_progress("Downloading version %s ..." % release.version)
        self._log("Installing %s (%s) as %s" % (release.version, plan.asset_name, plan.kind))
        threading.Thread(target=self._install_worker, args=(plan,), daemon=True).start()

    def _install_worker(self, plan):
        # Background thread: download, verify, unpack, start the swap.
        work = None
        outcome, error = None, None
        try:
            work = update_apply.make_work_dir()
            outcome = update_flow.perform_install(
                plan, self.settings["update_api_base"], work, self.log_path,
                version.APP_VERSION, progress=self._progress_from_worker)
        except updater.UpdateError as problem:
            error = str(problem)
        except Exception as problem:  # last resort - see the module Notes
            error = "Unexpected problem during the update: %s" % problem
        self.root.after(0, lambda: self._install_done(outcome, error, work))

    def _install_done(self, outcome, error, work):
        self._busy = False
        self._close_progress()
        if error:
            self._log("Update FAILED: " + error)
            if work:
                shutil.rmtree(work, ignore_errors=True)
            messagebox.showerror(
                version.APP_NAME + " - Update",
                "The update was not installed, and nothing was changed.\n\n" + error)
            return
        if outcome.message:
            messagebox.showinfo(version.APP_NAME + " - Update", outcome.message)
        if outcome.must_exit:
            self._log("Update handed over; closing so it can be installed.")
            self.root.destroy()

    # ---- progress box -----------------------------------------------------------
    def _open_progress(self, text):
        window = tk.Toplevel(self.root)
        window.title(version.APP_NAME + " - Update")
        window.transient(self.root)
        window.resizable(False, False)
        # Not closable mid-download: a half-finished update helps nobody.
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        self._progress_label = ttk.Label(window, text=text, width=52)
        self._progress_label.pack(padx=16, pady=(16, 8))
        self._progress_bar = ttk.Progressbar(window, mode="indeterminate", length=380)
        self._progress_bar.pack(padx=16, pady=(0, 16))
        self._progress_bar.start(12)
        window.grab_set()
        self._progress_window = window

    def _close_progress(self):
        if self._progress_window is not None:
            try:
                self._progress_window.grab_release()
                self._progress_window.destroy()
            except tk.TclError:
                pass
        self._progress_window = None

    def _progress_from_worker(self, done, total):
        # Called on the worker thread for every chunk; redraw at most ~10
        # times a second so the window's event queue is not flooded.
        now = time.time()
        if done < total and now - self._last_progress_draw < 0.1:
            return
        self._last_progress_draw = now
        self.root.after(0, lambda: self._draw_progress(done, total))

    def _draw_progress(self, done, total):
        if self._progress_window is None:
            return
        if total:
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate", maximum=total, value=done)
            self._progress_label.configure(
                text="Downloading ... %d%% (%.1f of %.1f MB)"
                % (done * 100 // total, done / 1048576.0, total / 1048576.0))

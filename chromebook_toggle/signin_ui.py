# chromebook_toggle/signin_ui.py
#
# Script:   signin_ui.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The "GAM sign-in" window: lets someone who cannot open a command line renew
#   (gam oauth update) or create (gam oauth create) GAM's Google sign-in from
#   inside this app. It shows who GAM is signed in as, opens GAM in its own
#   window with the right command, and re-checks when asked. All the facts live
#   in gam_signin.py (Tk-free, unit-tested); this file is only the window.
#
# Notes:
#   gam runs in a SEPARATE window because the sign-in opens the web browser and
#   shows a numbered list of permissions that needs a keypress. The window's
#   text tells the person exactly what to press.
#   The status check runs gam in a background thread; results come back to the
#   window with root.after(0, ...) because tkinter must only be touched from
#   the main thread.

import os
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from chromebook_toggle import gam_signin

_WRAP = 560


class SigninWindow(object):
    def __init__(self, root, gam_path, on_closed=None):
        self.root = root
        self.gam_path = gam_path
        self.state = "checking"
        self.checking = False
        self.alive = True

        self.win = tk.Toplevel(root)
        self.win.title("GAM sign-in")
        self.win.transient(root)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self._on_closed = on_closed

        body = ttk.Frame(self.win, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, wraplength=_WRAP, justify="left", text=(
            "This tool works through GAM, which needs a current Google sign-in. If GAM says "
            "\"Reauthentication is needed\" or a similar sign-in message, renew it here - "
            "no command line needed.")).pack(anchor="w")

        status_box = ttk.LabelFrame(body, text="Current sign-in", padding=8)
        status_box.pack(fill="x", pady=(10, 4))
        self.status = ttk.Label(status_box, text="Checking...", wraplength=_WRAP - 20, justify="left")
        self.status.pack(anchor="w")

        action_box = ttk.LabelFrame(body, text="Renew the sign-in", padding=8)
        action_box.pack(fill="x", pady=4)
        ttk.Label(action_box, wraplength=_WRAP - 20, justify="left", text=(
            "1. Click the button. A command window and your web browser open.\n"
            "2. In the browser, sign in with the GAM administrator account and click Allow.\n"
            "3. If the command window shows a numbered list of permissions, just type  c  and "
            "press Enter to keep what is already selected.\n"
            "4. When it says the authentication flow has completed, come back here and click "
            "Check again.")).pack(anchor="w")

        email_line = ttk.Frame(action_box)
        email_line.pack(anchor="w", pady=(8, 0))
        ttk.Label(email_line, text="GAM administrator email (optional):").pack(side="left")
        self.admin_var = tk.StringVar()
        ttk.Entry(email_line, textvariable=self.admin_var, width=34).pack(side="left", padx=(6, 0))

        button_line = ttk.Frame(action_box)
        button_line.pack(anchor="w", pady=(8, 0))
        self.renew_button = ttk.Button(button_line, text="Renew sign-in (gam oauth update)",
                                       command=lambda: self._launch("update"))
        self.renew_button.pack(side="left")
        self.create_button = ttk.Button(button_line, text="First-time sign-in (gam oauth create)",
                                        command=lambda: self._launch("create"))
        self.create_button.pack(side="left", padx=(8, 0))

        self.note = ttk.Label(body, text="", wraplength=_WRAP, justify="left")
        self.note.pack(anchor="w", pady=(6, 0))

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Close", command=self._close).pack(side="right")
        self.check_button = ttk.Button(bottom, text="Check again", command=self.check)
        self.check_button.pack(side="right", padx=6)

        self.check()

    # -- public ----------------------------------------------------------------
    def lift(self):
        # Bring an already-open window to the front.
        try:
            self.win.deiconify()
            self.win.lift()
        except tk.TclError:
            pass

    def exists(self):
        return self.alive

    # -- status ----------------------------------------------------------------
    def check(self):
        # Reads "gam oauth info" in the background, then fills the window.
        if self.checking:
            return
        self.checking = True
        self.status.config(text="Checking...")
        self.check_button.config(state="disabled")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        # Background thread: only runs gam; the window is updated via after().
        try:
            state, detail = gam_signin.check_signin(self.gam_path)
        except Exception as error:  # last-resort guard so the button never stays disabled
            state, detail = "error", "Unexpected problem: %s" % error
        try:
            self.root.after(0, lambda: self._show_state(state, detail))
        except (RuntimeError, tk.TclError):
            pass  # the app is closing

    def _show_state(self, state, detail):
        self.checking = False
        if not self.alive:
            return
        self.state = state
        self.check_button.config(state="normal")
        if state == "ok":
            self.status.config(text="GAM is signed in as %s.\nIf commands still say you need to sign "
                                    "in again, renew it below." % detail)
            if not self.admin_var.get().strip():
                self.admin_var.set(detail)
        elif state == "missing":
            self.status.config(text="GAM has no sign-in yet on this PC. Use \"First-time sign-in\" "
                                    "below. (If it says a client secrets file is missing, IT must "
                                    "set GAM up first.)")
        else:
            self.status.config(text="Could not read GAM's sign-in:\n%s" % detail)
        # Only the matching button is useful: renewing needs an existing
        # sign-in file, and a first sign-in is not needed when one exists.
        self.renew_button.config(state="disabled" if state == "missing" else "normal")
        self.create_button.config(state="normal")

    # -- launching ---------------------------------------------------------------
    def _launch(self, step):
        admin = self.admin_var.get().strip()
        if admin and not gam_signin.valid_email(admin):
            messagebox.showerror("GAM sign-in", "That does not look like an email address.", parent=self.win)
            return
        try:
            words = gam_signin.step_argv(step, admin)
        except ValueError as error:
            messagebox.showerror("GAM sign-in", str(error), parent=self.win)
            return
        argv = [self.gam_path] + words
        system = platform.system()
        plan = gam_signin.launch_plan(
            argv, "GAM sign-in", system, os.environ.get("GAMCFGDIR", ""),
            cmd_blocked=(system == "Windows" and gam_signin.windows_cmd_blocked()))
        shown = " ".join(argv)
        if plan is None:
            messagebox.showinfo("GAM sign-in", "No terminal program was found on this computer. "
                                "Ask IT to run this command:\n\n" + shown, parent=self.win)
            return
        try:
            kwargs = {"creationflags": plan.creationflags} if plan.creationflags else {}
            subprocess.Popen(plan.command, **kwargs)
        except OSError as error:
            messagebox.showerror("GAM sign-in", "Could not open the sign-in window: %s\n\nAsk IT to run:\n\n%s"
                                 % (error, shown), parent=self.win)
            return
        self.note.config(text=(
            "A window and your web browser should be opening. Finish the sign-in there, then "
            "click Check again.") + ("" if plan.stays_open else
                                    " (The window closes by itself when GAM is done.)"))

    def _close(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._on_closed:
            self._on_closed()


class SigninController(object):
    # Owns the single sign-in window. The main window calls open().
    def __init__(self, root, settings):
        self.root = root
        self.settings = settings
        self.window = None

    def open(self):
        if self.window is not None and self.window.exists():
            self.window.lift()
            self.window.check()
            return
        self.window = SigninWindow(self.root, self.settings["gam_path"], on_closed=self._forget)

    def _forget(self):
        self.window = None

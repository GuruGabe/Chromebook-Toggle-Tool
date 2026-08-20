# chromebook_toggle/gui.py
#
# Script:   gui.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.1
#
# Purpose:
#   The tkinter GUI for the Chromebook Toggle Tool. Lets an IT admin pick an
#   action (disable/reenable) and an input method (typed/pasted serials, a
#   CSV file, or a Google Sheet), look devices up read-only, review exactly
#   what will happen, confirm, run the action through gam.exe, and see
#   verified before/after results. This module wires together config.py,
#   serials.py, sheet_url.py, gam_runner.py, device_lookup.py, workflow.py,
#   logging_util.py (Tasks 1-7), and gam_calls.py (also Task 8, split out
#   from this file - see below) - all of those are already unit-tested in
#   isolation; this file itself is intentionally NOT covered by the same
#   kind of assert-based automated tests (asserting against tkinter widget
#   internals provides little real confidence) and was instead verified by
#   manually running the app.
#
# Notes:
#   THREADING / "CALLER OBLIGATION" SUMMARY - this is the single most
#   important design point in this file. Every gam.exe call (gam_runner.
#   run_gam) happens on a background thread (via threading.Thread) so the
#   window never freezes while gam is running - a lookup or a batch action
#   can legitimately take a while. Five of the backend modules this file
#   (indirectly, via gam_calls.py) calls each document, in their own
#   headers, that they deliberately let a specific exception escape
#   uncaught, and each places a "CALLER OBLIGATION" on whichever code
#   calls them from a background thread:
#
#     - gam_runner.run_gam()              -> subprocess.TimeoutExpired, OSError
#     - device_lookup.parse_lookup_json() (indirectly, via ValueError)
#     - workflow.build_review()/build_results() -> KeyError
#     - logging_util.write_log()          -> OSError, UnicodeError
#     - serials.write_temp_serial_csv()   -> ValueError
#
#   Python's default behavior for an exception that escapes a background
#   thread is to print a traceback to stderr and let the thread quietly
#   die - nobody sees that stderr text on a deployed EXE with no console
#   window, so the practical result of missing even one of these wrappers
#   is the "Working..." screen staying up forever with no explanation.
#   Every one of the five calls above is wrapped in its own small
#   "..._or_none()" plain function in chromebook_toggle/gam_calls.py (split
#   out of this file specifically so that logic could be covered by real
#   unit tests - see tests\test_gam_calls.py - the same way every other
#   backend module in this project is) that catches exactly the documented
#   exception type(s) and turns them into a plain (value, error_message)
#   pair instead of letting anything escape. Every background-thread
#   method in this file calls those gam_calls functions instead of calling
#   the backend functions directly.
#
#   THREAD-SAFETY OF TK WIDGETS/VARIABLES: tkinter is not thread-safe. Two
#   separate rules follow from that, both applied throughout this file:
#     (1) Any code that changes what is on screen (building/destroying
#         widgets, showing a messagebox) that runs as a result of
#         background-thread work is scheduled back onto the main thread via
#         self.root.after(0, ...) rather than called directly from the
#         background thread.
#     (2) Any value that lives in a tk.StringVar (the chosen action, the
#         pasted Sheet URL, etc.) is read out on the MAIN thread - before
#         the background thread is started - and handed to the background
#         function as a plain Python argument, rather than the background
#         thread calling .get() on a tk.StringVar itself.

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config, gam_calls, gam_runner, serials, sheet_url

# Shown as the messagebox title and the window title, so every dialog this
# tool pops up is clearly identifiable to whoever is looking at the screen.
APP_TITLE = "Chromebook Toggle Tool"

# Human-readable label for each of the two gam action words this tool ever
# passes around, used to build screen titles/button text without repeating
# the same if/else in five different places.
_ACTION_LABELS = {
    "disable": "Disable",
    "reenable": "Re-enable",
}


class ChromebookToggleApp(tk.Frame):

    def __init__(self, root, settings_path, log_dir):
        super().__init__(root)
        self.root = root
        self.settings_path = settings_path
        self.log_dir = log_dir

        # config.load_settings() never raises - a missing/corrupt
        # settings.ini quietly falls back to sane defaults (see config.py's
        # own docstring), so no try/except is needed around this call.
        self.settings = config.load_settings(settings_path)

        # tk.StringVar objects back the radio buttons and entry fields on
        # the input screen. These are only ever read/written on the main
        # thread (see the module-level Notes above on why).
        self.mode_var = tk.StringVar(value="individual")
        self.action_var = tk.StringVar(value="disable")
        self.csv_path_var = tk.StringVar(value="")
        self.sheet_url_var = tk.StringVar(value="")

        # Widget references that need to be reached from other methods
        # (e.g. to disable the Look Up button) - set up in
        # _build_input_screen()/_refresh_input_widgets().
        self.lookup_button = None
        self.individual_text = None

        # CSV mode's path and Sheet mode's URL live in tk.StringVars
        # (self.csv_path_var/self.sheet_url_var above), which are NOT
        # destroyed when their widgets are torn down for a screen
        # transition - only the widgets bound to them are, so their
        # values naturally survive a Cancel back to the input screen.
        # Individual mode's typed/pasted serials, by contrast, live only
        # inside a plain tk.Text widget with no backing StringVar, so that
        # widget's content is deliberately mirrored into this plain string
        # every time the widget is about to be destroyed (see
        # _stash_individual_text()/_clear_screen() below) - otherwise a
        # user who pastes 50 serials, reviews, and clicks Cancel to fix
        # one typo would have to retype all 50 from scratch.
        self.individual_text_value = ""

        # Set once at startup by _check_gam_on_startup(); used to keep the
        # Look Up button disabled if gam.exe was never found, so the user
        # cannot even attempt a lookup that is guaranteed to fail.
        self.gam_available = True

        # review_rows holds the last review screen's ReviewRow list so the
        # Confirm step (which runs later, after the user has looked at the
        # review screen) knows exactly which serials to act on.
        self.review_rows = []

        self.pack(fill="both", expand=True, padx=10, pady=10)
        self._check_gam_on_startup()
        self._build_input_screen()

    # ------------------------------------------------------------------
    # Screen-teardown helpers - used by every screen transition instead of
    # a bare destroy loop, so Individual mode's typed/pasted text is never
    # silently lost (see self.individual_text_value's comment in __init__).
    # ------------------------------------------------------------------
    def _stash_individual_text(self):
        # Copies whatever is currently in the Individual-mode text box
        # into self.individual_text_value, so it survives the widget
        # itself being destroyed for a screen transition. Safe to call
        # any time, from any screen: self.individual_text is None on any
        # screen that never built the widget, and .get() on a widget that
        # was already destroyed earlier in this same transition raises
        # tk.TclError, which is caught and ignored (nothing new to
        # capture - the value already stashed from that earlier moment is
        # still correct and is left alone).
        if self.individual_text is not None:
            try:
                self.individual_text_value = self.individual_text.get("1.0", "end")
            except tk.TclError:
                pass

    def _clear_screen(self):
        # Every screen transition in this app destroys every widget
        # currently in this frame, then builds the next screen's widgets
        # fresh (see _build_input_screen()'s own comment for why). This
        # single helper is used for every one of those transitions so the
        # stash above always happens first, no matter which screen is
        # being left.
        self._stash_individual_text()
        for widget in self.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------
    # Startup pre-flight check
    # ------------------------------------------------------------------
    def _check_gam_on_startup(self):
        # check_gam_available() only does a plain file-existence check (see
        # gam_runner.py's own docstring) - fast enough to call directly on
        # the main thread with no background thread needed.
        ok, message = gam_runner.check_gam_available(self.settings["gam_path"])
        self.gam_available = ok
        if not ok:
            # Per the task requirement: warn up front and do not let the
            # user proceed to a lookup that will just fail. The Look Up
            # button is also disabled (see _build_input_screen()) as a
            # second, belt-and-suspenders guard, and the lookup handler
            # re-checks gam availability again immediately before it would
            # actually shell out to gam.exe.
            messagebox.showerror(
                APP_TITLE,
                "GAM was not found, so this tool cannot look up or change "
                "any devices right now.\n\n" + message +
                "\n\nContact IT - this usually means GAM is not installed "
                "on this PC yet, the configured path in settings.ini is "
                "wrong, or a network drive GAM depends on is unavailable.",
            )

    # ------------------------------------------------------------------
    # Screen 1: choose action, input method, and enter/select input
    # ------------------------------------------------------------------
    def _build_input_screen(self):
        # Every screen transition in this app works the same way: destroy
        # every widget currently in this frame, then build the next
        # screen's widgets fresh. Simpler and far less error-prone than
        # trying to show/hide/reuse widgets across five very different
        # screen layouts. _clear_screen() (rather than a bare destroy
        # loop) also preserves Individual mode's typed text first - see
        # _stash_individual_text()'s own comment for why that matters.
        self._clear_screen()

        tk.Label(self, text=APP_TITLE, font=("Segoe UI", 14, "bold")).pack(anchor="w")

        action_frame = ttk.LabelFrame(self, text="Action")
        action_frame.pack(fill="x", pady=(10, 5))
        ttk.Radiobutton(action_frame, text="Disable", variable=self.action_var, value="disable").pack(side="left", padx=5)
        ttk.Radiobutton(action_frame, text="Re-enable", variable=self.action_var, value="reenable").pack(side="left", padx=5)

        mode_frame = ttk.LabelFrame(self, text="Input Method")
        mode_frame.pack(fill="x", pady=5)
        ttk.Radiobutton(mode_frame, text="Individual (type/paste serials)", variable=self.mode_var,
                         value="individual", command=self._refresh_input_widgets).pack(anchor="w", padx=5)
        ttk.Radiobutton(mode_frame, text="CSV file", variable=self.mode_var,
                         value="csv", command=self._refresh_input_widgets).pack(anchor="w", padx=5)
        ttk.Radiobutton(mode_frame, text="Google Sheet", variable=self.mode_var,
                         value="sheet", command=self._refresh_input_widgets).pack(anchor="w", padx=5)

        # input_container holds whichever widgets the currently-selected
        # input mode needs (text box / CSV browse row / URL entry) -
        # rebuilt by _refresh_input_widgets() every time the mode changes.
        self.input_container = ttk.Frame(self)
        self.input_container.pack(fill="both", expand=True, pady=5)
        self._refresh_input_widgets()

        self.lookup_button = ttk.Button(self, text="Look Up Devices", command=self._on_look_up_clicked)
        self.lookup_button.pack(anchor="e", pady=(10, 0))
        if not self.gam_available:
            # Belt-and-suspenders per the task requirement: gam.exe was not
            # found at startup, so do not let the user even click Look Up -
            # the click handler's own re-check would catch this too, but
            # disabling the button here means the failure is visible before
            # the user wastes time filling in serials/a CSV/a URL first.
            self.lookup_button.configure(state="disabled")

    def _refresh_input_widgets(self):
        # Rebuild only the input-method-specific widgets, not the whole
        # screen, so switching modes does not lose the Action selection
        # above or require re-creating the mode radio buttons themselves.
        # Stash Individual mode's text FIRST, in case the widget about to
        # be destroyed below is the individual_text box itself (e.g. the
        # admin switches from Individual to CSV mode and back) - this is
        # in addition to _clear_screen()'s own stash, which only covers a
        # full screen transition, not a same-screen mode switch like this.
        self._stash_individual_text()
        for widget in self.input_container.winfo_children():
            widget.destroy()

        mode = self.mode_var.get()
        if mode == "individual":
            tk.Label(self.input_container, text="One serial number per line:").pack(anchor="w")
            self.individual_text = tk.Text(self.input_container, height=10)
            self.individual_text.pack(fill="both", expand=True)
            if self.individual_text_value:
                # Restore whatever was typed/pasted before this widget was
                # last destroyed - e.g. after Cancel from the review
                # screen, or after switching to another mode and back.
                self.individual_text.insert("1.0", self.individual_text_value)
        elif mode == "csv":
            row = ttk.Frame(self.input_container)
            row.pack(fill="x")
            # state="readonly" - the path is only ever set via the Browse
            # button below, never hand-typed, so a mistyped path can never
            # reach read_csv_serials().
            ttk.Entry(row, textvariable=self.csv_path_var, state="readonly").pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse...", command=self._browse_csv).pack(side="left", padx=(5, 0))
            tk.Label(self.input_container, text='File must have a "Serial" or "SerialNumber" column.').pack(anchor="w", pady=(5, 0))
        elif mode == "sheet":
            tk.Label(self.input_container, text="Paste the Google Sheet URL:").pack(anchor="w")
            ttk.Entry(self.input_container, textvariable=self.sheet_url_var).pack(fill="x")
            # Helper text per the task requirement: show the configured
            # acting email and remind the user the header must be exactly
            # "Serial" (not "SerialNumber" - unlike CSV mode, gam reads the
            # Sheet directly, so this tool's own tolerant CSV header
            # matching in serials.py never gets a chance to run on it).
            tk.Label(
                self.input_container,
                text='The sheet must have a column with the header exactly "Serial" '
                     "(this exact spelling only - gam reads the sheet directly, so "
                     "this tool cannot correct a different header the way it can for "
                     "an uploaded CSV file), and the sheet must be shared with " +
                     self.settings["sheet_acting_email"] + " (the Workspace identity "
                     "this tool uses to read Google Sheets).",
                wraplength=550, justify="left",
            ).pack(anchor="w", pady=(5, 0))

    def _browse_csv(self):
        path = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path_var.set(path)

    # ------------------------------------------------------------------
    # Look Up Devices button handler - resolves input, then either goes
    # to a background lookup (Individual/CSV) or straight to a confirm
    # screen (Google Sheet - see the task design for why Sheet mode has
    # no local list to review ahead of time).
    # ------------------------------------------------------------------
    def _on_look_up_clicked(self):
        # Read every tk.StringVar/widget value needed below on the main
        # thread now, before any background thread is started - see the
        # module-level Notes on why background code never touches tk
        # widgets/variables directly.
        mode = self.mode_var.get()
        action = self.action_var.get()

        try:
            if mode == "individual":
                # parse_multiline_serials() never raises - blank lines are
                # simply dropped - so no try/except is needed for this
                # branch specifically, but it is still inside the shared
                # try below for the csv branch's sake.
                serial_list = serials.parse_multiline_serials(self.individual_text.get("1.0", "end"))
            elif mode == "csv":
                path = self.csv_path_var.get()
                if not path:
                    messagebox.showwarning(APP_TITLE, "Choose a CSV file first.")
                    return
                # read_csv_serials() raises ValueError for every input-file
                # problem it can hit (missing file, no header, wrong
                # header) - caught below with one clear message regardless
                # of which of those it was, per serials.py's own docstring.
                serial_list = serials.read_csv_serials(path)
            else:
                sheet_url_text = self.sheet_url_var.get().strip()
                if not sheet_url_text:
                    messagebox.showwarning(APP_TITLE, "Paste a Google Sheet URL first.")
                    return
                # Sheet mode has no local serial list - gam reads the sheet
                # directly at execution time. Here we only confirm the URL
                # parses at all, so a bad paste fails fast with a clear
                # message instead of only surfacing once gam.exe runs.
                sheet_url.parse_sheet_url(sheet_url_text)
                serial_list = None
        except ValueError as value_error:
            messagebox.showerror(APP_TITLE, str(value_error))
            return

        if mode != "sheet" and not serial_list:
            messagebox.showwarning(APP_TITLE, "No serial numbers were found in that input.")
            return

        # Re-check gam availability immediately before doing anything that
        # would actually shell out to gam.exe - settings.ini/the PC's
        # environment could have changed since startup, and this is the
        # task's explicit requirement for the Look Up flow.
        ok, message = gam_runner.check_gam_available(self.settings["gam_path"])
        if not ok:
            messagebox.showerror(APP_TITLE, message)
            return

        if mode == "sheet":
            self._show_sheet_confirm_screen(action, self.sheet_url_var.get().strip())
            return

        # Switch to the "please wait" interstitial immediately - this
        # destroys the Look Up button (and every other screen-1 widget)
        # entirely via _clear_screen(), which is a stronger guard against
        # a fast double-click starting two overlapping lookups than merely
        # disabling the button would be, and also means the window is
        # never just sitting there looking unresponsive while gam.exe runs.
        self._show_looking_up_screen()
        self._run_in_background(lambda: self._do_lookup_and_show_review(serial_list, action))

    # ------------------------------------------------------------------
    # NOTE: the six "CALLER OBLIGATION" wrapper functions this file used
    # to define here as methods (_run_gam_or_none(), _parse_lookup_or_none(),
    # _build_review_or_none(), _build_results_or_none(),
    # _write_log_or_warning(), _write_temp_csv_or_none()) now live in
    # chromebook_toggle/gam_calls.py as plain functions (gam_calls.
    # run_gam_or_none(), etc.), taking gam_path/log_dir as explicit
    # parameters instead of reading them off self. That module has zero
    # tkinter dependency, which is what makes it unit-testable with plain
    # unittest + mock.patch - see tests\test_gam_calls.py. Every call site
    # below was updated to call gam_calls.xxx_or_none(...) instead of
    # self._xxx_or_none(...).
    # ------------------------------------------------------------------
    # Background thread: Individual/CSV lookup -> review screen
    # ------------------------------------------------------------------
    def _do_lookup_and_show_review(self, serial_list, action):
        result, error = gam_calls.run_gam_or_none(self.settings["gam_path"], gam_runner.build_lookup_args(serial_list))
        if error:
            self._show_error_and_return_to_input(error)
            return
        if result.returncode != 0:
            # A nonzero gam.exe exit code on the lookup call itself means
            # the lookup failed outright (bad credentials, gam config
            # problem, etc.) - distinct from a lookup that ran fine but
            # simply found nothing for some serials, which build_review()
            # already reports per-row on the review screen.
            self._show_error_and_return_to_input(
                "Looking up devices failed:\n\n" + (result.stderr or "(gam.exe printed no error output)")
            )
            return

        looked_up, error = gam_calls.parse_lookup_or_none(result.stdout)
        if error:
            self._show_error_and_return_to_input(error)
            return

        review_rows, error = gam_calls.build_review_or_none(serial_list, looked_up, action)
        if error:
            self._show_error_and_return_to_input(error)
            return

        # Marshal the screen change back onto the main thread - tkinter
        # widgets must only ever be created/changed from the main thread.
        self.root.after(0, lambda: self._show_review_screen(review_rows, action))

    # ------------------------------------------------------------------
    # Screen 2a: review/confirm for Individual and CSV modes
    # ------------------------------------------------------------------
    def _show_review_screen(self, review_rows, action):
        self.review_rows = review_rows
        self._clear_screen()

        action_label = _ACTION_LABELS[action]
        tk.Label(self, text=action_label + " - Review", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        tree = ttk.Treeview(self, columns=("status", "will_process"), show="tree headings")
        tree.heading("#0", text="Serial")
        tree.heading("status", text="Current Status")
        tree.heading("will_process", text="Will Process?")
        tree.pack(fill="both", expand=True, pady=10)

        will_process_count = 0
        for row in review_rows:
            if row.will_process:
                will_process_count += 1
                will_process_text = "Yes"
            else:
                will_process_text = "Skip - " + row.skip_reason
            tree.insert("", "end", text=row.serial, values=(row.current_status or "(not found)", will_process_text))

        tk.Label(
            self, text=str(will_process_count) + " of " + str(len(review_rows)) + " device(s) will be changed."
        ).pack(anchor="w")

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", pady=(10, 0))
        ttk.Button(button_row, text="Cancel", command=self._build_input_screen).pack(side="right", padx=(5, 0))
        confirm_state = "normal" if will_process_count > 0 else "disabled"
        ttk.Button(
            button_row, text="Confirm - " + action_label, state=confirm_state,
            command=lambda: self._on_confirm_list_action(action),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Screen 2b: confirm for Google Sheet mode (no local per-device table -
    # see the task design note on why: gam reads the sheet directly at
    # execution time, there is no local list to look up ahead of time).
    # ------------------------------------------------------------------
    def _show_sheet_confirm_screen(self, action, sheet_url_text):
        self._clear_screen()
        action_label = _ACTION_LABELS[action]
        tk.Label(self, text=action_label + " - Confirm Google Sheet", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(
            self,
            text="GAM will read every row's Serial column directly from this sheet "
                 "and " + action_label.lower() + " each device listed:\n\n" + sheet_url_text,
            wraplength=550, justify="left",
        ).pack(anchor="w", pady=10)
        button_row = ttk.Frame(self)
        button_row.pack(fill="x", pady=(10, 0))
        ttk.Button(button_row, text="Cancel", command=self._build_input_screen).pack(side="right", padx=(5, 0))
        ttk.Button(
            button_row, text="Confirm - " + action_label,
            command=lambda: self._on_confirm_sheet_action(action, sheet_url_text),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Confirm button handlers - switch to the Working screen immediately,
    # then hand off to a background thread.
    # ------------------------------------------------------------------
    def _on_confirm_list_action(self, action):
        self._show_working_screen()
        self._run_in_background(lambda: self._do_list_action(action))

    def _on_confirm_sheet_action(self, action, sheet_url_text):
        self._show_working_screen()
        self._run_in_background(lambda: self._do_sheet_action(action, sheet_url_text))

    def _show_looking_up_screen(self):
        self._clear_screen()
        tk.Label(self, text="Looking up devices - please wait...", font=("Segoe UI", 12)).pack(pady=(40, 5))
        # Reassurance text: this screen gives no other feedback for up to
        # 180 seconds (gam_runner.run_gam()'s default timeout) while a
        # larger list looks up, and the target users are non-technical -
        # without this, a slow-but-normal lookup can look identical to a
        # frozen window.
        tk.Label(self, text="A large list can take a minute or two - this is normal.").pack()

    def _show_working_screen(self):
        self._clear_screen()
        tk.Label(self, text="Working - do not close this window...", font=("Segoe UI", 12)).pack(pady=(40, 5))
        # Same reassurance as _show_looking_up_screen() above, for the
        # same reason.
        tk.Label(self, text="A large list can take a minute or two - this is normal.").pack()

    # ------------------------------------------------------------------
    # Background thread: Individual/CSV confirm -> execute -> verify
    # ------------------------------------------------------------------
    def _do_list_action(self, action):
        will_process_serials = [row.serial for row in self.review_rows if row.will_process]

        temp_csv_path, error = gam_calls.write_temp_csv_or_none(will_process_serials)
        if error:
            self._show_error_and_return_to_input("Could not prepare the action: " + error)
            return

        try:
            result, error = gam_calls.run_gam_or_none(self.settings["gam_path"], gam_runner.build_csv_action_args(temp_csv_path, action))
            if error:
                self._show_error_and_return_to_input(error)
                return
            if result.returncode != 0:
                self._show_error_and_return_to_input(
                    "Running the action failed:\n\n" + (result.stderr or "(gam.exe printed no error output)")
                )
                return

            # The mutating action call above reported success (exit code
            # 0). By design, "success" is never trusted from
            # gam's own exit code/stdout text alone - a second, independent
            # lookup verifies the real resulting status of every device
            # that was just processed. From this point on, if anything
            # below fails, the error message says so explicitly, since the
            # real district devices have already been changed - this is
            # NOT the same situation as the lookup/action calls above
            # failing before anything happened.
            post_result, error = gam_calls.run_gam_or_none(self.settings["gam_path"], gam_runner.build_lookup_args(will_process_serials))
            if error:
                self._show_error_and_return_to_input(
                    "The action ran, but verifying the results failed: " + error +
                    "\n\nCheck device status manually in the Google Admin console."
                )
                return
            if post_result.returncode != 0:
                self._show_error_and_return_to_input(
                    "The action ran, but the follow-up status check failed:\n\n" +
                    (post_result.stderr or "(gam.exe printed no error output)") +
                    "\n\nCheck device status manually in the Google Admin console."
                )
                return

            post_looked_up, error = gam_calls.parse_lookup_or_none(post_result.stdout)
            if error:
                self._show_error_and_return_to_input(
                    "The action ran, but verifying the results failed: " + error +
                    "\n\nCheck device status manually in the Google Admin console."
                )
                return

            results, error = gam_calls.build_results_or_none(self.review_rows, post_looked_up, action)
            if error:
                self._show_error_and_return_to_input(error)
                return

            # A failed log write is deliberately treated as a softer
            # warning, not a failure of the run itself - per
            # logging_util.py's CALLER OBLIGATION note, the real action
            # already succeeded and the verified results are already in
            # hand, so they are still shown on the results screen even if
            # the log could not be written.
            log_path, log_error = gam_calls.write_log_or_warning(self.log_dir, action, results)
            self.root.after(0, lambda: self._show_results_screen(results, log_path, log_error))
        finally:
            # Always clean up the temp CSV, whether everything above
            # succeeded or any step failed and returned early.
            self._safe_remove_temp_file(temp_csv_path)

    def _safe_remove_temp_file(self, path):
        try:
            os.remove(path)
        except OSError:
            # A leftover temp file under %TEMP% is a minor housekeeping
            # issue, not a reason to raise a second error on top of
            # whatever this run's real result already was (success or
            # failure) - silently ignored here rather than surfaced.
            pass

    # ------------------------------------------------------------------
    # Background thread: Google Sheet confirm -> execute
    # ------------------------------------------------------------------
    def _do_sheet_action(self, action, sheet_url_text):
        try:
            # Re-parse the URL for the actual gam call (it was already
            # validated once in _on_look_up_clicked, but parsed again here
            # per the task design, and wrapped again defensively so this
            # background thread can never die on an uncaught ValueError
            # even in the unlikely case something about the URL changed).
            file_id, gid = sheet_url.parse_sheet_url(sheet_url_text)
        except ValueError as value_error:
            self._show_error_and_return_to_input("Could not read the Google Sheet URL: " + str(value_error))
            return

        result, error = gam_calls.run_gam_or_none(
            self.settings["gam_path"],
            gam_runner.build_gsheet_action_args(self.settings["sheet_acting_email"], file_id, gid, action),
        )
        if error:
            self._show_error_and_return_to_input(error)
            return
        if result.returncode != 0:
            self._show_error_and_return_to_input(
                "Running the action failed:\n\n" + (result.stderr or "(gam.exe printed no error output)")
            )
            return

        # Sheet mode has no local pre-fetched serial list to independently
        # re-verify against, so per the task design, the raw gam output is
        # shown directly instead of a verified per-device table, and
        # logging_util.write_log() is deliberately NOT called here (there
        # is no ResultRow list to log without per-device verification).
        self.root.after(0, lambda: self._show_sheet_results_screen(result.stdout))

    # ------------------------------------------------------------------
    # Screen 3a: results for Individual/CSV modes
    # ------------------------------------------------------------------
    def _show_results_screen(self, results, log_path, log_error):
        self._clear_screen()
        tk.Label(self, text="Results", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        tree = ttk.Treeview(self, columns=("previous", "new", "result"), show="tree headings")
        tree.heading("#0", text="Serial")
        tree.heading("previous", text="Previous Status")
        tree.heading("new", text="New Status")
        tree.heading("result", text="Result")
        tree.pack(fill="both", expand=True, pady=10)

        success_count = 0
        for row in results:
            if row.success:
                success_count += 1
            tree.insert("", "end", text=row.serial, values=(
                row.previous_status or "", row.new_status or "", "SUCCESS" if row.success else "FAILED"
            ))

        tk.Label(
            self, text=str(success_count) + " of " + str(len(results)) + " device(s) succeeded.",
        ).pack(anchor="w")

        if log_error:
            # Softer warning styling than a hard error - the real results
            # above are still valid and already visible; only the audit
            # log write itself failed.
            tk.Label(
                self, text="WARNING: the log file could not be written: " + log_error,
                wraplength=550, justify="left", fg="#B00000",
            ).pack(anchor="w", pady=(5, 0))
        else:
            tk.Label(self, text="Log file: " + log_path, wraplength=550, justify="left").pack(anchor="w", pady=(5, 0))

        ttk.Button(self, text="Done", command=self._build_input_screen).pack(anchor="e", pady=(10, 0))

    # ------------------------------------------------------------------
    # Screen 3b: results for Google Sheet mode (raw gam output, no table)
    # ------------------------------------------------------------------
    def _show_sheet_results_screen(self, raw_output):
        self._clear_screen()
        tk.Label(self, text="Google Sheet Action Complete", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        text_box = tk.Text(self, height=18)
        text_box.insert("1.0", raw_output)
        # Read-only after inserting the text - this is gam's own output for
        # the record, not something the admin should be able to edit.
        text_box.configure(state="disabled")
        text_box.pack(fill="both", expand=True, pady=10)

        tk.Label(
            self,
            text="No structured log was written for this run - Sheet-mode results are not "
                 "independently re-verified per device the way Individual/CSV mode results "
                 "are, so there is no ResultRow list to log. The gam output above is the "
                 "record of what gam.exe reported for this run. The Logs folder for other "
                 "runs (Individual/CSV mode) is: " + self.log_dir,
            wraplength=550, justify="left",
        ).pack(anchor="w")

        ttk.Button(self, text="Done", command=self._build_input_screen).pack(anchor="e", pady=(10, 0))

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _run_in_background(self, target):
        # daemon=True so a still-running background thread (e.g. gam.exe
        # genuinely hung) does not prevent the whole process from exiting
        # if the admin closes the window.
        threading.Thread(target=target, daemon=True).start()

    def _show_error_and_return_to_input(self, message):
        # Called from a background thread - marshal both the messagebox
        # and the screen rebuild back onto the main thread together, via a
        # single after() call, so the two always happen in order and
        # neither runs on the wrong thread.
        self.root.after(0, lambda: self._show_error_and_reset(message))

    def _show_error_and_reset(self, message):
        messagebox.showerror(APP_TITLE, message)
        self._build_input_screen()

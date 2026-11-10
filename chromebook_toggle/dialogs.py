# chromebook_toggle/dialogs.py
#
# Script:   dialogs.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The one custom dialog box the tool needs: the "type the word to
#   continue" confirmation shown before a PERMANENT action (deprovisioning).
#   An ordinary Yes/No box is too easy to click through on autopilot; making
#   the person type DEPROVISION means they have to stop and read it.
#
# Notes:
#   The decision of what counts as a correct answer is NOT made here - it is
#   actions.typed_confirmation_ok(), which is unit-tested. This module only
#   draws the box and enables the button when that function says yes. Like
#   gui.py, the drawing itself is checked by running the app rather than by
#   assert-based tests.

import tkinter as tk
from tkinter import ttk

from . import actions


def ask_typed_confirmation(parent, title, message, button_text):
    # Shows a modal box with 'message', a text field, and Cancel / button_text
    # buttons. The action button stays DISABLED until the person has typed
    # the confirmation word exactly. Returns True only if they typed it and
    # pressed the button; closing the box or pressing Cancel returns False.
    answer = {"ok": False}

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)

    ttk.Label(dialog, text=message, wraplength=480, justify="left").pack(padx=16, pady=(16, 8))
    ttk.Label(dialog, text="To continue, type  " + actions.CONFIRM_WORD + "  below:").pack(padx=16, anchor="w")

    typed = tk.StringVar()
    entry = ttk.Entry(dialog, textvariable=typed, width=28)
    entry.pack(padx=16, pady=(4, 12), anchor="w")

    buttons = ttk.Frame(dialog)
    buttons.pack(fill="x", padx=16, pady=(0, 16))

    def accept():
        # Re-check at the moment of pressing, not just when the button was
        # enabled - nothing but an exact match may get through.
        if actions.typed_confirmation_ok(typed.get()):
            answer["ok"] = True
            dialog.destroy()

    def cancel():
        dialog.destroy()

    ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right", padx=(6, 0))
    go = ttk.Button(buttons, text=button_text, command=accept, state="disabled")
    go.pack(side="right")

    def on_typing(*_ignored):
        go.configure(state="normal" if actions.typed_confirmation_ok(typed.get()) else "disabled")

    typed.trace_add("write", on_typing)
    dialog.bind("<Return>", lambda _event: accept())
    dialog.bind("<Escape>", lambda _event: cancel())
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    # Modal: nothing else in the app can be clicked until this is answered.
    dialog.grab_set()
    entry.focus_set()
    parent.wait_window(dialog)
    return answer["ok"]

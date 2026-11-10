# chromebook_toggle/actions.py
#
# Script:   actions.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The ONE place that defines which Chromebook actions this tool can run:
#   disable, re-enable, and (when an administrator turns it on) deprovision.
#   For each action it answers four questions that the rest of the code used
#   to hard-code in separate places: what GAM calls it, what status the
#   device should have afterwards, what extra GAM arguments it needs, and
#   what to call it on screen. Keeping that in one module means a new action
#   cannot be half-added.
#
# Notes:
#   An "action" everywhere in this tool is the exact GAM action word
#   ("disable", "reenable", "deprovision_retiring_device", ...). That string
#   is passed straight to GAM, used as a dictionary key, and written to the
#   audit log - there is no separate internal name to translate.
#
#   DEPROVISIONING IS PERMANENT. GAM's own documentation (ChromeOS Devices
#   wiki, "Deprovisioning") says it is not reversible: the device must be
#   physically wiped and re-enrolled to be managed again, and it can change
#   the license count. GAM therefore refuses to deprovision unless the
#   command includes acknowledge_device_touch_requirement, and by default it
#   will not deprovision more than ONE device per command (max_to_deprov).
#   This tool always supplies the acknowledgement for a deprovision action
#   (the person has already typed a confirmation word by then - see
#   CONFIRM_WORD), and it runs one device per GAM command through "gam csv",
#   so GAM's one-device default is never hit.

# ---- the two everyday actions ------------------------------------------------
DISABLE = "disable"
REENABLE = "reenable"

# ---- deprovisioning ---------------------------------------------------------
# (GAM action word, text shown to the person). Order is the order shown in the
# reason list; the FIRST entry is the default. These four are the reasons the
# GAM wiki documents for "gam update cros ... action <CrOSAction>"; GAM also
# accepts *_replacement spellings of the two replace reasons, which are
# aliases and are not listed here.
DEPROVISION_REASONS = (
    ("deprovision_retiring_device", "Retiring the device"),
    ("deprovision_same_model_replace", "Replacing it with the same model"),
    ("deprovision_different_model_replace", "Replacing it with a different model"),
    ("deprovision_upgrade_transfer", "Upgrade transfer"),
)

# Just the GAM words, for membership tests.
DEPROVISION_ACTIONS = tuple(word for word, _text in DEPROVISION_REASONS)

# What the reason list starts on.
DEFAULT_DEPROVISION_ACTION = DEPROVISION_ACTIONS[0]

# The argument GAM requires before it will deprovision anything. GAM's wiki:
# "As deprovisioning ChromeOS devices is not reversible, you must enter
# acknowledge_device_touch_requirement".
ACKNOWLEDGE_ARG = "acknowledge_device_touch_requirement"

# The word a person must type to confirm a deprovision. Deliberately a word
# nobody types by accident, and case-sensitive on purpose.
CONFIRM_WORD = "DEPROVISION"

# ---- what each action should leave behind -------------------------------------
# The device status (as GAM reports it in "status") that proves the action
# worked. The tool never trusts GAM's exit code for a change - it looks the
# device up again afterwards and compares against this table.
TARGET_STATUS = {
    DISABLE: "DISABLED",
    REENABLE: "ACTIVE",
}
for _word in DEPROVISION_ACTIONS:
    TARGET_STATUS[_word] = "DEPROVISIONED"

# The status a deprovisioned device reports. A deprovisioned device is no
# longer managed, so it cannot be disabled or re-enabled (see workflow.py).
DEPROVISIONED_STATUS = "DEPROVISIONED"

# ---- plain-English names ------------------------------------------------------
_REASON_TEXT = dict(DEPROVISION_REASONS)


def is_deprovision(action):
    # True for any of the four deprovision words, False for everything else
    # (including a typo - an unknown string is never treated as destructive
    # here; workflow.py's TARGET_STATUS lookup rejects it loudly instead).
    return action in DEPROVISION_ACTIONS


def label(action):
    # The name shown on buttons and screen titles. A deprovision includes its
    # reason so the review and results screens say exactly what was chosen.
    if action == DISABLE:
        return "Disable"
    if action == REENABLE:
        return "Re-enable"
    if is_deprovision(action):
        return "Deprovision (" + _REASON_TEXT[action] + ")"
    return str(action)


def verb(action):
    # The lower-case verb used inside sentences ("cannot re-enable").
    if action == DISABLE:
        return "disable"
    if action == REENABLE:
        return "re-enable"
    if is_deprovision(action):
        return "deprovision"
    return str(action)


def reason_text(action):
    # The reason's display text, or "" for a non-deprovision action.
    return _REASON_TEXT.get(action, "")


def action_for_reason_text(text):
    # Reverse lookup for the reason drop-down: the GAM word for the text the
    # person picked. Falls back to the default reason if the text is not
    # recognised, so a stale drop-down value can never produce a bad action.
    for word, shown in DEPROVISION_REASONS:
        if shown == text:
            return word
    return DEFAULT_DEPROVISION_ACTION


def extra_gam_args(action):
    # Arguments that must follow "action <word>" on the GAM command line.
    # Only deprovisioning needs any (the acknowledgement flag).
    if is_deprovision(action):
        return (ACKNOWLEDGE_ARG,)
    return ()


def typed_confirmation_ok(typed):
    # True only when the person typed the confirmation word exactly
    # (surrounding spaces are forgiven - a trailing space from a paste should
    # not lock them out - but the letters must match, including case).
    return typed.strip() == CONFIRM_WORD

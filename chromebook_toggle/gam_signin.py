# chromebook_toggle/gam_signin.py
#
# Script:   gam_signin.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The facts behind the "GAM sign-in" window, so people who cannot open a
#   command line (or run "gam oauth update") can renew GAM's Google sign-in
#   from inside this app. Ported from the sibling GAMGUI project's gam_setup.py
#   and trimmed to the two sign-in commands:
#
#       gam oauth update [admin <email>]   renew / re-approve an EXISTING sign-in
#       gam oauth create [<email>]         the first sign-in (no oauth2.txt yet)
#       gam oauth info                     read-only: who is GAM signed in as?
#
#   Both oauth commands open the person's web browser and (for update/create)
#   show GAM's numbered scope list, asking for a keystroke. That needs a real
#   keyboard and window, so they run in their OWN console window (never in the
#   app's output), exactly as GAMGUI does.
#
# What was checked against a real GAM 7.51.00 (not assumed):
#   - "gam oauth info" with no sign-in: exit code 51 and a line
#       "Client OAuth2 File: <path>\oauth2.txt, Not Shown: Does not exist".
#   - "gam oauth update" with no sign-in: exit 51, "... Not Updated: Does not
#       exist" - so the window must offer "create" in that case, not "update".
#   - "gam oauth create" shows the numbered scope list and ends with the prompt
#       "Please enter 0-57[a|r] or s|u|e|c:"; "c" continues to authorization.
#
# Notes:
#   Everything here is a pure function except check_signin() (runs gam once,
#   read-only) and windows_cmd_blocked() (reads two registry values) - and both
#   of those take the thing that does the real work as a parameter, so
#   tests\test_gam_signin.py runs them with stand-ins on any OS.

import os
import re
import shlex
import shutil
import subprocess

# Windows process-creation flags (spelled out so this works on every OS).
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000

# "gam oauth info" with no sign-in yet (checked live, see header).
_NO_OAUTH = re.compile(r"Client OAuth2 File:.*(Does not exist|Not Found)|"
                       r"oauth2\.txt,? Not Found", re.I)
_ADMIN = re.compile(r"Google Workspace Admin:\s*(\S+@\S+)")

# A failed command that the sign-in window can fix: a missing, expired or
# too-narrow sign-in. (Ported from GAMGUI; "invalid_grant: Invalid email or
# User ID" is a wrong user name, NOT a sign-in problem, so it is excluded.)
_SIGNIN_ERRORS = re.compile(
    r"Reauthentication is needed|invalid_grant(?!: Invalid email)|"
    r"No Client Access allowed|There are no scopes authorized|"
    r"Client OAuth2 File:.*(Does not exist|Not Found)", re.I)

# A plain email address check (no spaces, quotes or a second @).
_EMAIL = re.compile(r"^[^@\s'\"]+@[^@\s'\"]+\.[^@\s'\"]+$")


def valid_email(text):
    # True if text looks like an email address. Used on the admin box so a typo
    # never reaches a command line.
    return bool(_EMAIL.match((text or "").strip()))


def signin_can_fix(output):
    # True when a failed GAM command's output is a sign-in problem the window
    # can fix. The GUI then offers to open it.
    return bool(_SIGNIN_ERRORS.search(output or ""))


def oauth_state(returncode, output):
    # Reads "gam oauth info" and returns (state, detail):
    #   ("ok", admin email)      GAM is signed in
    #   ("missing", "")          there is no sign-in file yet
    #   ("error", first line)    something else (no network, unreadable file...)
    found = _ADMIN.search(output or "")
    if found:
        return "ok", found.group(1)
    if _NO_OAUTH.search(output or ""):
        return "missing", ""
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    first = next((line for line in lines if line.upper().startswith("ERROR")),
                 lines[0] if lines else "")
    return "error", first[:200] or ("exit code %s" % returncode)


def info_argv(gam_path):
    # The read-only status command.
    return [gam_path, "oauth", "info"]


def step_argv(step, admin=""):
    # The words after gam for a button: "update" (renew) or "create" (first
    # sign-in). The admin email is optional for both.
    if admin and not valid_email(admin):
        raise ValueError("that does not look like an email address")
    admin = (admin or "").strip()
    if step == "update":
        return ["oauth", "update"] + (["admin", admin] if admin else [])
    if step == "create":
        return ["oauth", "create"] + ([admin] if admin else [])
    raise ValueError("unknown step: " + str(step))


def check_signin(gam_path, run=subprocess.run, env=None):
    # Runs "gam oauth info" once (read-only, no prompts) and returns
    # oauth_state()'s answer. Never raises: a problem running gam is reported
    # as ("error", message) so the window can show it.
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace",
              "timeout": 60, "stdin": subprocess.DEVNULL}
    if env is not None:
        kwargs["env"] = env
    if os.name == "nt":
        # The app has no console of its own; without this a black window would
        # flash up each time gam runs.
        kwargs["creationflags"] = CREATE_NO_WINDOW
    try:
        done = run(info_argv(gam_path), **kwargs)
    except subprocess.TimeoutExpired:
        return "error", "GAM did not answer in time."
    except OSError as error:
        return "error", "Could not run GAM: %s" % error
    return oauth_state(done.returncode, (done.stdout or "") + "\n" + (done.stderr or ""))


# ---- opening GAM in its own window ----------------------------------------------
def windows_cmd_blocked(read_value=None):
    # True if an administrator has switched off the Windows Command Prompt
    # (the "Prevent access to the command prompt" policy, DisableCMD = 1 or 2).
    # When it is off, "cmd /k" cannot be used to keep GAM's window open, so
    # gam.exe is started in its own console directly instead.
    if read_value is None:
        read_value = _read_policy_value
    for hive in ("HKCU", "HKLM"):
        value = read_value(hive, r"Software\Policies\Microsoft\Windows\System", "DisableCMD")
        if isinstance(value, int) and value != 0:
            return True
    return False


def _read_policy_value(hive, key_path, name):
    # Reads one registry value; None if it is not there (or not Windows).
    try:
        import winreg
    except ImportError:
        return None
    root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        with winreg.OpenKey(root, key_path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


class LaunchPlan(object):
    # How to open a window: 'command' for subprocess.Popen, 'creationflags'
    # (Windows only), and whether the window stays open after GAM finishes
    # (then the person can read the result; otherwise the status check shows it).
    def __init__(self, command, creationflags=0, stays_open=True):
        self.command = command
        self.creationflags = creationflags
        self.stays_open = stays_open

    def __repr__(self):
        return "LaunchPlan(%r, %r, %r)" % (self.command, self.creationflags, self.stays_open)


def _applescript_text(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def launch_plan(argv, title, system, cfg_dir="", which=None, cmd_blocked=False):
    # The command that opens a NEW terminal window running argv (gam and its
    # words), or None when this system has no terminal the app knows.
    #   argv       full command, gam first
    #   system     platform.system(): "Windows", "Darwin" or "Linux"
    #   cfg_dir    the GAM config folder (GAMCFGDIR); a macOS Terminal window
    #              does NOT inherit this app's environment
    #   cmd_blocked  True if the Command Prompt is switched off on this PC
    if system == "Windows":
        plain = all(re.match(r"^[A-Za-z0-9_.:\\/@+=-]+$", a) for a in argv)
        if cmd_blocked or not plain:
            # No cmd.exe: start gam.exe straight into a new console window. The
            # window closes when GAM finishes; the sign-in window's status
            # check shows the outcome.
            return LaunchPlan(list(argv), CREATE_NEW_CONSOLE, stays_open=False)
        # 'start' opens a console and 'cmd /k' keeps it open after gam exits.
        return LaunchPlan(["cmd", "/c", "start", title, "cmd", "/k"] + list(argv))
    shell = " ".join(shlex.quote(a) for a in argv)
    if cfg_dir:
        shell = "export GAMCFGDIR=%s; %s" % (shlex.quote(cfg_dir), shell)
    shell += "; echo; read -r -p 'Press Enter to close this window...' _"
    if system == "Darwin":
        return LaunchPlan(["osascript",
                           "-e", 'tell application "Terminal" to do script %s' % _applescript_text(
                               "bash -c " + shlex.quote(shell)),
                           "-e", 'tell application "Terminal" to activate'])
    if system == "Linux":
        if which is None:
            which = shutil.which
        for name, form in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]),
                           ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]), ("xterm", ["-e"])):
            if which(name):
                return LaunchPlan([name] + form + ["bash", "-c", shell])
    return None

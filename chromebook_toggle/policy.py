# chromebook_toggle/policy.py
#
# Script:   policy.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-11-2026
# Modified: 11-11-2026
# Version:  1.0
#
# Purpose:
#   Lets an ADMINISTRATOR turn the permanent Deprovision action on or off after
#   the app is installed, without uninstalling and reinstalling it. The setting
#   lives in a machine-wide place that only administrators can write, and it
#   OVERRIDES settings.ini:
#
#     Windows  HKLM\SOFTWARE\Policies\ChromebookToggle  AllowDeprovision (DWORD 1/0)
#              (the standard "Policies" location, so it can also be deployed
#              with Group Policy Preferences > Registry)
#     macOS    /Library/Preferences/com.gurugabe.chromebooktoggle.plist
#              key AllowDeprovision (boolean)
#     Linux    /etc/chromebooktoggle/policy.ini  [Settings] allow_deprovision
#
#   Ways to change it:
#     1. Run the program with a switch (this module's cli_main):
#          ChromebookToggle.exe --set-deprovision on      (or: off, clear)
#          ChromebookToggle.exe --deprovision-status
#        On Windows the switch asks for administrator approval by itself
#        (the normal UAC prompt); on macOS/Linux run it with sudo.
#     2. Edit the registry value / plist / file directly, or deploy it with
#        Group Policy / a configuration profile.
#     3. "clear" removes the policy so settings.ini decides again.
#   Reading is allowed for everybody; WRITING needs administrator rights. HKCU
#   (per-user registry) is deliberately NOT used: a standard user can write
#   there, which would let anybody switch the permanent action on.
#
# Notes:
#   Each platform's storage is a small "backend" class with the same three
#   methods (get / set / clear). They take their location as a parameter so the
#   unit tests exercise the REAL registry / plist / ini code against throw-away
#   locations instead of the machine's real policy.

import configparser
import os
import plistlib
import sys

WIN_KEY = r"SOFTWARE\Policies\ChromebookToggle"
WIN_VALUE = "AllowDeprovision"
MAC_PLIST = "/Library/Preferences/com.gurugabe.chromebooktoggle.plist"
MAC_KEY = "AllowDeprovision"
LINUX_FILE = "/etc/chromebooktoggle/policy.ini"

_TRUE_WORDS = ("1", "yes", "true", "on")
_FALSE_WORDS = ("0", "no", "false", "off")

SOURCE_POLICY = "machine policy"
SOURCE_SETTINGS = "settings.ini"


class PolicyError(Exception):
    # Something went wrong reading or writing the policy (message is for people).
    pass


class PolicyPermissionError(PolicyError):
    # The policy could not be written because administrator rights are needed.
    pass


def _as_bool(value):
    # Registry/plist/ini value -> True / False / None (not a recognisable yes/no,
    # which is treated as "no policy set" so a typo can never switch it ON).
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0 if value in (0, 1) else None
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    return None


# ---- Windows registry ----------------------------------------------------------
class WindowsBackend(object):
    def __init__(self, hive="HKLM", key_path=WIN_KEY, value_name=WIN_VALUE):
        self.hive, self.key_path, self.value_name = hive, key_path, value_name

    def _root(self, winreg):
        return winreg.HKEY_LOCAL_MACHINE if self.hive == "HKLM" else winreg.HKEY_CURRENT_USER

    def get(self):
        import winreg
        # KEY_WOW64_64KEY: always the 64-bit registry view, where the installer
        # and Group Policy write, whatever bitness the program is.
        try:
            with winreg.OpenKey(self._root(winreg), self.key_path, 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                return _as_bool(winreg.QueryValueEx(key, self.value_name)[0])
        except FileNotFoundError:
            return None
        except OSError as error:
            raise PolicyError("Could not read the registry policy: %s" % error) from error

    def set(self, value):
        import winreg
        try:
            with winreg.CreateKeyEx(self._root(winreg), self.key_path, 0,
                                    winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                winreg.SetValueEx(key, self.value_name, 0, winreg.REG_DWORD, 1 if value else 0)
        except PermissionError as error:
            raise PolicyPermissionError("Administrator rights are needed to change this setting.") from error
        except OSError as error:
            raise PolicyError("Could not write the registry policy: %s" % error) from error

    def clear(self):
        import winreg
        try:
            with winreg.OpenKey(self._root(winreg), self.key_path, 0,
                                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                winreg.DeleteValue(key, self.value_name)
        except FileNotFoundError:
            return  # nothing to remove
        except PermissionError as error:
            raise PolicyPermissionError("Administrator rights are needed to change this setting.") from error
        except OSError as error:
            raise PolicyError("Could not remove the registry policy: %s" % error) from error


# ---- macOS property list -------------------------------------------------------
class MacBackend(object):
    def __init__(self, path=MAC_PLIST, key=MAC_KEY):
        self.path, self.key = path, key

    def _load(self):
        try:
            with open(self.path, "rb") as handle:
                data = plistlib.load(handle)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, plistlib.InvalidFileException, ValueError) as error:
            raise PolicyError("Could not read %s: %s" % (self.path, error)) from error

    def _save(self, data):
        try:
            with open(self.path, "wb") as handle:
                plistlib.dump(data, handle)
        except PermissionError as error:
            raise PolicyPermissionError("Administrator rights are needed (run it with sudo).") from error
        except OSError as error:
            raise PolicyError("Could not write %s: %s" % (self.path, error)) from error

    def get(self):
        return _as_bool(self._load().get(self.key))

    def set(self, value):
        data = self._load()
        data[self.key] = bool(value)
        self._save(data)

    def clear(self):
        data = self._load()
        if self.key in data:
            del data[self.key]
            self._save(data)


# ---- Linux ini file ---------------------------------------------------------------
class LinuxBackend(object):
    def __init__(self, path=LINUX_FILE):
        self.path = path

    def _parser(self):
        parser = configparser.ConfigParser()
        try:
            parser.read(self.path, encoding="ascii")
        except (configparser.Error, UnicodeError, OSError) as error:
            raise PolicyError("Could not read %s: %s" % (self.path, error)) from error
        return parser

    def get(self):
        return _as_bool(self._parser().get("Settings", "allow_deprovision", fallback=None))

    def _save(self, parser):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="ascii") as handle:
                parser.write(handle)
        except PermissionError as error:
            raise PolicyPermissionError("Administrator rights are needed (run it with sudo).") from error
        except OSError as error:
            raise PolicyError("Could not write %s: %s" % (self.path, error)) from error

    def set(self, value):
        parser = self._parser()
        if not parser.has_section("Settings"):
            parser.add_section("Settings")
        parser.set("Settings", "allow_deprovision", "true" if value else "false")
        self._save(parser)

    def clear(self):
        parser = self._parser()
        if parser.has_option("Settings", "allow_deprovision"):
            parser.remove_option("Settings", "allow_deprovision")
            self._save(parser)


def default_backend(system=None):
    # The real, machine-wide store for this operating system.
    system = system or sys.platform
    if system.startswith("win"):
        return WindowsBackend()
    if system == "darwin":
        return MacBackend()
    return LinuxBackend()


def describe_location(system=None):
    # Where the policy lives, for messages.
    system = system or sys.platform
    if system.startswith("win"):
        return "HKEY_LOCAL_MACHINE\\" + WIN_KEY + "  (value " + WIN_VALUE + ")"
    if system == "darwin":
        return MAC_PLIST + "  (key " + MAC_KEY + ")"
    return LINUX_FILE + "  (allow_deprovision)"


def read_policy(backend=None):
    # True / False when a policy is set, None when not. A problem reading it
    # counts as "not set" (the program must still start); the Deprovision
    # switch then falls back to settings.ini, which defaults to OFF.
    try:
        return (backend or default_backend()).get()
    except PolicyError:
        return None
    except Exception:  # last resort: never let a policy problem stop the app starting
        return None


def apply_to_settings(settings, backend=None):
    # Lays the policy over the settings read from settings.ini: when a policy is
    # set it wins, and settings["deprovision_source"] says where the answer came
    # from. Returns the same dict.
    value = read_policy(backend)
    if value is None:
        settings["deprovision_source"] = SOURCE_SETTINGS
    else:
        settings["allow_deprovision"] = value
        settings["deprovision_source"] = SOURCE_POLICY
    return settings


# ---- the command-line switches -------------------------------------------------------
SWITCHES = ("--set-deprovision", "--deprovision-status")


def is_policy_command(argv):
    return any(arg in SWITCHES for arg in argv[1:])


def _usage():
    return ("Chromebook Toggle Tool - Deprovision switch\n\n"
            "  --set-deprovision on      turn the permanent Deprovision action ON for this PC\n"
            "  --set-deprovision off     turn it OFF for this PC\n"
            "  --set-deprovision clear   remove the policy (settings.ini decides again)\n"
            "  --deprovision-status      show the current setting\n\n"
            "Changing it needs administrator rights.")


def status_text(backend=None, system=None, settings_value=None):
    value = read_policy(backend)
    where = describe_location(system)
    if value is None:
        extra = "" if settings_value is None else (
            " settings.ini currently says: %s." % ("on" if settings_value else "off"))
        return "No machine policy is set (%s).%s" % (where, extra)
    return "Deprovision is %s by machine policy (%s)." % ("ON" if value else "OFF", where)


def cli_main(argv, backend=None, system=None, say=print, elevate=None):
    # Handles --set-deprovision / --deprovision-status. Returns the exit code
    # (0 = done). 'say' shows a message; 'elevate' is called with argv when
    # Windows says administrator rights are needed (it re-runs this program
    # with the UAC prompt and returns True if it did).
    args = list(argv[1:])
    elevated_run = "--elevated" in args
    args = [a for a in args if a != "--elevated"]
    backend = backend or default_backend(system)

    if args == ["--deprovision-status"]:
        say(status_text(backend, system))
        return 0
    if len(args) == 2 and args[0] == "--set-deprovision" and args[1].lower() in ("on", "off", "clear"):
        choice = args[1].lower()
        try:
            if choice == "clear":
                backend.clear()
            else:
                backend.set(choice == "on")
        except PolicyPermissionError as error:
            if elevate is not None and not elevated_run and elevate(argv):
                return 0  # the elevated copy will do it and report
            say("%s\n\nRun it again as an administrator (on Windows: right-click, Run as "
                "administrator; on macOS/Linux use sudo)." % error)
            return 3
        except PolicyError as error:
            say(str(error))
            return 2
        done = {"on": "Deprovision is now turned ON for everyone who uses this PC.",
                "off": "Deprovision is now turned OFF for everyone who uses this PC.",
                "clear": "The machine policy was removed. settings.ini decides again."}[choice]
        say(done + "\n\n" + status_text(backend, system) +
            "\nIt takes effect the next time the program is started.")
        return 0
    say(_usage())
    return 1


# ---- Windows plumbing (message boxes, UAC) ----------------------------------------------
def make_say(frozen=None):
    # Where messages go. The packaged Windows app has no console, so a message
    # box is used there; everywhere else the text is printed.
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if sys.platform.startswith("win") and (frozen or sys.stdout is None):
        def say(text):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Chromebook Toggle Tool", 0x40)
        return say
    return print


def elevate_windows(argv):
    # Re-runs this program through the Windows UAC prompt ("runas") with the
    # same switch plus --elevated. Returns True if Windows accepted the request.
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    frozen = getattr(sys, "frozen", False)
    exe = sys.executable
    pieces = [] if frozen else [os.path.abspath(argv[0])]
    pieces += [a for a in argv[1:] if a != "--elevated"] + ["--elevated"]
    params = " ".join('"%s"' % p if (" " in p or not p) else p for p in pieces)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return result > 32

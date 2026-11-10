# chromebook_toggle/update_posix.py
#
# Script:   update_posix.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   In-app updates on macOS and Linux (Windows uses update_apply.py). Nothing
#   to install: the app downloads the release file, checks its SHA-256
#   (updater.py), unpacks it, and hands a small bash script the job of
#   swapping the new copy in AFTER the app has closed, then reopening it.
#
#     macOS, ChromebookToggle.app   ChromebookToggle-<v>-macOS.zip -> ditto ->
#                                   codesign --verify -> swap the .app (old one
#                                   restored if the copy fails) -> open
#     Linux, portable folder        ChromebookToggle-<v>-Linux.tar.gz -> swap
#                                   the files, keeping settings.ini, state.ini
#                                   and Logs -> relaunch
#     Linux, .deb / .rpm            (in /opt, needs root) -> the app downloads
#                                   and verifies the package, then shows the
#                                   one sudo command to run - it never asks
#                                   for root itself
#
# Notes:
#   Ported from GAMGUI's gam_update.py, which has run in production on macOS
#   and Linux. This module only BUILDS the script text and the install
#   command; it does no downloading and starts nothing, so every piece is
#   testable on any OS (tests\test_update_posix.py). The linux script is also
#   executed for real in a scratch folder by the tests when bash is present.
#   The macOS script needs codesign/ditto/open and so can only be
#   syntax-checked here; it is exercised by the release workflow on a macOS
#   runner and by anyone using the macOS build.
#
#   Every script waits (up to 60 seconds) for the app's process to close
#   first - a running program's files must not be replaced - and writes a
#   timestamped log so a failed update can be diagnosed afterwards.

import shlex
import shutil

# Names inside a Linux portable folder that an update must keep.
KEEP_ON_UPDATE = ("settings.ini", "state.ini", "Logs")

_HEADER = """#!/bin/bash
# Chromebook Toggle Tool updater ({what}) - written by version {version}. It
# waits for the app (process {pid}) to close, installs the new version, and
# reopens it. Safe to delete afterwards. Log: {log}
LOG={log_q}
log() {{ echo "[$(date '+%m-%d-%Y %H:%M:%S')] $*" >> "$LOG"; }}
PID={pid}
# Wait up to 60 seconds for the app to close (its files must not be in use).
for i in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
if kill -0 "$PID" 2>/dev/null; then
    log "The app is still running - update cancelled"; exit 1
fi
"""


def detect_package_tool(which=shutil.which):
    # Which package manager installed (and will update) a /opt copy.
    for tool in ("apt", "dnf", "yum", "zypper"):
        if which(tool):
            return tool
    return "rpm"


def package_command(tool, path):
    # The one command an administrator runs to install a downloaded package.
    quoted = shlex.quote(path)
    return {"apt": "sudo apt install " + quoted,
            "dnf": "sudo dnf install " + quoted,
            "yum": "sudo yum install " + quoted,
            "zypper": "sudo zypper install " + quoted}.get(tool, "sudo rpm -U " + quoted)


def mac_update_script(pid, app, new_app, work, log, version):
    # Swaps /Applications/ChromebookToggle.app for the verified new copy. The
    # person's settings, logs and state live in ~/Library/Application Support
    # (never inside the app - see paths.py), so replacing the app loses
    # nothing. If the signature check or the copy fails, the old app stays.
    q = shlex.quote
    return _HEADER.format(what="macOS", version=version, pid=int(pid), log=log, log_q=q(log)) + """APP={app}
NEW={new}
WORK={work}
log "updating $APP"
# The new app must pass Apple's signature check before it replaces anything.
if ! codesign --verify --deep --strict "$NEW" >> "$LOG" 2>&1; then
    log "new app failed the signature check - nothing changed"; open "$APP"; exit 1
fi
rm -rf "$APP.old"
if ! mv "$APP" "$APP.old"; then log "could not move the old app aside"; open "$APP"; exit 1; fi
if ditto "$NEW" "$APP"; then
    rm -rf "$APP.old"; log "updated to the new version"
else
    rm -rf "$APP"; mv "$APP.old" "$APP"; log "copy failed - old version restored"
fi
rm -rf "$WORK"
open "$APP"
""".format(app=q(app), new=q(new_app), work=q(work))


def linux_update_script(pid, folder, new_folder, work, log, version):
    # Replaces the files of a portable Linux copy with the verified new ones,
    # keeping the person's settings, state and logs. The old files are moved
    # aside first and put back if anything fails.
    q = shlex.quote
    keep = " ".join(KEEP_ON_UPDATE)
    return _HEADER.format(what="Linux", version=version, pid=int(pid), log=log, log_q=q(log)) + """DIR={folder}
NEW={new}
WORK={work}
OLD="$WORK/old"
log "updating $DIR"
mkdir -p "$OLD" || {{ log "cannot create $OLD"; exit 1; }}
# Move the old files aside - except the person's settings, state and logs.
for item in "$DIR"/* "$DIR"/.[!.]*; do
    [ -e "$item" ] || continue
    case "$(basename "$item")" in {keep_case}) continue ;; esac
    mv "$item" "$OLD/" || {{ log "could not move $item"; FAIL=1; break; }}
done
if [ -z "$FAIL" ]; then
    for item in "$NEW"/* "$NEW"/.[!.]*; do
        [ -e "$item" ] || continue
        case "$(basename "$item")" in {keep_case}) continue ;; esac
        cp -Rp "$item" "$DIR/" || {{ log "could not copy $item"; FAIL=1; break; }}
    done
fi
if [ -n "$FAIL" ]; then
    log "update failed - putting the old version back"
    for item in "$OLD"/* "$OLD"/.[!.]*; do
        [ -e "$item" ] || continue
        rm -rf "$DIR/$(basename "$item")"; mv "$item" "$DIR/"
    done
else
    log "updated to the new version (kept: {keep})"
fi
rm -rf "$WORK"
nohup "$DIR/ChromebookToggle" > /dev/null 2>&1 &
""".format(folder=q(folder), new=q(new_folder), work=q(work), keep=keep,
           keep_case="|".join(KEEP_ON_UPDATE))

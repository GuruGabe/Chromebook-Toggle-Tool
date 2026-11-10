# chromebook_toggle/updater.py
#
# Script:   updater.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The "find out whether there is a newer release, and fetch it safely" half
#   of the self-updater. It asks GitHub for the latest release, decides
#   whether it is newer than the running version, works out HOW this copy of
#   the app is installed (so the right update method is chosen), and
#   downloads the right file - refusing to hand anything on unless its
#   SHA-256 matches the checksum published in the release notes.
#   update_apply.py is the other half: it swaps the files in.
#
# Notes:
#   WHY PURE PYTHON, NOT POWERSHELL. GAMGUI's Windows updater is a
#   PowerShell script. That cannot be used here: standard users on the PCs
#   this tool targets have PowerShell blocked, and launching a script with
#   -ExecutionPolicy Bypass is exactly the kind of thing security tooling
#   refuses. Everything here uses only the Python standard library.
#
#   SAFETY RULES (each one is covered by tests\test_updater.py):
#     - Nothing is installed unless the download's SHA-256 equals the value
#       published in the release notes. No published checksum = no update.
#     - Only https is used, except plain http to THIS PC for testing.
#       A redirect may never downgrade https to http or leave GitHub.
#     - The zip/tar is extracted by code that refuses any member whose path
#       would land outside the destination folder (absolute paths, "..",
#       links), and that caps size and file count against zip bombs.
#     - Every network or file problem is raised as the one exception type
#       UpdateError with a message a non-technical person can act on, so the
#       GUI needs a single except clause and a background thread can never
#       die silently (see gam_runner.py's CALLER OBLIGATION notes).
#
#   HONEST LIMIT: the checksum comes from the same GitHub release as the
#   file, so it protects against a corrupt or truncated download and
#   against a tampered file, but not against someone who has taken over the
#   GitHub account itself (they could change both). Windows code signing
#   would close that gap; this free tool deliberately does not use paid
#   signing certificates.

import collections
import dataclasses
import hashlib
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import version

# Limits against a hostile or broken download. The real assets are about
# 14 MB, so these are generous but still finite.
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
MAX_EXTRACT_BYTES = 800 * 1024 * 1024
MAX_EXTRACT_FILES = 20000
MAX_API_BYTES = 2 * 1024 * 1024

# Hosts a release asset may legitimately come from (GitHub serves downloads
# from github.com and redirects to githubusercontent.com hosts).
_GITHUB_HOST_SUFFIXES = ("github.com", "githubusercontent.com")
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")

# owner/repo: letters, digits, dot, underscore, hyphen, one slash.
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(Exception):
    # The one exception type this module raises on purpose. The message is
    # written for the person reading the dialog, not for a developer.
    pass


# ---- versions ---------------------------------------------------------------
def parse_version(text):
    # "v1.4", "1.4" and "1.4.2" -> (1, 4) / (1, 4) / (1, 4, 2). Any text
    # with no digits at all -> (0,), which is older than every real release,
    # so a garbled tag can never be offered as an "update".
    numbers = re.findall(r"\d+", str(text))
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer(candidate, current):
    # True when 'candidate' is a higher version than 'current'. The two are
    # padded to the same length first, so 1.4 and 1.4.0 compare as EQUAL
    # (plain tuple comparison would call 1.4.0 newer).
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return a > b


def version_from_tag(tag):
    # "v1.4" -> "1.4". Asset file names use the bare number.
    tag = str(tag).strip()
    return tag[1:] if tag[:1] in ("v", "V") else tag


# ---- where releases come from -------------------------------------------------
def _host_of(url):
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _is_loopback_url(url):
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "http" and _host_of(url) in _LOOPBACK_HOSTS


def _is_github_url(url):
    host = _host_of(url)
    return (urllib.parse.urlparse(url).scheme == "https"
            and any(host == s or host.endswith("." + s) for s in _GITHUB_HOST_SUFFIXES))


def api_base_is_acceptable(api_base):
    # The update server address must be https (GitHub itself, or a mirror
    # such as a GitHub Enterprise server). Plain http is allowed ONLY to
    # this same PC, which is what the tests use.
    parsed = urllib.parse.urlparse(api_base)
    if _is_loopback_url(api_base):
        return True
    return parsed.scheme == "https" and bool(parsed.hostname)


def url_is_allowed(url, api_base):
    # Whether a download or redirect target is acceptable, given the API
    # address this run started from:
    #   - a test run against this PC may only talk to this PC;
    #   - otherwise it must be https and either on GitHub's own hosts or on
    #     the very same host as the (custom) API address.
    if _is_loopback_url(api_base):
        return _is_loopback_url(url)
    if _is_github_url(url):
        return True
    return (urllib.parse.urlparse(url).scheme == "https"
            and bool(_host_of(url)) and _host_of(url) == _host_of(api_base))


def latest_release_url(repo, api_base="https://api.github.com"):
    if not _REPO_RE.match(str(repo)):
        raise UpdateError("The update source '%s' is not a valid GitHub owner/repo name." % repo)
    if not api_base_is_acceptable(api_base):
        raise UpdateError("The update server address '%s' is not allowed (it must be https)." % api_base)
    return api_base.rstrip("/") + "/repos/" + repo + "/releases/latest"


# ---- a release, as GitHub describes it ----------------------------------------
Asset = collections.namedtuple("Asset", "name url size")


@dataclasses.dataclass(frozen=True)
class Release:
    tag: str
    version: str
    name: str
    body: str
    html_url: str
    assets: dict  # asset name -> Asset


def parse_release(data):
    # Turns GitHub's JSON into a Release, checking every field it relies on
    # so a surprise from the server becomes an UpdateError, not a KeyError.
    if not isinstance(data, dict):
        raise UpdateError("GitHub's answer was not in the expected format.")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        raise UpdateError("GitHub did not report a release version.")
    assets = {}
    for item in data.get("assets") or []:
        if not isinstance(item, dict):
            continue
        name, url = item.get("name"), item.get("browser_download_url")
        if isinstance(name, str) and isinstance(url, str):
            size = item.get("size")
            assets[name] = Asset(name, url, size if isinstance(size, int) else 0)
    return Release(
        tag=tag.strip(),
        version=version_from_tag(tag),
        name=str(data.get("name") or tag),
        body=str(data.get("body") or ""),
        html_url=str(data.get("html_url") or ""),
        assets=assets,
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    # Follows redirects (GitHub sends downloads to a different host) but only
    # to addresses url_is_allowed() accepts - so a redirect can never
    # downgrade https to http or send the download somewhere that is not
    # GitHub.
    def __init__(self, api_base):
        super().__init__()
        self._api_base = api_base

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_is_allowed(newurl, self._api_base):
            raise UpdateError("The download was redirected to an address that is not allowed.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, api_base, timeout, opener=None):
    # One place that opens a URL, with the headers GitHub requires (it
    # rejects requests with no User-Agent) and the safe redirect rule.
    request = urllib.request.Request(url, headers={
        "User-Agent": "ChromebookToggle-Updater/" + version.APP_VERSION,
        "Accept": "application/vnd.github+json, application/octet-stream",
    })
    if opener is None:
        opener = urllib.request.build_opener(_SafeRedirectHandler(api_base))
    return opener.open(request, timeout=timeout)


def _friendly(error):
    # A short, plain explanation for a network failure.
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 404:
            return "No release was found at that address (HTTP 404)."
        if error.code in (403, 429):
            return "GitHub is limiting requests from this network right now (HTTP %d). Try again later." % error.code
        return "GitHub answered with an error (HTTP %d)." % error.code
    if isinstance(error, urllib.error.URLError):
        return "Could not reach GitHub (%s). Check the internet connection." % (error.reason,)
    return "Network problem: %s" % (error,)


def fetch_latest_release(repo, api_base="https://api.github.com", timeout=12, opener=None):
    # Asks GitHub for the newest published release of 'repo'. Raises
    # UpdateError (never anything else) if it cannot.
    url = latest_release_url(repo, api_base)
    try:
        with _open(url, api_base, timeout, opener) as response:
            raw = response.read(MAX_API_BYTES + 1)
    except UpdateError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise UpdateError(_friendly(error)) from error
    if len(raw) > MAX_API_BYTES:
        raise UpdateError("GitHub's answer was unexpectedly large, so it was ignored.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise UpdateError("GitHub's answer could not be read.") from error
    return parse_release(data)


def published_sha256(body, asset_name):
    # The release notes carry a line "SHA-256 (<file name>):" followed by the
    # 64-character checksum (same line or the next one). Returns it in upper
    # case, or None if the notes do not publish one for that file.
    found = re.search(r"SHA-256 \(" + re.escape(asset_name) + r"\):\s*([0-9A-Fa-f]{64})", body or "")
    return found.group(1).upper() if found else None


def notes_for_display(body, max_lines=12):
    # The release notes minus the checksum lines (noise for a person), cut to
    # a reasonable length for a dialog.
    lines = []
    skip_next_hash = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("SHA-256 ("):
            skip_next_hash = not re.search(r"[0-9A-Fa-f]{64}", stripped)
            continue
        if skip_next_hash and re.fullmatch(r"[0-9A-Fa-f]{64}", stripped):
            skip_next_hash = False
            continue
        skip_next_hash = False
        lines.append(line.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    return "\n".join(lines)


# ---- which file does this install need? ---------------------------------------
KIND_SOURCE = "source"
KIND_WINDOWS_SETUP = "windows-setup"
KIND_WINDOWS_PORTABLE = "windows-portable"
KIND_WINDOWS_PROTECTED = "windows-protected"
KIND_MAC_APP = "mac-app"
KIND_LINUX_PORTABLE = "linux-portable"
KIND_LINUX_PACKAGE = "linux-package"
KIND_UNKNOWN = "unknown"

InstallInfo = collections.namedtuple("InstallInfo", "kind target scope")


def asset_name(kind, ver, package_tool=None):
    # The release file each kind of install needs. These names are what the
    # build workflow (.github/workflows/build-installers.yml) produces.
    if kind == KIND_WINDOWS_SETUP:
        return "ChromebookToggle-%s-Setup.exe" % ver
    if kind == KIND_WINDOWS_PORTABLE:
        return "ChromebookToggle-%s-Windows.zip" % ver
    if kind == KIND_MAC_APP:
        return "ChromebookToggle-%s-macOS.zip" % ver
    if kind == KIND_LINUX_PORTABLE:
        return "ChromebookToggle-%s-Linux.tar.gz" % ver
    if kind == KIND_LINUX_PACKAGE:
        if package_tool == "apt":
            return "chromebooktoggle_%s_amd64.deb" % ver
        return "chromebooktoggle-%s-1.x86_64.rpm" % ver
    return None


class CannotSelfUpdate(UpdateError):
    # Raised by make_plan() when this copy of the app simply cannot update
    # itself (run from source, in a protected folder, unknown layout). The GUI
    # treats it differently from a failure: it explains and offers to open
    # the Releases page so the person can update by hand.
    pass


UpdatePlan = collections.namedtuple("UpdatePlan", "kind target scope asset asset_name sha256")


def make_plan(info, release, package_tool=None):
    # Decides exactly what to download and how it will be installed for this
    # InstallInfo and this Release, or raises CannotSelfUpdate / UpdateError
    # saying why not. Pure: no network, no files.
    if info.kind == KIND_SOURCE:
        raise CannotSelfUpdate(
            "This copy is running from the source code, not from an installed app, so it does "
            "not update itself. Download the new version, or update the source (for example "
            "with git pull).")
    if info.kind == KIND_WINDOWS_PROTECTED:
        raise CannotSelfUpdate(
            "This copy is in a folder that standard users cannot change (%s), so it cannot "
            "update itself. Ask IT to install the new version." % info.target)
    if info.kind == KIND_UNKNOWN:
        raise CannotSelfUpdate(
            "This copy is installed in a way the updater does not recognise, so it cannot "
            "update itself. Download the new version by hand.")
    name = asset_name(info.kind, release.version, package_tool)
    asset = release.assets.get(name)
    if asset is None:
        raise UpdateError(
            "Version %s has been published, but it does not include the file this copy needs "
            "(%s). It may still be being built - try again later." % (release.version, name))
    sha = published_sha256(release.body, name)
    if not sha:
        raise UpdateError(
            "Version %s does not publish a checksum for %s, so it will not be installed "
            "automatically. Ask the publisher, or download and check it by hand." % (release.version, name))
    return UpdatePlan(info.kind, info.target, info.scope, asset, name, sha)


def same_path(a, b):
    # Whether two folder paths are the same place (case-insensitive on
    # Windows, trailing slashes ignored).
    na = os.path.normcase(os.path.abspath(a)).rstrip("\\/")
    nb = os.path.normcase(os.path.abspath(b)).rstrip("\\/")
    return na == nb


def mac_bundle_path(executable):
    # /Applications/ChromebookToggle.app/Contents/MacOS/ChromebookToggle
    #   -> /Applications/ChromebookToggle.app  (None if not inside a bundle)
    parts = os.path.abspath(executable).split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].endswith(".app") and parts[i + 1:i + 2] == ["Contents"]:
            return os.sep.join(parts[:i + 1]) or os.sep
    return None


def detect_install(system, executable, frozen, writable, registry=None):
    # Works out how this copy of the app is installed, which decides how it
    # can be updated.
    #   system     - sys.platform ("win32", "darwin", "linux")
    #   executable - the running program
    #   frozen     - True when running as the built app (not "python x.py")
    #   writable   - function(folder) -> bool, "can I create files there?"
    #   registry   - on Windows, {"scope": "machine"|"user", "location": path}
    #                from the installer's registry key, or None
    # Returns InstallInfo(kind, target, scope). 'target' is the folder (or
    # the .app) to replace; 'scope' is only used by windows-setup.
    if not frozen:
        return InstallInfo(KIND_SOURCE, None, None)
    folder = os.path.dirname(os.path.abspath(executable))
    if system.startswith("win"):
        if registry and registry.get("location") and same_path(folder, registry["location"]):
            # Put there by Setup.exe: update by running the new Setup.exe so
            # the Add/Remove Programs entry and version stay correct.
            return InstallInfo(KIND_WINDOWS_SETUP, folder, registry.get("scope"))
        if writable(folder):
            return InstallInfo(KIND_WINDOWS_PORTABLE, folder, None)
        return InstallInfo(KIND_WINDOWS_PROTECTED, folder, None)
    if system == "darwin":
        app = mac_bundle_path(executable)
        if app and writable(os.path.dirname(app)) and writable(app):
            return InstallInfo(KIND_MAC_APP, app, None)
        return InstallInfo(KIND_UNKNOWN, app, None)
    if system.startswith("linux"):
        if writable(folder):
            return InstallInfo(KIND_LINUX_PORTABLE, folder, None)
        return InstallInfo(KIND_LINUX_PACKAGE, folder, None)
    return InstallInfo(KIND_UNKNOWN, None, None)


def windows_registry_install():
    # What the Windows installer recorded, or None if this was not installed
    # by Setup.exe (or this is not Windows). Setup writes
    # SOFTWARE\ChromebookToggle (Version, InstallLocation) under HKLM for an
    # all-users install or HKCU for a just-me install. Both are checked, in
    # both registry views, and a registry problem simply means "not found".
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg
    except ImportError:
        return None
    views = (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0))
    for scope, root in (("user", winreg.HKEY_CURRENT_USER), ("machine", winreg.HKEY_LOCAL_MACHINE)):
        for view in views:
            try:
                with winreg.OpenKey(root, r"SOFTWARE\ChromebookToggle", 0, winreg.KEY_READ | view) as key:
                    location, _kind = winreg.QueryValueEx(key, "InstallLocation")
                    if location:
                        return {"scope": scope, "location": str(location)}
            except OSError:
                continue
    return None


# ---- downloading, verifying, unpacking ----------------------------------------
def sha256_of_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def download_asset(asset, dest_path, expected_sha256, api_base="https://api.github.com",
                   progress=None, timeout=30, opener=None):
    # Downloads 'asset' to dest_path and checks it against expected_sha256
    # (upper-case hex). The bytes go to dest_path + ".part" first and are only
    # renamed into place once the checksum matches - so a bad or interrupted
    # download can never be mistaken for a good one. 'progress' (optional) is
    # called as progress(bytes_so_far, total_bytes_or_0).
    if not expected_sha256:
        raise UpdateError(
            "This release does not publish a checksum for %s, so it will not be installed." % asset.name)
    if not url_is_allowed(asset.url, api_base):
        raise UpdateError("The download address for %s is not an allowed GitHub address." % asset.name)
    part_path = dest_path + ".part"
    digest = hashlib.sha256()
    done = 0
    try:
        with _open(asset.url, api_base, timeout, opener) as response:
            total = int(response.headers.get("Content-Length") or asset.size or 0)
            if total > MAX_DOWNLOAD_BYTES:
                raise UpdateError("The download is larger than expected, so it was stopped.")
            with open(part_path, "wb") as out:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("The download is larger than expected, so it was stopped.")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress:
                        progress(done, total)
    except UpdateError:
        _remove_quietly(part_path)
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        _remove_quietly(part_path)
        raise UpdateError("The download failed: " + _friendly(error)) from error
    if digest.hexdigest().upper() != expected_sha256.upper():
        _remove_quietly(part_path)
        raise UpdateError(
            "The downloaded file does not match the checksum published for it, so it was "
            "discarded and nothing was changed.")
    os.replace(part_path, dest_path)


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def safe_extract_zip(zip_path, dest):
    # Unpacks a zip into 'dest', refusing anything that would land outside it.
    # Returns the number of files written. Refused outright: absolute paths,
    # drive letters, ".." components, symbolic links, and archives that claim
    # too many files or too much data (zip bombs).
    dest_real = os.path.realpath(dest)
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as error:
        raise UpdateError("The downloaded update is not a valid zip file.") from error
    with archive:
        members = archive.infolist()
        if len(members) > MAX_EXTRACT_FILES:
            raise UpdateError("The update contains an unexpected number of files.")
        if sum(m.file_size for m in members) > MAX_EXTRACT_BYTES:
            raise UpdateError("The update would unpack to an unexpected size.")
        # Check every member BEFORE writing any of them.
        targets = []
        for member in members:
            name = member.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                raise UpdateError("The update contains an unsafe path (%s) and was rejected." % member.filename)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise UpdateError("The update contains a link (%s) and was rejected." % member.filename)
            target = os.path.realpath(os.path.join(dest, *name.split("/")))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise UpdateError("The update contains an unsafe path (%s) and was rejected." % member.filename)
            targets.append((member, target))
        written = 0
        for member, target in targets:
            if member.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as out:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            written += 1
    return written


def safe_extract_tar(archive_path, dest):
    # The same protection for the Linux .tar.gz (ported from GAMGUI's
    # gam_update.safe_extract_tar). Returns the number of members.
    dest_real = os.path.realpath(dest)
    try:
        tar = tarfile.open(archive_path, "r:gz")
    except (tarfile.TarError, OSError) as error:
        raise UpdateError("The downloaded update is not a valid archive.") from error
    with tar:
        members = tar.getmembers()
        if len(members) > MAX_EXTRACT_FILES or sum(m.size for m in members) > MAX_EXTRACT_BYTES:
            raise UpdateError("The update contains an unexpected number or size of files.")
        for m in members:
            target = os.path.realpath(os.path.join(dest, m.name))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise UpdateError("The update contains an unsafe path (%s) and was rejected." % m.name)
            if m.issym() or m.islnk():
                link = os.path.realpath(os.path.join(os.path.dirname(target), m.linkname))
                if not link.startswith(dest_real + os.sep):
                    raise UpdateError("The update contains an unsafe link (%s) and was rejected." % m.name)
            if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                raise UpdateError("The update contains an unexpected item (%s) and was rejected." % m.name)
        tar.extractall(dest, members=members)
    return len(members)

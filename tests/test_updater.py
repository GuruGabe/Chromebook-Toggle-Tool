# tests/test_updater.py
# ASCII only. Tests chromebook_toggle/updater.py - finding a newer release,
# deciding how this copy is installed, and downloading/unpacking the update
# safely. Network code is exercised against a tiny web server started on THIS
# PC (127.0.0.1), standing in for GitHub, so no test ever touches the internet.
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import zipfile

from chromebook_toggle import updater
from tests import helpers
from tests.helpers import FakeGitHub as _FakeGitHub


class _ServerCase(unittest.TestCase):
    # Starts the stand-in GitHub (tests/helpers.py) for each test and stops it
    # afterwards.
    def setUp(self):
        self.server, self.base = helpers.start_server()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        helpers.stop_server(self.server)
        self.tmp.cleanup()

    def release_json(self, assets=(), tag="v9.9", body="notes"):
        return json.dumps({
            "tag_name": tag, "name": tag, "body": body,
            "html_url": "https://github.com/x/y/releases/tag/" + tag,
            "assets": [{"name": n, "browser_download_url": self.base + p, "size": s}
                       for n, p, s in assets],
        }).encode("utf-8")


# ---- versions ---------------------------------------------------------------
class TestVersions(unittest.TestCase):

    def test_parse_version_accepts_a_leading_v(self):
        self.assertEqual(updater.parse_version("v1.4"), (1, 4))
        self.assertEqual(updater.parse_version("1.4.2"), (1, 4, 2))

    def test_garbage_is_older_than_everything(self):
        self.assertEqual(updater.parse_version("latest"), (0,))
        self.assertFalse(updater.is_newer("latest", "1.0"))

    def test_is_newer_compares_numerically_not_as_text(self):
        self.assertTrue(updater.is_newer("1.10", "1.9"))
        self.assertTrue(updater.is_newer("v1.4", "1.3"))
        self.assertFalse(updater.is_newer("1.3", "1.4"))

    def test_equal_versions_are_not_newer_even_with_a_trailing_zero(self):
        self.assertFalse(updater.is_newer("1.4", "1.4"))
        self.assertFalse(updater.is_newer("1.4.0", "1.4"))
        self.assertFalse(updater.is_newer("1.4", "1.4.0"))
        self.assertTrue(updater.is_newer("1.4.1", "1.4"))

    def test_version_from_tag(self):
        self.assertEqual(updater.version_from_tag("v1.4"), "1.4")
        self.assertEqual(updater.version_from_tag("1.4"), "1.4")


# ---- addresses --------------------------------------------------------------
class TestAddresses(unittest.TestCase):

    def test_default_address(self):
        self.assertEqual(
            updater.latest_release_url("GuruGabe/Chromebook-Toggle-Tool"),
            "https://api.github.com/repos/GuruGabe/Chromebook-Toggle-Tool/releases/latest")

    def test_bad_repo_names_are_refused(self):
        for repo in ("", "noslash", "a/b/c", "a b/c", "a/b;rm", "../x/y", "a/b?x=1"):
            with self.assertRaises(updater.UpdateError, msg=repo):
                updater.latest_release_url(repo)

    def test_plain_http_is_refused_except_to_this_pc(self):
        with self.assertRaises(updater.UpdateError):
            updater.latest_release_url("a/b", "http://api.github.com")
        with self.assertRaises(updater.UpdateError):
            updater.latest_release_url("a/b", "http://evil.example.com")
        self.assertIn("127.0.0.1", updater.latest_release_url("a/b", "http://127.0.0.1:8000"))

    def test_download_hosts(self):
        base = "https://api.github.com"
        self.assertTrue(updater.url_is_allowed("https://github.com/o/r/releases/download/v1/a.zip", base))
        self.assertTrue(updater.url_is_allowed("https://objects.githubusercontent.com/x", base))
        self.assertTrue(updater.url_is_allowed("https://release-assets.githubusercontent.com/x", base))
        self.assertFalse(updater.url_is_allowed("http://github.com/x", base))
        self.assertFalse(updater.url_is_allowed("https://github.com.evil.example/x", base))
        self.assertFalse(updater.url_is_allowed("https://evilgithub.com/x", base))
        self.assertFalse(updater.url_is_allowed("https://example.com/x", base))

    def test_custom_https_mirror_may_serve_its_own_downloads(self):
        base = "https://git.example.org/api/v3"
        self.assertTrue(updater.url_is_allowed("https://git.example.org/dl/a.zip", base))
        self.assertFalse(updater.url_is_allowed("https://other.example.org/dl/a.zip", base))

    def test_a_test_run_against_this_pc_may_only_talk_to_this_pc(self):
        base = "http://127.0.0.1:9"
        self.assertTrue(updater.url_is_allowed("http://127.0.0.1:9/a", base))
        self.assertFalse(updater.url_is_allowed("https://github.com/a", base))


# ---- release JSON, checksums, notes -----------------------------------------
class TestReleaseParsing(unittest.TestCase):

    def test_a_normal_release_is_parsed(self):
        release = updater.parse_release({
            "tag_name": "v1.5", "name": "1.5", "body": "hello", "html_url": "https://x",
            "assets": [{"name": "a.zip", "browser_download_url": "https://github.com/a.zip", "size": 10}],
        })
        self.assertEqual((release.tag, release.version), ("v1.5", "1.5"))
        self.assertEqual(release.assets["a.zip"].size, 10)

    def test_missing_tag_is_an_update_error(self):
        for bad in ({}, {"tag_name": ""}, {"tag_name": 5}, [], "text", None):
            with self.assertRaises(updater.UpdateError, msg=repr(bad)):
                updater.parse_release(bad)

    def test_malformed_assets_are_skipped_not_fatal(self):
        release = updater.parse_release({
            "tag_name": "v1", "assets": [None, "x", {"name": 1}, {"name": "ok", "browser_download_url": "https://github.com/ok"}]})
        self.assertEqual(list(release.assets), ["ok"])


class TestChecksums(unittest.TestCase):
    HASH = "AB" * 32

    def test_checksum_on_the_next_line(self):
        body = "Notes\n\nSHA-256 (ChromebookToggle-1.5-Windows.zip):\n" + self.HASH + "\n"
        self.assertEqual(updater.published_sha256(body, "ChromebookToggle-1.5-Windows.zip"), self.HASH)

    def test_checksum_on_the_same_line_and_lowercase(self):
        body = "SHA-256 (a.zip): " + self.HASH.lower()
        self.assertEqual(updater.published_sha256(body, "a.zip"), self.HASH)

    def test_no_checksum_for_that_file_gives_none(self):
        body = "SHA-256 (other.zip):\n" + self.HASH
        self.assertIsNone(updater.published_sha256(body, "a.zip"))
        self.assertIsNone(updater.published_sha256("", "a.zip"))
        self.assertIsNone(updater.published_sha256(None, "a.zip"))

    def test_a_short_or_non_hex_value_is_not_accepted(self):
        self.assertIsNone(updater.published_sha256("SHA-256 (a.zip):\n" + "AB" * 10, "a.zip"))
        self.assertIsNone(updater.published_sha256("SHA-256 (a.zip):\n" + "ZZ" * 32, "a.zip"))

    def test_a_file_name_with_regex_characters_is_matched_literally(self):
        body = "SHA-256 (a+b.zip):\n" + self.HASH
        self.assertEqual(updater.published_sha256(body, "a+b.zip"), self.HASH)
        self.assertIsNone(updater.published_sha256(body, "aab.zip"))

    def test_notes_for_display_drops_checksum_lines(self):
        body = ("Fixes a bug.\n\nSHA-256 (a.zip):\n" + self.HASH
                + "\nSHA-256 (b.exe): " + self.HASH + "\n")
        shown = updater.notes_for_display(body)
        self.assertEqual(shown, "Fixes a bug.")
        self.assertNotIn(self.HASH, shown)

    def test_notes_for_display_is_trimmed_to_a_dialog_sized_length(self):
        shown = updater.notes_for_display("\n".join("line %d" % i for i in range(40)), max_lines=5)
        self.assertEqual(shown.splitlines()[-1], "...")
        self.assertEqual(len(shown.splitlines()), 6)


# ---- which file for which install -------------------------------------------
class TestAssetNames(unittest.TestCase):

    def test_names_match_what_the_build_workflow_produces(self):
        self.assertEqual(updater.asset_name(updater.KIND_WINDOWS_SETUP, "1.5"), "ChromebookToggle-1.5-Setup.exe")
        self.assertEqual(updater.asset_name(updater.KIND_WINDOWS_PORTABLE, "1.5"), "ChromebookToggle-1.5-Windows.zip")
        self.assertEqual(updater.asset_name(updater.KIND_MAC_APP, "1.5"), "ChromebookToggle-1.5-macOS.zip")
        self.assertEqual(updater.asset_name(updater.KIND_LINUX_PORTABLE, "1.5"), "ChromebookToggle-1.5-Linux.tar.gz")
        self.assertEqual(updater.asset_name(updater.KIND_LINUX_PACKAGE, "1.5", "apt"), "chromebooktoggle_1.5_amd64.deb")
        self.assertEqual(updater.asset_name(updater.KIND_LINUX_PACKAGE, "1.5", "dnf"), "chromebooktoggle-1.5-1.x86_64.rpm")

    def test_kinds_with_no_download_have_no_name(self):
        for kind in (updater.KIND_SOURCE, updater.KIND_WINDOWS_PROTECTED, updater.KIND_UNKNOWN):
            self.assertIsNone(updater.asset_name(kind, "1.5"))


class TestMakePlan(unittest.TestCase):
    HASH = "CD" * 32

    def release(self, with_asset=True, with_hash=True):
        name = "ChromebookToggle-1.5-Windows.zip"
        assets = {name: updater.Asset(name, "https://github.com/x", 9)} if with_asset else {}
        body = ("SHA-256 (%s):\n%s\n" % (name, self.HASH)) if with_hash else "no checksum here"
        return updater.Release("v1.5", "1.5", "1.5", body, "https://x", assets)

    def info(self, kind, target="T", scope=None):
        return updater.InstallInfo(kind, target, scope)

    def test_a_portable_windows_copy_gets_the_zip_and_its_checksum(self):
        plan = updater.make_plan(self.info(updater.KIND_WINDOWS_PORTABLE), self.release())
        self.assertEqual(plan.asset_name, "ChromebookToggle-1.5-Windows.zip")
        self.assertEqual(plan.sha256, self.HASH)
        self.assertEqual(plan.asset.size, 9)

    def test_copies_that_cannot_update_themselves_say_so_with_the_special_error(self):
        for kind in (updater.KIND_SOURCE, updater.KIND_WINDOWS_PROTECTED, updater.KIND_UNKNOWN):
            with self.assertRaises(updater.CannotSelfUpdate, msg=kind):
                updater.make_plan(self.info(kind), self.release())

    def test_cannot_self_update_is_still_an_update_error(self):
        # So a caller with a single "except UpdateError" is still covered.
        self.assertTrue(issubclass(updater.CannotSelfUpdate, updater.UpdateError))

    def test_a_release_still_being_built_is_a_plain_update_error(self):
        with self.assertRaises(updater.UpdateError) as raised:
            updater.make_plan(self.info(updater.KIND_WINDOWS_PORTABLE), self.release(with_asset=False))
        self.assertNotIsInstance(raised.exception, updater.CannotSelfUpdate)
        self.assertIn("ChromebookToggle-1.5-Windows.zip", str(raised.exception))

    def test_no_published_checksum_means_no_plan(self):
        with self.assertRaises(updater.UpdateError) as raised:
            updater.make_plan(self.info(updater.KIND_WINDOWS_PORTABLE), self.release(with_hash=False))
        self.assertIn("checksum", str(raised.exception))


class TestDetectInstall(unittest.TestCase):

    def always(self, folder):
        return True

    def never(self, folder):
        return False

    def test_not_frozen_is_a_source_run(self):
        info = updater.detect_install("win32", "python.exe", False, self.always)
        self.assertEqual(info.kind, updater.KIND_SOURCE)

    def test_windows_registered_install_updates_via_setup(self):
        exe = os.path.join("C:\\", "Program Files", "ChromebookToggle", "ChromebookToggle.exe")
        registry = {"scope": "machine", "location": os.path.join("C:\\", "Program Files", "ChromebookToggle") + os.sep}
        info = updater.detect_install("win32", exe, True, self.never, registry)
        self.assertEqual((info.kind, info.scope), (updater.KIND_WINDOWS_SETUP, "machine"))

    def test_windows_registry_for_a_different_folder_does_not_apply(self):
        exe = os.path.join("D:\\", "Portable", "ChromebookToggle.exe")
        registry = {"scope": "user", "location": os.path.join("C:\\", "Somewhere", "Else")}
        info = updater.detect_install("win32", exe, True, self.always, registry)
        self.assertEqual(info.kind, updater.KIND_WINDOWS_PORTABLE)

    def test_windows_writable_unregistered_folder_is_portable(self):
        info = updater.detect_install("win32", os.path.join("D:\\", "CT", "ChromebookToggle.exe"), True, self.always)
        self.assertEqual(info.kind, updater.KIND_WINDOWS_PORTABLE)

    def test_windows_read_only_unregistered_folder_is_protected(self):
        info = updater.detect_install("win32", os.path.join("C:\\", "Program Files", "CT", "ChromebookToggle.exe"), True, self.never)
        self.assertEqual(info.kind, updater.KIND_WINDOWS_PROTECTED)

    def test_mac_app_bundle(self):
        exe = "/Applications/ChromebookToggle.app/Contents/MacOS/ChromebookToggle"
        info = updater.detect_install("darwin", exe, True, self.always)
        self.assertEqual((info.kind, os.path.basename(info.target)), (updater.KIND_MAC_APP, "ChromebookToggle.app"))
        self.assertEqual(updater.detect_install("darwin", exe, True, self.never).kind, updater.KIND_UNKNOWN)

    def test_mac_bundle_path_outside_a_bundle_is_none(self):
        self.assertIsNone(updater.mac_bundle_path("/usr/local/bin/ChromebookToggle"))

    def test_linux_portable_vs_package(self):
        exe = "/opt/ChromebookToggle/ChromebookToggle"
        self.assertEqual(updater.detect_install("linux", exe, True, self.always).kind, updater.KIND_LINUX_PORTABLE)
        self.assertEqual(updater.detect_install("linux", exe, True, self.never).kind, updater.KIND_LINUX_PACKAGE)

    def test_same_path_ignores_case_and_trailing_slash_on_windows(self):
        if os.name == "nt":
            self.assertTrue(updater.same_path("C:\\Foo\\Bar", "c:\\foo\\bar\\"))
        self.assertFalse(updater.same_path("C:\\Foo\\Bar", "C:\\Foo\\Baz"))


# ---- unpacking ---------------------------------------------------------------
def _make_zip(path, entries, symlink=None):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, "target")


class TestSafeExtractZip(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.zip = os.path.join(self.tmp.name, "u.zip")
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_normal_archive_is_unpacked(self):
        _make_zip(self.zip, [("ChromebookToggle/ChromebookToggle.exe", b"x"),
                             ("ChromebookToggle/_internal/a.dll", b"y")])
        self.assertEqual(updater.safe_extract_zip(self.zip, self.out), 2)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "ChromebookToggle", "_internal", "a.dll")))

    def test_dot_dot_paths_are_rejected_and_nothing_is_written(self):
        _make_zip(self.zip, [("ok.txt", b"1"), ("../evil.txt", b"2")])
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract_zip(self.zip, self.out)
        # Members are all checked before any is written.
        self.assertEqual(os.listdir(self.out), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.txt")))

    def test_absolute_and_drive_paths_are_rejected(self):
        for name in ("/etc/passwd", "C:/Windows/evil.txt", "C:\\evil.txt", "a/../../b"):
            _make_zip(self.zip, [(name, b"x")])
            with self.assertRaises(updater.UpdateError, msg=name):
                updater.safe_extract_zip(self.zip, self.out)

    def test_symbolic_links_are_rejected(self):
        _make_zip(self.zip, [("ok.txt", b"1")], symlink="link")
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract_zip(self.zip, self.out)

    def test_a_file_that_is_not_a_zip_is_an_update_error(self):
        with open(self.zip, "wb") as handle:
            handle.write(b"this is not a zip")
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract_zip(self.zip, self.out)


class TestSafeExtractTar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tar = os.path.join(self.tmp.name, "u.tar.gz")
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def _make(self, names):
        with tarfile.open(self.tar, "w:gz") as archive:
            for name in names:
                info = tarfile.TarInfo(name)
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))

    def test_a_normal_archive_is_unpacked(self):
        self._make(["ChromebookToggle/ChromebookToggle"])
        self.assertEqual(updater.safe_extract_tar(self.tar, self.out), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "ChromebookToggle", "ChromebookToggle")))

    def test_a_member_that_escapes_is_rejected(self):
        self._make(["../evil"])
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract_tar(self.tar, self.out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil")))


# ---- the network, against the stand-in GitHub --------------------------------
class TestFetchLatestRelease(_ServerCase):

    def test_a_release_is_fetched_and_parsed(self):
        _FakeGitHub.routes["/repos/o/r/releases/latest"] = (
            200, {}, self.release_json(assets=[("a.zip", "/dl/a.zip", 5)], tag="v2.0"))
        release = updater.fetch_latest_release("o/r", self.base)
        self.assertEqual(release.version, "2.0")
        self.assertIn("a.zip", release.assets)

    def test_no_release_published_is_a_friendly_error(self):
        with self.assertRaises(updater.UpdateError) as raised:
            updater.fetch_latest_release("o/r", self.base)
        self.assertIn("404", str(raised.exception))

    def test_rate_limit_is_a_friendly_error(self):
        _FakeGitHub.routes["/repos/o/r/releases/latest"] = (403, {}, b"limit")
        with self.assertRaises(updater.UpdateError) as raised:
            updater.fetch_latest_release("o/r", self.base)
        self.assertIn("limiting", str(raised.exception))

    def test_a_reply_that_is_not_json_is_an_update_error(self):
        _FakeGitHub.routes["/repos/o/r/releases/latest"] = (200, {}, b"<html>captive portal</html>")
        with self.assertRaises(updater.UpdateError):
            updater.fetch_latest_release("o/r", self.base)

    def test_nothing_listening_is_an_update_error_not_a_crash(self):
        dead = "http://127.0.0.1:1"
        with self.assertRaises(updater.UpdateError):
            updater.fetch_latest_release("o/r", dead, timeout=3)


class TestDownloadAsset(_ServerCase):
    PAYLOAD = b"pretend this is a 14 MB installer" * 1000

    def _asset(self, payload=None):
        _FakeGitHub.routes["/dl/a.bin"] = (200, {}, payload if payload is not None else self.PAYLOAD)
        return updater.Asset("a.bin", self.base + "/dl/a.bin", 0)

    def test_a_good_download_is_kept_and_progress_is_reported(self):
        dest = os.path.join(self.tmp.name, "a.bin")
        seen = []
        updater.download_asset(self._asset(), dest, hashlib.sha256(self.PAYLOAD).hexdigest().upper(),
                               api_base=self.base, progress=lambda done, total: seen.append((done, total)))
        with open(dest, "rb") as handle:
            self.assertEqual(handle.read(), self.PAYLOAD)
        self.assertFalse(os.path.exists(dest + ".part"))
        self.assertEqual(seen[-1][0], len(self.PAYLOAD))

    def test_a_wrong_checksum_discards_the_file(self):
        dest = os.path.join(self.tmp.name, "a.bin")
        with self.assertRaises(updater.UpdateError) as raised:
            updater.download_asset(self._asset(), dest, "00" * 32, api_base=self.base)
        self.assertIn("checksum", str(raised.exception))
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_no_published_checksum_means_no_download_at_all(self):
        dest = os.path.join(self.tmp.name, "a.bin")
        with self.assertRaises(updater.UpdateError):
            updater.download_asset(self._asset(), dest, None, api_base=self.base)
        self.assertFalse(os.path.exists(dest))

    def test_a_download_from_a_disallowed_address_is_refused(self):
        asset = updater.Asset("a.bin", "https://example.com/a.bin", 0)
        with self.assertRaises(updater.UpdateError):
            updater.download_asset(asset, os.path.join(self.tmp.name, "a.bin"), "AB" * 32, api_base=self.base)

    def test_a_redirect_off_the_allowed_hosts_is_refused(self):
        _FakeGitHub.routes["/dl/r.bin"] = (302, {"Location": "https://example.com/evil.bin"}, b"")
        asset = updater.Asset("r.bin", self.base + "/dl/r.bin", 0)
        dest = os.path.join(self.tmp.name, "r.bin")
        with self.assertRaises(updater.UpdateError):
            updater.download_asset(asset, dest, "AB" * 32, api_base=self.base)
        self.assertFalse(os.path.exists(dest))

    def test_a_redirect_that_stays_on_the_allowed_host_is_followed(self):
        _FakeGitHub.routes["/dl/r.bin"] = (302, {"Location": self.base + "/dl/a.bin"}, b"")
        _FakeGitHub.routes["/dl/a.bin"] = (200, {}, self.PAYLOAD)
        asset = updater.Asset("r.bin", self.base + "/dl/r.bin", 0)
        dest = os.path.join(self.tmp.name, "r.bin")
        updater.download_asset(asset, dest, hashlib.sha256(self.PAYLOAD).hexdigest().upper(), api_base=self.base)
        self.assertTrue(os.path.isfile(dest))

    def test_sha256_of_file_matches_hashlib(self):
        path = os.path.join(self.tmp.name, "f.bin")
        with open(path, "wb") as handle:
            handle.write(self.PAYLOAD)
        self.assertEqual(updater.sha256_of_file(path), hashlib.sha256(self.PAYLOAD).hexdigest().upper())


if __name__ == "__main__":
    unittest.main()

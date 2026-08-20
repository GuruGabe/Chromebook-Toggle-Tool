# tests/test_config.py
#
# Script:   test_config.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-07-2026
# Modified: 08-10-2026
# Version:  1.2
#
# Purpose:
#   Unit tests for chromebook_toggle/config.py - covers the documented
#   "never crash on a bad settings file" behavior (missing file, partially
#   filled-in file, corrupt/malformed file, non-ASCII bytes) plus the normal
#   save-then-load round trip.
#
# Usage:
#   python -m unittest tests.test_config -v
#   (run from the Chromebook-Toggle-Tool project root)
#
# Requirements:
#   Python 3.14, stdlib only (unittest, tempfile, configparser). No admin
#   rights needed - everything runs against a temp directory, never a real
#   settings.ini.
#
# Notes:
#   ASCII only. Tests config.load_settings / config.save_settings using a
#   temp directory so no real settings.ini is touched during the test run.

import configparser
import os
import tempfile
import unittest

from chromebook_toggle import config


class TestConfig(unittest.TestCase):

    def test_load_settings_returns_defaults_when_file_missing(self):
        # If settings.ini does not exist yet (first run on a fresh PC), the
        # tool must still work using the documented defaults rather than
        # crashing - this is the "never let a script silently fail" rule
        # applied to a missing-file case that is expected to happen on
        # every brand-new deployment.
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_path = os.path.join(tmp_dir, "settings.ini")
            settings = config.load_settings(missing_path)
            self.assertEqual(settings["gam_path"], config.DEFAULT_GAM_PATH)
            self.assertEqual(settings["sheet_acting_email"], config.DEFAULT_SHEET_ACTING_EMAIL)

    def test_save_then_load_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.ini")
            config.save_settings(settings_path, {
                "gam_path": r"D:\CustomGAM\gam.exe",
                "sheet_acting_email": "someone@example.com",
            })
            loaded = config.load_settings(settings_path)
            self.assertEqual(loaded["gam_path"], r"D:\CustomGAM\gam.exe")
            self.assertEqual(loaded["sheet_acting_email"], "someone@example.com")

    def test_load_settings_fills_in_missing_key_when_partially_set(self):
        # Simulates a settings.ini that someone hand-edited or that was
        # written by an older version of the tool that only ever wrote one
        # of the two keys. The key that IS present should load as written;
        # the key that is absent should fall back to its default rather
        # than raising or silently returning an empty string.
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.ini")
            parser = configparser.ConfigParser()
            parser["Settings"] = {
                "gam_path": r"E:\OnlyThisOneIsSet\gam.exe",
                # sheet_acting_email deliberately omitted.
            }
            with open(settings_path, "w", encoding="ascii") as settings_file:
                parser.write(settings_file)

            loaded = config.load_settings(settings_path)
            self.assertEqual(loaded["gam_path"], r"E:\OnlyThisOneIsSet\gam.exe")
            self.assertEqual(loaded["sheet_acting_email"], config.DEFAULT_SHEET_ACTING_EMAIL)

    def test_load_settings_returns_defaults_when_file_is_malformed(self):
        # Simulates a corrupted/hand-broken settings.ini - here, a duplicate
        # "gam_path" key under the same section, which configparser rejects
        # with DuplicateOptionError (a subclass of configparser.Error).
        # load_settings() must catch this and fall back to defaults instead
        # of letting the whole tool crash on startup.
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.ini")
            with open(settings_path, "w", encoding="ascii") as settings_file:
                settings_file.write(
                    "[Settings]\n"
                    "gam_path = C:\\GAM7\\gam.exe\n"
                    "gam_path = C:\\SomewhereElse\\gam.exe\n"
                )

            settings = config.load_settings(settings_path)
            self.assertEqual(settings["gam_path"], config.DEFAULT_GAM_PATH)
            self.assertEqual(settings["sheet_acting_email"], config.DEFAULT_SHEET_ACTING_EMAIL)

    def test_load_settings_returns_defaults_when_file_has_non_ascii_bytes(self):
        # Simulates the classic "someone opened it in Notepad and it saved a
        # UTF-8 BOM" or "hand-edited in a smart-quote-happy word processor"
        # case. encoding="ascii" makes parser.read() raise UnicodeDecodeError
        # on the BOM bytes; load_settings() must catch that too and fall
        # back to defaults rather than crashing.
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.ini")
            with open(settings_path, "wb") as settings_file:
                # UTF-8 BOM followed by an otherwise-valid section, written
                # as raw bytes so the BOM survives.
                settings_file.write(b"\xef\xbb\xbf[Settings]\r\ngam_path = C:\\GAM7\\gam.exe\r\n")

            settings = config.load_settings(settings_path)
            self.assertEqual(settings["gam_path"], config.DEFAULT_GAM_PATH)
            self.assertEqual(settings["sheet_acting_email"], config.DEFAULT_SHEET_ACTING_EMAIL)

    def test_save_settings_raises_clear_error_when_directory_missing(self):
        # Simulates an unwritable target - here, a parent directory that
        # does not exist. save_settings() must not let a raw OSError bubble
        # up uncommented; it should raise RuntimeError with a message that
        # names the path and the underlying problem.
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = os.path.join(tmp_dir, "no_such_subfolder", "settings.ini")
            with self.assertRaises(RuntimeError) as raised:
                config.save_settings(bad_path, {
                    "gam_path": r"C:\GAM7\gam.exe",
                    "sheet_acting_email": "someone@example.com",
                })
            self.assertIn(bad_path, str(raised.exception))

    def test_save_settings_raises_clear_error_when_value_is_non_ascii(self):
        # Simulates someone typing/pasting an accented name or a smart quote
        # into a settings value - e.g. an email address with an accented
        # "e" (e-acute, U+00E9). Written here as a unicode escape sequence
        # ("\u00e9") rather than a literal accented character so this
        # source file's own bytes stay pure ASCII; Python decodes the
        # escape to the real character at runtime, so the test value is
        # unchanged. save_settings() opens the file with encoding="ascii",
        # so writing a non-ASCII character raises UnicodeEncodeError (a
        # UnicodeError, which is a ValueError subclass - NOT an OSError).
        # That must still be caught and turned into the same clear
        # RuntimeError, not a raw traceback, so the header's "raises
        # RuntimeError if the file cannot be written" promise holds for
        # this failure mode too.
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.ini")
            non_ascii_email = "jos\u00e9@example.com"
            with self.assertRaises(RuntimeError) as raised:
                config.save_settings(settings_path, {
                    "gam_path": config.DEFAULT_GAM_PATH,
                    "sheet_acting_email": non_ascii_email,
                })
            self.assertIn(settings_path, str(raised.exception))


if __name__ == "__main__":
    unittest.main()

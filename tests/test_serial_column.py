# tests/test_serial_column.py
#
# The serial-number column: GAM's own download header is "serialNumber", GAM
# matches a ~Column substitution against a Sheet header EXACTLY, and the person
# can choose a different column. The GAM output samples below were captured from
# a real GAM 7.51.00 (csvtest on a local file), not invented.

import os
import tempfile
import unittest

from chromebook_toggle import config, gam_runner, serials

REAL_CSVTEST = (
    "The CSV file (C:\Temp\t.csv) has the following headers:\n"
    "  serialNumber\n"
    "  status\n"
    "  orgUnitPath\n"
    "Here are the first 2 commands GAM will run\n"
    "  gam update cros cros_sn ABC123 action disable\n")

REAL_MISSING = ('Command: gam csvtest t.csv gam update cros cros_sn >>>~Serial<<< action disable\n\n'
                'ERROR: Header "Serial" not found in CSV headers of "serialNumber,status,orgUnitPath".\n')


class TestSheetColumn(unittest.TestCase):
    def test_default_is_gams_own_header(self):
        self.assertEqual(config.default_settings()["serial_column"], "serialNumber")
        args = gam_runner.build_gsheet_action_args("a@example.com", "F", "0", "disable")
        self.assertIn("~serialNumber", args)

    def test_a_chosen_column_is_used_exactly(self):
        args = gam_runner.build_gsheet_action_args("a@example.com", "F", "0", "disable", column="Serial Number")
        self.assertEqual(args[args.index("cros_sn") + 1], "~Serial Number")

    def test_bad_column_names_are_refused(self):
        for bad in ("", "   ", "a\nb", "a\x00b"):
            with self.assertRaises(ValueError):
                gam_runner.clean_column_name(bad)
        self.assertEqual(gam_runner.clean_column_name("  Serial  "), "Serial")

    def test_columns_command_is_read_only(self):
        self.assertEqual(gam_runner.build_gsheet_columns_args("a@example.com", "F", "7"),
                         ["csvtest", "gsheet", "a@example.com", "id:F", "id:7", "gam", "version"])

    def test_parse_real_csvtest_headers(self):
        self.assertEqual(gam_runner.parse_csvtest_headers(REAL_CSVTEST), ["serialNumber", "status", "orgUnitPath"])
        self.assertEqual(gam_runner.parse_csvtest_headers("ERROR: nope"), [])
        self.assertEqual(gam_runner.parse_csvtest_headers(None), [])

    def test_missing_header_error_is_explained_with_the_real_columns(self):
        text = gam_runner.explain_missing_header(REAL_MISSING)
        self.assertIn('no column named "Serial"', text)
        self.assertIn("serialNumber, status, orgUnitPath", text)
        self.assertEqual(gam_runner.explain_missing_header("ERROR: Device not found"), "")


class TestPickSerialColumn(unittest.TestCase):
    def test_prefers_the_named_column(self):
        self.assertEqual(serials.pick_serial_column(["Asset", "Serial", "SerialNumber"], "SerialNumber"), "SerialNumber")

    def test_matches_ignoring_case_and_spacing(self):
        self.assertEqual(serials.pick_serial_column(["Serial Number", "x"], "serialNumber"), "Serial Number")
        self.assertEqual(serials.pick_serial_column(["serial_number"], ""), "serial_number")

    def test_falls_back_to_anything_serial_like(self):
        self.assertEqual(serials.pick_serial_column(["status", "SERIAL"], "nonsense"), "SERIAL")

    def test_nothing_fits(self):
        self.assertEqual(serials.pick_serial_column(["status", "orgUnitPath"], "serialNumber"), "")


class TestCsvColumn(unittest.TestCase):
    def _csv(self, text):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        path = os.path.join(folder, "t.csv")
        with open(path, "w", newline="", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_gams_own_download_header_works_automatically(self):
        path = self._csv("serialNumber,status\nabc1,ACTIVE\ndef2,ACTIVE\n")
        self.assertEqual(serials.read_csv_serials(path), ["ABC1", "DEF2"])

    def test_headers_listed_for_the_dropdown(self):
        path = self._csv("Asset Tag,Serial No,Room\n1,AAA,2\n")
        self.assertEqual(serials.read_csv_headers(path), ["Asset Tag", "Serial No", "Room"])

    def test_unusual_header_found_automatically_or_chosen(self):
        path = self._csv("Asset Tag,Serial No,Room\n1,aaa,2\n")
        self.assertEqual(serials.read_csv_serials(path), ["AAA"])           # "Serial No" is recognised
        self.assertEqual(serials.read_csv_serials(path, "Asset Tag"), ["1"])  # but the person may pick another
        self.assertEqual(serials.read_csv_serials(path, serials.AUTO_COLUMN), ["AAA"])

    def test_chosen_column_must_exist_and_error_lists_columns(self):
        path = self._csv("a,b\n1,2\n")
        with self.assertRaises(ValueError) as caught:
            serials.read_csv_serials(path, "zzz")
        self.assertIn("a, b", str(caught.exception))

    def test_no_serial_like_column_error_lists_columns(self):
        path = self._csv("a,b\n1,2\n")
        with self.assertRaises(ValueError) as caught:
            serials.read_csv_serials(path)
        self.assertIn("a, b", str(caught.exception))


class TestSettingRoundTrip(unittest.TestCase):
    def test_serial_column_setting_loads_and_blank_falls_back(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        path = os.path.join(folder, "settings.ini")
        with open(path, "w") as handle:
            handle.write("[Settings]\nserial_column = Serial Number\n")
        self.assertEqual(config.load_settings(path)["serial_column"], "Serial Number")
        with open(path, "w") as handle:
            handle.write("[Settings]\nserial_column =\n")
        self.assertEqual(config.load_settings(path)["serial_column"], "serialNumber")


if __name__ == "__main__":
    unittest.main()

# tests/test_state.py
# ASCII only. Tests chromebook_toggle/state.py - the tiny per-person note of
# when updates were last checked. The one rule that matters: nothing here may
# ever raise, because a bad state file must never stop the app starting.
import os
import tempfile
import unittest

from chromebook_toggle import state


class TestLastCheckFile(unittest.TestCase):

    def test_missing_file_means_never_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(state.load_last_check(os.path.join(folder, "state.ini")), 0)

    def test_save_then_load_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.ini")
            self.assertTrue(state.save_last_check(path, when=1700000000))
            self.assertEqual(state.load_last_check(path), 1700000000)

    def test_garbage_value_is_treated_as_never_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.ini")
            with open(path, "w", encoding="ascii") as handle:
                handle.write("[State]\nlast_update_check = soon\n")
            self.assertEqual(state.load_last_check(path), 0)

    def test_malformed_file_is_treated_as_never_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.ini")
            with open(path, "w", encoding="ascii") as handle:
                handle.write("this is not an ini file\n[[[\n")
            self.assertEqual(state.load_last_check(path), 0)

    def test_a_missing_folder_is_created(self):
        # First run for a person: their app-data folder does not exist yet.
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "new", "ChromebookToggle", "state.ini")
            self.assertTrue(state.save_last_check(path, when=1700000000))
            self.assertEqual(state.load_last_check(path), 1700000000)

    def test_unwritable_location_reports_false_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            # A "folder" that is really a file can never hold state.ini.
            blocker = os.path.join(folder, "blocker")
            with open(blocker, "w", encoding="ascii") as handle:
                handle.write("x")
            self.assertFalse(state.save_last_check(os.path.join(blocker, "state.ini")))


class TestCheckIsDue(unittest.TestCase):

    def test_never_checked_is_due(self):
        self.assertTrue(state.check_is_due(0, now=1000))

    def test_checked_an_hour_ago_is_not_due(self):
        self.assertFalse(state.check_is_due(1000, now=1000 + 3600))

    def test_checked_a_day_ago_is_due(self):
        self.assertTrue(state.check_is_due(1000, now=1000 + 24 * 3600))

    def test_a_future_timestamp_counts_as_due(self):
        # PC clock was set back: do not let that switch update checks off.
        self.assertTrue(state.check_is_due(5000, now=1000))


if __name__ == "__main__":
    unittest.main()

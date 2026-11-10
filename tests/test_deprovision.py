# tests/test_deprovision.py
# ASCII only. Tests how deprovisioning is wired into the rest of the backend:
# the GAM command builders must add the acknowledgement flag, the review step
# must skip deprovisioned devices for disable/re-enable, and the results step
# must judge a deprovision by the DEPROVISIONED status. No real gam.exe is
# ever run - these are pure argument-list and dictionary checks.
import unittest

from chromebook_toggle import gam_calls, gam_runner, workflow


class TestCommandBuilders(unittest.TestCase):

    def test_csv_deprovision_command_has_the_acknowledgement_after_the_action(self):
        args = gam_runner.build_csv_action_args(r"C:\temp\serials.csv", "deprovision_retiring_device")
        # Literal strings, not the constants, so a constant edited by
        # mistake cannot make this test pass.
        self.assertEqual(args, [
            "csv", r"C:\temp\serials.csv",
            "gam", "update", "cros", "cros_sn", "~Serial",
            "action", "deprovision_retiring_device",
            "acknowledge_device_touch_requirement",
        ])

    def test_sheet_deprovision_command_has_the_acknowledgement_after_the_action(self):
        args = gam_runner.build_gsheet_action_args(
            "admin@example.com", "FILEID", "7", "deprovision_same_model_replace")
        self.assertEqual(args, [
            "csv", "gsheet", "admin@example.com", "id:FILEID", "id:7",
            "gam", "update", "cros", "cros_sn", "~Serial",
            "action", "deprovision_same_model_replace",
            "acknowledge_device_touch_requirement",
        ])

    def test_disable_and_reenable_commands_are_unchanged(self):
        # The new acknowledgement must never leak onto the everyday actions.
        for action in ("disable", "reenable"):
            csv_args = gam_runner.build_csv_action_args("f.csv", action)
            self.assertEqual(csv_args[-2:], ["action", action])
            sheet_args = gam_runner.build_gsheet_action_args("a@example.com", "F", "0", action)
            self.assertEqual(sheet_args[-2:], ["action", action])
            self.assertNotIn("acknowledge_device_touch_requirement", csv_args + sheet_args)

    def test_every_deprovision_reason_gets_the_flag(self):
        from chromebook_toggle import actions
        for word in actions.DEPROVISION_ACTIONS:
            self.assertEqual(
                gam_runner.build_csv_action_args("f.csv", word)[-1],
                "acknowledge_device_touch_requirement")


class TestReviewRules(unittest.TestCase):

    def test_deprovisioned_device_is_skipped_for_disable_and_reenable(self):
        # A deprovisioned device is no longer managed: nothing to disable or
        # re-enable, so the review says so instead of sending a doomed command.
        looked_up = {"GONE1": {"status": "DEPROVISIONED"}}
        for action, verb in (("disable", "disable"), ("reenable", "re-enable")):
            row = workflow.build_review(["GONE1"], looked_up, action)[0]
            self.assertTrue(row.found)
            self.assertFalse(row.will_process)
            self.assertEqual(row.skip_reason, "Deprovisioned - cannot " + verb)

    def test_deprovision_of_an_active_or_disabled_device_will_process(self):
        looked_up = {"A1": {"status": "ACTIVE"}, "D1": {"status": "DISABLED"}}
        rows = workflow.build_review(["A1", "D1"], looked_up, "deprovision_retiring_device")
        self.assertTrue(all(r.will_process for r in rows))
        self.assertEqual([r.current_status for r in rows], ["ACTIVE", "DISABLED"])

    def test_deprovision_of_an_already_deprovisioned_device_is_skipped(self):
        looked_up = {"GONE1": {"status": "DEPROVISIONED"}}
        row = workflow.build_review(["GONE1"], looked_up, "deprovision_retiring_device")[0]
        self.assertFalse(row.will_process)
        self.assertEqual(row.skip_reason, "Already DEPROVISIONED")

    def test_unknown_action_still_fails_loudly(self):
        # Adding deprovision must not weaken the existing rule that a bad
        # action string is a programming error, not something to guess at.
        with self.assertRaises(KeyError):
            workflow.build_review(["A1"], {"A1": {"status": "ACTIVE"}}, "deprovision_typo")


class TestResultRules(unittest.TestCase):

    def test_deprovision_succeeds_only_when_the_device_reports_deprovisioned(self):
        review = [workflow.ReviewRow("A1", True, "ACTIVE", True, None),
                  workflow.ReviewRow("A2", True, "ACTIVE", True, None)]
        post = {"A1": {"status": "DEPROVISIONED"}, "A2": {"status": "ACTIVE"}}
        results = workflow.build_results(review, post, "deprovision_retiring_device")
        self.assertEqual([(r.serial, r.success) for r in results],
                         [("A1", True), ("A2", False)])

    def test_gam_calls_wrappers_accept_deprovision_actions(self):
        # The GUI reaches the workflow through these wrappers; a deprovision
        # word must pass through them without an "unrecognized action" error.
        rows, error = gam_calls.build_review_or_none(
            ["A1"], {"A1": {"status": "ACTIVE"}}, "deprovision_upgrade_transfer")
        self.assertIsNone(error)
        self.assertTrue(rows[0].will_process)


if __name__ == "__main__":
    unittest.main()

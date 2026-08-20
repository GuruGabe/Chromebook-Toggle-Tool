# tests/test_workflow.py
# ASCII only. Tests workflow.build_review / workflow.build_results, which
# turn a resolved serial list plus a device-status lookup dict into the
# review screen's rows (Task 6a) and the results screen's rows (Task 6b).
import unittest

from chromebook_toggle import workflow


class TestBuildReview(unittest.TestCase):

    def test_not_found_serial_is_excluded_with_reason(self):
        # A serial that gam's lookup never returned anything for (typo,
        # wrong device, not enrolled in this Workspace) must be flagged as
        # not-found and excluded from processing, with a human-readable
        # reason the review screen can show.
        rows = workflow.build_review(["MISSING1"], {}, "disable")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].found)
        self.assertFalse(rows[0].will_process)
        self.assertIn("not found", rows[0].skip_reason.lower())

    def test_already_in_target_state_is_excluded_with_reason(self):
        # A device that is already DISABLED should not be re-processed by
        # a "disable" run - skip it, and say why, rather than silently
        # sending it through gam again for no effect.
        looked_up = {"ABC123": {"status": "DISABLED"}}
        rows = workflow.build_review(["ABC123"], looked_up, "disable")
        self.assertTrue(rows[0].found)
        self.assertFalse(rows[0].will_process)
        self.assertIn("DISABLED", rows[0].skip_reason)

    def test_normal_device_will_process(self):
        # A found device NOT already in the target state is exactly the
        # normal case this tool exists for - it should be marked to
        # process, with no skip reason, and its current status carried
        # through for the review screen to display.
        looked_up = {"ABC123": {"status": "ACTIVE"}}
        rows = workflow.build_review(["ABC123"], looked_up, "disable")
        self.assertTrue(rows[0].will_process)
        self.assertIsNone(rows[0].skip_reason)
        self.assertEqual(rows[0].current_status, "ACTIVE")

    def test_mixed_outcomes_across_multiple_serials_in_one_call(self):
        # Real usage always processes a batch of serials in a single call,
        # not one at a time - this exercises all three row outcomes
        # (not-found, already-at-target, normal) together in one
        # serial_list, and asserts each row is correct AND in the same
        # order as serial_list, so a bug where state leaks between loop
        # iterations (e.g. reusing a previous row's skip_reason) or where
        # rows come out reordered would be caught.
        serial_list = ["MISSING1", "ABC123", "DEF456"]
        looked_up = {
            "ABC123": {"status": "DISABLED"},  # already at target - skipped
            "DEF456": {"status": "ACTIVE"},  # normal - will process
            # MISSING1 intentionally absent - not found
        }
        rows = workflow.build_review(serial_list, looked_up, "disable")
        self.assertEqual(len(rows), 3)

        self.assertEqual(rows[0].serial, "MISSING1")
        self.assertFalse(rows[0].found)
        self.assertFalse(rows[0].will_process)
        self.assertIn("not found", rows[0].skip_reason.lower())

        self.assertEqual(rows[1].serial, "ABC123")
        self.assertTrue(rows[1].found)
        self.assertFalse(rows[1].will_process)
        self.assertEqual(rows[1].current_status, "DISABLED")
        self.assertIn("DISABLED", rows[1].skip_reason)

        self.assertEqual(rows[2].serial, "DEF456")
        self.assertTrue(rows[2].found)
        self.assertTrue(rows[2].will_process)
        self.assertEqual(rows[2].current_status, "ACTIVE")
        self.assertIsNone(rows[2].skip_reason)


class TestBuildResults(unittest.TestCase):

    def test_success_when_new_status_matches_target(self):
        # By design, success is decided by comparing the
        # post-action lookup's status against the action's target status -
        # not by parsing gam's mutating-command text output.
        review_rows = [workflow.ReviewRow("ABC123", True, "ACTIVE", True, None)]
        post_lookup = {"ABC123": {"status": "DISABLED"}}
        results = workflow.build_results(review_rows, post_lookup, "disable")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].previous_status, "ACTIVE")
        self.assertEqual(results[0].new_status, "DISABLED")

    def test_failure_when_new_status_does_not_match_target(self):
        # If the post-action status still is not the target status, the
        # action did not actually take effect (gam error, device offline
        # and never checked in, etc.) - that must be reported as a failure
        # rather than assumed to have worked.
        review_rows = [workflow.ReviewRow("ABC123", True, "ACTIVE", True, None)]
        post_lookup = {"ABC123": {"status": "ACTIVE"}}  # did not actually change
        results = workflow.build_results(review_rows, post_lookup, "disable")
        self.assertFalse(results[0].success)

    def test_skipped_rows_are_not_included_in_results(self):
        # A row that was skipped during review (not found, or already in
        # the target state) was never sent to gam for this action, so it
        # must not appear in the results/log at all - including it would
        # falsely imply this run touched that device.
        review_rows = [workflow.ReviewRow("ABC123", True, "DISABLED", False, "Already DISABLED")]
        results = workflow.build_results(review_rows, {"ABC123": {"status": "DISABLED"}}, "disable")
        self.assertEqual(results, [])

    def test_multiple_will_process_rows_are_scored_independently(self):
        # Real usage always processes a batch - this exercises multiple
        # will_process=True rows in a single call, one that succeeded and
        # one that did not, to confirm each row's success is determined
        # independently from post_looked_up rather than one row's outcome
        # leaking into another's (e.g. a bug that reused the same
        # new_status/target_status comparison across the whole loop).
        review_rows = [
            workflow.ReviewRow("ABC123", True, "ACTIVE", True, None),
            workflow.ReviewRow("DEF456", True, "ACTIVE", True, None),
        ]
        post_lookup = {
            "ABC123": {"status": "DISABLED"},  # actually changed - success
            "DEF456": {"status": "ACTIVE"},  # did not change - failure
        }
        results = workflow.build_results(review_rows, post_lookup, "disable")
        self.assertEqual(len(results), 2)

        self.assertEqual(results[0].serial, "ABC123")
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].previous_status, "ACTIVE")
        self.assertEqual(results[0].new_status, "DISABLED")

        self.assertEqual(results[1].serial, "DEF456")
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].previous_status, "ACTIVE")
        self.assertEqual(results[1].new_status, "ACTIVE")


class TestInvalidAction(unittest.TestCase):

    def test_build_review_raises_keyerror_on_unknown_action(self):
        # action is never free-text from an untrusted source - it only
        # ever comes from the GUI's own two action radio buttons ("disable"
        # or "reenable"), so an unrecognized value here means a programming
        # mistake (a typo'd literal, or a future caller passing the wrong
        # string), not a data-quality problem from an external system. This
        # test locks in the deliberate choice to let that raise a raw,
        # immediate KeyError rather than silently produce wrong rows or
        # wrap it in a misleading "user-facing" exception type - see the
        # ERROR-HANDLING DESIGN comment in workflow.py for the full
        # reasoning.
        with self.assertRaises(KeyError):
            workflow.build_review(["ABC123"], {"ABC123": {"status": "ACTIVE"}}, "not_a_real_action")

    def test_build_results_raises_keyerror_on_unknown_action(self):
        review_rows = [workflow.ReviewRow("ABC123", True, "ACTIVE", True, None)]
        with self.assertRaises(KeyError):
            workflow.build_results(review_rows, {"ABC123": {"status": "ACTIVE"}}, "not_a_real_action")


if __name__ == "__main__":
    unittest.main()

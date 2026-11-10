# tests/test_actions.py
# ASCII only. Tests chromebook_toggle/actions.py - the one place that defines
# which Chromebook actions exist, what status each should produce, and the
# extra GAM arguments a deprovision needs. These are small on purpose: the
# table is what every other module trusts, so every row is pinned here.
import unittest

from chromebook_toggle import actions


class TestActionTable(unittest.TestCase):

    def test_everyday_actions_map_to_their_statuses(self):
        self.assertEqual(actions.TARGET_STATUS["disable"], "DISABLED")
        self.assertEqual(actions.TARGET_STATUS["reenable"], "ACTIVE")

    def test_every_deprovision_reason_targets_deprovisioned(self):
        # All four reasons end in the same status - a reason is only
        # metadata Google records, it does not change the end state.
        for word in actions.DEPROVISION_ACTIONS:
            self.assertEqual(actions.TARGET_STATUS[word], "DEPROVISIONED")

    def test_the_four_documented_reasons_are_present(self):
        # The words are GAM's own (ChromeOS Devices wiki). If one is ever
        # misspelled here GAM would reject the command, so pin them.
        self.assertEqual(
            sorted(actions.DEPROVISION_ACTIONS),
            ["deprovision_different_model_replace",
             "deprovision_retiring_device",
             "deprovision_same_model_replace",
             "deprovision_upgrade_transfer"])

    def test_default_reason_is_retiring_the_device(self):
        self.assertEqual(actions.DEFAULT_DEPROVISION_ACTION, "deprovision_retiring_device")

    def test_no_everyday_action_is_listed_as_a_deprovision(self):
        self.assertNotIn("disable", actions.DEPROVISION_ACTIONS)
        self.assertNotIn("reenable", actions.DEPROVISION_ACTIONS)


class TestHelpers(unittest.TestCase):

    def test_is_deprovision(self):
        self.assertTrue(actions.is_deprovision("deprovision_retiring_device"))
        self.assertFalse(actions.is_deprovision("disable"))
        self.assertFalse(actions.is_deprovision("reenable"))
        # A typo is NOT treated as a deprovision (and is rejected loudly by
        # workflow.py's table lookup instead).
        self.assertFalse(actions.is_deprovision("deprovision_retireing_device"))

    def test_labels(self):
        self.assertEqual(actions.label("disable"), "Disable")
        self.assertEqual(actions.label("reenable"), "Re-enable")
        self.assertEqual(
            actions.label("deprovision_retiring_device"),
            "Deprovision (Retiring the device)")

    def test_verbs(self):
        self.assertEqual(actions.verb("disable"), "disable")
        self.assertEqual(actions.verb("reenable"), "re-enable")
        self.assertEqual(actions.verb("deprovision_upgrade_transfer"), "deprovision")

    def test_reason_text_round_trips(self):
        for word, shown in actions.DEPROVISION_REASONS:
            self.assertEqual(actions.reason_text(word), shown)
            self.assertEqual(actions.action_for_reason_text(shown), word)

    def test_unknown_reason_text_falls_back_to_the_default(self):
        # A stale or blank drop-down value must never yield a bad action.
        self.assertEqual(actions.action_for_reason_text("nonsense"),
                         actions.DEFAULT_DEPROVISION_ACTION)
        self.assertEqual(actions.reason_text("disable"), "")


class TestExtraGamArgs(unittest.TestCase):

    def test_deprovision_needs_the_acknowledgement_flag(self):
        # GAM refuses to deprovision without this exact flag.
        for word in actions.DEPROVISION_ACTIONS:
            self.assertEqual(actions.extra_gam_args(word),
                             ("acknowledge_device_touch_requirement",))

    def test_everyday_actions_need_no_extra_arguments(self):
        self.assertEqual(actions.extra_gam_args("disable"), ())
        self.assertEqual(actions.extra_gam_args("reenable"), ())


class TestTypedConfirmation(unittest.TestCase):

    def test_exact_word_is_accepted(self):
        self.assertTrue(actions.typed_confirmation_ok("DEPROVISION"))

    def test_surrounding_spaces_are_forgiven(self):
        self.assertTrue(actions.typed_confirmation_ok("  DEPROVISION \n"))

    def test_near_misses_are_rejected(self):
        # Deliberately strict: case must match and nothing may be added.
        for typed in ("", "deprovision", "Deprovision", "DEPROVISIO",
                      "DEPROVISIONN", "yes", "y", "DEPROVISION ALL"):
            self.assertFalse(actions.typed_confirmation_ok(typed), typed)


if __name__ == "__main__":
    unittest.main()

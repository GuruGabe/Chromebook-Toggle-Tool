# Tests for installer/release_notes.py (extracts one version's CHANGELOG section).
import importlib.util
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("release_notes", os.path.join(_ROOT, "installer", "release_notes.py"))
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

SAMPLE = """=====
CHANGELOG
=====
08-10-2026 - v1.0
  - first

08-10-2026 - v1.10
  - tenth

11-10-2026 - v1.4 Title
  - fourth
  - more
=====
"""


class TestSectionFor(unittest.TestCase):
    def test_middle_section_stops_at_next_heading(self):
        text = release_notes.section_for(SAMPLE, "1.0")
        self.assertIn("first", text)
        self.assertNotIn("tenth", text)

    def test_version_match_is_exact_not_prefix(self):
        self.assertIn("tenth", release_notes.section_for(SAMPLE, "1.10"))
        self.assertNotIn("tenth", release_notes.section_for(SAMPLE, "1.1") or "")

    def test_last_section_stops_at_divider(self):
        text = release_notes.section_for(SAMPLE, "1.4")
        self.assertIn("more", text)
        self.assertNotIn("=====", text)

    def test_missing_version_is_none(self):
        self.assertIsNone(release_notes.section_for(SAMPLE, "9.9"))


if __name__ == "__main__":
    unittest.main()

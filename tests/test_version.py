# tests/test_version.py
# ASCII only. Guards the release bookkeeping: APP_VERSION must be a plain
# dotted number, and the newest CHANGELOG.txt entry must be that same number.
# A release that bumps one but forgets the other fails here, not in front of
# the people receiving the update.
import os
import re
import unittest

from chromebook_toggle import version

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _changelog_versions():
    # Every "MM-DD-YYYY - vX.Y" heading in CHANGELOG.txt, as number tuples.
    found = []
    with open(os.path.join(_PROJECT_ROOT, "CHANGELOG.txt"), encoding="ascii") as handle:
        for line in handle:
            match = re.match(r"^\d\d-\d\d-\d{4} - v(\d+(?:\.\d+)+)", line)
            if match:
                found.append(tuple(int(part) for part in match.group(1).split(".")))
    return found


class TestVersion(unittest.TestCase):

    def test_app_version_is_a_plain_dotted_number(self):
        # No leading "v": the tag has one, the constant must not.
        self.assertRegex(version.APP_VERSION, r"^\d+(\.\d+)+$")

    def test_newest_changelog_entry_matches_app_version(self):
        entries = _changelog_versions()
        self.assertTrue(entries, "CHANGELOG.txt has no version headings")
        newest = max(entries)
        current = tuple(int(part) for part in version.APP_VERSION.split("."))
        self.assertEqual(newest, current,
                         "CHANGELOG.txt's newest entry and version.APP_VERSION disagree")

    def test_releases_url_follows_the_repo_name(self):
        self.assertEqual(version.releases_url("someone/else"),
                         "https://github.com/someone/else/releases/latest")


if __name__ == "__main__":
    unittest.main()

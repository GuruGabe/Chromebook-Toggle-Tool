# tests/test_no_org_data.py
#
# Guard for the PUBLIC repository: no organization-specific values (domain
# names, server names, account names, internal addresses) may be committed in
# any text file, and every text file must be plain ASCII.
#
# The forbidden strings are built from pieces below so that this test file does
# not contain them itself (it would otherwise fail its own scan).

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Folders that hold build output or tooling, not project source.
SKIP_DIRS = {".git", "__pycache__", "build", "dist", "build_res", ".claude", ".venv", "venv"}
# Binary or generated files that are not scanned.
SKIP_SUFFIXES = (".exe", ".pyc", ".zip", ".dmg", ".deb", ".rpm", ".gz", ".png", ".ico", ".spec")

FORBIDDEN = [
    "fs" + "isd",
    "fort" + " stockton",
    "gabriel" + ".clifton",
    "gam" + "config",
    "tx" + "virtual",
    "10." + "100.",
]


def _text_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.lower().endswith(SKIP_SUFFIXES):
                continue
            yield os.path.join(folder, name)


class TestNoOrgData(unittest.TestCase):
    def test_no_organization_specific_values(self):
        problems = []
        for path in _text_files():
            with open(path, "rb") as handle:
                text = handle.read().decode("utf-8", "replace").lower()
            for word in FORBIDDEN:
                if word in text:
                    problems.append("%s contains %r" % (os.path.relpath(path, ROOT), word))
        self.assertEqual(problems, [])

    def test_every_text_file_is_ascii(self):
        problems = []
        for path in _text_files():
            with open(path, "rb") as handle:
                data = handle.read()
            try:
                data.decode("ascii")
            except UnicodeDecodeError as error:
                problems.append("%s: byte %d is not ASCII" % (os.path.relpath(path, ROOT), error.start))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

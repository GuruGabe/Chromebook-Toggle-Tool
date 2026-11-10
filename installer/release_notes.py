"""Print the CHANGELOG.txt section for one version, for use as GitHub release notes.

Usage:  python installer/release_notes.py 1.4

The section starts at the "MM-DD-YYYY - v<version>" heading and ends at the next
such heading or at the closing line of "=" characters. The release workflow uses
this to create the GitHub release when it does not exist yet. Exits with an error
if the version has no section, so a release can never go out with empty notes.
"""
import re
import sys

HEADING = re.compile(r"^\d{2}-\d{2}-\d{4} - v(\d+(?:\.\d+)*)\b")


def section_for(text, version):
    # Walk the file line by line, collecting from the matching heading until the
    # next heading (or the closing divider line).
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        found = HEADING.match(line)
        if found and found.group(1) == version:
            start = index
            break
    if start is None:
        return None
    collected = [lines[start]]
    for line in lines[start + 1:]:
        if HEADING.match(line) or line.startswith("====="):
            break
        collected.append(line)
    return "\n".join(collected).strip() + "\n"


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: release_notes.py <version>\n")
        return 2
    with open("CHANGELOG.txt", encoding="ascii") as handle:
        notes = section_for(handle.read(), argv[1])
    if not notes:
        sys.stderr.write("CHANGELOG.txt has no section for v%s\n" % argv[1])
        return 1
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

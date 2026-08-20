# chromebook_toggle/sheet_url.py
#
# Script:   sheet_url.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-10-2026
# Modified: 08-10-2026
# Version:  1.0
#
# Purpose:
#   Extracts the Drive file ID and tab (gid) out of a pasted Google Sheets
#   URL, so the non-technical user only ever has to paste a URL - never an
#   ID or a tab name - even though gam's gsheet: source needs both.
#
# Notes:
#   gid defaults to "0" (the first tab) when the URL does not include one,
#   which is the normal Google Sheets URL shape when someone is looking at
#   the first tab and never switched tabs.
#
#   parse_sheet_url() raises ValueError (never returns a partial/garbage
#   result) whenever the URL does not contain a recognizable
#   "/spreadsheets/d/<id>" segment - covers a URL that is not a Google
#   Sheets link at all, an empty string (e.g. the GUI's URL box was never
#   filled in, a later task), and a truncated/mangled copy-paste where the
#   file ID segment is present but empty.
#
#   gid is only ever communicated via the "#gid=" fragment in the modern
#   "/spreadsheets/d/<id>/edit" URL scheme (e.g. "#gid=N&range=A1:B2"),
#   optionally preceded by other query params before the "#" (e.g.
#   "?usp=sharing#gid=N") - both are handled below. A bare "?gid=" query
#   parameter is NOT a real shape this tool needs to handle: that only
#   ever existed in the pre-2014 legacy "/spreadsheet/ccc?key=..." URL
#   format, which uses a different path entirely and would never match
#   _FILE_ID_PATTERN above in the first place.

import re

# Matches the literal "/spreadsheets/d/" path segment Google Sheets URLs
# always use, then captures the file ID that follows: one or more of the
# characters Drive file IDs are actually made of (letters, digits,
# underscore, hyphen). Stops at the first character NOT in that set (e.g.
# the "/" before "/edit", or a "?"), which is exactly where the file ID
# ends in every real Sheets URL shape. Requiring 1+ characters (rather
# than 0+) means a URL with the segment present but nothing after it (a
# truncated copy-paste) correctly fails to match instead of "succeeding"
# with an empty file ID.
_FILE_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")

# Matches "gid=<digits>" wherever it appears in the URL, as long as it is
# immediately preceded by "#" (the fragment itself, e.g. "...#gid=123")
# or "&" (a later parameter after the "#gid=" one, e.g.
# "...#gid=123&range=A1:B2") - this covers the real shape Google produces
# without also matching an unrelated substring that merely happens to
# contain the letters "gid=" (e.g. some other parameter name ending in
# "gid="). Note the "&" branch does not actually require being inside the
# fragment - "&gid=123" earlier in the query string, before the "#",
# would also match. That is intentionally not tightened further: real
# Google Sheets URLs never emit gid outside the fragment (see the module
# docstring above), so the distinction does not matter for any input this
# tool will actually see.
_GID_PATTERN = re.compile(r"[#&]gid=([0-9]+)")


def parse_sheet_url(url):
    # Search (not match/fullmatch) since the file ID segment can appear
    # anywhere in the string - there is always a "https://docs.google.com"
    # prefix before it in a real URL, which this pattern deliberately does
    # not require, so a URL pasted without its scheme still works.
    file_id_match = _FILE_ID_PATTERN.search(url)
    if not file_id_match:
        # Covers every "not a real Sheets URL" case in one place: wrong
        # site entirely, empty string, or the segment present but with no
        # ID characters following it. One clear error message for the GUI
        # (a later task) to show, regardless of which of these it was.
        raise ValueError("Could not find a Google Sheets file ID in that URL")
    file_id = file_id_match.group(1)

    # gid is optional - most pasted URLs never had a tab switch, so most
    # of the time this simply will not match, which is expected, not an
    # error.
    gid_match = _GID_PATTERN.search(url)
    gid = gid_match.group(1) if gid_match else "0"

    return file_id, gid

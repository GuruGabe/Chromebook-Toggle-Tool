# chromebook_toggle/version.py
#
# Script:   version.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  11-10-2026
# Modified: 11-10-2026
# Version:  1.0
#
# Purpose:
#   The single place the app's name, version number and public home are
#   written down. The window title, the About box, the self-updater and the
#   release checks all read these constants, so a release only ever needs
#   one number changed here (plus the matching CHANGELOG.txt entry and git
#   tag - tests\test_version.py fails if the changelog and this file
#   disagree, so a forgotten bump cannot ship).
#
# Notes:
#   APP_VERSION is a plain dotted number ("1.4"), NEVER with a leading "v".
#   Git tags are written with the "v" ("v1.4"); updater.parse_version()
#   accepts either spelling when comparing.

# Shown in the window title, About box and update prompts.
APP_NAME = "Chromebook Toggle Tool"

# The version of THIS build. Bump it (and add a CHANGELOG.txt entry) for
# every release.
APP_VERSION = "1.5"

# owner/repo on GitHub that publishes releases. This is the default only -
# settings.ini can override it with update_repo (for a fork or a mirror).
DEFAULT_UPDATE_REPO = "GuruGabe/Chromebook-Toggle-Tool"

# Where a person can read about releases or download one by hand. Built
# from the repo name so it follows an update_repo override.
def releases_url(repo=DEFAULT_UPDATE_REPO):
    return "https://github.com/" + repo + "/releases/latest"

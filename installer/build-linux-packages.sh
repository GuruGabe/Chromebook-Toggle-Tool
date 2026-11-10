#!/usr/bin/env bash
# =============================================================================
# build-linux-packages.sh - build a .deb and a .rpm for the Chromebook Toggle
# Tool with fpm.
#
# Run AFTER build-app.sh has produced dist/ChromebookToggle/ (the one-folder
# app). Usage:
#   installer/build-linux-packages.sh <version>
# Produces, in the current directory:
#   chromebooktoggle_<version>_amd64.deb
#   chromebooktoggle-<version>-1.x86_64.rpm
#
# Installing either one registers the tool with the system package manager
# (dpkg / rpm) - so the OS knows it is installed and at what version
# (dpkg -l chromebooktoggle, rpm -q chromebooktoggle) - and it can be removed
# with apt/dnf/rpm. The app lands in /opt/ChromebookToggle, with a launcher at
# /usr/bin/chromebooktoggle and a desktop-menu entry.
#
# /opt is owned by root, so a standard user cannot write there: the app keeps
# its logs and state in ~/.local/share/ChromebookToggle instead (see
# chromebook_toggle/paths.py), and updates are installed by an administrator
# with the one command the app shows after downloading the new package.
#
# Requires fpm (gem install fpm) and, for the .rpm, the 'rpm' tools; the CI
# workflow installs both.
# =============================================================================
set -euo pipefail

VER="${1:?usage: build-linux-packages.sh <version>}"
APPDIR="dist/ChromebookToggle"
MAINT="Gabriel Clifton <gurugabe@users.noreply.github.com>"
URL="https://github.com/GuruGabe/Chromebook-Toggle-Tool"
DESC="Chromebook Toggle Tool - a point-and-click window for disabling, re-enabling and deprovisioning Chromebooks through GAM."

if [ ! -d "$APPDIR" ]; then
    echo "ERROR: $APPDIR not found. Run build-app.sh first." >&2
    exit 1
fi

# Build a staging tree that mirrors where the files install on the target.
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/opt/ChromebookToggle" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
cp -R "$APPDIR/." "$STAGE/opt/ChromebookToggle/"

# A small launcher on PATH so people can just run "chromebooktoggle".
cat > "$STAGE/usr/bin/chromebooktoggle" <<'EOF'
#!/bin/sh
exec /opt/ChromebookToggle/ChromebookToggle "$@"
EOF
chmod 755 "$STAGE/usr/bin/chromebooktoggle"

# A desktop-menu entry so it shows up in the application launcher.
cat > "$STAGE/usr/share/applications/chromebooktoggle.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Chromebook Toggle Tool
Comment=$DESC
Exec=/opt/ChromebookToggle/ChromebookToggle
Terminal=false
Categories=Utility;System;
EOF

COMMON=(-s dir -n chromebooktoggle -v "$VER" --description "$DESC" --url "$URL"
        --maintainer "$MAINT" --license "Apache-2.0" -a amd64
        --category admin -C "$STAGE" .)

# .deb (Debian/Ubuntu)
rm -f chromebooktoggle_*.deb
fpm -t deb -p "chromebooktoggle_${VER}_amd64.deb" "${COMMON[@]}"

# .rpm (Fedora/RHEL). fpm uses its own arch label for rpm.
rm -f chromebooktoggle-*.rpm
fpm -t rpm -a x86_64 -p "chromebooktoggle-${VER}-1.x86_64.rpm" -s dir -n chromebooktoggle -v "$VER" \
    --description "$DESC" --url "$URL" --maintainer "$MAINT" \
    --license "Apache-2.0" --category admin -C "$STAGE" .

rm -rf "$STAGE"
echo "Built chromebooktoggle_${VER}_amd64.deb and chromebooktoggle-${VER}-1.x86_64.rpm"

#!/usr/bin/env bash
#
# Build a Debian/Ubuntu .deb package for Inkstone.
#
# Run on Linux (Debian/Ubuntu tested). Requires: python venv with the project deps,
# and dpkg-deb (present on any Debian-family system). Output:
#   dist/inkstone_<version>_<arch>.deb
#
# The package installs the PyInstaller bundle under /opt/inkstone with a launcher
# symlink at /usr/bin/inkstone, plus a desktop entry and icon so Inkstone appears
# in the application menu and can be set as the default PDF reader.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"   # repo root: contains main.py and packaging/
PY="${PYTHON:-$ROOT/.venv/bin/python}"

cd "$ROOT"

VERSION="$("$PY" -c "from version import __version__; print(__version__)")"
ARCH="$(dpkg --print-architecture)"

"$HERE/build_bundle.sh"

PKGDIR="build/deb/inkstone_${VERSION}_${ARCH}"
echo ">> Assembling package tree at $PKGDIR…"
rm -rf "$PKGDIR"
mkdir -p "$PKGDIR/DEBIAN" "$PKGDIR/opt/inkstone" "$PKGDIR/usr/bin" \
         "$PKGDIR/usr/share/applications" \
         "$PKGDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "dist/Inkstone/." "$PKGDIR/opt/inkstone/"
ln -s /opt/inkstone/Inkstone "$PKGDIR/usr/bin/inkstone"
cp "$ROOT/packaging/icon.png" "$PKGDIR/usr/share/icons/hicolor/256x256/apps/inkstone.png"

cp "$ROOT/packaging/inkstone.desktop" "$PKGDIR/usr/share/applications/inkstone.desktop"

# Qt is bundled by PyInstaller, but its xcb platform plugin still dlopens these
# system libraries at runtime.
DEPENDS="libc6, libgl1, libegl1, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0"

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$PKGDIR" | cut -f1)"

cat > "$PKGDIR/DEBIAN/control" <<CONTROL
Package: inkstone
Version: $VERSION
Section: text
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Depends: $DEPENDS
Maintainer: Shone Anstey <xpctechnology@gmail.com>
Homepage: https://github.com/ShoneAnstey/Inkstone
Description: Simple, lightweight tabbed PDF reader
 Inkstone is a no-bloat PDF reader for Linux and Windows that goes a little
 beyond reading: sign with a photo of your paper signature, fill with the
 typewriter tool, highlight, search, print, and reorganize pages.
 .
 Local-first: no AI, no cloud uploads, no telemetry. Released into the
 public domain (The Unlicense).
CONTROL

mkdir -p dist
DEB="dist/inkstone_${VERSION}_${ARCH}.deb"
echo ">> Building $DEB…"
dpkg-deb --build --root-owner-group "$PKGDIR" "$DEB"

echo ">> Done: $DEB"

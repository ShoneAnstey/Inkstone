#!/usr/bin/env bash
#
# Build a portable Linux AppImage for Inkstone.
#
# Run on Linux (Debian/Ubuntu tested). Requires: python venv with the project deps,
# plus internet access on first run to download appimagetool. Output:
#   dist/Inkstone-x86_64.AppImage
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"   # repo root: contains main.py and packaging/

cd "$ROOT"

"$HERE/build_bundle.sh"

APPDIR="build/AppDir"
echo ">> Assembling AppDir at $APPDIR…"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "dist/Inkstone/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/inkstone.png"
cp "$ROOT/packaging/icon.png" "$APPDIR/inkstone.png"

# Shared desktop entry, with Exec rewritten to the binary name inside the
# AppDir (AppRun forwards any file arguments).
sed 's|^Exec=.*|Exec=Inkstone %F|' "$ROOT/packaging/inkstone.desktop" \
    > "$APPDIR/usr/share/applications/inkstone.desktop"
cp "$APPDIR/usr/share/applications/inkstone.desktop" "$APPDIR/inkstone.desktop"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/Inkstone" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-x86_64.AppImage"
if [[ ! -x "$TOOL" ]]; then
    echo ">> Downloading appimagetool…"
    curl -L -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p dist
echo ">> Building AppImage…"
# --appimage-extract-and-run avoids needing FUSE on the build host.
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/Inkstone-x86_64.AppImage"

echo ">> Done: dist/Inkstone-x86_64.AppImage"

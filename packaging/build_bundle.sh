#!/usr/bin/env bash
#
# Shared step for the Linux packaging scripts: build the PyInstaller one-dir
# bundle at dist/Inkstone. Invoked by build_appimage.sh and build_deb.sh so
# both package formats always ship a bundle built by the exact same tooling.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"   # repo root: contains main.py and packaging/
PY="${PYTHON:-$ROOT/.venv/bin/python}"

cd "$ROOT"

echo ">> Installing build tooling (PyInstaller)…"
"$PY" -m pip install --quiet --upgrade pyinstaller

echo ">> Building one-dir bundle with PyInstaller…"
# Clear all of build/ — PyInstaller's work dir is build/inkstone (lowercase,
# named after the spec file), and stale Analysis caches there can leak
# removed modules into the bundle.
rm -rf build "dist/Inkstone"
"$PY" -m PyInstaller --noconfirm "$ROOT/packaging/inkstone.spec"

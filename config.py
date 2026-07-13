"""Cross-platform persistent settings via QSettings.

Stores the remembered signature image path, the last-used folder, and basic window
geometry. QSettings writes to the registry on Windows and to an INI/conf file under
~/.config on Linux, so there are no stray files to manage.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QStandardPaths

ORG = "XPC"
APP = "Inkstone"
_LEGACY_APP = "XPDF"  # pre-rename settings live under this name

_SIGNATURE_PATH = "signature/path"
_LAST_DIR = "files/last_dir"
_WINDOW_GEOMETRY = "window/geometry"
_WINDOW_STATE = "window/state"
_RECENT_FILES = "files/recent"
_DARK_MODE = "ui/dark_mode"
_SIDEBAR_VISIBLE = "ui/sidebar_visible"
_ZOOM_MODE = "ui/zoom_mode"
_ZOOM_LEVEL = "ui/zoom_level"

ZOOM_MODES = ("fit_width", "fit_page", "custom")
# Zoom bounds live here (not in the view code) so the persisted level is
# clamped to the same range the viewer enforces.
ZOOM_MIN = 0.25
ZOOM_MAX = 5.0


_migrated = False


def _migrate_legacy_settings() -> None:
    """One-time copy of settings saved under the old app name (XPDF).

    Runs at most once per process, and only writes when the new store is
    still empty — so an existing Inkstone profile is never clobbered.
    """
    global _migrated
    if _migrated:
        return
    _migrated = True
    new = QSettings(ORG, APP)
    if new.allKeys():
        return
    old = QSettings(ORG, _LEGACY_APP)
    keys = old.allKeys()
    if not keys:
        return
    for key in keys:
        new.setValue(key, old.value(key))
    new.sync()


def _settings() -> QSettings:
    _migrate_legacy_settings()
    return QSettings(ORG, APP)

def get_recent_files() -> list[str]:
    value = _settings().value(_RECENT_FILES, [])
    # QSettings stores string lists, but a single-entry list can come back as a
    # plain string on some backends.
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def set_recent_files(paths: list[str]) -> None:
    _settings().setValue(_RECENT_FILES, list(paths))


def get_existing_recent_files() -> list[str]:
    """Recent files whose paths still exist on disk.

    Prunes dead entries from storage so the list doesn't accumulate stale
    paths forever. The single pruning policy for every recents UI surface.
    """
    recent = get_recent_files()
    existing = [p for p in recent if os.path.exists(p)]
    if existing != recent:
        set_recent_files(existing)
    return existing


def add_recent_file(path: str) -> None:
    recent = get_recent_files()
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    set_recent_files(recent[:10])  # keep top 10


def remove_recent_file(path: str) -> None:
    recent = get_recent_files()
    if path in recent:
        recent.remove(path)
        set_recent_files(recent)


def clear_recent_files() -> None:
    _settings().remove(_RECENT_FILES)


def get_signature_path() -> str | None:
    value = _settings().value(_SIGNATURE_PATH)
    return str(value) if value else None


def set_signature_path(path: str) -> None:
    _settings().setValue(_SIGNATURE_PATH, path)


def clear_signature_path() -> None:
    _settings().remove(_SIGNATURE_PATH)


def get_last_dir() -> str | None:
    value = _settings().value(_LAST_DIR)
    return str(value) if value else None


def set_last_dir(path: str) -> None:
    _settings().setValue(_LAST_DIR, path)


def get_window_geometry():
    return _settings().value(_WINDOW_GEOMETRY)


def set_window_geometry(geometry) -> None:
    _settings().setValue(_WINDOW_GEOMETRY, geometry)


def get_dark_mode() -> bool:
    return bool(_settings().value(_DARK_MODE, False, type=bool))


def set_dark_mode(enabled: bool) -> None:
    _settings().setValue(_DARK_MODE, bool(enabled))


def get_sidebar_visible() -> bool:
    return bool(_settings().value(_SIDEBAR_VISIBLE, True, type=bool))


def set_sidebar_visible(visible: bool) -> None:
    _settings().setValue(_SIDEBAR_VISIBLE, bool(visible))


_zoom_pref_cache: tuple[str, float] | None = None


def get_zoom_mode() -> str:
    """Last-used zoom mode; documents open in this mode.

    "fit_width" is the first-run default so a document looks right on any
    monitor/DPI combination.
    """
    value = str(_settings().value(_ZOOM_MODE, "fit_width"))
    return value if value in ZOOM_MODES else "fit_width"


def get_zoom_level() -> float:
    """Last-used zoom factor (1.0 = 100%), used when the mode is "custom"."""
    try:
        value = float(str(_settings().value(_ZOOM_LEVEL, 1.5)))
    except (TypeError, ValueError):
        value = 1.5
    return max(ZOOM_MIN, min(ZOOM_MAX, value))


def set_zoom_pref(mode: str, level: float) -> None:
    """Persist zoom mode and level together, skipping the write when unchanged.

    The skip matters because this runs on every zoom action, including each
    Ctrl+wheel notch: without it every notch costs two settings-store syncs.
    """
    global _zoom_pref_cache
    if mode not in ZOOM_MODES:
        return
    pref = (mode, float(level))
    if pref == _zoom_pref_cache:
        return
    settings = _settings()
    settings.setValue(_ZOOM_MODE, mode)
    settings.setValue(_ZOOM_LEVEL, pref[1])
    _zoom_pref_cache = pref


def cache_dir() -> str:
    """Return a writable per-user cache directory for Inkstone, creating it if needed."""
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache", APP)
    os.makedirs(base, exist_ok=True)
    return base


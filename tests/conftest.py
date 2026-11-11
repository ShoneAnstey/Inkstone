"""Shared test fixtures.

Qt needs an application object before QImage/QPixmap rendering or any widget
works, and tests run headless, so force the offscreen platform plugin before Qt
is imported. Settings are redirected to a throwaway folder so a test run never
reads or writes the real Inkstone profile (recent files, zoom, signature).
"""

from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make the application modules importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """A single QApplication for the whole test session."""
    QStandardPaths.setTestModeEnabled(True)
    settings_dir = tempfile.mkdtemp(prefix="inkstone-test-settings-")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir)
    app = QApplication.instance() or QApplication([])
    yield app

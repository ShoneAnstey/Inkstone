"""Inkstone — a simple cross-platform PDF reader with signature stamping.

Entry point: creates the Qt application and shows the main window, or — when
Inkstone is already running — hands the files to that window and exits.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import single_instance
from version import __version__, version_line

# The main window pulls in the PDF engine (PyMuPDF), Pillow and the printing
# stack. It is imported inside main(), after the single-instance hand-off, so a
# launch that only passes its files to the running window — and `--version` —
# never pays for any of it.


def _icon_path() -> str:
    # Works both from source (packaging/icon.png) and from a PyInstaller bundle,
    # where data files are unpacked next to the executable under sys._MEIPASS.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
        os.path.join(base, "icon.png"),
        os.path.join(base, "packaging", "icon.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", "icon.png"),
    ):
        if os.path.exists(candidate):
            return candidate
    return ""


def _is_pdf_file(path: str) -> bool:
    """True if ``path`` is an existing PDF, by extension or %PDF header sniff."""
    if not os.path.isfile(path):
        return False
    if path.lower().endswith(".pdf"):
        return True
    try:
        with open(path, "rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def serve_window(window, parent=None):
    """Let later launches open their PDFs as new tabs in ``window``."""

    def open_from_other_launch(requested: list[str]) -> None:
        window.open_paths([p for p in requested if _is_pdf_file(p)])
        window.bring_to_front()

    return single_instance.serve(open_from_other_launch, parent=parent)


def main() -> int:
    if "--version" in sys.argv[1:] or "-V" in sys.argv[1:]:
        print(version_line())
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Inkstone")
    app.setApplicationDisplayName("Inkstone")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("XPC")

    # PDFs passed on the command line (e.g. a file association). Files without
    # a .pdf extension are accepted too if they have a PDF header.
    paths = [os.path.abspath(arg) for arg in sys.argv[1:] if _is_pdf_file(arg)]

    # Already running? Give it the files (it opens each in a new tab and comes
    # to the front) and exit.
    if single_instance.hand_off(paths):
        return 0

    from viewer import MainWindow

    icon = _icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))

    window = MainWindow()
    server = serve_window(window, app)  # noqa: F841 - keep it alive
    window.show()
    window.open_paths(paths)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

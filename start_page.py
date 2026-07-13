"""Start page shown when no document is open.

A simple landing view: app name, an Open button, and the recent-files list so
the last documents are one click away. MainWindow swaps between this page and
the tab widget depending on whether any document is open.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import config


class StartPage(QWidget):
    """Landing view for an empty window: open a file or reopen a recent one."""

    open_requested = Signal()
    file_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # The stacked layout hosting this page sizes itself to the max over
        # ALL pages, shown or not — without this, the start page's content
        # would dictate the window's minimum size even while a document is open.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # A fixed-width centered column keeps the page readable when maximized.
        column = QWidget(self)
        column.setMaximumWidth(560)
        layout = QVBoxLayout(column)
        layout.setSpacing(12)
        outer.addWidget(column)

        title = QLabel("Inkstone", column)
        font = title.font()
        font.setPointSize(28)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("A simple, no-bloat PDF reader.", column)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(subtitle)

        open_button = QPushButton("Open PDF…", column)
        open_button.clicked.connect(self.open_requested)
        layout.addWidget(open_button)

        self._recent_label = QLabel("Recent files", column)
        recent_font = self._recent_label.font()
        recent_font.setBold(True)
        self._recent_label.setFont(recent_font)
        layout.addWidget(self._recent_label)

        self._recent_list = QListWidget(column)
        self._recent_list.setMinimumHeight(220)
        # itemClicked covers the mouse; itemActivated covers Enter/Return for
        # keyboard users. Double-clicks fire both, but open_path already
        # focuses an existing tab instead of opening a duplicate.
        self._recent_list.itemClicked.connect(self._on_item_activated)
        self._recent_list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._recent_list)

        self._hint = QLabel("Files you open will show up here.", column)
        self._hint.setStyleSheet("color: gray;")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint)

        # Populated by refresh(); MainWindow calls it with the pruned list
        # whenever the recents change, so no settings I/O happens here.
        self.refresh([])

    def refresh(self, recent: list[str] | None = None) -> None:
        """Rebuild the recent-files list; fetches the pruned list if not given."""
        if recent is None:
            recent = config.get_existing_recent_files()

        self._recent_list.clear()
        self._recent_label.setVisible(bool(recent))
        self._recent_list.setVisible(bool(recent))
        self._hint.setVisible(not recent)

        for path in recent:
            item = QListWidgetItem(f"{os.path.basename(path)}\n{path}")
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._recent_list.addItem(item)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.file_selected.emit(path)

"""A collapsible navigation sidebar: page thumbnails and document outline.

The sidebar is driven by the currently-active DocumentTab. It shows two tabs:
- Thumbnails: a clickable preview of every page.
- Outline: the PDF's table of contents (bookmarks), if it has one.

Clicking either navigates the active document to the chosen page.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
)

THUMB_PX = 150
# Thumbnails are rendered in the background of the event loop, a slice at a
# time, so opening a 500-page PDF shows its first page immediately instead of
# waiting for 500 page renders. Each slice stops after this many milliseconds.
THUMB_SLICE_MS = 12.0


class Sidebar(QTabWidget):
    """Thumbnail + outline navigation for the active document."""

    # Emitted with a 0-based page index when the user picks a page.
    page_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(320)

        self._thumbs = QListWidget(self)
        self._thumbs.setIconSize(QSize(THUMB_PX, THUMB_PX))
        self._thumbs.setSpacing(4)
        self._thumbs.setUniformItemSizes(False)
        self._thumbs.itemClicked.connect(self._on_thumb_clicked)
        self.addTab(self._thumbs, "Pages")

        self._outline = QTreeWidget(self)
        self._outline.setHeaderHidden(True)
        self._outline.itemClicked.connect(self._on_outline_clicked)
        self.addTab(self._outline, "Outline")

        # Track what's currently displayed so we can skip a full, expensive
        # rebuild when the active document and its page set haven't changed.
        self._shown_path: str | None = None
        self._shown_version: int = -1

        # Lazy thumbnail rendering: pages still showing a placeholder, and the
        # document they belong to.
        self._doc = None
        self._pending: set[int] = set()
        self._placeholders: dict[tuple[int, int], QIcon] = {}
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(0)
        self._thumb_timer.timeout.connect(self._render_thumb_slice)

    def clear(self) -> None:
        self._thumb_timer.stop()
        self._pending.clear()
        self._doc = None
        self._thumbs.clear()
        self._outline.clear()
        self._shown_path = None
        self._shown_version = -1

    def load_document(self, doc) -> None:
        """Populate thumbnails and the outline from a PdfDocument.

        Rendering a thumbnail is costly, so: if we're asked to show the same
        document at the same structure version we already have on screen, we
        do nothing; otherwise every page gets a placeholder at once and the
        real thumbnails are filled in afterwards, visible pages first.
        """
        if doc is None or not doc.is_open:
            self.clear()
            return

        if doc.path == self._shown_path and doc.structure_version == self._shown_version:
            return

        self.clear()
        self._shown_path = doc.path
        self._shown_version = doc.structure_version

        self._doc = doc
        for i in range(doc.page_count):
            cached = doc.cached_thumbnail(i, THUMB_PX)
            if cached is not None:
                icon = QIcon(QPixmap.fromImage(cached))
            else:
                icon = self._placeholder(*doc.page_size_points(i))
                self._pending.add(i)
            item = QListWidgetItem(icon, f"{i + 1}")
            item.setData(Qt.UserRole, i)
            item.setTextAlignment(Qt.AlignHCenter)
            self._thumbs.addItem(item)
        if self._pending:
            self._thumb_timer.start()

        rows = doc.outline()
        if rows:
            self.setTabEnabled(1, True)
            stack: list[tuple[int, QTreeWidgetItem]] = []
            for level, title, page_index in rows:
                node = QTreeWidgetItem([title])
                node.setData(0, Qt.UserRole, page_index)
                # Find the right parent by walking back to a shallower level.
                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    stack[-1][1].addChild(node)
                else:
                    self._outline.addTopLevelItem(node)
                stack.append((level, node))
            self._outline.expandAll()
        else:
            # No bookmarks: grey out the Outline tab and show the Pages tab instead.
            self.setTabEnabled(1, False)
            self.setCurrentIndex(0)

    def _placeholder(self, width_pt: float, height_pt: float) -> QIcon:
        """A blank page the size its thumbnail will be, so the list doesn't jump."""
        longest = max(width_pt, height_pt) or 1.0
        size = (max(1, round(width_pt * THUMB_PX / longest)), max(1, round(height_pt * THUMB_PX / longest)))
        icon = self._placeholders.get(size)
        if icon is None:
            pixmap = QPixmap(*size)
            pixmap.fill(QColor(255, 255, 255))
            icon = QIcon(pixmap)
            self._placeholders[size] = icon
        return icon

    def _visible_rows(self) -> range:
        """Rows currently scrolled into view (empty if the list isn't laid out)."""
        viewport = self._thumbs.viewport()
        top = self._thumbs.indexAt(QPoint(viewport.width() // 2, 4)).row()
        if top < 0:
            return range(0)
        bottom = self._thumbs.indexAt(QPoint(viewport.width() // 2, max(4, viewport.height() - 4))).row()
        if bottom < 0:
            bottom = self._thumbs.count() - 1
        return range(top, bottom + 1)

    def _render_thumb_slice(self) -> None:
        """Render placeholders into thumbnails for a few milliseconds, then yield."""
        doc = self._doc
        if doc is None or not doc.is_open or doc.structure_version != self._shown_version:
            self._thumb_timer.stop()
            self._pending.clear()
            return
        deadline = time.perf_counter() + THUMB_SLICE_MS / 1000.0
        while self._pending:
            # What the user can see comes first; the rest follow in page order.
            index = next((row for row in self._visible_rows() if row in self._pending), None)
            if index is None:
                index = min(self._pending)
            self._pending.discard(index)
            item = self._thumbs.item(index)
            if item is not None:
                item.setIcon(QIcon(QPixmap.fromImage(doc.render_thumbnail(index, THUMB_PX))))
            if time.perf_counter() >= deadline:
                break
        if not self._pending:
            self._thumb_timer.stop()

    def highlight_page(self, index: int) -> None:
        """Reflect the current page in the thumbnail list without re-navigating."""
        if 0 <= index < self._thumbs.count():
            self._thumbs.blockSignals(True)
            self._thumbs.setCurrentRow(index)
            self._thumbs.blockSignals(False)

    def _on_thumb_clicked(self, item: QListWidgetItem) -> None:
        self.page_selected.emit(int(item.data(Qt.UserRole)))

    def _on_outline_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if data is not None:
            self.page_selected.emit(int(data))

"""Main-window behaviour: tabs, the Save action, unsaved-change markers and prompts."""

from __future__ import annotations

import fitz
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QToolBar

import document_tab
from viewer import MainWindow


def make_pdf(path: str, pages: int = 3) -> str:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Hello page {i + 1}", fontsize=12)
    doc.save(path)
    doc.close()
    return path


def page_texts(path: str) -> list[str]:
    with fitz.open(path) as check:
        return [page.get_text() for page in check]


@pytest.fixture
def window():
    win = MainWindow()
    win.resize(1000, 800)
    win.show()
    QApplication.processEvents()
    yield win
    for i in range(win.tabs.count()):
        win.tabs.widget(i).close_document()
    win.hide()
    win.deleteLater()


@pytest.fixture
def pdf(tmp_path) -> str:
    return make_pdf(str(tmp_path / "doc.pdf"))


def open_tab(win: MainWindow, path: str):
    win.open_path(path)
    for _ in range(5):
        QApplication.processEvents()  # initial fit + first layout
    return win.current_tab()


def answer(monkeypatch, button) -> list[str]:
    """Make every message box the tab shows answer ``button``; returns the prompts shown."""
    shown: list[str] = []

    def fake(_parent, title, text, *_args, **_kwargs):
        shown.append(f"{title}: {text}")
        return button

    for kind in ("warning", "question", "critical", "information"):
        monkeypatch.setattr(document_tab.QMessageBox, kind, staticmethod(fake))
    return shown


def type_note(tab, text: str = "NOTE") -> None:
    assert tab.add_text()
    tab._texts[-1].setPlainText(text)


# ----- tabs ----------------------------------------------------------------------
def test_each_pdf_opens_in_its_own_tab(window, tmp_path):
    a = make_pdf(str(tmp_path / "a.pdf"))
    b = make_pdf(str(tmp_path / "b.pdf"))
    window.open_paths([a, b])
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["a.pdf", "b.pdf"]
    assert window.tabs.currentIndex() == 1
    # Re-opening an open file focuses its tab instead of adding another.
    window.open_path(a)
    assert window.tabs.count() == 2 and window.tabs.currentIndex() == 0


# ----- save ----------------------------------------------------------------------
def test_save_is_a_first_class_action(window):
    file_menu = next(m for m in window.findChildren(QMenu) if m.title() == "File")
    assert window.act_save in file_menu.actions()
    assert window.act_save.shortcut() == QKeySequence(QKeySequence.StandardKey.Save)
    assert any(window.act_save in bar.actions() for bar in window.findChildren(QToolBar))
    # Nothing open, nothing to save.
    assert not window.act_save.isEnabled()


def test_ctrl_s_saves(window, pdf):
    tab = open_tab(window, pdf)
    type_note(tab)
    tab.scene.clearFocus()  # typing focus is in the note; Ctrl+S must still reach the window
    tab.view.setFocus()
    window.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(tab.view, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert "NOTE" in page_texts(pdf)[0]
    assert not tab.modified


def test_annotation_marks_the_tab_unsaved_and_save_overwrites_the_file(window, pdf):
    tab = open_tab(window, pdf)
    assert not tab.modified and not window.act_save.isEnabled()
    assert window.tabs.tabText(0) == "doc.pdf"

    type_note(tab)
    assert tab.modified and window.act_save.isEnabled()
    assert window.tabs.tabText(0) == "\u25cf doc.pdf"
    assert "NOTE" not in page_texts(pdf)[0]  # not on disk yet

    window.act_save.trigger()
    assert "NOTE" in page_texts(pdf)[0]  # the open file itself was overwritten
    assert not tab.modified and not window.act_save.isEnabled()
    assert window.tabs.tabText(0) == "doc.pdf"
    assert tab.path == pdf and tab.doc.is_open and tab.doc.page_count == 3


def test_page_changes_wait_for_save(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    answer(monkeypatch, QMessageBox.Yes)  # "Delete page 2?"
    assert tab.rotate_page(0, 90)
    assert tab.delete_page(1)
    assert tab.doc.page_count == 2
    assert tab.modified and window.act_save.isEnabled()
    assert window.tabs.tabText(0).startswith("\u25cf")
    # The file still has all three pages, unrotated.
    with fitz.open(pdf) as check:
        assert check.page_count == 3 and check[0].rotation == 0

    window.act_save.trigger()
    with fitz.open(pdf) as check:
        assert check.page_count == 2 and check[0].rotation == 90
        assert "page 3" in check[1].get_text()
    assert not tab.modified and window.tabs.tabText(0) == "doc.pdf"


def test_annotation_survives_a_page_change_and_both_are_saved(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    answer(monkeypatch, QMessageBox.Yes)
    tab.goto_page(2)
    QApplication.processEvents()
    type_note(tab, "ON THREE")  # placed on page 3
    assert tab.delete_page(0)  # no "discard your annotations?" prompt any more
    assert len(tab._texts) == 1  # the note followed its page (now page 2)
    window.act_save.trigger()
    texts = page_texts(pdf)
    assert len(texts) == 2
    assert "page 3" in texts[1] and "ON THREE" in texts[1]
    assert "ON THREE" not in texts[0]


def test_annotation_on_a_deleted_page_goes_with_it(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    answer(monkeypatch, QMessageBox.Yes)
    type_note(tab, "ON ONE")  # placed on page 1
    assert tab.delete_page(0)
    assert tab._texts == []
    window.act_save.trigger()
    assert all("ON ONE" not in text for text in page_texts(pdf))


def test_save_as_writes_a_copy_and_leaves_the_tab_on_the_original(window, pdf, tmp_path):
    tab = open_tab(window, pdf)
    type_note(tab)
    copy = str(tmp_path / "copy.pdf")
    assert tab.save_as(copy, None)
    assert "NOTE" in page_texts(copy)[0]
    assert "NOTE" not in page_texts(pdf)[0]
    assert tab.path == pdf and tab.modified


def test_refused_overwrite_explains_and_keeps_the_changes(window, pdf, monkeypatch):
    import pdf_document

    tab = open_tab(window, pdf)
    type_note(tab)
    shown = answer(monkeypatch, QMessageBox.Ok)

    def refuse(src, dst):
        raise PermissionError(13, "Access is denied", dst)

    monkeypatch.setattr(pdf_document.os, "replace", refuse)
    window.act_save.trigger()
    assert any("read-only or open in another program" in s and "Save As" in s for s in shown)
    assert tab.modified and len(tab._texts) == 1 and window.act_save.isEnabled()
    assert "NOTE" not in page_texts(pdf)[0]


# ----- closing with unsaved changes --------------------------------------------------
def test_closing_an_unchanged_tab_asks_nothing(window, pdf, monkeypatch):
    open_tab(window, pdf)
    shown = answer(monkeypatch, QMessageBox.Cancel)
    window.close_tab(0)
    assert shown == [] and window.tabs.count() == 0


def test_close_prompt_cancel_keeps_the_tab(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    type_note(tab)
    shown = answer(monkeypatch, QMessageBox.Cancel)
    window.close_tab(0)
    assert len(shown) == 1 and "Save changes to doc.pdf" in shown[0]
    assert window.tabs.count() == 1 and tab.modified


def test_close_prompt_save_writes_then_closes(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    type_note(tab)
    answer(monkeypatch, QMessageBox.Save)
    window.close_tab(0)
    assert window.tabs.count() == 0
    assert "NOTE" in page_texts(pdf)[0]


def test_close_prompt_discard_closes_without_writing(window, pdf, monkeypatch):
    tab = open_tab(window, pdf)
    before = open(pdf, "rb").read()
    answer(monkeypatch, QMessageBox.Yes)
    type_note(tab)
    assert tab.delete_page(2)
    answer(monkeypatch, QMessageBox.Discard)
    window.close_tab(0)
    assert window.tabs.count() == 0
    assert open(pdf, "rb").read() == before


# ----- sidebar ------------------------------------------------------------------------
def test_thumbnails_are_filled_in_lazily(window, tmp_path):
    big = make_pdf(str(tmp_path / "big.pdf"), pages=40)
    tab = open_tab(window, big)
    thumbs = window.sidebar._thumbs
    assert thumbs.count() == 40  # every page has an entry straight away...
    assert tab.doc.cached_thumbnail(39, 150) is None or window.sidebar._pending == set()
    for _ in range(400):  # ...and the real thumbnails arrive over the next event-loop turns
        if not window.sidebar._pending:
            break
        QApplication.processEvents()
    assert window.sidebar._pending == set()
    assert tab.doc.cached_thumbnail(39, 150) is not None

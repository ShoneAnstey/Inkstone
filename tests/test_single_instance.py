"""Single-instance hand-off: a second launch gives its PDFs to the running window."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

import fitz
import pytest
from PySide6.QtWidgets import QApplication

import single_instance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_pdf(path: str, pages: int = 2) -> str:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"page {i + 1}")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def user(monkeypatch) -> str:
    """A throwaway user name, so the test's socket can't collide with a real Inkstone."""
    name = f"inktest-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("LOGNAME", name)
    monkeypatch.setenv("USER", name)
    monkeypatch.setenv("USERNAME", name)
    return name


def spin_until(condition, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def launch(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.Popen:
    """Start `python main.py ARGS` as a separate process, headless, with its own settings."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.update(env_extra or {})
    return subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "main.py"), *args],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_request_round_trip(tmp_path):
    paths = [str(tmp_path / "a.pdf"), str(tmp_path / "né w.pdf")]
    assert single_instance.decode_request(single_instance.encode_request(paths).strip()) == paths
    assert single_instance.decode_request(single_instance.encode_request([]).strip()) == []


@pytest.mark.parametrize(
    "junk",
    [b"", b"not json", b"[1, 2]", b'{"open": "a.pdf"}', b'{"open": [1]}', b'{"other": []}', b"\xff\xfe"],
)
def test_malformed_requests_are_rejected(junk):
    assert single_instance.decode_request(junk) is None


def test_socket_name_is_per_user(user):
    assert single_instance.socket_name() == f"inkstone-{user}"


def test_hand_off_without_a_running_instance(user):
    assert single_instance.hand_off(["/nowhere/a.pdf"]) is False


def test_second_launch_opens_its_pdfs_as_tabs_in_the_running_window(user, tmp_path, monkeypatch):
    import main
    from viewer import MainWindow

    first = make_pdf(str(tmp_path / "first.pdf"))
    second = make_pdf(str(tmp_path / "second.pdf"))
    third = make_pdf(str(tmp_path / "third.pdf"))
    not_a_pdf = tmp_path / "notes.txt"
    not_a_pdf.write_text("hello")

    window = MainWindow()
    raised = []
    monkeypatch.setattr(window, "bring_to_front", lambda: raised.append(True))
    server = main.serve_window(window)
    try:
        window.open_paths([first])
        assert window.tabs.count() == 1

        # A second launch of the real entry point, in another process.
        started = time.monotonic()
        proc = launch(second, third, str(not_a_pdf))
        assert spin_until(lambda: proc.poll() is not None), "second launch did not exit"
        elapsed = time.monotonic() - started
        assert proc.returncode == 0, proc.stderr.read().decode()
        assert spin_until(lambda: window.tabs.count() == 3)

        titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert titles == ["first.pdf", "second.pdf", "third.pdf"]
        assert window.tabs.currentIndex() == 2  # the newest file is in front
        assert raised, "the running window was not brought to the front"
        # It handed off instead of building a window of its own (generous bound for slow CI).
        assert elapsed < 10

        # Opening a file that is already open focuses its tab rather than duplicating it.
        proc = launch(first)
        assert spin_until(lambda: proc.poll() is not None)
        assert spin_until(lambda: window.tabs.currentIndex() == 0)
        assert window.tabs.count() == 3

        # A launch with no file just surfaces the window.
        raised.clear()
        proc = launch()
        assert spin_until(lambda: proc.poll() is not None)
        assert spin_until(lambda: bool(raised))
        assert window.tabs.count() == 3
    finally:
        server.close()
        for i in range(window.tabs.count()):
            window.tabs.widget(i).close_document()
        window.deleteLater()


def test_version_flag_does_not_need_a_display_or_a_running_instance(user):
    proc = launch("--version")
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err.decode()
    assert out.decode().startswith("Inkstone ")

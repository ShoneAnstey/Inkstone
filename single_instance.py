"""One Inkstone window per user: later launches hand their files to it.

The first instance listens on a per-user local socket (a named pipe on
Windows). A second launch connects, sends the PDF paths it was asked to open,
and exits; the running window opens each in a new tab and comes to the front.
Double-clicking PDFs in a file manager therefore fills one window with tabs
instead of scattering windows — and the second launch never has to load the
PDF engine or build a window, so it is close to instant.

Wire format, one line each way:
    server -> client   "<pid>\\n"            (so the client can let it take focus)
    client -> server   '{"open": [paths]}\\n'
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

CONNECT_TIMEOUT_MS = 150
IO_TIMEOUT_MS = 500
# A request is a list of paths; anything bigger than this is not one of ours.
MAX_REQUEST_BYTES = 1_000_000


def socket_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no usable user name; still single-instance per machine
        user = "user"
    return f"inkstone-{user}"


def encode_request(paths: list[str]) -> bytes:
    return (json.dumps({"open": [os.path.abspath(p) for p in paths]}) + "\n").encode("utf-8")


def decode_request(data: bytes) -> list[str] | None:
    """Paths from a request line, or None if it isn't a well-formed request."""
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    paths = message.get("open")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return None
    return paths


def _allow_foreground(pid: int) -> None:
    """Let the running instance raise its window (Windows blocks focus stealing).

    Only a process that currently owns the foreground — this freshly launched
    one — can grant that right.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(pid)
    except Exception:  # noqa: BLE001 - cosmetic; the taskbar button flashes instead
        pass


def hand_off(paths: list[str]) -> bool:
    """Send ``paths`` to a running instance. False if there isn't one."""
    socket = QLocalSocket()
    socket.connectToServer(socket_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    if socket.waitForReadyRead(IO_TIMEOUT_MS):
        try:
            _allow_foreground(int(bytes(socket.readLine().data()).strip()))
        except ValueError:
            pass
    socket.write(encode_request(paths))
    socket.flush()
    socket.waitForBytesWritten(IO_TIMEOUT_MS)
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(IO_TIMEOUT_MS)
    return True


def serve(on_open: Callable[[list[str]], None], parent: QObject | None = None) -> QLocalServer:
    """Listen for later launches; ``on_open(paths)`` runs for each one."""
    name = socket_name()
    QLocalServer.removeServer(name)  # clear a stale socket left by a crash
    server = QLocalServer(parent)
    # Same-user only: nobody else on the machine can ask this window to open files.
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(name)

    def handle_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        buffer = bytearray()
        connection.write(f"{os.getpid()}\n".encode())
        connection.flush()

        def read() -> None:
            buffer.extend(bytes(connection.readAll().data()))
            if len(buffer) > MAX_REQUEST_BYTES:
                connection.abort()
                return
            if b"\n" not in buffer:
                return
            line = bytes(buffer).split(b"\n", 1)[0]
            buffer.clear()
            paths = decode_request(line)
            if paths is not None:
                on_open(paths)
            connection.disconnectFromServer()

        connection.readyRead.connect(read)
        connection.disconnected.connect(connection.deleteLater)
        if connection.bytesAvailable():
            read()

    server.newConnection.connect(handle_connection)
    return server

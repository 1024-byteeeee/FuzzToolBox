"""Cross-platform single-instance coordination using Qt local IPC."""

from __future__ import annotations

import hashlib
from enum import Enum, auto

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .app_settings import application_root


class InstanceRole(Enum):
    PRIMARY = auto()
    SECONDARY = auto()


class SingleInstanceCoordinator(QObject):
    """Own the application IPC endpoint or notify the existing owner."""

    activation_requested = Signal()
    _ACTIVATE_MESSAGE = b"activate\n"
    _ACTIVATED_REPLY = b"activated\n"

    def __init__(self, server_name: str, parent: QObject | None = None):
        super().__init__(parent)
        self.server_name = server_name
        digest = hashlib.sha256(server_name.encode("utf-8")).hexdigest()[:20]
        self.lock_path = application_root() / f"fuzztoolbox-{digest}.lock"
        self.lock = QLockFile(str(self.lock_path))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._accept_connections)

    def acquire(self) -> InstanceRole:
        if not self.lock.tryLock(0):
            self._notify_existing_instance()
            return InstanceRole.SECONDARY

        # Only the lock owner may remove a stale IPC endpoint.  This prevents a
        # simultaneous second launch from unlinking the active primary server.
        QLocalServer.removeServer(self.server_name)
        if self.server.listen(self.server_name):
            return InstanceRole.PRIMARY
        self.lock.unlock()
        return InstanceRole.SECONDARY

    def close(self) -> None:
        if self.server.isListening():
            self.server.close()
            QLocalServer.removeServer(self.server_name)
        if self.lock.isLocked():
            self.lock.unlock()

    def _notify_existing_instance(self) -> bool:
        # The primary can hold the lock just before its server starts listening,
        # so allow a short bounded startup race without ever starting a second UI.
        for _attempt in range(10):
            socket = QLocalSocket()
            socket.connectToServer(self.server_name)
            if socket.waitForConnected(100):
                socket.write(self._ACTIVATE_MESSAGE)
                socket.flush()
                if socket.bytesToWrite() > 0 and not socket.waitForBytesWritten(250):
                    socket.abort()
                    continue
                acknowledged = socket.waitForReadyRead(1000) and (
                    self._ACTIVATED_REPLY.strip() in bytes(socket.readAll())
                )
                socket.disconnectFromServer()
                return acknowledged
            socket.abort()
        return False

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda sock=socket: self._read_message(sock))
            socket.disconnected.connect(socket.deleteLater)
            self._read_message(socket)

    def _read_message(self, socket: QLocalSocket) -> None:
        if self._ACTIVATE_MESSAGE.strip() in bytes(socket.readAll()):
            self.activation_requested.emit()
            socket.write(self._ACTIVATED_REPLY)
            socket.flush()

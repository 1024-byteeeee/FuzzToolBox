"""Cross-platform single-instance coordination using Qt local IPC."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .app_settings import application_root


class InstanceRole(Enum):
    PRIMARY = auto()
    SECONDARY = auto()


RUNTIME_PROTOCOL_VERSION = 1


def _runtime_file_path(directory: Path, server_name: str, suffix: str) -> Path:
    digest = hashlib.sha256(server_name.encode("utf-8")).hexdigest()[:20]
    return directory / f"fuzztoolbox-{digest}.{suffix}.json"


def ready_marker_path(directory: str | Path, server_name: str) -> Path:
    """Return the process-ready marker used by frozen application smoke tests."""
    return _runtime_file_path(Path(directory), server_name, "ready")


def activation_marker_path(directory: str | Path, server_name: str) -> Path:
    """Return the marker updated after an existing window is restored."""
    return _runtime_file_path(Path(directory), server_name, "activation")


class SingleInstanceCoordinator(QObject):
    """Own the application IPC endpoint or notify the existing owner."""

    activation_requested = Signal()
    _ACTIVATE_MESSAGE = b"activate\n"
    _ACTIVATED_REPLY = b"activated\n"
    _ACTIVATION_FAILED_REPLY = b"activation-failed\n"

    def __init__(
        self,
        server_name: str,
        parent: QObject | None = None,
        *,
        runtime_dir: str | Path | None = None,
    ):
        super().__init__(parent)
        self.server_name = server_name
        digest = hashlib.sha256(server_name.encode("utf-8")).hexdigest()[:20]
        if runtime_dir is None:
            lock_directory = application_root()
            self.ipc_name = server_name
        else:
            lock_directory = Path(runtime_dir).resolve()
            lock_directory.mkdir(parents=True, exist_ok=True)
            namespace = f"{lock_directory}\0{server_name}".encode()
            namespace_digest = hashlib.sha256(namespace).hexdigest()[:20]
            self.ipc_name = f"fuzztoolbox-{namespace_digest}"

        self.lock_path = lock_directory / f"fuzztoolbox-{digest}.lock"
        self.ready_path = ready_marker_path(lock_directory, server_name)
        self.activation_path = activation_marker_path(lock_directory, server_name)
        self.lock = QLockFile(str(self.lock_path))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._accept_connections)
        self.notification_succeeded = False
        self._owns_instance = False
        self._activation_probe: Callable[[], bool] | None = None
        self._activation_sequence = 0

    def acquire(self) -> InstanceRole:
        if not self.lock.tryLock(0):
            self.notification_succeeded = self._notify_existing_instance()
            return InstanceRole.SECONDARY

        # Only the lock owner may remove a stale IPC endpoint.  This prevents a
        # simultaneous second launch from unlinking the active primary server.
        self._remove_runtime_markers()
        QLocalServer.removeServer(self.ipc_name)
        if self.server.listen(self.ipc_name):
            self._owns_instance = True
            return InstanceRole.PRIMARY
        self.lock.unlock()
        return InstanceRole.SECONDARY

    def publish_ready(self, activation_probe: Callable[[], bool]) -> bool:
        """Publish readiness only after the native main window is visible."""
        if not self._owns_instance or not activation_probe():
            return False
        self._activation_probe = activation_probe
        return self._write_marker(
            self.ready_path,
            {
                "protocol": RUNTIME_PROTOCOL_VERSION,
                "pid": os.getpid(),
                "window_visible": True,
            },
        )

    def close(self) -> None:
        if self.server.isListening():
            self.server.close()
            QLocalServer.removeServer(self.ipc_name)
        if self._owns_instance:
            self._remove_runtime_markers()
            self._owns_instance = False
        if self.lock.isLocked():
            self.lock.unlock()

    def _notify_existing_instance(self) -> bool:
        # The primary can hold the lock just before its server starts listening,
        # so allow a short bounded startup race without ever starting a second UI.
        for _attempt in range(10):
            socket = QLocalSocket()
            socket.connectToServer(self.ipc_name)
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
            # Qt signals in the GUI thread are delivered synchronously.  The
            # restore slot has therefore requested a visible native window by
            # the time it returns, and the probe can gate the acknowledgement
            # without retaining a QLocalSocket past its lifetime.
            self._finish_activation(socket)

    def _finish_activation(self, socket: QLocalSocket) -> None:
        visible = bool(self._activation_probe and self._activation_probe())
        reply = self._ACTIVATION_FAILED_REPLY
        if visible:
            self._activation_sequence += 1
            marker_written = self._write_marker(
                self.activation_path,
                {
                    "protocol": RUNTIME_PROTOCOL_VERSION,
                    "pid": os.getpid(),
                    "sequence": self._activation_sequence,
                    "window_visible": True,
                },
            )
            if marker_written:
                reply = self._ACTIVATED_REPLY
        socket.write(reply)
        socket.flush()

    def _write_marker(self, path: Path, payload: dict[str, object]) -> bool:
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError:
            return False
        return True

    def _remove_runtime_markers(self) -> None:
        self.ready_path.unlink(missing_ok=True)
        self.activation_path.unlink(missing_ok=True)

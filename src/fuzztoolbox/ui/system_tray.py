"""Windows system tray integration."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCursor, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class SystemTrayController:
    def __init__(self, window, icon_path):
        self.window = window
        self.tray = QSystemTrayIcon(QIcon(str(icon_path)), window)
        self.tray.setToolTip("FuzzToolBox")
        menu = QMenu(window)
        menu.setObjectName("trayMenu")
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(window.restore_from_tray)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(window.request_application_quit)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.menu = menu
        self.actions = (show_action, quit_action)
        self.tray.activated.connect(self._activated)
        self.tray.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.window.restore_from_tray()
        elif reason == QSystemTrayIcon.Context:
            # Do not bind the menu through setContextMenu(): Windows converts
            # that path into a native menu which ignores the application's QSS.
            self.menu.popup(QCursor.pos())

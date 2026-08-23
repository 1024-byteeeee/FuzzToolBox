"""Windows system tray integration."""

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class SystemTrayController:
    def __init__(self, window, icon_path):
        self.window = window
        self.tray = QSystemTrayIcon(QIcon(str(icon_path)), window)
        self.tray.setToolTip("FuzzToolBox")
        menu = QMenu()
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(window.restore_from_tray)
        picker_action = QAction("屏幕取色", menu)
        picker_action.triggered.connect(window.start_color_picker)
        screenshot_action = QAction("截图", menu)
        screenshot_action.triggered.connect(window.start_screenshot)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(window.request_application_quit)
        menu.addAction(show_action)
        menu.addAction(picker_action)
        menu.addAction(screenshot_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.menu = menu
        self.actions = (show_action, picker_action, screenshot_action, quit_action)
        self.tray.activated.connect(self._activated)
        self.tray.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.window.restore_from_tray()

"""Lightweight startup screen shown while the toolbox UI is imported."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from .. import __version__


SPLASH_SIZE = (500, 400)


def create_splash_screen() -> QSplashScreen:
    """Create the startup screen without importing the heavyweight main window."""
    width, height = SPLASH_SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#f5f7fa"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#161b22"))

    title_font = QFont("Segoe UI", 38)
    title_font.setWeight(QFont.Bold)
    painter.setFont(title_font)
    painter.drawText(0, 92, width, 80, Qt.AlignCenter, "FuzzToolBox")

    version_font = QFont("Segoe UI", 11)
    painter.setFont(version_font)
    painter.setPen(QColor("#3f4752"))
    painter.drawText(0, 186, width, 28, Qt.AlignCenter, f"版本：{__version__}")

    description_font = QFont("Microsoft YaHei UI", 12)
    painter.setFont(description_font)
    painter.drawText(0, 232, width, 30, Qt.AlignCenter, "一站式桌面 IT 工具箱")

    copyright_font = QFont("Segoe UI", 9)
    painter.setFont(copyright_font)
    painter.setPen(QColor("#68717d"))
    painter.drawText(
        0,
        306,
        width,
        24,
        Qt.AlignCenter,
        "Copyright © 2026 1024_byteeeee. All rights reserved.",
    )
    painter.end()

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setObjectName("startupSplash")
    return splash


def show_splash_screen(app: QApplication) -> QSplashScreen:
    """Show and paint the splash immediately before expensive imports begin."""
    splash = create_splash_screen()
    splash.show()
    app.processEvents()
    return splash

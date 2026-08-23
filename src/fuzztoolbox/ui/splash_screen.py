"""Lightweight startup screen shown while the toolbox UI is imported."""

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from .. import __version__

SPLASH_SIZE = (500, 400)
APP_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "app-icon.png"


def _font(size: int, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont(QApplication.font().family(), size)
    font.setWeight(weight)
    return font


def create_splash_screen(device_pixel_ratio: Optional[float] = None) -> QSplashScreen:
    """Create the startup screen without importing the heavyweight main window."""
    width, height = SPLASH_SIZE
    if device_pixel_ratio is None:
        screen = QApplication.primaryScreen()
        device_pixel_ratio = screen.devicePixelRatio() if screen is not None else 1.0
    device_pixel_ratio = max(1.0, float(device_pixel_ratio))
    pixmap = QPixmap(
        math.ceil(width * device_pixel_ratio),
        math.ceil(height * device_pixel_ratio),
    )
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(QColor("#f5f7fa"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Quiet brand label and version badge establish a clear top edge.
    painter.setFont(_font(9, QFont.DemiBold))
    painter.setPen(QColor("#53708d"))
    painter.drawText(36, 34, 250, 22, Qt.AlignLeft | Qt.AlignVCenter, "FUZZTOOLBOX  /  DESKTOP UTILITIES")

    badge = QRectF(414, 30, 52, 26)
    badge_path = QPainterPath()
    badge_path.addRoundedRect(badge, 13, 13)
    painter.fillPath(badge_path, QColor("#e2f5f7"))
    painter.setFont(_font(9, QFont.DemiBold))
    painter.setPen(QColor("#087f8c"))
    painter.drawText(badge, Qt.AlignCenter, f"v{__version__}")

    # The existing vector app mark remains the visual anchor.
    icon_rect = QRectF(44, 112, 126, 126)
    icon = QIcon(str(APP_ICON_PATH))
    icon_pixmap = icon.pixmap(
        math.ceil(icon_rect.width() * device_pixel_ratio),
        math.ceil(icon_rect.height() * device_pixel_ratio),
    )
    painter.drawPixmap(icon_rect, icon_pixmap, QRectF(icon_pixmap.rect()))

    painter.setFont(_font(32, QFont.Bold))
    painter.setPen(QColor("#172a3d"))
    painter.drawText(194, 121, 272, 58, Qt.AlignLeft | Qt.AlignVCenter, "FuzzToolBox")

    painter.setFont(_font(13, QFont.Medium))
    painter.setPen(QColor("#3f5b73"))
    painter.drawText(196, 180, 270, 32, Qt.AlignLeft | Qt.AlignVCenter, "一站式桌面 IT 工具箱")

    painter.setFont(_font(10))
    painter.setPen(QColor("#71859a"))
    painter.drawText(196, 215, 270, 28, Qt.AlignLeft | Qt.AlignVCenter, "Preparing your workspace…")

    painter.setPen(QPen(QColor("#dde5ec"), 1))
    painter.drawLine(36, 292, 464, 292)
    painter.setFont(_font(8))
    painter.setPen(QColor("#7c8d9e"))
    painter.drawText(
        36,
        314,
        428,
        20,
        Qt.AlignLeft | Qt.AlignVCenter,
        "Copyright © 2026 1024_byteeeee. All rights reserved.",
    )
    painter.end()

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setObjectName("startupSplash")
    splash.setAttribute(Qt.WA_TransparentForMouseEvents)
    splash.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
    return splash


def show_splash_screen(app: QApplication) -> QSplashScreen:
    """Show and paint the splash immediately before expensive imports begin."""
    splash = create_splash_screen()
    splash.show()
    app.processEvents()
    return splash

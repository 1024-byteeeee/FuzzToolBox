"""Small, reusable motion primitives for the Qt widget interface."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
)
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QWidget
from shiboken6 import isValid

FAST_DURATION = 120
PAGE_DURATION = 180
THEME_DURATION = 220


def motion_enabled() -> bool:
    app = QApplication.instance()
    return app is not None and not bool(app.property("reduceMotion"))


class PageTransitionController(QObject):
    """Run one lightweight page entrance transition at a time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation = None
        self._widget = None

    def enter(self, widget: QWidget, vertical_offset: int = 8) -> None:
        if self.animation is not None:
            previous = self.animation
            previous.stop()
            self._finish(self._widget, previous)
        if not motion_enabled() or not widget.isVisible():
            return

        end_position = widget.pos()
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        widget.move(end_position + QPoint(0, vertical_offset))

        opacity = QPropertyAnimation(effect, b"opacity")
        opacity.setDuration(PAGE_DURATION)
        opacity.setStartValue(0.0)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.OutCubic)

        position = QPropertyAnimation(widget, b"pos")
        position.setDuration(PAGE_DURATION)
        position.setStartValue(widget.pos())
        position.setEndValue(end_position)
        position.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(opacity)
        group.addAnimation(position)
        group.finished.connect(lambda: self._finish(widget, group))
        self.animation = group
        self._widget = widget
        group.start(QAbstractAnimation.DeleteWhenStopped)

    def clear_widget(self, widget: QWidget | None = None) -> None:
        """Release any reference held for a page transition.

        Called when a tool page is disposed so the controller cannot keep a
        deleted page's Python wrapper (and its child objects) alive.
        """
        if widget is not None and self._widget is not widget:
            return
        if self.animation is not None:
            self.animation.stop()
            self.animation = None
        if self._widget is not None and isValid(self._widget):
            self._widget.setGraphicsEffect(None)
        self._widget = None

    def _finish(
        self,
        widget: QWidget | None,
        animation: QParallelAnimationGroup,
    ) -> None:
        if widget is not None and isValid(widget):
            widget.setGraphicsEffect(None)
        if self.animation is animation:
            self.animation = None
            self._widget = None


class ThemeTransitionController(QObject):
    """Cross-fade from a snapshot of the old theme to the new theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlay = None
        self.effect = None
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(THEME_DURATION)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._update_opacity)
        self.animation.finished.connect(self._cleanup)

    def transition(self, widget: QWidget, apply_change) -> None:
        self.animation.stop()
        self._cleanup()
        if not motion_enabled() or not widget.isVisible():
            apply_change()
            return

        snapshot = widget.grab()
        if snapshot.isNull():
            apply_change()
            return

        overlay = QLabel(widget)
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        overlay.setGeometry(widget.rect())
        overlay.setPixmap(snapshot)
        overlay.setScaledContents(True)
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        overlay.show()
        overlay.raise_()
        self.overlay = overlay
        self.effect = effect

        apply_change()
        self.animation.start()

    def _update_opacity(self, progress) -> None:
        if self.effect is not None:
            self.effect.setOpacity(1.0 - float(progress))

    def _cleanup(self) -> None:
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.deleteLater()
        self.overlay = None
        self.effect = None

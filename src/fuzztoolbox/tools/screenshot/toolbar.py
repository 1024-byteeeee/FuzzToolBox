"""Screenshot annotation toolbar and its transient option panels."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from fuzztoolbox.ui.style_loader import apply_style

from .controls import (
    ColorSwatchButton,
    ColorValueButton,
    ScreenshotScrollBar,
    SmoothSlider,
)


class ScreenshotToolbar(QFrame):
    """Own toolbar widgets, option panels, and their presentation state.

    The overlay consumes semantic signals and does not need to know how the
    controls are laid out or how transient panels are coordinated.
    """

    tool_changed = Signal(str, bool)
    color_changed = Signal(QColor)
    custom_color_requested = Signal()
    width_changed = Signal(float)
    font_size_changed = Signal(float)
    font_family_changed = Signal(str)
    undo_requested = Signal()
    save_requested = Signal()
    finish_requested = Signal()
    cancel_requested = Signal()

    HEIGHT = 50
    _PALETTE = (
        "#ff4d4f",
        "#ff8a00",
        "#ffd43b",
        "#19be6b",
        "#00b8d9",
        "#409eff",
        "#7c4dff",
        "#d946ef",
        "#ffffff",
        "#aeb6c2",
        "#202124",
        "#000000",
    )

    def __init__(
        self,
        parent,
        *,
        tools: Sequence[tuple[str, str]],
        color: QColor,
        width: float,
        font_size: float,
        font: QFont,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("screenshotToolbar")
        self.setCursor(Qt.ArrowCursor)
        self._font_family = font.family()
        self._build_toolbar(tools, width, font_size)
        self._build_color_palette()
        self._build_width_panel(width)
        self._build_font_size_panel(font_size)
        self._build_font_panel(font)
        for panel in (
            self.color_palette,
            self.width_panel,
            self.font_size_panel,
            self.font_panel,
        ):
            panel.setCursor(Qt.ArrowCursor)
        self.set_color(color)
        self.set_font_family(self._font_family, emit=False)
        self.resize(self.sizeHint().width(), self.HEIGHT)
        self._center_buttons()
        self.hide()

    def _build_toolbar(
        self,
        tools: Sequence[tuple[str, str]],
        width: float,
        font_size: float,
    ) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignVCenter)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)
        self._tool_buttons: dict[str, QPushButton] = {}
        for label, tool in tools:
            button = QPushButton(label)
            button.setObjectName("screenshotToolButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, value=tool: self.tool_changed.emit(
                    value, checked
                )
            )
            self.tool_group.addButton(button)
            self._tool_buttons[tool] = button
            layout.addWidget(button)

        self.color_button = ColorValueButton()
        self.color_button.setObjectName("screenshotColorButton")
        self.color_button.setFixedWidth(108)
        self.color_button.clicked.connect(
            lambda: self._toggle_panel(self.color_palette, self.color_button)
        )
        layout.addWidget(self.color_button)

        self.width_button = QPushButton(f"粗细 {width:g}")
        self.width_button.clicked.connect(
            lambda: self._toggle_panel(self.width_panel, self.width_button)
        )
        layout.addWidget(self.width_button)
        self.font_size_button = QPushButton(f"字号 {font_size:g}")
        self.font_size_button.clicked.connect(
            lambda: self._toggle_panel(self.font_size_panel, self.font_size_button)
        )
        layout.addWidget(self.font_size_button)
        self.font_button = QPushButton()
        self.font_button.setFixedWidth(138)
        self.font_button.clicked.connect(
            lambda: self._toggle_panel(self.font_panel, self.font_button)
        )
        layout.addWidget(self.font_button)

        for label, signal in (
            ("撤销", self.undo_requested),
            ("保存", self.save_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(signal.emit)
            layout.addWidget(button)
        finish = QPushButton("完成")
        finish.setObjectName("screenshotFinishButton")
        finish.clicked.connect(self.finish_requested.emit)
        layout.addWidget(finish)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(cancel)
        for button in self.findChildren(
            QPushButton, options=Qt.FindDirectChildrenOnly
        ):
            button.setFixedHeight(38)
            button.ensurePolished()
        self.ensurePolished()

    def _build_color_palette(self) -> None:
        self.color_palette = QFrame(self.parentWidget())
        self.color_palette.setObjectName("screenshotPopup")
        layout = QGridLayout(self.color_palette)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(10)
        self._swatches: list[ColorSwatchButton] = []
        for index, value in enumerate(self._PALETTE):
            swatch = ColorSwatchButton(value, self.color_palette)
            swatch.clicked.connect(
                lambda checked=False, selected=value: self._select_color(selected)
            )
            layout.addWidget(swatch, index // 6, index % 6)
            self._swatches.append(swatch)
        custom = QPushButton("自定义颜色")
        custom.setObjectName("screenshotPopupButton")
        custom.setFixedHeight(32)
        custom.clicked.connect(self._request_custom_color)
        layout.addWidget(custom, 2, 0, 1, 6)
        layout.setRowMinimumHeight(0, 28)
        layout.setRowMinimumHeight(1, 28)
        layout.setRowMinimumHeight(2, 32)
        self.color_palette.setFixedSize(self.color_palette.sizeHint())
        self.color_palette.hide()

    def _build_width_panel(self, width: float) -> None:
        self.width_panel = QFrame(self.parentWidget())
        self.width_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.width_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(QLabel("粗细"))
        self.width_slider = SmoothSlider(Qt.Horizontal)
        self.width_slider.setRange(10, 150)
        self.width_slider.setValue(round(width * 10))
        self.width_slider.setMinimumWidth(150)
        layout.addWidget(self.width_slider)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 15)
        self.width_spin.setDecimals(1)
        self.width_spin.setSingleStep(0.1)
        self.width_spin.setValue(width)
        self.width_spin.setSuffix(" px")
        self.width_spin.setFixedWidth(90)
        layout.addWidget(self.width_spin)
        self.width_slider.valueChanged.connect(
            lambda value: self.width_spin.setValue(value / 10)
        )
        self.width_spin.valueChanged.connect(
            lambda value: self.width_slider.setValue(round(value * 10))
        )
        self.width_spin.valueChanged.connect(self._width_value_changed)
        self.width_panel.adjustSize()
        self.width_panel.hide()

    def _build_font_size_panel(self, font_size: float) -> None:
        self.font_size_panel = QFrame(self.parentWidget())
        self.font_size_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.font_size_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(QLabel("字号"))
        self.font_size_slider = SmoothSlider(Qt.Horizontal)
        self.font_size_slider.setRange(100, 1000)
        self.font_size_slider.setValue(round(font_size * 10))
        self.font_size_slider.setMinimumWidth(150)
        layout.addWidget(self.font_size_slider)
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(10, 100)
        self.font_size_spin.setDecimals(1)
        self.font_size_spin.setSingleStep(0.5)
        self.font_size_spin.setValue(font_size)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedWidth(104)
        layout.addWidget(self.font_size_spin)
        self.font_size_slider.valueChanged.connect(
            lambda value: self.font_size_spin.setValue(value / 10)
        )
        self.font_size_spin.valueChanged.connect(
            lambda value: self.font_size_slider.setValue(round(value * 10))
        )
        self.font_size_spin.valueChanged.connect(self._font_size_value_changed)
        self.font_size_panel.adjustSize()
        self.font_size_panel.hide()

    def _build_font_panel(self, font: QFont) -> None:
        self.font_panel = QFrame(self.parentWidget())
        self.font_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.font_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(QLabel("字体"))
        self.font_combo = QFontComboBox()
        self.font_combo.setObjectName("screenshotFontCombo")
        font_view = self.font_combo.view()
        font_view.setObjectName("screenshotFontList")
        font_view.setFrameShape(QFrame.NoFrame)
        font_view.setAttribute(Qt.WA_MacShowFocusRect, False)
        font_scrollbar = ScreenshotScrollBar(Qt.Vertical, font_view)
        font_view.setVerticalScrollBar(font_scrollbar)
        font_scrollbar.setObjectName("screenshotFontScrollBar")
        font_scrollbar.setFocusPolicy(Qt.NoFocus)
        font_scrollbar.setAttribute(Qt.WA_MacShowFocusRect, False)
        apply_style(font_view, "tools.screenshot.overlay.font_list")
        apply_style(font_scrollbar, "tools.screenshot.overlay.font_scrollbar")
        self.font_combo.setMinimumWidth(240)
        self.font_combo.setCurrentFont(font)
        self.font_combo.currentFontChanged.connect(
            lambda selected: self._font_value_changed(selected.family())
        )
        layout.addWidget(self.font_combo)
        self.font_panel.adjustSize()
        self.font_panel.hide()

    def set_active_tool(self, tool: str, checked: bool) -> None:
        for other_tool, button in self._tool_buttons.items():
            if other_tool != tool:
                button.setChecked(False)
        if tool in self._tool_buttons:
            self._tool_buttons[tool].setChecked(checked)

    def set_color(self, color: QColor) -> None:
        selected = QColor(color)
        self.color_button.setProperty("colorValue", selected.name())
        self.color_button.set_display_color(selected)
        for swatch in self._swatches:
            swatch.setChecked(swatch.color == selected)
        self.color_button.style().unpolish(self.color_button)
        self.color_button.style().polish(self.color_button)

    def set_width(self, value: float) -> None:
        self.width_spin.setValue(float(value))

    def set_font_size(self, value: float) -> None:
        self.font_size_spin.setValue(float(value))

    def set_font_family(self, family: str, *, emit: bool = True) -> None:
        self._font_family = family or self.font().family()
        font = self.font_combo.currentFont()
        font.setFamily(self._font_family)
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentFont(font)
        self.font_combo.blockSignals(False)
        self._refresh_font_button()
        if emit:
            self.font_family_changed.emit(self._font_family)

    def position_for(self, selection: QRect, bounds: QRect) -> None:
        self.resize(self.sizeHint().width(), self.HEIGHT)
        self._center_buttons()
        x = min(
            max(8, selection.right() - self.width()),
            bounds.width() - self.width() - 8,
        )
        y = selection.bottom() + 10
        if y + self.height() > bounds.height() - 8:
            y = selection.top() - self.height() - 10
        self.move(x, max(8, y))

    def hide_popups(self) -> None:
        for panel in self._panels():
            panel.hide()

    def font_list_is_scrolling(self, event_type) -> bool:
        return self.font_combo.view().isVisible() and event_type in (
            QEvent.Wheel,
            QEvent.NativeGesture,
            QEvent.Gesture,
            QEvent.TouchBegin,
            QEvent.TouchUpdate,
            QEvent.TouchEnd,
        )

    def is_control_event_target(self, watched) -> bool:
        roots = (self.font_combo, self.font_combo.view())
        return any(root is watched or root.isAncestorOf(watched) for root in roots)

    def _select_color(self, color: str) -> None:
        self.color_palette.hide()
        self.color_changed.emit(QColor(color))

    def _request_custom_color(self) -> None:
        self.color_palette.hide()
        self.custom_color_requested.emit()

    def _width_value_changed(self, value: float) -> None:
        self.width_button.setText(f"粗细 {value:g}")
        self.width_changed.emit(float(value))

    def _font_size_value_changed(self, value: float) -> None:
        self.font_size_button.setText(f"字号 {value:g}")
        self.font_size_changed.emit(float(value))

    def _font_value_changed(self, family: str) -> None:
        self._font_family = family or self.font().family()
        self._refresh_font_button()
        self.font_family_changed.emit(self._font_family)

    def _refresh_font_button(self) -> None:
        metrics = QFontMetrics(self.font_button.font())
        family = metrics.elidedText(self._font_family, Qt.ElideRight, 88)
        self.font_button.setText(f"字体 {family}")
        self.font_button.setToolTip(self._font_family)

    def _toggle_panel(self, panel: QFrame, anchor: QPushButton) -> None:
        was_visible = panel.isVisible()
        self.hide_popups()
        if was_visible:
            return
        self._position_popup(panel, anchor)
        panel.show()
        if panel is self.color_palette:
            panel.layout().activate()
        panel.raise_()

    def _position_popup(self, popup: QFrame, anchor: QPushButton) -> None:
        popup.adjustSize()
        parent = self.parentWidget()
        anchor_pos = anchor.mapTo(parent, QPoint())
        x = min(max(8, anchor_pos.x()), parent.width() - popup.width() - 8)
        y = anchor_pos.y() - popup.height() - 8
        if y < 8:
            y = anchor_pos.y() + anchor.height() + 8
        popup.move(x, y)

    def _center_buttons(self) -> None:
        for button in self.findChildren(
            QPushButton, options=Qt.FindDirectChildrenOnly
        ):
            button.move(button.x(), (self.height() - button.height()) // 2)

    def _panels(self) -> tuple[QFrame, ...]:
        return (
            self.color_palette,
            self.width_panel,
            self.font_size_panel,
            self.font_panel,
        )

"""Application settings dialog."""

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from .app_state import ApplicationPreferences, ShortcutAction
from .global_hotkey import WindowsShortcutRecorder, canonical_shortcut
from .style_loader import apply_style
from .tool_registry import TOOLS


class ShortcutEdit(QLineEdit):
    """Self-contained shortcut recorder without Qt's private English prompt."""

    shortcutChanged = Signal(str)

    def __init__(self, sequence=None, parent=None):
        super().__init__(parent)
        self._portable = ""
        self._pressed = set()
        self._recorded = []
        self._recording = False
        self._windows_recorder = WindowsShortcutRecorder(self)
        self._windows_recorder.key_changed.connect(self._handle_native_key)
        self.setPlaceholderText("请按下组合键")
        self.setReadOnly(True)
        self.setKeySequence(sequence or "")

    def keySequence(self) -> QKeySequence:
        return QKeySequence(self._portable)

    def portableText(self) -> str:
        return self._portable

    def setKeySequence(self, sequence) -> None:
        next_sequence = (
            sequence.toString(QKeySequence.PortableText)
            if isinstance(sequence, QKeySequence)
            else str(sequence)
        )
        if next_sequence == self._portable:
            self._sync_display()
            return
        self._portable = next_sequence
        self._sync_display()
        self.shortcutChanged.emit(self._portable)

    def clear(self) -> None:
        self.setKeySequence(QKeySequence())

    def _sync_display(self, portable=None) -> None:
        portable = (
            self._portable
            if portable is None
            else portable
        )
        if not portable:
            super().clear()
            return
        keys = portable.split("+")
        if sys.platform == "darwin":
            symbols = {"Ctrl": "⌘", "Meta": "⌃", "Alt": "⌥", "Shift": "⇧"}
            keys = [symbols.get(key, key) for key in keys]
        self.setText(" + ".join(keys))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self.clear()
            event.accept()
            return
        if event.isAutoRepeat():
            event.accept()
            return
        key = self._key_name(event.key())
        if key:
            if not self._recording:
                self._recording = True
                self._pressed.clear()
                self._recorded.clear()
            self._pressed.add(key)
            if key not in self._recorded:
                self._recorded.append(key)
            self._set_recorded_keys(self._recorded)
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        if event.isAutoRepeat():
            event.accept()
            return
        key = self._key_name(event.key())
        self._pressed.discard(key)
        if self._recording and not self._pressed:
            self._recording = False
        event.accept()

    def focusOutEvent(self, event) -> None:
        self._windows_recorder.stop()
        self._recording = False
        self._pressed.clear()
        super().focusOutEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._windows_recorder.start()

    def closeEvent(self, event) -> None:
        self._windows_recorder.stop()
        super().closeEvent(event)

    def _handle_native_key(self, key: str, pressed: bool) -> None:
        if pressed and key in ("Backspace", "Delete"):
            self.clear()
            self._recording = False
            self._pressed.clear()
            self._recorded.clear()
            return
        if pressed:
            if not self._recording:
                self._recording = True
                self._pressed.clear()
                self._recorded.clear()
            self._pressed.add(key)
            if key not in self._recorded:
                self._recorded.append(key)
            self._set_recorded_keys(self._recorded)
        else:
            self._pressed.discard(key)
            if self._recording and not self._pressed:
                self._recording = False

    def _set_recorded_keys(self, keys) -> None:
        portable = "+".join(keys)
        self._portable = portable
        self._sync_display(portable)
        self.shortcutChanged.emit(self._portable)

    @staticmethod
    def _key_name(key) -> str:
        modifiers = {
            Qt.Key_Control: "Ctrl",
            Qt.Key_Shift: "Shift",
            Qt.Key_Alt: "Alt",
            Qt.Key_Meta: "Meta",
        }
        if key in modifiers:
            return modifiers[key]
        text = QKeySequence(key).toString(QKeySequence.PortableText)
        if text in ("+", "="):
            return "="
        return text if text and text != "Unknown" else ""


class SettingsDialog(QDialog):
    shortcuts_changed = Signal()

    def __init__(self, settings, parent=None, hotkey_validator=None):
        super().__init__(parent)
        self.preferences = (
            settings
            if isinstance(settings, ApplicationPreferences)
            else ApplicationPreferences(settings)
        )
        bindings = self.preferences.shortcuts()
        self.hotkey_validator = hotkey_validator
        self.setWindowTitle("设置")
        self.setFixedSize(620, 680)
        apply_style(self, "ui.settings_dialog:workspace")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(12)
        title = QLabel("偏好设置")
        title.setObjectName("settingsTitle")
        root.addWidget(title)
        description = QLabel("配置 FuzzToolBox 的工具行为，设置会自动保存在当前设备。")
        description.setObjectName("settingsDescription")
        root.addWidget(description)
        root.addSpacing(6)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        cards_host = QFrame()
        cards_host.setObjectName("settingsCardsHost")
        cards = QVBoxLayout(cards_host)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)

        shortcut_group = QFrame()
        shortcut_group.setObjectName("settingsCard")
        shortcut_layout = QVBoxLayout(shortcut_group)
        shortcut_layout.setContentsMargins(16, 16, 16, 16)
        shortcut_layout.setSpacing(10)
        shortcut_title = QLabel("快捷键")
        shortcut_title.setObjectName("settingsCardTitle")
        shortcut_layout.addWidget(shortcut_title)
        shortcut_description = QLabel("为应用功能设置全局组合键。")
        shortcut_description.setObjectName("settingsCardDescription")
        shortcut_layout.addWidget(shortcut_description)

        self.screen_picker_edit = self._add_shortcut_item(
            shortcut_layout,
            "屏幕取色",
            "隐藏主程序窗口后启动屏幕取色。",
            ShortcutAction.COLOR_PICKER,
            bindings,
        )
        self.screenshot_edit = self._add_shortcut_item(
            shortcut_layout,
            "截图",
            "隐藏主程序窗口后启动截图工具。",
            ShortcutAction.SCREENSHOT,
            bindings,
        )
        self.screen_picker_keep_edit = self._add_shortcut_item(
            shortcut_layout,
            "屏幕取色（保留主程序）",
            "保持主程序窗口可见并启动屏幕取色。",
            ShortcutAction.COLOR_PICKER_KEEP_MAIN,
            bindings,
        )
        self.screenshot_keep_edit = self._add_shortcut_item(
            shortcut_layout,
            "截图（保留主程序）",
            "保持主程序窗口可见并启动截图工具。",
            ShortcutAction.SCREENSHOT_KEEP_MAIN,
            bindings,
        )
        cards.addWidget(shortcut_group)
        cards.addStretch()
        scroll.setWidget(cards_host)
        root.addWidget(scroll, 1)
        self.error = QLabel()
        self.error.setObjectName("settingsError")
        self.error.setWordWrap(True)
        root.addWidget(self.error)

        buttons = QDialogButtonBox()
        cancel_button = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        cancel_button.setObjectName("settingsCancelButton")
        save_button = buttons.addButton("保存设置", QDialogButtonBox.AcceptRole)
        save_button.setObjectName("settingsSaveButton")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_shortcut_item(self, root, title, description, action, bindings):
        host = QFrame()
        host.setObjectName("settingsShortcutItem")
        card = QVBoxLayout(host)
        card.setContentsMargins(14, 10, 14, 12)
        card.setSpacing(6)

        card_title = QLabel(title)
        card_title.setObjectName("settingsCardTitle")
        card.addWidget(card_title)
        card_description = QLabel(f"{description} 至少需要两个按键。")
        card_description.setObjectName("settingsCardDescription")
        card.addWidget(card_description)

        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(10)
        edit = ShortcutEdit(bindings.for_action(action), host)
        edit.setFixedHeight(42)
        edit.setToolTip("按下至少两个键组成的快捷键")
        shortcut_row.addWidget(edit, 1)
        clear_button = QPushButton("清除")
        clear_button.setObjectName("settingsClearButton")
        clear_button.setFixedHeight(42)
        clear_button.clicked.connect(edit.clear)
        shortcut_row.addWidget(clear_button)
        card.addLayout(shortcut_row)
        root.addWidget(host)
        return edit

    def _save(self):
        shortcut_fields = (
            (
                "屏幕取色",
                ShortcutAction.COLOR_PICKER,
                self.screen_picker_edit,
            ),
            (
                "截图",
                ShortcutAction.SCREENSHOT,
                self.screenshot_edit,
            ),
            (
                "保留主程序的屏幕取色",
                ShortcutAction.COLOR_PICKER_KEEP_MAIN,
                self.screen_picker_keep_edit,
            ),
            (
                "保留主程序的截图",
                ShortcutAction.SCREENSHOT_KEEP_MAIN,
                self.screenshot_keep_edit,
            ),
        )
        values = []
        for title, _action, edit in shortcut_fields:
            sequence = edit.portableText()
            if sequence and len(sequence.split("+")) < 2:
                self.error.setText(f"{title}快捷键至少需要两个按键。")
                return
            values.append(sequence)
        active_values = [canonical_shortcut(value) for value in values if value]
        if None in active_values:
            self.error.setText("快捷键包含重复或不支持的按键。")
            return
        if len(active_values) != len(set(active_values)):
            self.error.setText("不同功能不能使用相同的快捷键。")
            return
        if self.hotkey_validator is not None and not self.hotkey_validator(
            *values
        ):
            self.error.setText("无法注册快捷键，可能已被系统或其他软件占用。")
            return
        for tool in TOOLS:
            self.preferences.remove_shortcut(f"shortcuts/{tool.id}")
        self.preferences.save_shortcuts(
            {
                action: value
                for (_title, action, _edit), value in zip(shortcut_fields, values)
            }
        )
        self.shortcuts_changed.emit()
        self.accept()

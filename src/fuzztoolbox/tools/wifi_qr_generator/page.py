from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...ui.components import configure_combo
from ..qr_generator.components import ColorButton
from .generator import generate_wifi_qr_png
from fuzztoolbox.ui.style_loader import apply_style


class WiFiQRGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()
        self.png_data = b""
        self._pixmap = QPixmap()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.generate)
        self._build_ui()
        self._update_security()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)
        intro = QLabel("根据网络名称、密码和加密方式生成 Wi-Fi 连接二维码")
        apply_style(intro, "tools.wifi_qr_generator.page:42")
        root.addWidget(intro)

        content = QHBoxLayout()
        content.setSpacing(14)
        panel = QFrame()
        panel.setObjectName("toolPanel")
        form = QVBoxLayout(panel)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(14)

        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(12)
        fields.setColumnMinimumWidth(0, 88)
        fields.setColumnStretch(1, 1)
        self.ssid = QLineEdit()
        self.ssid.setPlaceholderText("输入 Wi-Fi 名称（SSID）")
        self.security = QComboBox()
        self.security.addItem("WPA / WPA2 / WPA3（通用）", "WPA")
        self.security.addItem("WEP", "WEP")
        self.security.addItem("无密码", "nopass")
        configure_combo(self.security)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("输入 Wi-Fi 密码")
        fields.addWidget(QLabel("Wi-Fi 名称"), 0, 0, Qt.AlignRight)
        fields.addWidget(self.ssid, 0, 1, 1, 3)
        fields.addWidget(QLabel("加密方式"), 1, 0, Qt.AlignRight)
        fields.addWidget(self.security, 1, 1)
        fields.addWidget(QLabel("密码"), 2, 0, Qt.AlignRight)
        fields.addWidget(self.password, 2, 1, 1, 3)
        form.addLayout(fields)

        flags = QHBoxLayout()
        flags.setSpacing(22)
        flags.addSpacing(98)
        self.show_password = QCheckBox("显示密码")
        self.hidden_network = QCheckBox("隐藏网络")
        flags.addWidget(self.show_password)
        flags.addWidget(self.hidden_network)
        flags.addStretch()
        form.addLayout(flags)

        appearance = QHBoxLayout()
        appearance.setSpacing(8)
        appearance.addWidget(QLabel("前景色"))
        self.foreground = ColorButton("#000000", "选择二维码前景色")
        appearance.addWidget(self.foreground)
        appearance.addSpacing(10)
        appearance.addWidget(QLabel("背景色"))
        self.background = ColorButton("#ffffff", "选择二维码背景色")
        appearance.addWidget(self.background)
        appearance.addStretch()
        form.addLayout(appearance)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(QLabel("容错率"))
        self.error_level = QComboBox()
        for label, value in (
            ("L · 约 7%", "L"),
            ("M · 约 15%（推荐）", "M"),
            ("Q · 约 25%", "Q"),
            ("H · 约 30%", "H"),
        ):
            self.error_level.addItem(label, value)
        configure_combo(self.error_level)
        self.error_level.setMinimumWidth(150)
        actions.addWidget(self.error_level)
        actions.addStretch()
        form.addLayout(actions)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        self.generate_button = QPushButton("生成二维码")
        self.save_button = QPushButton("保存 PNG")
        self.copy_button = QPushButton("复制图片")
        self.clear_button = QPushButton("清空")
        self.save_button.setObjectName("secondary")
        self.copy_button.setObjectName("secondary")
        self.clear_button.setObjectName("neutral")
        for button in (
            self.generate_button,
            self.save_button,
            self.copy_button,
            self.clear_button,
        ):
            buttons.addWidget(button)
        form.addStretch()
        form.addLayout(buttons)
        content.addWidget(panel, 3)

        preview_panel = QFrame()
        preview_panel.setObjectName("toolPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.addWidget(QLabel("实时预览"))
        self.preview = QLabel("输入 Wi-Fi 名称后自动生成")
        self.preview.setObjectName("qrPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        preview_layout.addWidget(self.preview, 1)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        apply_style(self.status, "tools.wifi_qr_generator.page:143")
        preview_layout.addWidget(self.status)
        content.addWidget(preview_panel, 2)
        root.addLayout(content, 1)

        self.ssid.textChanged.connect(self.update_preview)
        self.password.textChanged.connect(self.update_preview)
        self.security.currentIndexChanged.connect(self._update_security)
        self.show_password.toggled.connect(self._toggle_password)
        self.hidden_network.toggled.connect(self.update_preview)
        self.error_level.currentIndexChanged.connect(self.update_preview)
        self.foreground.color_changed.connect(self.update_preview)
        self.background.color_changed.connect(self.update_preview)
        self.generate_button.clicked.connect(self.generate)
        self.save_button.clicked.connect(self.save_png)
        self.copy_button.clicked.connect(self.copy_image)
        self.clear_button.clicked.connect(self.clear)

    def _update_security(self):
        no_password = self.security.currentData() == "nopass"
        self.password.setEnabled(not no_password)
        self.show_password.setEnabled(not no_password)
        if no_password:
            self.password.clear()
            self.show_password.setChecked(False)
        self.update_preview()

    def _toggle_password(self, visible):
        self.password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def update_preview(self):
        self.preview_timer.start()

    def generate(self):
        try:
            self.png_data = generate_wifi_qr_png(
                self.ssid.text(),
                self.password.text(),
                self.security.currentData(),
                self.hidden_network.isChecked(),
                self.foreground.color.name(),
                self.background.color.name(),
                self.error_level.currentData(),
            )
        except ValueError as exc:
            self.png_data = b""
            self._pixmap = QPixmap()
            self.preview.setPixmap(QPixmap())
            self.preview.setText(str(exc))
            self.status.clear()
            return
        self._pixmap = QPixmap()
        self._pixmap.loadFromData(QByteArray(self.png_data), "PNG")
        self._show_scaled_preview()
        security = self.security.currentText().split("（")[0]
        hidden = " · 隐藏网络" if self.hidden_network.isChecked() else ""
        self.status.setText(f"{self.ssid.text().strip()} · {security}{hidden}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_scaled_preview()

    def _show_scaled_preview(self):
        if not self._pixmap.isNull():
            self.preview.setPixmap(
                self._pixmap.scaled(
                    self.preview.contentsRect().size(), Qt.KeepAspectRatio, Qt.FastTransformation
                )
            )

    def save_png(self):
        if not self.png_data:
            QMessageBox.information(self, "暂无二维码", "请先输入 Wi-Fi 信息并生成二维码。")
            return
        default_name = f"{self.ssid.text().strip() or 'wifi'}-qrcode.png"
        path, _ = QFileDialog.getSaveFileName(self, "保存 Wi-Fi 二维码", default_name, "PNG 图片 (*.png)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        try:
            Path(path).write_bytes(self.png_data)
            self.status.setText(f"已保存到 {path}")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def copy_image(self):
        if self._pixmap.isNull():
            QMessageBox.information(self, "暂无二维码", "请先输入 Wi-Fi 信息并生成二维码。")
            return
        QGuiApplication.clipboard().setPixmap(self._pixmap)
        self.status.setText("Wi-Fi 二维码已复制到剪贴板")

    def clear(self):
        self.ssid.clear()
        self.password.clear()
        self.security.setCurrentIndex(0)
        self.hidden_network.setChecked(False)
        self.show_password.setChecked(False)
        self.status.clear()

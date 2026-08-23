from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style

from ...ui.components import configure_combo
from .components import ColorButton
from .generator import generate_qr_png


class QRGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()
        self.png_data = b""
        self._pixmap = QPixmap()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.generate)
        self._build_ui()
        self.update_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        intro = QLabel("将文本或网址生成可自定义颜色与容错率的标准二维码")
        apply_style(intro, "tools.qr_generator.page:41")
        root.addWidget(intro)

        content = QHBoxLayout()
        content.setSpacing(14)
        panel = QFrame()
        panel.setObjectName("toolPanel")
        form = QVBoxLayout(panel)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        form.addWidget(QLabel("二维码内容"))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("输入文本、网址或其他需要写入二维码的内容")
        self.text.setPlainText("https://github.com/1024-byteeeee")
        self.text.setMinimumHeight(190)
        form.addWidget(self.text, 1)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        color_row.addWidget(QLabel("前景色"))
        self.foreground = ColorButton("#000000", "选择二维码前景色")
        color_row.addWidget(self.foreground)
        color_row.addSpacing(12)
        color_row.addWidget(QLabel("背景色"))
        self.background = ColorButton("#ffffff", "选择二维码背景色")
        color_row.addWidget(self.background)
        color_row.addStretch()
        form.addLayout(color_row)

        options = QHBoxLayout()
        options.setSpacing(8)
        options.addWidget(QLabel("容错率"))
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
        options.addWidget(self.error_level)
        options.addStretch()
        form.addLayout(options)

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
        form.addLayout(buttons)
        content.addWidget(panel, 3)

        preview_panel = QFrame()
        preview_panel.setObjectName("toolPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.addWidget(QLabel("实时预览"))
        self.preview = QLabel("请输入二维码内容")
        self.preview.setObjectName("qrPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        preview_layout.addWidget(self.preview, 1)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        apply_style(self.status, "tools.qr_generator.page:115")
        preview_layout.addWidget(self.status)
        content.addWidget(preview_panel, 2)
        root.addLayout(content, 1)

        self.text.textChanged.connect(self.update_preview)
        self.error_level.currentIndexChanged.connect(self.update_preview)
        self.foreground.color_changed.connect(self.update_preview)
        self.background.color_changed.connect(self.update_preview)
        self.generate_button.clicked.connect(self.generate)
        self.save_button.clicked.connect(self.save_png)
        self.copy_button.clicked.connect(self.copy_image)
        self.clear_button.clicked.connect(self.clear)

    def update_preview(self):
        self.preview_timer.start()

    def generate(self):
        try:
            self.png_data = generate_qr_png(
                self.text.toPlainText(),
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
        self.status.setText(
            f"容错率 {self.error_level.currentData()} · {len(self.text.toPlainText().encode('utf-8')):,} 字节"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_scaled_preview()

    def _show_scaled_preview(self):
        if self._pixmap.isNull():
            return
        size = self.preview.contentsRect().size()
        self.preview.setPixmap(self._pixmap.scaled(size, Qt.KeepAspectRatio, Qt.FastTransformation))

    def save_png(self):
        if not self.png_data:
            QMessageBox.information(self, "暂无二维码", "请先输入内容并生成二维码。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存二维码", "qrcode.png", "PNG 图片 (*.png)")
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
            QMessageBox.information(self, "暂无二维码", "请先输入内容并生成二维码。")
            return
        QGuiApplication.clipboard().setPixmap(self._pixmap)
        self.status.setText("二维码图片已复制到剪贴板")

    def clear(self):
        self.text.clear()
        self.status.clear()

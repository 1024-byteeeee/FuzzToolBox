from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .ui_components import configure_table
from .word_pdf import ConversionError, convert_to_pdf, supported_files, unique_output_path


class FileDropTable(QTableView):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class WordFileModel(QAbstractTableModel):
    columns = ("文件名", "格式", "大小", "状态", "转换引擎", "输出文件")

    def __init__(self):
        super().__init__()
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, _parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        row = self.rows[index.row()]
        source = row["source"]
        values = (
            source.name,
            source.suffix.lower(),
            self._format_size(source.stat().st_size),
            row["status"],
            row["engine"],
            str(row["output"]) if row["output"] else "—",
        )
        return values[index.column()]

    @staticmethod
    def _format_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"

    def add_files(self, paths):
        existing = {row["source"] for row in self.rows}
        additions = [
            {"source": path, "status": "等待转换", "engine": "—", "output": None}
            for path in supported_files(paths)
            if path not in existing
        ]
        if not additions:
            return 0
        first = len(self.rows)
        self.beginInsertRows(QModelIndex(), first, first + len(additions) - 1)
        self.rows.extend(additions)
        self.endInsertRows()
        return len(additions)

    def remove_rows(self, indexes):
        for row in sorted(set(indexes), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            self.rows.pop(row)
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self.rows.clear()
        self.endResetModel()

    def update_row(self, row, status, engine="—", output=None):
        if not 0 <= row < len(self.rows):
            return
        self.rows[row].update(status=status, engine=engine, output=output)
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))


class ConversionWorker(QObject):
    row_started = Signal(int)
    row_finished = Signal(int, str, str)
    row_failed = Signal(int, str)
    finished = Signal(bool)

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs
        self.cancelled = False

    @Slot()
    def run(self):
        for row, source, output in self.jobs:
            if self.cancelled:
                break
            self.row_started.emit(row)
            try:
                result = convert_to_pdf(source, output)
                self.row_finished.emit(row, result.engine, str(result.output))
            except (ConversionError, OSError) as exc:
                self.row_failed.emit(row, str(exc))
        self.finished.emit(self.cancelled)

    @Slot()
    def cancel(self):
        self.cancelled = True


class WordToPdfPage(QWidget):
    def __init__(self):
        super().__init__()
        self.model = WordFileModel()
        self.thread = None
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        intro = QLabel("将 Word/WPS 文档转换为 PDF · 支持 .doc、.docx、.wps · 文件仅在本机处理")
        intro.setStyleSheet(
            "background: #ecf5ff; color: #406080; border: 1px solid #d9ecff; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        root.addWidget(intro)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录"))
        self.output_folder = QLineEdit()
        self.output_folder.setPlaceholderText("默认输出到各源文件所在目录")
        self.browse_output_button = QPushButton("选择目录")
        self.browse_output_button.setObjectName("secondary")
        output_row.addWidget(self.output_folder, 1)
        output_row.addWidget(self.browse_output_button)
        root.addLayout(output_row)

        controls = QHBoxLayout()
        self.add_button = QPushButton("添加文档")
        self.remove_button = QPushButton("移除选中")
        self.remove_button.setObjectName("secondary")
        self.clear_button = QPushButton("清空列表")
        self.clear_button.setObjectName("secondary")
        self.start_button = QPushButton("开始转换")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setObjectName("secondary")
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.start_button,
            self.stop_button,
            self.open_output_button,
        ):
            controls.addWidget(widget)
        controls.insertStretch(3, 1)
        root.addLayout(controls)

        self.table = FileDropTable()
        self.table.setModel(self.model)
        configure_table(self.table)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for column, width in enumerate((260, 70, 90, 130, 130, 320)):
            header.resizeSection(column, width)
        root.addWidget(self.table, 1)

        self.status = QLabel("拖入文档或点击“添加文档”")
        self.status.setStyleSheet("color: #606266;")
        root.addWidget(self.status)

        self.add_button.clicked.connect(self.choose_files)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_files)
        self.start_button.clicked.connect(self.start_conversion)
        self.stop_button.clicked.connect(self.stop_conversion)
        self.browse_output_button.clicked.connect(self.choose_output_folder)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.table.files_dropped.connect(self.add_files)
        self._update_controls()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加 Word/WPS 文档", "", "Word/WPS 文档 (*.doc *.docx *.wps)"
        )
        self.add_files(paths)

    def add_files(self, paths):
        added = self.model.add_files(paths)
        self.status.setText(f"已添加 {added} 个文档，共 {self.model.rowCount()} 个")
        self._update_controls()

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 PDF 输出目录")
        if folder:
            self.output_folder.setText(folder)

    def remove_selected(self):
        rows = [index.row() for index in self.table.selectionModel().selectedIndexes()]
        self.model.remove_rows(rows)
        self._update_controls()

    def clear_files(self):
        self.model.clear()
        self.status.setText("列表已清空")
        self._update_controls()

    def _jobs(self):
        selected_folder = self.output_folder.text().strip()
        jobs = []
        for row, item in enumerate(self.model.rows):
            source = item["source"]
            folder = Path(selected_folder).expanduser() if selected_folder else source.parent
            output = unique_output_path(folder, source)
            jobs.append((row, source, output))
        return jobs

    def start_conversion(self):
        if not self.model.rows:
            return
        self.thread = QThread(self)
        self.worker = ConversionWorker(self._jobs())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.row_started.connect(lambda row: self.model.update_row(row, "正在转换"))
        self.worker.row_finished.connect(
            lambda row, engine, output: self.model.update_row(
                row, "转换完成", engine, Path(output)
            )
        )
        self.worker.row_failed.connect(
            lambda row, error: self.model.update_row(row, f"失败：{error}")
        )
        self.worker.finished.connect(self._conversion_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self._set_running(True)
        self.status.setText("正在转换文档…")
        self.thread.start()

    def stop_conversion(self):
        if self.worker:
            self.worker.cancel()
            self.stop_button.setEnabled(False)
            self.status.setText("正在停止，将在当前文档处理完成后停止…")

    def _conversion_finished(self, cancelled):
        completed = sum(row["status"] == "转换完成" for row in self.model.rows)
        failed = sum(str(row["status"]).startswith("失败") for row in self.model.rows)
        self.status.setText(
            f"{'已停止' if cancelled else '转换结束'}：成功 {completed}，失败 {failed}"
        )
        self._set_running(False)

    def _thread_finished(self):
        self.worker = None
        self.thread = None

    def _set_running(self, running):
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.start_button,
            self.output_folder,
            self.browse_output_button,
        ):
            widget.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _update_controls(self):
        has_files = self.model.rowCount() > 0
        self.remove_button.setEnabled(has_files)
        self.clear_button.setEnabled(has_files)
        self.start_button.setEnabled(has_files)

    def open_output_folder(self):
        selected = self.output_folder.text().strip()
        if selected:
            folder = Path(selected).expanduser()
        elif self.model.rows:
            folder = self.model.rows[0]["source"].parent
        else:
            QMessageBox.information(self, "没有输出目录", "请先添加文档或选择输出目录")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def prepare_close(self, on_ready):
        if self.thread and self.thread.isRunning():
            if self.worker:
                self.worker.cancel()
            self.thread.finished.connect(on_ready)
            self.status.setText("正在完成当前文档，完成后将自动关闭…")
            return False
        return True

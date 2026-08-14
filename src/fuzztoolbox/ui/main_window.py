"""FuzzToolBox application shell and tool navigation."""

import contextlib
import ctypes
import sys
from pathlib import Path
from fuzztoolbox.ui.style_loader import (
    apply_style,
    load_qss,
    refresh_widget_styles,
    set_theme,
)

try:
    from PySide6.QtCore import QSettings, QTimer, Qt
    from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 GUI 依赖，请运行：pip install -e '.[gui]'") from exc

from .. import __version__
from ..tools.color_picker.page import ColorPickerPage
from ..tools.datetime_converter.page import DateTimeConverterPage
from ..tools.ip_scanner.page import IPScannerPage
from ..tools.ip_lookup.page import IPLookupPage
from ..tools.ipv4_converter.page import IPv4ConverterPage
from ..tools.json_formatter.page import JSONFormatterPage
from ..tools.password_strength.page import PasswordStrengthPage
from ..tools.qr_generator.page import QRGeneratorPage
from ..tools.random_port.page import RandomPortPage
from ..tools.roman_numeral.page import RomanNumeralPage
from ..tools.subnet_calculator.page import SubnetCalculatorPage
from ..tools.text_comparer.page import TextComparerPage
from ..tools.text_statistics.page import TextStatisticsPage
from ..tools.timer.page import TimerPage
from ..tools.token_generator.page import TokenGeneratorPage
from ..tools.uuid_generator.page import UUIDGeneratorPage
from ..tools.wifi_qr_generator.page import WiFiQRGeneratorPage
from .animations import PageTransitionController, ThemeTransitionController
from .home_page import ToolboxHomePage
from .tool_registry import TOOLS
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
APP_ICON_PATH = ASSET_DIR / "app-icon.svg"
WINDOWS_APP_ID = "1024_byteeeee.FuzzToolBox"
FOOTER_COPYRIGHT = "© 2026 1024_byteeeee. All rights reserved."
THEME_MODES = ("system", "light", "dark")
DEFAULT_WINDOW_SIZE = (1180, 760)
MINIMUM_WINDOW_SIZE = (900, 600)


def configure_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)


def configure_application(app: QApplication) -> None:
    """Apply application metadata and theme before constructing the main window."""
    configure_windows_app_id()
    if sys.platform == "darwin":
        app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("FuzzToolBox")
    app.setOrganizationName("1024_byteeeee")
    app.setApplicationVersion(__version__)
    requested = str(
        QSettings("1024_byteeeee", "FuzzToolBox").value(
            "appearance/theme", "system"
        )
    )
    hints = app.styleHints()
    dark_value = getattr(getattr(Qt, "ColorScheme", object), "Dark", None)
    system_dark = (
        dark_value is not None
        and getattr(hints, "colorScheme", lambda: None)() == dark_value
    )
    set_theme(
        "dark"
        if requested == "dark" or (requested == "system" and system_dark)
        else "light"
    )
    app.setStyleSheet(load_qss("base.qss"))


def show_main_window(window: QMainWindow) -> None:
    """Map the fully constructed window directly in its saved state."""
    window.ensurePolished()
    if window.centralWidget() is not None and window.centralWidget().layout() is not None:
        window.centralWidget().layout().activate()
    if getattr(window, "_start_maximized", False):
        window.showMaximized()
    else:
        window.show()


def _valid_normal_geometry(rect) -> bool:
    minimum_width, minimum_height = MINIMUM_WINDOW_SIZE
    return bool(
        rect
        and rect.width() >= minimum_width
        and rect.height() >= minimum_height
        and any(
            screen.availableGeometry().intersects(rect)
            for screen in QGuiApplication.screens()
        )
    )


def restore_window_placement(window: QMainWindow, settings: QSettings) -> bool:
    """Restore normal geometry separately from the maximized startup state."""
    normal_geometry = settings.value("window/normalGeometry")
    maximized = settings.value("window/maximized", False, type=bool)

    # One-time migration from the old saveGeometry blob, which also embeds state.
    legacy_geometry = settings.value("window/geometry")
    if normal_geometry is None and legacy_geometry and window.restoreGeometry(legacy_geometry):
        maximized = window.isMaximized()
        normal_geometry = window.normalGeometry() if maximized else window.geometry()
        window.setWindowState(Qt.WindowNoState)
        settings.remove("window/geometry")

    restored = _valid_normal_geometry(normal_geometry)
    if restored:
        window.setGeometry(normal_geometry)
    else:
        window.resize(*DEFAULT_WINDOW_SIZE)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            window.move(available.center() - window.rect().center())
    window._start_maximized = bool(maximized)
    return restored


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.settings = QSettings("1024_byteeeee", "FuzzToolBox")
        self.setWindowTitle(f"FuzzToolBox v{__version__}")
        self.setMinimumSize(*MINIMUM_WINDOW_SIZE)
        self.resize(*DEFAULT_WINDOW_SIZE)
        self._closing_after_worker = False
        self._application_quitting = False
        self._page_transition = PageTransitionController(self)
        self._theme_transition = ThemeTransitionController(self)
        self.theme_mode = str(self.settings.value("appearance/theme", "system"))
        if self.theme_mode not in THEME_MODES:
            self.theme_mode = "system"

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 11, 20, 11)
        self.back_button = QPushButton("←  返回主页")
        self.back_button.setObjectName("backButton")
        self.back_button.clicked.connect(self.show_home)
        self.page_title = QLabel("FuzzToolBox")
        apply_style(self.page_title, "ui.main_window:83")
        self.page_icon = QLabel()
        self.page_icon.setFixedSize(32, 32)
        top_layout.addWidget(self.page_icon)
        top_layout.addSpacing(2)
        top_layout.addWidget(self.page_title)
        top_layout.addStretch()
        top_layout.addWidget(self.back_button)
        root_layout.addWidget(self.top_bar)

        self.pages = QStackedWidget()
        self.home_page = ToolboxHomePage()
        self.ip_scanner_page = IPScannerPage()
        self.ip_lookup_page = IPLookupPage()
        network_info = self.ip_scanner_page.network_info
        self.subnet_calculator_page = SubnetCalculatorPage(network_info)
        self.uuid_generator_page = UUIDGeneratorPage()
        self.token_generator_page = TokenGeneratorPage()
        self.json_formatter_page = JSONFormatterPage()
        self.text_comparer_page = TextComparerPage()
        self.text_statistics_page = TextStatisticsPage()
        self.ipv4_converter_page = IPv4ConverterPage(network_info)
        self.qr_generator_page = QRGeneratorPage()
        self.wifi_qr_generator_page = WiFiQRGeneratorPage()
        self.color_picker_page = ColorPickerPage()
        self.roman_numeral_page = RomanNumeralPage()
        self.password_strength_page = PasswordStrengthPage()
        self.random_port_page = RandomPortPage()
        self.timer_page = TimerPage()
        self.datetime_converter_page = DateTimeConverterPage()
        for page in (
            self.home_page,
            self.ip_scanner_page,
            self.ip_lookup_page,
            self.subnet_calculator_page,
            self.uuid_generator_page,
            self.token_generator_page,
            self.json_formatter_page,
            self.text_comparer_page,
            self.text_statistics_page,
            self.ipv4_converter_page,
            self.qr_generator_page,
            self.wifi_qr_generator_page,
            self.color_picker_page,
            self.roman_numeral_page,
            self.password_strength_page,
            self.random_port_page,
            self.timer_page,
            self.datetime_converter_page,
        ):
            self.pages.addWidget(page)
        root_layout.addWidget(self.pages, 1)

        self.copyright_label = QLabel()
        self.copyright_label.setAlignment(Qt.AlignCenter)
        self.copyright_label.setOpenExternalLinks(True)
        apply_style(self.copyright_label, "ui.main_window:144")
        root_layout.addWidget(self.copyright_label)
        self.setCentralWidget(root)

        self.home_page.tool_requested.connect(self.open_tool)
        self.home_page.theme_requested.connect(self.cycle_theme)
        quit_action = QAction(self)
        quit_action.setText("退出 FuzzToolBox")
        quit_action.setMenuRole(QAction.QuitRole)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.request_application_quit)
        self.addAction(quit_action)

        restore_window_placement(self, self.settings)
        self._connect_system_theme()
        self.apply_theme()
        self.show_home()

    def show_in_saved_state(self) -> None:
        show_main_window(self)

    def _system_theme(self) -> str:
        hints = QApplication.styleHints()
        color_scheme = getattr(hints, "colorScheme", lambda: None)()
        dark_value = getattr(getattr(Qt, "ColorScheme", object), "Dark", None)
        return "dark" if dark_value is not None and color_scheme == dark_value else "light"

    def _connect_system_theme(self):
        signal = getattr(QApplication.styleHints(), "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._system_theme_changed)

    def _system_theme_changed(self, *_args):
        if self.theme_mode == "system":
            self.apply_theme()

    def cycle_theme(self):
        resolved = self._system_theme() if self.theme_mode == "system" else self.theme_mode
        self.theme_mode = "light" if resolved == "dark" else "dark"
        self.settings.setValue("appearance/theme", self.theme_mode)
        self._theme_transition.transition(self.centralWidget(), self.apply_theme)

    def apply_theme(self):
        resolved = self._system_theme() if self.theme_mode == "system" else self.theme_mode
        set_theme(resolved)
        QApplication.instance().setStyleSheet(load_qss("base.qss"))
        refresh_widget_styles(QApplication.allWidgets())
        self.home_page.theme_button.setText("")
        next_mode = "light" if resolved == "dark" else "dark"
        icon_name = "theme-sun-dark.svg" if resolved == "dark" else "theme-moon.svg"
        self.home_page.theme_button.setIcon(QIcon(str(ASSET_DIR / icon_name)))
        self.home_page.theme_button.setToolTip(f"切换到{'浅色' if next_mode == 'light' else '深色'}模式")
        github_icon = ASSET_DIR / ("github-dark.svg" if resolved == "dark" else "github.svg")
        self.copyright_label.setText(
            f'FuzzToolBox v{__version__} · {FOOTER_COPYRIGHT} '
            f'<img src="{github_icon.as_posix()}" width="14" height="14"> '
            '<a href="https://github.com/1024-byteeeee">GitHub</a>'
        )

    def show_home(self):
        self.pages.setCurrentWidget(self.home_page)
        self.top_bar.setVisible(False)
        self.home_page.search.setFocus()
        self._page_transition.enter(self.home_page, -8)

    def open_tool(self, tool_id: str):
        destinations = {
            "ip-scanner": (self.ip_scanner_page, "IP Scanner · 网络扫描"),
            "ip-lookup": (self.ip_lookup_page, "公网IP信息查询 · 网络工具"),
            "subnet-calculator": (
                self.subnet_calculator_page,
                "子网划分计算器 · 网络规划",
            ),
            "uuid-generator": (self.uuid_generator_page, "UUID 生成器 · 开发工具"),
            "token-generator": (
                self.token_generator_page,
                "Token 生成器 · 开发工具",
            ),
            "json-formatter": (
                self.json_formatter_page,
                "JSON 格式化与校验器 · 开发工具",
            ),
            "text-comparer": (
                self.text_comparer_page,
                "文本对比工具 · 开发工具",
            ),
            "text-statistics": (
                self.text_statistics_page,
                "文本统计工具 · 实用工具",
            ),
            "ipv4-converter": (
                self.ipv4_converter_page,
                "IPv4 地址转换器 · 网络工具",
            ),
            "qr-generator": (self.qr_generator_page, "二维码生成器 · 开发工具"),
            "wifi-qr-generator": (
                self.wifi_qr_generator_page,
                "WiFi 二维码生成器 · 网络工具",
            ),
            "color-picker": (self.color_picker_page, "取色器 · 开发工具"),
            "roman-numeral": (
                self.roman_numeral_page,
                "罗马数字转换器 · 开发工具",
            ),
            "password-strength": (
                self.password_strength_page,
                "密码强度分析器 · 开发工具",
            ),
            "random-port": (
                self.random_port_page,
                "随机端口生成器 · 网络工具",
            ),
            "timer": (self.timer_page, "计时器 · 实用工具"),
            "datetime-converter": (
                self.datetime_converter_page,
                "日期时间转换器 · 开发工具",
            ),
        }
        destination = destinations.get(tool_id)
        if destination is None:
            return
        page, title = destination
        tool = next(tool for tool in TOOLS if tool.id == tool_id)
        self.page_icon.setPixmap(QIcon(str(ASSET_DIR / tool.icon)).pixmap(32, 32))
        self.top_bar.setVisible(True)
        self.pages.setCurrentWidget(page)
        self.page_title.setText(title)
        self._page_transition.enter(page, 8)
        if page is self.ip_scanner_page:
            self.ip_scanner_page.schedule_result_column_resize()

    def closeEvent(self, event):
        normal_geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.setValue("window/normalGeometry", normal_geometry)
        self.settings.setValue("window/maximized", self.isMaximized())
        self.settings.remove("window/geometry")
        if sys.platform == "darwin" and not self._application_quitting:
            event.ignore()
            self.hide()
            return
        if self.ip_scanner_page.prepare_close(self._finish_deferred_close):
            if self.ip_lookup_page.prepare_close(self._finish_deferred_close):
                event.accept()
                if self._application_quitting:
                    QTimer.singleShot(0, QApplication.instance().quit)
                return
        self._closing_after_worker = True
        event.ignore()

    def request_application_quit(self):
        self._application_quitting = True
        self.close()

    def restore_from_application_activation(self, state):
        if (
            sys.platform == "darwin"
            and state == Qt.ApplicationActive
            and not self.isVisible()
            and not self._application_quitting
        ):
            self.show()
            self.raise_()
            self.activateWindow()

    def _finish_deferred_close(self):
        if self._closing_after_worker:
            self._closing_after_worker = False
            self.close()


def main() -> None:
    app = QApplication(sys.argv)
    configure_application(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    if sys.platform == "darwin":
        app.applicationStateChanged.connect(window.restore_from_application_activation)
    window.show_in_saved_state()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

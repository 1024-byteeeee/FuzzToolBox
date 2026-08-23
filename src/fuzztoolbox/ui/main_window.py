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
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 GUI 依赖，请运行：pip install -e '.'") from exc

from .. import __version__
from .animations import PageTransitionController, ThemeTransitionController
from .global_hotkey import GlobalHotkeyManager
from .home_page import ToolboxHomePage
from .settings_dialog import SettingsDialog
from .system_tray import SystemTrayController
from .tool_registry import TOOLS

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
# PNG is used at runtime because the Windows taskbar icon path is more
# reliable with a raster QIcon than with an SVG loaded through Qt's image
# plugins in a frozen application.  The SVG remains the source artwork and is
# still used by the asset/build pipeline.
APP_ICON_PATH = ASSET_DIR / "app-icon.png"
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
        stored_favorites = self.settings.value("home/favorites", [])
        if isinstance(stored_favorites, str):
            stored_favorites = [stored_favorites] if stored_favorites else []
        self.home_page = ToolboxHomePage(favorite_ids=stored_favorites or [])
        self.pages.addWidget(self.home_page)
        self._tool_pages = {}
        self._tool_factories = self._build_tool_factories()
        root_layout.addWidget(self.pages, 1)

        self.copyright_label = QLabel()
        self.copyright_label.setAlignment(Qt.AlignCenter)
        self.copyright_label.setOpenExternalLinks(True)
        apply_style(self.copyright_label, "ui.main_window:144")
        root_layout.addWidget(self.copyright_label)
        self.setCentralWidget(root)

        self.home_page.tool_requested.connect(self.open_tool)
        self.home_page.theme_requested.connect(self.cycle_theme)
        self.home_page.settings_requested.connect(self.open_settings)
        self.home_page.favorite_changed.connect(self._save_favorites)
        quit_action = QAction(self)
        quit_action.setText("退出 FuzzToolBox")
        quit_action.setMenuRole(QAction.QuitRole)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.request_application_quit)
        self.addAction(quit_action)

        restore_window_placement(self, self.settings)
        self._connect_system_theme()
        self.apply_theme()
        app = QApplication.instance()
        self._color_hotkey = GlobalHotkeyManager(app, hotkey_id=1, parent=self)
        self._screenshot_hotkey = GlobalHotkeyManager(app, hotkey_id=2, parent=self)
        self._color_keep_hotkey = GlobalHotkeyManager(app, hotkey_id=3, parent=self)
        self._screenshot_keep_hotkey = GlobalHotkeyManager(app, hotkey_id=4, parent=self)
        self._shortcuts_suspended = False
        self._color_hotkey.activated.connect(self.start_color_picker)
        self._screenshot_hotkey.activated.connect(self.start_screenshot)
        self._color_keep_hotkey.activated.connect(
            lambda: self.start_color_picker(keep_main_window=True)
        )
        self._screenshot_keep_hotkey.activated.connect(
            lambda: self.start_screenshot(keep_main_window=True)
        )
        self.refresh_shortcuts()
        self._tray_controller = None
        if sys.platform == "win32" and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_controller = SystemTrayController(self, APP_ICON_PATH)
        self.show_home()

    def open_settings(self):
        self._shortcuts_suspended = True
        self._color_hotkey.unregister()
        self._screenshot_hotkey.unregister()
        self._color_keep_hotkey.unregister()
        self._screenshot_keep_hotkey.unregister()
        dialog = SettingsDialog(
            self.settings, self, hotkey_validator=self.validate_global_hotkeys
        )
        dialog.setObjectName("settingsDialog")
        try:
            dialog.exec()
        finally:
            self._shortcuts_suspended = False
            self.refresh_shortcuts()

    def refresh_shortcuts(self):
        color_shortcut = str(self.settings.value("shortcuts/color-picker-screen", ""))
        screenshot_shortcut = str(self.settings.value("shortcuts/screenshot", ""))
        color_keep_shortcut = str(
            self.settings.value("shortcuts/color-picker-screen-keep-main", "")
        )
        screenshot_keep_shortcut = str(
            self.settings.value("shortcuts/screenshot-keep-main", "")
        )
        self._color_hotkey.register(
            color_shortcut if self._is_safe_shortcut(color_shortcut) else ""
        )
        self._screenshot_hotkey.register(
            screenshot_shortcut if self._is_safe_shortcut(screenshot_shortcut) else ""
        )
        self._color_keep_hotkey.register(
            color_keep_shortcut if self._is_safe_shortcut(color_keep_shortcut) else ""
        )
        self._screenshot_keep_hotkey.register(
            screenshot_keep_shortcut
            if self._is_safe_shortcut(screenshot_keep_shortcut)
            else ""
        )

    def validate_global_hotkeys(self, *sequences):
        managers = (
            self._color_hotkey,
            self._screenshot_hotkey,
            self._color_keep_hotkey,
            self._screenshot_keep_hotkey,
        )
        for manager in managers:
            manager.unregister()
        registered = True
        for manager, sequence in zip(managers, sequences):
            if not manager.register(sequence):
                registered = False
                break
        for manager in managers:
            manager.unregister()
        if not self._shortcuts_suspended:
            self.refresh_shortcuts()
        return registered

    @staticmethod
    def _is_safe_shortcut(value):
        """Avoid plain text keys being captured from editors."""
        normalized = value.strip().upper()
        return bool(normalized and len(normalized.split("+")) >= 2)

    def start_color_picker(self, *, keep_main_window=False):
        if self._shortcuts_suspended:
            return
        page = self._load_tool_page("color-picker")
        if page is not None:
            # A keep-main capture must preserve the page that is already painted.
            # Switching pages immediately before grabbing the screen can capture an
            # unpainted color-picker page and make the main window appear blank.
            if not keep_main_window:
                self.open_tool("color-picker")
            page._start_eyedropper(keep_main_window=keep_main_window)
            if keep_main_window and page._eyedropper is not None:
                page._eyedropper.color_picked.connect(
                    lambda _color: self.open_tool("color-picker")
                )

    def start_screenshot(self, *, keep_main_window=False):
        if self._shortcuts_suspended:
            return
        page = self._load_tool_page("screenshot")
        if page is not None:
            page.start_capture(keep_main_window=keep_main_window)

    def restore_from_tray(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def show_in_saved_state(self) -> None:
        show_main_window(self)

    def _save_favorites(self, _tool_id=None, _favorite=None):
        ordered = [tool.id for tool in TOOLS if tool.id in self.home_page.favorite_ids]
        self.settings.setValue("home/favorites", ordered)

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
        self.home_page.refresh_favorite_icons()
        self.home_page.settings_button.setIcon(QIcon(str(ASSET_DIR / ("settings-dark.svg" if resolved == "dark" else "settings.svg"))))
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
        self.home_page.setFocus(Qt.OtherFocusReason)
        self._page_transition.enter(self.home_page, -8)

    def _build_tool_factories(self):
        """Return lazy page factories so the home page starts quickly."""
        def network_pages():
            from ..tools.ip_scanner.page import IPScannerPage
            scanner = self._tool_pages.get("ip-scanner")
            if scanner is None:
                scanner = IPScannerPage()
                self._tool_pages["ip-scanner"] = scanner
                self.pages.addWidget(scanner)
            return scanner.network_info

        return {
            "device-info": lambda: __import__("fuzztoolbox.tools.device_info.page", fromlist=["DeviceInfoPage"]).DeviceInfoPage(),
            "ip-scanner": lambda: __import__("fuzztoolbox.tools.ip_scanner.page", fromlist=["IPScannerPage"]).IPScannerPage(),
            "ip-lookup": lambda: __import__("fuzztoolbox.tools.ip_lookup.page", fromlist=["IPLookupPage"]).IPLookupPage(),
            "subnet-calculator": lambda: __import__("fuzztoolbox.tools.subnet_calculator.page", fromlist=["SubnetCalculatorPage"]).SubnetCalculatorPage(network_pages()),
            "subnet-mask-inverse": lambda: __import__("fuzztoolbox.tools.subnet_mask_inverse.page", fromlist=["SubnetMaskInversePage"]).SubnetMaskInversePage(),
            "uuid-generator": lambda: __import__("fuzztoolbox.tools.uuid_generator.page", fromlist=["UUIDGeneratorPage"]).UUIDGeneratorPage(),
            "token-generator": lambda: __import__("fuzztoolbox.tools.token_generator.page", fromlist=["TokenGeneratorPage"]).TokenGeneratorPage(),
            "json-formatter": lambda: __import__("fuzztoolbox.tools.json_formatter.page", fromlist=["JSONFormatterPage"]).JSONFormatterPage(),
            "docker-compose-converter": lambda: __import__("fuzztoolbox.tools.docker_compose_converter.page", fromlist=["DockerComposeConverterPage"]).DockerComposeConverterPage(),
            "text-comparer": lambda: __import__("fuzztoolbox.tools.text_comparer.page", fromlist=["TextComparerPage"]).TextComparerPage(),
            "text-statistics": lambda: __import__("fuzztoolbox.tools.text_statistics.page", fromlist=["TextStatisticsPage"]).TextStatisticsPage(),
            "lorem-ipsum": lambda: __import__("fuzztoolbox.tools.lorem_ipsum.page", fromlist=["LoremIpsumPage"]).LoremIpsumPage(),
            "ipv4-converter": lambda: __import__("fuzztoolbox.tools.ipv4_converter.page", fromlist=["IPv4ConverterPage"]).IPv4ConverterPage(network_pages()),
            "qr-generator": lambda: __import__("fuzztoolbox.tools.qr_generator.page", fromlist=["QRGeneratorPage"]).QRGeneratorPage(),
            "wifi-qr-generator": lambda: __import__("fuzztoolbox.tools.wifi_qr_generator.page", fromlist=["WiFiQRGeneratorPage"]).WiFiQRGeneratorPage(),
            "color-picker": lambda: __import__("fuzztoolbox.tools.color_picker.page", fromlist=["ColorPickerPage"]).ColorPickerPage(),
            "screenshot": lambda: __import__("fuzztoolbox.tools.screenshot.page", fromlist=["ScreenshotPage"]).ScreenshotPage(),
            "roman-numeral": lambda: __import__("fuzztoolbox.tools.roman_numeral.page", fromlist=["RomanNumeralPage"]).RomanNumeralPage(),
            "password-strength": lambda: __import__("fuzztoolbox.tools.password_strength.page", fromlist=["PasswordStrengthPage"]).PasswordStrengthPage(),
            "random-port": lambda: __import__("fuzztoolbox.tools.random_port.page", fromlist=["RandomPortPage"]).RandomPortPage(),
            "timer": lambda: __import__("fuzztoolbox.tools.timer.page", fromlist=["TimerPage"]).TimerPage(),
            "datetime-converter": lambda: __import__("fuzztoolbox.tools.datetime_converter.page", fromlist=["DateTimeConverterPage"]).DateTimeConverterPage(),
        }

    def _load_tool_page(self, tool_id):
        page = self._tool_pages.get(tool_id)
        if page is not None:
            return page
        factory = self._tool_factories.get(tool_id)
        if factory is None:
            return None
        page = factory()
        self._tool_pages[tool_id] = page
        # Keep the historical attributes available to integrations and tests,
        # while still creating the page only when it is first requested.
        setattr(self, f"{tool_id.replace('-', '_')}_page", page)
        self.pages.addWidget(page)
        return page

    def __getattr__(self, name):
        """Lazily resolve legacy ``<tool>_page`` attributes."""
        if name.endswith("_page") and "_tool_factories" in self.__dict__:
            tool_id = name[:-5].replace("_", "-")
            if tool_id in self._tool_factories:
                page = self._load_tool_page(tool_id)
                if page is not None:
                    return page
        raise AttributeError(name)

    def open_tool(self, tool_id: str):
        page = self._load_tool_page(tool_id)
        if page is None:
            return
        titles = {tool.id: f"{tool.name} · {tool.category}" for tool in TOOLS}
        title = titles.get(tool_id, tool_id)
        tool = next(tool for tool in TOOLS if tool.id == tool_id)
        self.page_icon.setPixmap(QIcon(str(ASSET_DIR / tool.icon)).pixmap(32, 32))
        self.top_bar.setVisible(True)
        self.pages.setCurrentWidget(page)
        self.page_title.setText(title)
        self._page_transition.enter(page, 8)
        if tool_id == "ip-scanner":
            page.schedule_result_column_resize()

    def closeEvent(self, event):
        normal_geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.setValue("window/normalGeometry", normal_geometry)
        self.settings.setValue("window/maximized", self.isMaximized())
        self.settings.remove("window/geometry")
        if (
            sys.platform == "win32"
            and self._tray_controller is not None
            and not self._application_quitting
        ):
            event.ignore()
            self.hide()
            return
        if sys.platform == "darwin" and not self._application_quitting:
            event.ignore()
            self.hide()
            return
        worker_states = [
            page.prepare_close(self._finish_deferred_close)
            for tool_id in ("ip-scanner", "ip-lookup", "device-info")
            for page in (self._tool_pages.get(tool_id),)
            if page is not None
        ]
        workers_ready = all(worker_states)
        if workers_ready:
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

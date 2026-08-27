"""Lightweight public desktop application entry point."""

import sys


def _install_chinese_translations(app) -> None:
    """Make every Qt-standard context menu (剪切/复制/粘贴/删除/全选) Chinese.

    Loading qtbase_zh_CN.qm localizes all built-in Qt strings (line edits,
    text edits, spin boxes, standard dialogs, ...) so the whole app shares one
    Chinese input experience. The file is bundled by PyInstaller's PySide6
    hook and also resolved from the dev environment via QLibraryInfo.
    """
    from pathlib import Path

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    candidates = [
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        str(
            Path(__file__).resolve().parent.parent
            / "assets"
            / "translations"
        ),
    ]
    for directory in candidates:
        if not directory:
            continue
        translator = QTranslator(app)
        if translator.load(QLocale("zh_CN"), "qtbase", "_", directory):
            app.installTranslator(translator)
            return


def main() -> None:
    # Keep heavyweight tool-page imports below the first paint so users get
    # immediate feedback while the complete application is being constructed.
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.single_instance import InstanceRole, SingleInstanceCoordinator
    from .ui.splash_screen import show_splash_screen

    app = QApplication(sys.argv)
    _install_chinese_translations(app)
    instance = SingleInstanceCoordinator("1024-byteeeee.FuzzToolBox")
    if instance.acquire() is InstanceRole.SECONDARY:
        raise SystemExit(0 if instance.notification_succeeded else 2)
    splash = show_splash_screen(app)

    from .ui.main_window import APP_ICON_PATH, MainWindow, configure_application

    configure_application(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    instance.activation_requested.connect(window.restore_from_tray)
    app.aboutToQuit.connect(instance.close)
    if sys.platform == "darwin":
        app.applicationStateChanged.connect(window.restore_from_application_activation)
    window.show_in_saved_state()
    splash.finish(window)

    def window_is_visible() -> bool:
        native_window = window.windowHandle()
        return bool(
            window.isVisible()
            and native_window is not None
            and native_window.isVisible()
        )

    native_window = window.windowHandle()
    if native_window is not None:
        native_window.visibleChanged.connect(
            lambda _visible: instance.publish_ready(window_is_visible)
        )
    QTimer.singleShot(
        0,
        lambda: instance.publish_ready(window_is_visible),
    )
    raise SystemExit(app.exec())


def __getattr__(name: str):
    """Preserve the former public imports without slowing normal startup."""
    if name in {"MainWindow", "configure_windows_app_id"}:
        from .ui import main_window

        return getattr(main_window, name)
    raise AttributeError(name)


__all__ = (  # noqa: F822 - names are provided lazily by __getattr__
    "MainWindow",
    "configure_windows_app_id",
    "main",
)


if __name__ == "__main__":
    main()

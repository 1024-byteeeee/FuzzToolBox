"""Lightweight public desktop application entry point."""

import sys


def main() -> None:
    # Keep heavyweight tool-page imports below the first paint so users get
    # immediate feedback while the complete application is being constructed.
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.splash_screen import show_splash_screen

    app = QApplication(sys.argv)
    splash = show_splash_screen(app)

    from .ui.main_window import APP_ICON_PATH, MainWindow, configure_application

    configure_application(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    if sys.platform == "darwin":
        app.applicationStateChanged.connect(window.restore_from_application_activation)
    window.show_in_saved_state()
    splash.finish(window)
    raise SystemExit(app.exec())


def __getattr__(name: str):
    """Preserve the former public imports without slowing normal startup."""
    if name in {"MainWindow", "configure_windows_app_id"}:
        from .ui import main_window

        return getattr(main_window, name)
    raise AttributeError(name)


__all__ = ("MainWindow", "configure_windows_app_id", "main")


if __name__ == "__main__":
    main()

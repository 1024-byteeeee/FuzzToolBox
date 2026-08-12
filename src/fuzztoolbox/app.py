"""Public desktop application entry point."""

from .ui.main_window import MainWindow, configure_windows_app_id, main

__all__ = ("MainWindow", "configure_windows_app_id", "main")


if __name__ == "__main__":
    main()

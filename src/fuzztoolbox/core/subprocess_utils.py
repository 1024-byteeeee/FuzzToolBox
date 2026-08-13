"""Cross-platform subprocess options used by GUI pages and workers."""

import platform
import subprocess


def hidden_subprocess_kwargs() -> dict:
    """Return flags that prevent child console windows in Windows GUI builds."""
    if platform.system() != "Windows":
        return {}
    options = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }
    startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_class is not None:
        startupinfo = startupinfo_class()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        options["startupinfo"] = startupinfo
    return options

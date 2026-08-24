"""Application state shared by the shell and capture tools.

The module intentionally contains no QWidget logic.  It records decisions and
lifecycles; callers remain responsible for presenting UI and scheduling timers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SettingsReader(Protocol):
    def value(self, key: str, default_value: object = None) -> object: ...


class SettingsBackend(SettingsReader, Protocol):
    def setValue(self, key: str, value: object) -> None: ...

    def remove(self, key: str) -> None: ...

    def sync(self) -> None: ...


class CaptureKind(Enum):
    COLOR_PICKER = "color-picker"
    SCREENSHOT = "screenshot"


class ShortcutAction(Enum):
    """Stable shortcut identities shared by settings and runtime wiring."""

    COLOR_PICKER = (
        "shortcuts/color-picker-screen",
        CaptureKind.COLOR_PICKER,
        False,
    )
    SCREENSHOT = (
        "shortcuts/screenshot",
        CaptureKind.SCREENSHOT,
        False,
    )
    COLOR_PICKER_KEEP_MAIN = (
        "shortcuts/color-picker-screen-keep-main",
        CaptureKind.COLOR_PICKER,
        True,
    )
    SCREENSHOT_KEEP_MAIN = (
        "shortcuts/screenshot-keep-main",
        CaptureKind.SCREENSHOT,
        True,
    )

    def __init__(
        self,
        setting_key: str,
        capture_kind: CaptureKind,
        keep_main_window: bool,
    ) -> None:
        self.setting_key = setting_key
        self.capture_kind = capture_kind
        self.keep_main_window = keep_main_window


SHORTCUT_ACTIONS = tuple(ShortcutAction)


@dataclass(frozen=True)
class ShortcutBindings:
    values: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: SettingsReader) -> ShortcutBindings:
        return cls(
            tuple(
                str(settings.value(action.setting_key, ""))
                for action in SHORTCUT_ACTIONS
            )
        )

    def for_action(self, action: ShortcutAction) -> str:
        return self.values[SHORTCUT_ACTIONS.index(action)]

    def ordered(self) -> tuple[str, ...]:
        return self.values

    @property
    def color_picker(self) -> str:
        return self.for_action(ShortcutAction.COLOR_PICKER)

    @property
    def screenshot(self) -> str:
        return self.for_action(ShortcutAction.SCREENSHOT)

    @property
    def color_picker_keep_main(self) -> str:
        return self.for_action(ShortcutAction.COLOR_PICKER_KEEP_MAIN)

    @property
    def screenshot_keep_main(self) -> str:
        return self.for_action(ShortcutAction.SCREENSHOT_KEEP_MAIN)


@dataclass(frozen=True)
class CaptureSession:
    token: int
    kind: CaptureKind
    keep_main_window: bool
    restore_main_window: bool


class CaptureSessionState:
    """Own the active capture and macOS activation-restore guard.

    A monotonically increasing token prevents a late completion signal from an
    old overlay from finishing a newer capture session.
    """

    def __init__(self) -> None:
        self._next_token = 1
        self._active: CaptureSession | None = None
        self._activation_restore_blocked = False

    @property
    def active(self) -> CaptureSession | None:
        return self._active

    @property
    def is_active(self) -> bool:
        return self._active is not None

    @property
    def activation_restore_blocked(self) -> bool:
        return self._activation_restore_blocked

    def begin(
        self,
        kind: CaptureKind,
        *,
        keep_main_window: bool,
        restore_main_window: bool,
    ) -> CaptureSession | None:
        if self._active is not None:
            return None
        session = CaptureSession(
            token=self._next_token,
            kind=kind,
            keep_main_window=keep_main_window,
            restore_main_window=restore_main_window,
        )
        self._next_token += 1
        self._active = session
        self._activation_restore_blocked = not keep_main_window
        return session

    def finish(self, token: int) -> CaptureSession | None:
        """Consume and return the matching session.

        Returning the session keeps completion policy at the shell boundary:
        the caller can apply the restore decision captured at ``begin`` without
        consulting mutable page state.  A stale signal receives ``None`` and
        therefore cannot affect a newer capture.
        """
        if self._active is None or self._active.token != token:
            return None
        session = self._active
        self._active = None
        return session

    def abort(self, token: int) -> bool:
        if self.finish(token) is None:
            return False
        self._activation_restore_blocked = False
        return True

    def release_activation_restore(self) -> None:
        self._activation_restore_blocked = False

    def application_became_inactive(self) -> None:
        if self._active is None:
            self.release_activation_restore()


class ApplicationPreferences:
    """Typed persistence boundary for shell and capture-tool settings."""

    _THEME_KEY = "appearance/theme"
    _FAVORITES_KEY = "home/favorites"
    _NORMAL_GEOMETRY_KEY = "window/normalGeometry"
    _MAXIMIZED_KEY = "window/maximized"
    _LEGACY_GEOMETRY_KEY = "window/geometry"

    def __init__(self, backend: SettingsBackend) -> None:
        self._backend = backend

    def theme_mode(self) -> str:
        return str(self._backend.value(self._THEME_KEY, "system"))

    def set_theme_mode(self, mode: str) -> None:
        self._backend.setValue(self._THEME_KEY, mode)

    def favorite_ids(self) -> tuple[str, ...]:
        stored = self._backend.value(self._FAVORITES_KEY, [])
        if isinstance(stored, str):
            return (stored,) if stored else ()
        return tuple(stored or ())

    def set_favorite_ids(self, tool_ids) -> None:
        self._backend.setValue(self._FAVORITES_KEY, list(tool_ids))

    def keep_main_window(self, kind: CaptureKind) -> bool:
        value = self._backend.value(f"capture/{kind.value}-keep-main", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def set_keep_main_window(self, kind: CaptureKind, keep: bool) -> None:
        self._backend.setValue(f"capture/{kind.value}-keep-main", bool(keep))

    def shortcuts(self) -> ShortcutBindings:
        return ShortcutBindings.from_settings(self._backend)

    def save_shortcuts(self, values: dict[ShortcutAction, str]) -> None:
        for action in SHORTCUT_ACTIONS:
            self._backend.setValue(action.setting_key, values.get(action, ""))
        self._backend.sync()

    def remove_shortcut(self, setting_key: str) -> None:
        self._backend.remove(setting_key)

    def window_placement(self) -> tuple[object, bool, object]:
        return (
            self._backend.value(self._NORMAL_GEOMETRY_KEY),
            self._bool_value(self._MAXIMIZED_KEY),
            self._backend.value(self._LEGACY_GEOMETRY_KEY),
        )

    def migrate_legacy_window_placement(
        self, normal_geometry: object, maximized: bool
    ) -> None:
        self._backend.setValue(self._NORMAL_GEOMETRY_KEY, normal_geometry)
        self._backend.setValue(self._MAXIMIZED_KEY, bool(maximized))
        self._backend.remove(self._LEGACY_GEOMETRY_KEY)

    def save_window_placement(self, normal_geometry: object, maximized: bool) -> None:
        self._backend.setValue(self._NORMAL_GEOMETRY_KEY, normal_geometry)
        self._backend.setValue(self._MAXIMIZED_KEY, bool(maximized))
        self._backend.remove(self._LEGACY_GEOMETRY_KEY)

    def _bool_value(self, key: str) -> bool:
        value = self._backend.value(key, False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


class ApplicationState:
    """Small interface for shell-wide settings and capture state."""

    def __init__(self, settings: SettingsBackend) -> None:
        self.preferences = ApplicationPreferences(settings)
        self.capture = CaptureSessionState()

    def shortcuts(self) -> ShortcutBindings:
        return self.preferences.shortcuts()

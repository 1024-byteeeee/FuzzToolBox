import unittest

from fuzztoolbox.ui.app_state import (
    SHORTCUT_ACTIONS,
    ApplicationPreferences,
    ApplicationState,
    CaptureKind,
    CaptureSessionState,
    ShortcutAction,
    ShortcutBindings,
)


class FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}

    def value(self, key, default_value=None):
        return self.values.get(key, default_value)

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)

    def sync(self):
        self.values["__synced__"] = True


class ShortcutBindingsTests(unittest.TestCase):
    def test_reads_all_capture_shortcuts_in_manager_order(self):
        settings = FakeSettings(
            {
                "shortcuts/color-picker-screen": "Ctrl+Alt+C",
                "shortcuts/screenshot": "Ctrl+Alt+S",
                "shortcuts/color-picker-screen-keep-main": "Ctrl+Shift+C",
                "shortcuts/screenshot-keep-main": "Ctrl+Shift+S",
            }
        )

        bindings = ShortcutBindings.from_settings(settings)

        self.assertEqual(
            bindings.ordered(),
            (
                "Ctrl+Alt+C",
                "Ctrl+Alt+S",
                "Ctrl+Shift+C",
                "Ctrl+Shift+S",
            ),
        )
        self.assertEqual(
            tuple(bindings.for_action(action) for action in SHORTCUT_ACTIONS),
            bindings.ordered(),
        )

    def test_shortcut_actions_own_capture_policy_and_setting_keys(self):
        self.assertEqual(
            ShortcutAction.COLOR_PICKER.setting_key,
            "shortcuts/color-picker-screen",
        )
        self.assertIs(
            ShortcutAction.SCREENSHOT_KEEP_MAIN.capture_kind,
            CaptureKind.SCREENSHOT,
        )
        self.assertTrue(ShortcutAction.SCREENSHOT_KEEP_MAIN.keep_main_window)


class CaptureSessionStateTests(unittest.TestCase):
    def test_only_one_capture_can_be_active(self):
        state = CaptureSessionState()
        first = state.begin(
            CaptureKind.SCREENSHOT,
            keep_main_window=False,
            restore_main_window=False,
        )

        second = state.begin(
            CaptureKind.COLOR_PICKER,
            keep_main_window=False,
            restore_main_window=True,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_late_completion_cannot_finish_a_newer_capture(self):
        state = CaptureSessionState()
        first = state.begin(
            CaptureKind.COLOR_PICKER,
            keep_main_window=False,
            restore_main_window=True,
        )
        self.assertTrue(state.finish(first.token))
        second = state.begin(
            CaptureKind.SCREENSHOT,
            keep_main_window=False,
            restore_main_window=False,
        )

        self.assertFalse(state.finish(first.token))
        self.assertEqual(state.active, second)

    def test_background_screenshot_blocks_activation_until_released(self):
        state = CaptureSessionState()
        session = state.begin(
            CaptureKind.SCREENSHOT,
            keep_main_window=False,
            restore_main_window=False,
        )

        self.assertTrue(state.activation_restore_blocked)
        self.assertTrue(state.finish(session.token))
        self.assertTrue(state.activation_restore_blocked)

        state.release_activation_restore()
        self.assertFalse(state.activation_restore_blocked)

    def test_keep_main_capture_never_blocks_activation_restore(self):
        state = CaptureSessionState()
        session = state.begin(
            CaptureKind.SCREENSHOT,
            keep_main_window=True,
            restore_main_window=False,
        )

        self.assertFalse(state.activation_restore_blocked)
        self.assertTrue(state.finish(session.token))

    def test_hidden_color_picker_blocks_activation_and_returns_restore_policy(self):
        state = CaptureSessionState()
        session = state.begin(
            CaptureKind.COLOR_PICKER,
            keep_main_window=False,
            restore_main_window=True,
        )

        self.assertTrue(state.activation_restore_blocked)
        completed = state.finish(session.token)

        self.assertEqual(completed, session)
        self.assertTrue(completed.restore_main_window)

    def test_application_inactive_releases_guard_after_capture_finished(self):
        state = CaptureSessionState()
        session = state.begin(
            CaptureKind.SCREENSHOT,
            keep_main_window=False,
            restore_main_window=False,
        )
        state.finish(session.token)

        state.application_became_inactive()

        self.assertFalse(state.activation_restore_blocked)


class ApplicationStateTests(unittest.TestCase):
    def test_exposes_shortcuts_and_capture_state(self):
        state = ApplicationState(
            FakeSettings({"shortcuts/screenshot": "Ctrl+Alt+S"})
        )

        self.assertEqual(state.shortcuts().screenshot, "Ctrl+Alt+S")
        self.assertFalse(state.capture.is_active)

    def test_preferences_normalize_values_and_persist_domain_settings(self):
        backend = FakeSettings(
            {
                "appearance/theme": "dark",
                "home/favorites": "timer",
                "capture/screenshot-keep-main": "true",
            }
        )
        preferences = ApplicationPreferences(backend)

        self.assertEqual(preferences.theme_mode(), "dark")
        self.assertEqual(preferences.favorite_ids(), ("timer",))
        self.assertTrue(preferences.keep_main_window(CaptureKind.SCREENSHOT))

        preferences.set_theme_mode("light")
        preferences.set_favorite_ids(("timer", "screenshot"))
        preferences.set_keep_main_window(CaptureKind.SCREENSHOT, False)

        self.assertEqual(backend.values["appearance/theme"], "light")
        self.assertEqual(backend.values["home/favorites"], ["timer", "screenshot"])
        self.assertFalse(backend.values["capture/screenshot-keep-main"])

    def test_preferences_save_shortcuts_as_one_typed_operation(self):
        backend = FakeSettings()
        preferences = ApplicationPreferences(backend)

        preferences.save_shortcuts(
            {
                ShortcutAction.COLOR_PICKER: "Ctrl+Alt+C",
                ShortcutAction.SCREENSHOT: "Ctrl+Alt+S",
            }
        )

        self.assertEqual(
            backend.values[ShortcutAction.COLOR_PICKER.setting_key],
            "Ctrl+Alt+C",
        )
        self.assertEqual(
            backend.values[ShortcutAction.SCREENSHOT.setting_key],
            "Ctrl+Alt+S",
        )
        self.assertTrue(backend.values["__synced__"])


if __name__ == "__main__":
    unittest.main()

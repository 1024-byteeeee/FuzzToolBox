"""Tests for the global-hotkey compatibility seam and native adapter routing."""

from __future__ import annotations

import ctypes
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from fuzztoolbox.ui.global_hotkey import (
    GlobalHotkeyManager,
    canonical_shortcut,
    windows_shortcut_needs_registration_probe,
    windows_shortcut_supported,
)
from fuzztoolbox.ui.hotkeys import macos as macos_module
from fuzztoolbox.ui.hotkeys import windows as windows_module
from fuzztoolbox.ui.hotkeys.macos import MacOSHotkeyAdapter
from fuzztoolbox.ui.hotkeys.manager import create_platform_adapter
from fuzztoolbox.ui.hotkeys.windows import WindowsHotkeyAdapter


class GlobalHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _mac_event_tap_libraries(*, tap=101, source=202):
        core_graphics = Mock()
        core_graphics.CGEventTapCreate.return_value = tap
        core_graphics.CGEventGetIntegerValueField.return_value = 0x38
        core_graphics.CGEventGetFlags.return_value = 0
        core_foundation = Mock()
        core_foundation.CFMachPortCreateRunLoopSource.return_value = source
        core_foundation.CFRunLoopGetMain.return_value = 303
        return core_graphics, core_foundation

    def test_compatibility_interface_handles_arbitrary_length_chords(self):
        sequence = "Ctrl+Shift+A+S+D"
        self.assertEqual(
            canonical_shortcut(sequence),
            frozenset({"ctrl", "shift", "a", "s", "d"}),
        )
        self.assertTrue(windows_shortcut_supported(sequence))
        self.assertFalse(windows_shortcut_needs_registration_probe(sequence))

    def test_platform_factory_routes_to_native_adapter(self):
        activated = Mock()
        update_chord = Mock()
        windows = create_platform_adapter(
            "win32", self.app, 7, activated, update_chord
        )
        macos = create_platform_adapter(
            "darwin", self.app, 7, activated, update_chord
        )

        self.assertIsInstance(windows, WindowsHotkeyAdapter)
        self.assertIsInstance(macos, MacOSHotkeyAdapter)
        self.assertIsNone(
            create_platform_adapter("linux", self.app, 7, activated, update_chord)
        )

    @patch("fuzztoolbox.ui.hotkeys.manager.create_platform_adapter")
    def test_manager_routes_simple_shortcut_and_owns_adapter_lifecycle(self, create):
        adapter = create.return_value
        adapter.register_simple.return_value = True
        manager = GlobalHotkeyManager(self.app, hotkey_id=9)

        self.assertTrue(manager.register("Ctrl+P"))
        adapter.register_simple.assert_called_once_with({"ctrl"}, "p")
        adapter.register_chord.assert_not_called()
        self.assertEqual(manager.sequence, "Ctrl+P")

        manager.unregister()
        adapter.unregister.assert_called_once_with()
        self.assertEqual(manager.sequence, "")

    @patch("fuzztoolbox.ui.hotkeys.manager.create_platform_adapter")
    def test_manager_routes_multi_key_chord_without_native_probe(self, create):
        adapter = create.return_value
        adapter.register_chord.return_value = True
        manager = GlobalHotkeyManager(self.app)

        self.assertTrue(manager.register("A+S+D"))
        adapter.register_chord.assert_called_once_with(["a", "s", "d"])
        adapter.register_simple.assert_not_called()

    @patch("fuzztoolbox.ui.hotkeys.manager.create_platform_adapter")
    def test_manager_normalizes_aliases_before_native_chord_registration(self, create):
        adapter = create.return_value
        adapter.register_chord.return_value = True
        manager = GlobalHotkeyManager(self.app)

        self.assertTrue(manager.register("Cmd+Option+A+S"))

        adapter.register_chord.assert_called_once_with(["meta", "alt", "a", "s"])

    @patch("fuzztoolbox.ui.hotkeys.manager.create_platform_adapter")
    def test_failed_registration_releases_partial_native_resources(self, create):
        adapter = create.return_value
        adapter.register_chord.return_value = False
        manager = GlobalHotkeyManager(self.app)

        self.assertFalse(manager.register("A+S+D"))
        adapter.unregister.assert_called_once_with()
        self.assertEqual(manager.sequence, "")
        self.assertIsNone(manager._adapter)

    @patch("fuzztoolbox.ui.hotkeys.manager.create_platform_adapter")
    def test_registering_replacement_unregisters_previous_adapter(self, create):
        first = Mock()
        first.register_simple.return_value = True
        second = Mock()
        second.register_simple.return_value = True
        create.side_effect = [first, second]
        manager = GlobalHotkeyManager(self.app)

        self.assertTrue(manager.register("Ctrl+A"))
        self.assertTrue(manager.register("Ctrl+B"))

        first.unregister.assert_called_once_with()
        self.assertIs(manager._adapter, second)
        self.assertEqual(manager.sequence, "Ctrl+B")

    def test_chord_latches_until_any_key_is_released(self):
        manager = GlobalHotkeyManager(self.app)
        triggered = Mock()
        manager.activated.connect(triggered)
        expected = {"ctrl", "shift", "a", "s", "d"}

        for key in ("ctrl", "shift", "a", "s", "d", "d"):
            manager._update_chord(expected, key, True)
        triggered.assert_called_once_with()

        manager._update_chord(expected, "a", False)
        manager._update_chord(expected, "a", True)
        self.assertEqual(triggered.call_count, 2)

    def test_windows_adapter_releases_registration_and_event_filter_once(self):
        app = Mock()
        user32 = Mock()
        user32.RegisterHotKey.return_value = True
        windll = Mock(user32=user32)
        adapter = WindowsHotkeyAdapter(app, 3, Mock(), Mock())

        with patch.object(windows_module.ctypes, "windll", windll, create=True):
            self.assertTrue(adapter.register_simple({"ctrl", "shift"}, "p"))
            installed_filter = adapter._filter
            adapter.unregister()
            adapter.unregister()

        user32.UnregisterHotKey.assert_called_once_with(None, 0x4659 + 3)
        app.installNativeEventFilter.assert_called_once_with(installed_filter)
        app.removeNativeEventFilter.assert_called_once_with(installed_filter)

    def test_macos_adapter_removes_dispatch_callback_when_unregistered(self):
        carbon = Mock()
        carbon.GetApplicationEventTarget.return_value = 99

        def register(_key, _mods, _identifier, _target, _options, destination):
            ctypes.cast(destination, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
            return 0

        carbon.RegisterEventHotKey.side_effect = register
        activated = Mock()
        adapter = MacOSHotkeyAdapter(11, activated, Mock())

        with patch.object(macos_module, "_hotkey_dispatcher", return_value=carbon), patch.object(
            macos_module, "_EVENT_CARBON", carbon
        ):
            self.assertTrue(adapter.register_simple({"ctrl"}, "p"))
            self.assertIs(macos_module._HOTKEY_CALLBACKS[11], activated)
            adapter.unregister()
            adapter.unregister()

        self.assertNotIn(11, macos_module._HOTKEY_CALLBACKS)
        self.assertEqual(carbon.UnregisterEventHotKey.call_count, 1)
        unregistered_ref = carbon.UnregisterEventHotKey.call_args.args[0]
        self.assertEqual(unregistered_ref.value, 123)

    def test_macos_modifier_flags_changed_reports_press_and_release(self):
        core_graphics, core_foundation = self._mac_event_tap_libraries()
        core_graphics.CGEventGetFlags.side_effect = [1 << 17, 0]
        update_chord = Mock()
        adapter = MacOSHotkeyAdapter(12, Mock(), update_chord)

        with (
            patch.object(
                macos_module,
                "_load_event_tap_libraries",
                return_value=(core_graphics, core_foundation),
            ),
            patch.object(
                macos_module,
                "_run_loop_common_modes",
                return_value=ctypes.c_void_p(404),
            ),
            patch.object(
                macos_module.ctypes,
                "CFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
            ),
        ):
            self.assertTrue(adapter.register_chord(["shift", "a"]))
            adapter._callback(None, 12, ctypes.c_void_p(505), None)
            adapter._callback(None, 12, ctypes.c_void_p(506), None)
            adapter.unregister()

        self.assertEqual(
            update_chord.call_args_list,
            [
                unittest.mock.call({"shift", "a"}, "shift", True),
                unittest.mock.call({"shift", "a"}, "shift", False),
            ],
        )

    def test_macos_chord_creation_failure_releases_callback_state(self):
        core_graphics, core_foundation = self._mac_event_tap_libraries(tap=None)
        adapter = MacOSHotkeyAdapter(13, Mock(), Mock())

        with (
            patch.object(
                macos_module,
                "_load_event_tap_libraries",
                return_value=(core_graphics, core_foundation),
            ),
            patch.object(
                macos_module.ctypes,
                "CFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
            ),
        ):
            self.assertFalse(adapter.register_chord(["a", "d"]))
            adapter.unregister()
            adapter.unregister()

        self.assertIsNone(adapter._callback)
        self.assertFalse(adapter._tap.value)
        self.assertFalse(adapter._source.value)
        core_foundation.CFMachPortCreateRunLoopSource.assert_not_called()
        core_foundation.CFRelease.assert_not_called()

    def test_macos_chord_source_failure_releases_created_tap(self):
        core_graphics, core_foundation = self._mac_event_tap_libraries(source=None)
        adapter = MacOSHotkeyAdapter(14, Mock(), Mock())

        with (
            patch.object(
                macos_module,
                "_load_event_tap_libraries",
                return_value=(core_graphics, core_foundation),
            ),
            patch.object(
                macos_module.ctypes,
                "CFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
            ),
        ):
            self.assertFalse(adapter.register_chord(["a", "d"]))
            adapter.unregister()
            adapter.unregister()

        self.assertIsNone(adapter._callback)
        self.assertFalse(adapter._tap.value)
        self.assertFalse(adapter._source.value)
        core_foundation.CFRelease.assert_called_once_with(101)

    def test_macos_chord_unregister_releases_native_resources_once(self):
        core_graphics, core_foundation = self._mac_event_tap_libraries()
        adapter = MacOSHotkeyAdapter(15, Mock(), Mock())

        with (
            patch.object(
                macos_module,
                "_load_event_tap_libraries",
                return_value=(core_graphics, core_foundation),
            ),
            patch.object(
                macos_module,
                "_run_loop_common_modes",
                return_value=ctypes.c_void_p(404),
            ),
            patch.object(
                macos_module.ctypes,
                "CFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
            ),
        ):
            self.assertTrue(adapter.register_chord(["a", "d"]))
            callback = adapter._callback
            adapter.unregister()
            adapter.unregister()

        self.assertIsNotNone(callback)
        self.assertIsNone(adapter._callback)
        self.assertFalse(adapter._tap.value)
        self.assertFalse(adapter._source.value)
        core_foundation.CFRunLoopRemoveSource.assert_called_once()
        core_foundation.CFMachPortInvalidate.assert_called_once()
        self.assertEqual(core_foundation.CFRelease.call_count, 2)

    def test_windows_chord_creation_failure_releases_callback_state(self):
        user32 = Mock()
        user32.SetWindowsHookExW.return_value = None
        windll = Mock(user32=user32, kernel32=Mock())
        adapter = WindowsHotkeyAdapter(Mock(), 16, Mock(), Mock())

        with (
            patch.object(windows_module.ctypes, "windll", windll, create=True),
            patch.object(
                windows_module.ctypes,
                "WINFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
                create=True,
            ),
        ):
            self.assertFalse(adapter.register_chord(["a", "d"]))
            adapter.unregister()
            adapter.unregister()

        self.assertIsNone(adapter._hook)
        self.assertIsNone(adapter._hook_callback)
        user32.UnhookWindowsHookEx.assert_not_called()

    def test_windows_chord_unregister_releases_hook_once(self):
        user32 = Mock()
        user32.SetWindowsHookExW.return_value = 707
        windll = Mock(user32=user32, kernel32=Mock())
        adapter = WindowsHotkeyAdapter(Mock(), 17, Mock(), Mock())

        with (
            patch.object(windows_module.ctypes, "windll", windll, create=True),
            patch.object(
                windows_module.ctypes,
                "WINFUNCTYPE",
                side_effect=lambda *_args: lambda callback: callback,
                create=True,
            ),
        ):
            self.assertTrue(adapter.register_chord(["a", "d"]))
            callback = adapter._hook_callback
            adapter.unregister()
            adapter.unregister()

        self.assertIsNotNone(callback)
        self.assertIsNone(adapter._hook)
        self.assertIsNone(adapter._hook_callback)
        user32.UnhookWindowsHookEx.assert_called_once_with(707)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import Mock, patch

from ip_scanner.gui import WINDOWS_APP_ID, ResultModel, configure_windows_app_id
from ip_scanner.models import ScanResult


class ResultModelTests(unittest.TestCase):
    def test_windows_app_id_is_registered_for_taskbar_icon(self):
        shell32 = Mock()
        windll = Mock(shell32=shell32)
        with patch("ip_scanner.gui.sys.platform", "win32"), patch(
            "ip_scanner.gui.ctypes.windll", windll, create=True
        ):
            configure_windows_app_id()

        shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            WINDOWS_APP_ID
        )

    def test_detail_update_replaces_existing_ip_without_adding_a_row(self):
        model = ResultModel()
        model.add_batch(
            [
                ScanResult(
                    ip="192.168.1.20",
                    is_alive=True,
                    method="ping",
                    details_pending=True,
                )
            ]
        )
        model.add_batch(
            [
                ScanResult(
                    ip="192.168.1.20",
                    is_alive=True,
                    method="ping",
                    hostname="printer.local",
                    mac="00:11:22:33:44:55",
                )
            ]
        )

        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.results[0].hostname, "printer.local")
        self.assertEqual(model.results[0].mac, "00:11:22:33:44:55")


if __name__ == "__main__":
    unittest.main()

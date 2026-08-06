import unittest

from ip_scanner.gui import ResultModel
from ip_scanner.models import ScanResult


class ResultModelTests(unittest.TestCase):
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

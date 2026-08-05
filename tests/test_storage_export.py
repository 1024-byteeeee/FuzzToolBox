import json
import csv
import tempfile
import unittest
from pathlib import Path

from ip_scanner.exporters import export_results
from ip_scanner.models import ScanConfig, ScanResult
from ip_scanner.storage import HistoryStore


class StorageExportTests(unittest.TestCase):
    def test_history_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            with HistoryStore(path) as store:
                task_id = store.create_task("127.0.0.1", 1, ScanConfig())
                store.add_results(
                    task_id,
                    [ScanResult("127.0.0.1", True, "tcp", open_ports=[80])],
                )
                store.finish_task(task_id, 1)
                row = store.recent_tasks(1)[0]
                self.assertEqual(row["status"], "completed")
                self.assertEqual(row["alive_count"], 1)

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            export_results(path, [ScanResult("127.0.0.1", True, "tcp", open_ports=[80])])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["open_ports"], [80])

    def test_csv_preserves_probe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            export_results(
                path,
                [ScanResult("192.0.2.1", False, "ping", error="ping command unavailable")],
            )
            with path.open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["error"], "ping command unavailable")


if __name__ == "__main__":
    unittest.main()

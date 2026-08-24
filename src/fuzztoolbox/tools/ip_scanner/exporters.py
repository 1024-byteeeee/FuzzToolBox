import csv
import json
from collections.abc import Iterable
from pathlib import Path

from .models import ScanResult


def export_csv(path: Path, results: Iterable[ScanResult]) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ip",
                "is_alive",
                "method",
                "response_time_ms",
                "hostname",
                "mac",
                "open_ports",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            row = result.to_dict()
            row["open_ports"] = ",".join(str(port) for port in result.open_ports)
            writer.writerow(row)


def export_json(path: Path, results: Iterable[ScanResult]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in results], handle, ensure_ascii=False, indent=2)


def export_results(path: Path, results: Iterable[ScanResult]) -> None:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        export_csv(path, results)
    elif suffix == ".json":
        export_json(path, results)
    else:
        raise ValueError("仅支持导出 CSV 或 JSON")

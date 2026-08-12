import json
import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import ScanConfig, ScanResult


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS scan_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,
    method TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    total_ips INTEGER NOT NULL,
    alive_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES scan_tasks(id) ON DELETE CASCADE,
    ip TEXT NOT NULL,
    method TEXT NOT NULL,
    response_time_ms REAL,
    hostname TEXT,
    mac TEXT,
    open_ports_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scan_results_task ON scan_results(task_id);
"""


class HistoryStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.executescript(SCHEMA)

    def create_task(self, target: str, total: int, config: ScanConfig) -> int:
        cursor = self.connection.execute(
            "INSERT INTO scan_tasks(target, method, total_ips, config_json) VALUES (?, ?, ?, ?)",
            (target, config.method, total, json.dumps(config.__dict__, ensure_ascii=False)),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_results(self, task_id: int, results: Iterable[ScanResult]) -> None:
        self.connection.executemany(
            """INSERT INTO scan_results
               (task_id, ip, method, response_time_ms, hostname, mac, open_ports_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    task_id,
                    result.ip,
                    result.method,
                    result.response_time_ms,
                    result.hostname,
                    result.mac,
                    json.dumps(result.open_ports),
                )
                for result in results
                if result.is_alive
            ],
        )
        self.connection.commit()

    def finish_task(self, task_id: int, alive_count: int, status: str = "completed") -> None:
        self.connection.execute(
            """UPDATE scan_tasks
               SET finished_at = CURRENT_TIMESTAMP, alive_count = ?, status = ? WHERE id = ?""",
            (alive_count, status, task_id),
        )
        self.connection.commit()

    def recent_tasks(self, limit: int = 50) -> List[sqlite3.Row]:
        self.connection.row_factory = sqlite3.Row
        return list(
            self.connection.execute(
                "SELECT * FROM scan_tasks ORDER BY id DESC LIMIT ?", (limit,)
            )
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

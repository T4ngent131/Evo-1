"""高光计数与本地数据库迁移，不加载游戏截图或视频编码器。"""

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import highlights
import storage


def main():
    start = datetime(2026, 10, 25, 20, 0, 0)
    t = lambda seconds: start + timedelta(seconds=seconds)
    events = highlights.kill_events([(t(0), 0), (t(10), 1), (t(11), 1), (t(12), 1),
                                     (t(20), 9), (t(21), None), (t(22), 1),
                                     (t(30), 3), (t(31), 3)])
    checks = {
        "confirmed kill and multikill": [(e["occurred_at"], e["amount"]) for e in events]
                                        == [("2026-10-25 20:00:10", 1), ("2026-10-25 20:00:30", 2)],
        "late start has no invented kill": highlights.kill_events([(t(0), 4), (t(1), 4)]) == [],
        "one bad reading has no marker": highlights.kill_events([(t(0), 0), (t(1), 7), (t(2), 0)]) == [],
    }
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "evo.db"
        conn = storage.connect(path)
        match_id = storage.insert_match(conn, {"ended_at": "2026-10-25 20:10:00"})
        storage.save_highlights(conn, match_id, events)
        storage.save_highlights(conn, match_id, events)
        checks["duplicate save is idempotent"] = len(storage.highlights_of(conn, match_id)) == 2
        storage.delete_match(conn, match_id)
        checks["deleting match removes markers"] = storage.highlights_of(conn, match_id) == []
        conn.execute("DROP TABLE highlights")
        conn.execute("PRAGMA user_version = 7")
        conn.commit()
        conn.close()
        conn = storage.connect(path)
        checks["schema 7 upgrades to 8"] = (conn.execute("PRAGMA user_version").fetchone()[0] == 8
                                            and conn.execute("SELECT COUNT(*) FROM highlights").fetchone()[0] == 0)
        conn.close()
    for label, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'} {label}")
    return all(checks.values())


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)

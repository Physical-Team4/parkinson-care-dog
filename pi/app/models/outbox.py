"""오프라인 대기열 (로컬 SQLite). 인터넷이 끊겼을 때 Supabase로 보낼 Op을 쌓아 둔다.

이 파일의 SQLite는 대기열 용도로만 쓴다. 알람·기록의 원본 저장소는 Supabase.
파일 위치: Settings.queue_path (기본 ~/pd-dog-data/outbox.db). 레포 안에 만들지 말 것.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from pi.app.views.api_schemas import Op

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY,
    created_at      REAL    NOT NULL,
    kind            TEXT    NOT NULL,
    target          TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    on_conflict     TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL    NOT NULL,
    last_error      TEXT,
    dead            INTEGER NOT NULL DEFAULT 0  -- 1 = 재시도해도 안 되는 항목 (사람이 확인)
);
CREATE INDEX IF NOT EXISTS outbox_next ON outbox (next_attempt_at, id);
"""


@dataclass
class QueuedOp:
    id: int
    op: Op
    attempts: int


class Outbox:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def enqueue(self, op: Op, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO outbox (created_at, kind, target, payload_json, on_conflict, next_attempt_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (now, op.kind, op.target, json.dumps(op.payload, ensure_ascii=False), op.on_conflict, now))
        return int(cur.lastrowid)

    def due(self, now: float | None = None, limit: int = 50) -> list[QueuedOp]:
        """보낼 차례인 항목. 순서 보장을 위해 id 순. 앞 항목이 대기 중이면 뒤 항목도 기다린다."""
        now = time.time() if now is None else now
        head = self._conn.execute(
            "SELECT next_attempt_at FROM outbox WHERE dead = 0 ORDER BY id LIMIT 1").fetchone()
        if head is None or head[0] > now:
            return []
        rows = self._conn.execute(
            "SELECT id, kind, target, payload_json, on_conflict, attempts FROM outbox"
            " WHERE dead = 0 ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [QueuedOp(r[0], Op(r[1], r[2], json.loads(r[3]), r[4]), r[5]) for r in rows]

    def mark_sent(self, item_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM outbox WHERE id = ?", (item_id,))

    def mark_failed(self, item_id: int, error: str, retry_at: float) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_error = ?, next_attempt_at = ?"
                " WHERE id = ?", (error[:500], retry_at, item_id))

    def mark_dead(self, item_id: int, error: str) -> None:
        """지우지 않고 남겨 둔다 (알람이 버그로 사라지지 않게). 확인: SELECT * FROM outbox WHERE dead=1"""
        with self._conn:
            self._conn.execute("UPDATE outbox SET dead = 1, last_error = ? WHERE id = ?",
                               (error[:500], item_id))

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT count(*) FROM outbox WHERE dead = 0").fetchone()[0])

    def dead_count(self) -> int:
        return int(self._conn.execute("SELECT count(*) FROM outbox WHERE dead = 1").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

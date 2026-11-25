"""하드웨어 없이 개발·테스트할 때 쓰는 가짜 adapter."""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

import numpy as np

from pi.app.adapters.base import RemoteError
from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import Op

log = logging.getLogger(__name__)


class MockEsp32Link:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.inbox: deque[dict[str, Any]] = deque()

    def send(self, line: bytes) -> None:
        self.sent.append(line)
        msg = sm.decode(line)
        if msg and "id" in msg:
            self.inbox.append({"t": sm.ACK, "id": msg["id"], "ok": True})

    def read_message(self, timeout_s: float) -> dict[str, Any] | None:
        return self.inbox.popleft() if self.inbox else None

    def close(self) -> None:
        pass


class MockRemote:
    """Supabase 가짜. online=False면 네트워크 끊김처럼 RemoteError(permanent=False)."""

    def __init__(self, online: bool = True) -> None:
        self.online = online
        self.executed: list[Op] = []
        self.status_rows: list[dict] = []
        self.broadcasts: list[tuple[str, str, dict]] = []
        self.settings = {"target_bpm": 96, "target_db": 68, "follow_limit_cm": 150,
                         "medication_times": ["08:00", "12:30", "18:00", "22:00"]}

    def _check(self) -> None:
        if not self.online:
            raise RemoteError("offline", permanent=False)

    def execute(self, op: Op) -> Any:
        self._check()
        self.executed.append(op)
        log.debug("mock %s %s %s", op.kind, op.target, op.payload)
        return {"alert_id": len(self.executed), "merged": False, "duplicate": False} if op.kind == "rpc" else None

    def insert_status(self, row: dict) -> None:
        self._check()
        self.status_rows.append(row)

    def broadcast(self, topic: str, event: str, payload: dict) -> None:
        self._check()
        self.broadcasts.append((topic, event, payload))

    def fetch_settings(self) -> dict:
        self._check()
        return dict(self.settings)


class MockCamera:
    def __init__(self, width: int = 320, height: int = 320) -> None:
        self.shape = (height, width, 3)

    def capture(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=np.uint8)


class MockMicrophone:
    sample_rate = 16000

    def __init__(self, amplitude: float = 0.0) -> None:
        self.amplitude = amplitude

    def record(self, seconds: float) -> np.ndarray:
        n = int(self.sample_rate * seconds)
        t = np.arange(n) / self.sample_rate
        return (self.amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class MockPowerMonitor:
    def battery_pct(self) -> float | None:
        return 100.0

    def charging(self) -> bool | None:
        return False

    def cpu_temp_c(self) -> float | None:
        return 45.0


class MockNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)

"""하드웨어 없이 개발·테스트할 때 쓰는 가짜 adapter."""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

import numpy as np

from pi.app.adapters.base import Detection, MarkerObs, PersonPose, RemoteError
from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import Op

log = logging.getLogger(__name__)


class MockEsp32Link:
    """connected=False로 USB 분리를 흉내 낸다: send는 dropped로, read는 None."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.dropped: list[bytes] = []
        self.inbox: deque[dict[str, Any]] = deque()
        self.connected = True

    def send(self, line: bytes) -> None:
        if not self.connected:
            self.dropped.append(line)
            return
        self.sent.append(line)
        msg = sm.decode(line)
        if msg and "id" in msg:
            self.inbox.append({"t": sm.ACK, "id": msg["id"], "ok": True})

    def read_message(self, timeout_s: float) -> dict[str, Any] | None:
        if not self.connected:
            return None
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
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.shape = (height, width, 3)
        self.closed = False

    def capture(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class MockPoseEstimator:
    """정해 둔 결과를 차례로 돌려준다 (다 쓰면 마지막 것 반복). 기본은 사람 없음."""

    def __init__(self, results: list[list[PersonPose]] | None = None,
                 input_size: tuple[int, int] = (640, 640)) -> None:
        self.results = results or [[]]
        self.input_size = input_size
        self.calls = 0
        self.closed = False

    def infer(self, frame: np.ndarray) -> list[PersonPose]:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r

    def close(self) -> None:
        self.closed = True


class MockMarkerDetector:
    """정해 둔 마커 결과를 차례로 돌려준다 (다 쓰면 마지막 것 반복). 기본은 마커 없음."""

    def __init__(self, results: list[list[MarkerObs]] | None = None) -> None:
        self.results = results or [[]]
        self.calls = 0
        self.last_ms = 0.0

    def detect(self, frame: np.ndarray) -> list[MarkerObs]:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


class MockObjectDetector:
    """정해 둔 물체 검출 결과를 차례로 돌려준다. 기본은 아무것도 없음."""

    def __init__(self, results: list[list[Detection]] | None = None) -> None:
        self.results = results or [[]]
        self.calls = 0
        self.last_ms = 0.0
        self.closed = False

    def detect(self, frame: np.ndarray) -> list[Detection]:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r

    def close(self) -> None:
        self.closed = True


class MockMicrophone:
    sample_rate = 16000

    def __init__(self, amplitude: float = 0.0) -> None:
        self.amplitude = amplitude

    def record(self, seconds: float) -> np.ndarray:
        n = int(self.sample_rate * seconds)
        t = np.arange(n) / self.sample_rate
        return (self.amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class MockPowerMonitor:
    """값을 바꿔 가며 배터리 정책을 시험한다. power_ok=None이면 GPIO6 미설정 상태."""

    def __init__(self, pct: float | None = 100.0, power_ok: bool | None = False,
                 temp_c: float | None = 45.0) -> None:
        self.pct = pct
        self.ok = power_ok
        self.temp_c = temp_c

    def battery_pct(self) -> float | None:
        return self.pct

    def power_ok(self) -> bool | None:
        return self.ok

    def charging(self) -> bool | None:
        return self.ok

    def cpu_temp_c(self) -> float | None:
        return self.temp_c


class MockHost:
    def __init__(self) -> None:
        self.poweroff_calls = 0

    def poweroff(self) -> None:
        log.warning("mock poweroff")
        self.poweroff_calls += 1


class MockNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)

"""adapter 인터페이스. 실제 구현과 mock(mock.py)이 같은 메서드를 가진다.

services는 이 Protocol 타입만 알고, 어떤 구현이 들어오는지는 main.py가 정한다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

if TYPE_CHECKING:
    from pi.app.views.api_schemas import Op


class RemoteError(Exception):
    """Supabase 호출 실패. permanent=False면 나중에 재시도 (네트워크 끊김, 5xx, 429)."""

    def __init__(self, message: str, permanent: bool) -> None:
        super().__init__(message)
        self.permanent = permanent


class RemoteStore(Protocol):
    """Supabase (adapters/supabase_rest.py). 실패 시 RemoteError."""
    def execute(self, op: Op) -> Any: ...
    def insert_status(self, row: dict) -> None: ...
    def broadcast(self, topic: str, event: str, payload: dict) -> None: ...
    def fetch_settings(self) -> dict: ...


class Esp32Link(Protocol):
    def send(self, line: bytes) -> None: ...
    def read_message(self, timeout_s: float) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


class Camera(Protocol):
    def capture(self) -> np.ndarray:
        """RGB 프레임 1장. 호출한 쪽은 처리 후 즉시 버린다 (저장 금지)."""
        ...


class Microphone(Protocol):
    sample_rate: int

    def record(self, seconds: float) -> np.ndarray:
        """float32 모노, -1~1. 원본 저장 금지."""
        ...


class PowerMonitor(Protocol):
    """X1200 (I²C 0x36 잔량, GPIO6 전원 차단 감지). 읽기 실패·미설정이면 None."""
    def battery_pct(self) -> float | None: ...
    def power_ok(self) -> bool | None:
        """외부 전원(X1200 USB-C 충전기) 연결 여부. GPIO6 극성 미설정이면 None."""
        ...
    def charging(self) -> bool | None:
        """대시보드 pi_charging. 지금은 power_ok와 같음 (충전 상태 핀 미확정, docs/todo.md)."""
        ...
    def cpu_temp_c(self) -> float | None: ...


class HostSystem(Protocol):
    """Pi OS 자체 제어 (안전 종료)."""
    def poweroff(self) -> None: ...


class Notifier(Protocol):
    """보호자 메신저 (종류 미확정)."""
    def send(self, text: str) -> None: ...

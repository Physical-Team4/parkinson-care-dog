"""ESP32 USB 시리얼 연결 (담당: B, ESP32 쪽 D와 형식 합의).

- 포트를 열 때 DTR/RTS 때문에 ESP32가 리셋될 수 있으므로 끈 상태로 연다.
- '#'로 시작하는 줄은 ESP32 디버그 출력이라 무시 (serial_messages.decode).
"""
from __future__ import annotations

import time
from typing import Any

from pi.app.views import serial_messages as sm


class SerialEsp32Link:
    def __init__(self, port: str, baud: int) -> None:
        import serial  # pyserial — 지연 import

        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = baud
        self._ser.timeout = 0.05
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._buf = b""

    def send(self, line: bytes) -> None:
        self._ser.write(line)

    def read_message(self, timeout_s: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                msg = sm.decode(line)
                if msg is not None:
                    return msg
                continue
            if time.monotonic() >= deadline:
                return None
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                self._buf += chunk
                if len(self._buf) > sm.MAX_LINE_BYTES * 4:  # 줄바꿈 없는 쓰레기 방지
                    self._buf = b""

    def close(self) -> None:
        self._ser.close()

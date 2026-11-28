"""ESP32 USB 시리얼 연결 (담당: B, ESP32 쪽 D와 형식 합의).

- 포트를 열 때 DTR/RTS 때문에 ESP32가 리셋될 수 있으므로 끈 상태로 연다.
- '#'로 시작하는 줄은 ESP32 디버그 출력이라 무시 (serial_messages.decode).
- USB 분리·MechDog 전원 꺼짐(SerialException/OSError)에도 앱을 멈추지 않는다 (T3, 2026-11-28).
  끊기면 포트를 닫고 1→2→4→5초 간격으로 다시 연다. 끊긴 동안 send()는 버린다
  (대기열 없음 → 재연결 뒤 예전 walk 등이 늦게 실행되지 않음). 앱 시작 때 포트가 없어도 같은 방식.
- 끊긴 동안 read_message()는 timeout_s만큼 잠들어 메인 루프가 CPU를 다 쓰지 않게 한다.
- 로그: 끊김 WARNING 1번, 복구(새 메시지 수신) INFO 1번, 계속 끊겨 있으면 60초마다 WARNING 1번.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from types import ModuleType
from typing import Any

from pi.app.views import serial_messages as sm

log = logging.getLogger(__name__)

RETRY_DELAYS_S = (1.0, 2.0, 4.0, 5.0)   # 마지막 값에서 멈춤
STILL_DOWN_LOG_S = 60.0


class SerialEsp32Link:
    def __init__(self, port: str, baud: int, *, serial_module: ModuleType | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if serial_module is None:
            import serial as serial_module  # pyserial — 지연 import
        self._serial = serial_module
        self._errors = (serial_module.SerialException, OSError)
        self._port = port
        self._baud = baud
        self._clock = clock
        self._sleep = sleep
        self._ser: Any = None
        self._buf = b""
        self._closed = False
        self._retry_idx = 0
        self._next_retry = 0.0
        self._down_since: float | None = None   # None = 정상 (새 메시지를 받은 뒤)
        self._last_down_log = 0.0
        if not self._open():
            self._went_down("ESP32 포트 열기 실패")

    @property
    def connected(self) -> bool:
        return self._ser is not None

    # ── 연결 관리 ──
    def _open(self) -> bool:
        ser = self._serial.Serial()
        ser.port = self._port
        ser.baudrate = self._baud
        ser.timeout = 0.05
        ser.dtr = False
        ser.rts = False
        try:
            ser.open()
            # 이전 연결의 남은 입력·보내지 못한 출력은 버린다 (예전 명령이 늦게 실행되지 않게)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except self._errors as e:
            log.debug("esp32 open %s failed: %s", self._port, e)
            self._safe_close(ser)
            return False
        self._ser = ser
        self._buf = b""
        return True

    def _safe_close(self, ser: Any) -> None:
        try:
            ser.close()
        except Exception as e:  # noqa: BLE001 - 끊긴 포트 닫기 실패는 무시
            log.debug("esp32 close failed: %s", e)

    def _went_down(self, why: str) -> None:
        now = self._clock()
        if self._down_since is None:
            self._down_since = now
            self._last_down_log = now
            log.warning("%s (%s) → esp32_ok=false, %.0f초 뒤부터 다시 연결 시도", why, self._port,
                        RETRY_DELAYS_S[self._retry_idx])
        else:   # 복구 전에 또 끊김 (포트만 열리고 바로 끊기는 깜빡임) → 간격 늘림
            self._retry_idx = min(self._retry_idx + 1, len(RETRY_DELAYS_S) - 1)
            log.debug("%s (%s)", why, self._port)
        self._next_retry = now + RETRY_DELAYS_S[self._retry_idx]

    def _drop(self, e: BaseException) -> None:
        ser, self._ser = self._ser, None
        self._buf = b""
        if ser is not None:
            self._safe_close(ser)
        self._went_down(f"ESP32 연결 끊김: {e}")

    def _maybe_reconnect(self) -> None:
        now = self._clock()
        if self._down_since is not None and now - self._last_down_log >= STILL_DOWN_LOG_S:
            self._last_down_log = now
            log.warning("ESP32 아직 연결 안 됨 (%.0f초째, %s)", now - self._down_since, self._port)
        if now < self._next_retry:
            return
        if self._open():
            log.debug("esp32 port %s opened, waiting for status", self._port)
            return
        self._retry_idx = min(self._retry_idx + 1, len(RETRY_DELAYS_S) - 1)
        self._next_retry = now + RETRY_DELAYS_S[self._retry_idx]

    def _got_message(self) -> None:
        # 포트만 열리고 바로 끊기는 경우(깜빡임)에는 간격을 줄이지 않도록, 메시지를 받은 뒤에 초기화
        self._retry_idx = 0
        if self._down_since is not None:
            log.info("ESP32 연결 복구 (%.0f초 끊김, %s)", self._clock() - self._down_since, self._port)
            self._down_since = None

    # ── Esp32Link ──
    def send(self, line: bytes) -> None:
        if self._ser is None:
            log.debug("esp32 disconnected, dropped: %r", line)
            return
        try:
            self._ser.write(line)
        except self._errors as e:
            self._drop(e)

    def read_message(self, timeout_s: float) -> dict[str, Any] | None:
        if self._ser is None:
            if not self._closed:
                self._maybe_reconnect()
            if self._ser is None:
                self._sleep(timeout_s)
                return None
        deadline = self._clock() + timeout_s
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                msg = sm.decode(line)
                if msg is not None:
                    self._got_message()
                    return msg
                continue
            if self._clock() >= deadline:
                return None
            try:
                chunk = self._ser.read(self._ser.in_waiting or 1)
            except self._errors as e:
                self._drop(e)
                return None
            if chunk:
                self._buf += chunk
                if len(self._buf) > sm.MAX_LINE_BYTES * 4:  # 줄바꿈 없는 쓰레기 방지
                    self._buf = b""

    def close(self) -> None:
        self._closed = True
        ser, self._ser = self._ser, None
        if ser is not None:
            self._safe_close(ser)

"""대시보드 설정 + 시계 → ESP32 settings (담당: D, Pi 통합 B). 형식: docs/serial-protocol.md

- poll_s마다 Supabase 설정을 읽어 바뀌었으면 보낸다 (now 포함).
- clock_s마다 now만 보낸다 (ESP32에는 시계가 없음. now를 못 받으면 복약 알림이 꺼진다).
- ESP32가 새로 켜지면(esp32_ok False → True) 마지막 설정 + now를 바로 다시 보낸다.
  인터넷이 끊겨 있으면 아는 설정만(없으면 now만) 보낸다 → 시계는 인터넷 없이도 맞춘다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from pi.app.adapters.base import RemoteError, RemoteStore
from pi.app.views import serial_messages as sm

log = logging.getLogger(__name__)


def _local_now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def esp32_fields(s: dict) -> dict:
    """fetch_settings() 결과 → ESP32 settings 필드 (now 제외). 값이 없는 것은 뺀다."""
    out = {"med_times": list(s.get("medication_times") or [])}
    if s.get("target_bpm") is not None:
        out["bpm"] = s["target_bpm"]
    if s.get("follow_limit_cm") is not None:
        out["follow_limit_cm"] = s["follow_limit_cm"]
    return out


class SettingsSync:
    def __init__(self, remote: RemoteStore, send: Callable[[bytes], None], poll_s: float, clock_s: float,
                 now_text: Callable[[], str] = _local_now_text) -> None:
        self._remote = remote
        self._send = send
        self._poll_s = poll_s
        self._clock_s = clock_s
        self._now_text = now_text
        self._sent: dict | None = None     # 마지막으로 보낸 설정
        self._last_poll: float | None = None
        self._last_clock: float | None = None
        self._resend = True                # 처음, 또는 ESP32가 끊겼다 다시 옴

    def tick(self, now_s: float, esp32_ok: bool) -> None:
        if not esp32_ok:
            self._resend = True            # 보드가 재부팅되면 설정·시계를 잊는다
            return
        fields = None
        if self._resend or self._last_poll is None or now_s - self._last_poll >= self._poll_s:
            self._last_poll = now_s
            try:
                fields = esp32_fields(self._remote.fetch_settings())
            except (RemoteError, ValueError, KeyError) as e:
                log.warning("settings fetch failed: %s", e)
        if fields is not None and fields != self._sent:
            self._sent = fields
            self._send_full(now_s)
        elif self._resend:
            self._send_full(now_s)
        elif self._last_clock is None or now_s - self._last_clock >= self._clock_s:
            self._send(sm.settings(now=self._now_text()))
            self._last_clock = now_s

    def _send_full(self, now_s: float) -> None:
        line = sm.settings(now=self._now_text(), **(self._sent or {}))
        self._send(line)
        log.info("esp32 settings: %s", line.decode().strip())
        self._last_clock = now_s
        self._resend = False

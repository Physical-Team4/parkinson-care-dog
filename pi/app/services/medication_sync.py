"""F1 복약: ESP32 med_due / med_ok / med_missed → medication_logs·알람 (담당: D). 형식: docs/serial-protocol.md

- ESP32는 "HH:MM"만 보낸다 → Pi 현지 날짜의 그 시각. 1시간 넘게 미래면 어제 것 (자정 직후의 23:50 복약 등).
- pending은 insert(이미 있으면 무시): 로봇이 다시 켜져 같은 복약을 또 알려도 confirmed·missed를 덮지 않는다.
- 이 Pi가 확인을 받은 복약을 로봇이 다시 알리면(로봇 재부팅) med_ack로 바로 끝낸다 → 다시 울리지 않음.
- 로봇이 꺼졌다 켜지면 대기 중이던 복약을 잊어 med_missed가 오지 않는다
  → Pi가 due + 확인 시간 + 여유가 지나도록 pending이면 missed로 처리 (tick).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Callable

from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import AlertReport, MedicationLog, Op

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def due_at(hhmm: str, now_local: datetime) -> datetime:
    """"HH:MM" → now_local 날짜의 그 시각. 1시간 넘게 미래면 하루 전. 형식이 틀리면 ValueError."""
    h, m = (int(x) for x in hhmm.split(":"))
    d = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    return d - timedelta(days=1) if d - now_local > timedelta(hours=1) else d


class MedicationSync:
    def __init__(self, submit: Callable[[Op], None], send: Callable[[bytes], None] | None = None,
                 next_id: Callable[[], int] | None = None, confirm_timeout_s: float = 1800.0,
                 missed_grace_s: float = 120.0, clock: Callable[[], datetime] = _utcnow,
                 tz: tzinfo | None = None) -> None:
        self._submit = submit
        self._send = send
        self._next_id = next_id or (lambda: 0)
        self._wait = timedelta(seconds=confirm_timeout_s + missed_grace_s)
        self._clock = clock
        self._tz = tz                       # None = Pi 시스템 시간대
        self._pending: set[datetime] = set()
        self._confirmed: set[datetime] = set()

    def _now(self) -> datetime:
        return self._clock().astimezone(self._tz)

    def handle(self, msg: dict) -> None:
        t, due = msg.get("t"), msg.get("due")
        now = self._now()
        try:
            at = due_at(due, now)
        except (AttributeError, TypeError, ValueError):
            log.warning("esp32 %s: bad due %r", t, due)
            return
        if t == sm.MED_DUE:
            if at in self._confirmed:
                if self._send:
                    self._send(sm.med_ack(due, self._next_id()))
                log.info("med %s already confirmed → med_ack", due)
                return
            self._pending.add(at)
            self._submit(MedicationLog(at, "pending").to_op())
        elif t == sm.MED_OK:
            self._pending.discard(at)
            self._confirmed.add(at)
            self._submit(MedicationLog(at, "confirmed", now, msg.get("method") or "touch").to_op())
        elif t == sm.MED_MISSED:
            self._pending.discard(at)
            if at in self._confirmed:
                log.info("med %s missed after confirm → ignored", due)
                return
            self._missed(at, now)

    def _missed(self, at: datetime, now: datetime) -> None:
        self._submit(MedicationLog(at, "missed").to_op())
        self._submit(AlertReport("medication_missed", now.astimezone(timezone.utc),
                                 detail={"due": at.strftime("%H:%M")}).to_op())

    def tick(self) -> None:
        """로봇이 잊은 pending → missed. 오래된 확인 기록 정리."""
        now = self._now()
        for at in sorted(self._pending):
            if now - at > self._wait:
                self._pending.discard(at)
                log.info("med %s still pending (robot restarted?) → missed", at.strftime("%H:%M"))
                self._missed(at, now)
        self._confirmed = {at for at in self._confirmed if now - at < timedelta(days=2)}

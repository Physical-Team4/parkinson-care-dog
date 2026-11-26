"""ESP32 이벤트를 받아 서비스·Supabase로 넘기는 controller (담당: B).

계산·판정은 여기서 하지 않는다. 메시지 종류에 따라 알맞은 곳으로 전달만 한다.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from pi.app.adapters.base import PowerMonitor, RemoteStore
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import AlertReport, RobotStatus

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RobotController:
    def __init__(self, sync: SyncService, remote: RemoteStore, power: PowerMonitor,
                 esp32_timeout_s: float, clock: Callable[[], datetime] = _utcnow) -> None:
        self.sync = sync
        self.remote = remote
        self.power = power
        self.esp32_timeout_s = esp32_timeout_s
        self.clock = clock
        self._last_esp_status: dict[str, Any] = {}
        self._last_esp_status_at: float | None = None
        self._next_id = 1

    def next_id(self) -> int:
        msg_id = self._next_id
        self._next_id += 1
        return msg_id

    # ── ESP32 → Pi ──
    def handle_esp32_message(self, msg: dict[str, Any], now_s: float | None = None) -> None:
        now_s = time.monotonic() if now_s is None else now_s
        t = msg.get("t")
        if t == sm.STATUS:
            self._last_esp_status = msg
            self._last_esp_status_at = now_s
        elif t == sm.TOUCH_SOS:
            self.sync.submit(AlertReport("touch", self.clock()).to_op())
        elif t == sm.MED_MISSED:
            self.sync.submit(AlertReport("medication_missed", self.clock(),
                                         detail={"due": msg.get("due")}).to_op())
            # TODO(D): MedicationLog(status="missed") — due "HH:MM" → 오늘 날짜 due_at 변환 규칙 확정 후
        elif t in (sm.MED_DUE, sm.MED_OK, sm.GAIT_END):
            # TODO(D, C): MedicationLog / GaitSession Op으로 변환해 sync.submit
            log.info("esp32 %s: %s", t, msg)
        elif t == sm.ACK:
            pass  # TODO(B): 명령별 ack 대기 처리
        else:
            log.warning("unknown esp32 message: %s", msg)

    # ── Pi → Supabase (2초마다, 대기열 없음) ──
    def build_status(self, now_s: float | None = None) -> RobotStatus:
        now_s = time.monotonic() if now_s is None else now_s
        fresh = (self._last_esp_status_at is not None
                 and now_s - self._last_esp_status_at <= self.esp32_timeout_s)
        esp = self._last_esp_status if fresh else {}
        return RobotStatus(
            esp32_ok=fresh,
            mode=esp.get("mode"),
            dog_battery_pct=esp.get("dog_battery_pct"),
            pi_battery_pct=self.power.battery_pct(),
            pi_charging=self.power.charging(),
            pi_temp_c=self.power.cpu_temp_c(),
            follow_distance_cm=esp.get("follow_distance_cm"),
            laser_on=esp.get("laser_on"),
            bpm=esp.get("bpm"),
            robot_tipped=esp.get("robot_tipped"),
        )

    def send_status(self) -> bool:
        return self.sync.send_now(self.remote.insert_status, self.build_status().to_json())

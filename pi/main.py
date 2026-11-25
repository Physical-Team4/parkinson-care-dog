"""PD-Dog Pi 앱 시작점 (담당: B).  실행: 레포 루트에서 `python -m pi.main`

adapter 구현(실기기/mock)을 고르고 controller·service에 주입한 뒤 메인 루프를 돈다.
"""
from __future__ import annotations

import logging
import time

from pi.app.adapters import mock
from pi.app.config import Settings, load_settings
from pi.app.controllers.robot_controller import RobotController
from pi.app.models.outbox import Outbox
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm

log = logging.getLogger("pd-dog")


def build(settings: Settings):
    if settings.mock_hardware:
        log.info("mock hardware mode")
        esp32 = mock.MockEsp32Link()
        remote = mock.MockRemote()
        power = mock.MockPowerMonitor()
        outbox = Outbox(":memory:")
    else:
        from pi.app.adapters.esp32_serial import SerialEsp32Link
        from pi.app.adapters.hardware_stubs import X1200PowerMonitor
        from pi.app.adapters.supabase_rest import SupabaseRest

        if not (settings.esp32_serial_port and settings.supabase_url and settings.supabase_service_key):
            raise SystemExit("ESP32_SERIAL_PORT, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY를 .env에 "
                             "설정하거나 PD_DOG_MOCK_HARDWARE=true로 실행하세요.")
        esp32 = SerialEsp32Link(settings.esp32_serial_port, settings.esp32_serial_baud)
        remote = SupabaseRest(settings.supabase_url, settings.supabase_service_key)
        power = X1200PowerMonitor()
        outbox = Outbox(settings.queue_path)
    sync = SyncService(outbox, remote, settings.queue_max_backoff_s)
    ctrl = RobotController(sync, remote, power, settings.esp32_status_timeout_s)
    return esp32, ctrl


def run(settings: Settings, max_seconds: float | None = None) -> None:
    esp32, ctrl = build(settings)
    started = last_hb = last_status = last_flush = time.monotonic()
    try:
        while max_seconds is None or time.monotonic() - started < max_seconds:
            now = time.monotonic()
            if now - last_hb >= settings.heartbeat_interval_s:
                esp32.send(sm.heartbeat())
                last_hb = now
            if now - last_status >= settings.status_interval_s:
                ctrl.send_status()  # 실패하면 버림 (대기열 없음)
                last_status = now
            if now - last_flush >= settings.queue_flush_interval_s:
                ctrl.sync.flush()   # 끊겼던 동안 쌓인 알람·기록 재전송
                last_flush = now
            msg = esp32.read_message(timeout_s=0.05)
            if msg is not None:
                ctrl.handle_esp32_message(msg)
            # TODO(A): 비전 루프 — pose를 remote.broadcast(settings.pose_topic, "pose", ...)로 0.4초마다
            # TODO(B): 음성 루프, 부팅 시 remote.fetch_settings() → ESP32 settings 전달
    finally:
        esp32.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(load_settings())


if __name__ == "__main__":
    main()

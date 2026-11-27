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
from pi.app.services.medication_sync import MedicationSync
from pi.app.services.power import BatteryPolicy, PowerGuard
from pi.app.services.settings_sync import SettingsSync
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm

log = logging.getLogger("pd-dog")


def build(settings: Settings):
    if settings.mock_hardware:
        log.info("mock hardware mode")
        esp32 = mock.MockEsp32Link()
        remote = mock.MockRemote()
        power = mock.MockPowerMonitor()
        host = mock.MockHost()
        outbox = Outbox(":memory:")
    else:
        from pi.app.adapters.esp32_serial import SerialEsp32Link
        from pi.app.adapters.host import LinuxHost
        from pi.app.adapters.supabase_rest import SupabaseRest
        from pi.app.adapters.x1200 import X1200PowerMonitor

        if not (settings.esp32_serial_port and settings.supabase_url and settings.supabase_service_key):
            raise SystemExit("ESP32_SERIAL_PORT, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY를 .env에 "
                             "설정하거나 PD_DOG_MOCK_HARDWARE=true로 실행하세요.")
        esp32 = SerialEsp32Link(settings.esp32_serial_port, settings.esp32_serial_baud)
        remote = SupabaseRest(settings.supabase_url, settings.supabase_service_key)
        power = X1200PowerMonitor(settings.x1200_i2c_bus, settings.x1200_i2c_addr,
                                  settings.x1200_pld_gpio, settings.x1200_pld_power_ok_level)
        host = LinuxHost()
        outbox = Outbox(settings.queue_path)
    sync = SyncService(outbox, remote, settings.queue_max_backoff_s)
    ctrl = RobotController(sync, remote, power, settings.esp32_status_timeout_s)
    ctrl.medication = MedicationSync(sync.submit, esp32.send, ctrl.next_id,
                                     settings.medication_confirm_timeout_s, settings.medication_missed_grace_s)
    settings_sync = SettingsSync(remote, esp32.send, settings.settings_poll_interval_s,
                                 settings.esp32_clock_sync_interval_s)
    policy = BatteryPolicy(settings.pi_battery_low_pct, settings.pi_battery_low_clear_pct,
                           settings.pi_battery_shutdown_pct, settings.pi_shutdown_confirm_checks,
                           settings.pi_shutdown_on_power_loss)
    guard = PowerGuard(power, esp32, sync, host, policy, ctrl.next_id)
    return esp32, ctrl, guard, settings_sync


def run(settings: Settings, max_seconds: float | None = None) -> None:
    esp32, ctrl, guard, settings_sync = build(settings)
    started = last_hb = last_status = last_flush = last_power = last_med = time.monotonic()
    try:
        while max_seconds is None or time.monotonic() - started < max_seconds:
            now = time.monotonic()
            if now - last_power >= settings.power_check_interval_s:
                last_power = now
                if guard.tick():   # 배터리 종료 시작 → 대기열 닫고 OS 종료 요청함
                    break
            if now - last_hb >= settings.heartbeat_interval_s:
                esp32.send(sm.heartbeat())
                last_hb = now
            if now - last_status >= settings.status_interval_s:
                ctrl.send_status()  # 실패하면 버림 (대기열 없음)
                last_status = now
            settings_sync.tick(now, ctrl.esp32_ok(now))   # 설정 바뀜·ESP32 재부팅 → settings, 10분마다 시계
            if now - last_med >= settings.medication_check_interval_s:
                ctrl.medication.tick()   # 로봇이 잊은 복약 대기 → missed
                last_med = now
            if now - last_flush >= settings.queue_flush_interval_s:
                ctrl.sync.flush()   # 끊겼던 동안 쌓인 알람·기록 재전송
                last_flush = now
            msg = esp32.read_message(timeout_s=0.05)
            if msg is not None:
                ctrl.handle_esp32_message(msg)
            # TODO(A): 비전 루프 — pose를 remote.broadcast(settings.pose_topic, "pose", ...)로 0.4초마다
            # TODO(B): 음성 루프 (음성 복약 확인은 ctrl.medication + sm.med_ack)
    finally:
        esp32.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(load_settings())


if __name__ == "__main__":
    main()

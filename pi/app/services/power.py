"""Pi 배터리 정책 (담당: B, 전원 정책 값은 D와 합의). 값은 Settings (config.py).

- 잔량 < pi_battery_low_pct (20%): ESP32에 pi_low 1번 → ESP32는 경보 모드 준비 + MP3 안내.
  pi_battery_low_clear_pct 이상으로 회복하거나 외부 전원이 연결되면 다시 보낼 수 있게 초기화.
- 잔량 < pi_battery_shutdown_pct (10%) 가 연속 N번, 또는 (옵션) 외부 전원 차단이 연속 N번:
  ESP32에 shutdown → 대기열 마지막 전송 시도 → 대기열 닫기 → OS 종료.
  외부 전원이 연결돼 있으면 잔량이 낮아도 종료하지 않는다 (충전 중).
- 대시보드 battery_low 알람은 DB 트리거가 robot_status에서 만든다 (여기서 따로 보내지 않음).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from pi.app.adapters.base import Esp32Link, HostSystem, PowerMonitor
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PowerDecision:
    warn_low: bool = False
    shutdown_reason: str | None = None   # "battery" / "power_loss"


class BatteryPolicy:
    """판정만 한다 (하드웨어 없음). 상태: 경고 보냈는지, 연속 확인 횟수."""

    def __init__(self, low_pct: float, low_clear_pct: float, shutdown_pct: float,
                 confirm_checks: int, shutdown_on_power_loss: bool) -> None:
        if not shutdown_pct < low_pct <= low_clear_pct:
            raise ValueError("shutdown_pct < low_pct <= low_clear_pct 이어야 합니다")
        self.low_pct = low_pct
        self.low_clear_pct = low_clear_pct
        self.shutdown_pct = shutdown_pct
        self.confirm_checks = max(1, confirm_checks)
        self.shutdown_on_power_loss = shutdown_on_power_loss
        self._low_sent = False
        self._below = 0
        self._lost = 0

    def update(self, pct: float | None, power_ok: bool | None) -> PowerDecision:
        plugged = power_ok is True

        # 저전량 경고 (한 번만, 회복·충전 시 초기화)
        warn = False
        if plugged or (pct is not None and pct >= self.low_clear_pct):
            self._low_sent = False
        elif pct is not None and pct < self.low_pct and not self._low_sent:
            self._low_sent = warn = True

        # 잔량 종료: 충전기 연결 중이면 안 함. 읽기 실패(None)는 판단 보류 (횟수 초기화)
        if not plugged and pct is not None and pct < self.shutdown_pct:
            self._below += 1
        else:
            self._below = 0

        # 외부 전원 차단 종료 (옵션). power_ok=None(미설정)은 차단으로 보지 않음
        if self.shutdown_on_power_loss and power_ok is False:
            self._lost += 1
        else:
            self._lost = 0

        reason = None
        if self._below >= self.confirm_checks:
            reason = "battery"
        elif self._lost >= self.confirm_checks:
            reason = "power_loss"
        return PowerDecision(warn_low=warn, shutdown_reason=reason)


class PowerGuard:
    """주기적으로 X1200을 읽고 정책 결과를 실행한다. adapter·서비스는 생성자로 주입."""

    def __init__(self, power: PowerMonitor, esp32: Esp32Link, sync: SyncService, host: HostSystem,
                 policy: BatteryPolicy, next_id: Callable[[], int]) -> None:
        self.power = power
        self.esp32 = esp32
        self.sync = sync
        self.host = host
        self.policy = policy
        self.next_id = next_id
        self.shutting_down = False

    def tick(self) -> bool:
        """종료를 시작했으면 True (메인 루프는 멈춘다)."""
        if self.shutting_down:
            return True
        pct = self.power.battery_pct()
        d = self.policy.update(pct, self.power.power_ok())
        if d.warn_low and pct is not None:
            log.warning("Pi 배터리 부족 %.0f%% → ESP32 pi_low", pct)
            self._send(sm.pi_low(pct, self.next_id()))
        if d.shutdown_reason:
            self.shutdown(d.shutdown_reason, pct)
        return self.shutting_down

    def shutdown(self, reason: str, pct: float | None = None) -> None:
        self.shutting_down = True
        log.warning("Pi 안전 종료 시작: reason=%s pct=%s", reason, pct)
        self._send(sm.shutdown(reason, self.next_id()))
        # 대기열은 enqueue 때 이미 SQLite에 commit됨 → 다음 부팅에 재전송. 여기선 한 번 더 보내 보기만.
        try:
            left = self.sync.flush()
            log.info("종료 전 재전송 %d건, 남은 대기열 %d건", left, len(self.sync.outbox))
        except Exception as e:  # noqa: BLE001 - 종료를 막지 않는다
            log.error("종료 전 재전송 실패: %s", e)
        try:
            self.sync.outbox.close()
        except Exception as e:  # noqa: BLE001
            log.error("대기열 닫기 실패: %s", e)
        self.host.poweroff()

    def _send(self, line: bytes) -> None:
        try:
            self.esp32.send(line)
        except Exception as e:  # noqa: BLE001 - 시리얼 끊겨도 종료는 진행
            log.error("ESP32 전송 실패: %s", e)

"""Suptronics X1200 v1.2 UPS (담당: 전원 D, Pi 코드 B). base.PowerMonitor 구현.

- 잔량: I²C1(GPIO 2·3), 주소 0x36 잔량 칩. 레지스터 0x04 = SOC (상위 바이트 %, 하위 바이트 1/256 %),
  0x02 = VCELL (상위 12비트, 1.25 mV 단위). MAX1704x 계열 형식 → 실기기에서 값 확인 (docs/todo.md).
- 외부 전원: GPIO6 전원 차단 감지(PLD). ⚠️ GPIO6은 다른 용도 금지.
  어느 레벨이 "전원 있음"인지는 Settings.x1200_pld_power_ok_level (미설정이면 감지 끔).
- smbus2·gpiozero는 Pi에서만 → 생성자 안에서 지연 import. 실패하면 해당 값만 None.
- 업무 판단(경고·종료)은 하지 않는다 → services/power.py.

확인: `python -m pi.app.adapters.x1200` (docs/setup.md 2-6)
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

REG_VCELL = 0x02
REG_SOC = 0x04
CPU_TEMP_PATH = Path("/sys/class/thermal/thermal_zone0/temp")


def soc_pct(msb: int, lsb: int) -> float:
    """SOC 레지스터 2바이트 → %. 칩이 100을 약간 넘게 줄 수 있어 0~100으로 자른다 (DB check)."""
    return max(0.0, min(100.0, msb + lsb / 256.0))


def vcell_v(msb: int, lsb: int) -> float:
    return (((msb << 8) | lsb) >> 4) * 1.25 / 1000.0


class X1200PowerMonitor:
    def __init__(self, i2c_bus: int, i2c_addr: int, pld_gpio: int, pld_power_ok_level: int | None) -> None:
        self._addr = i2c_addr
        self._bus = None
        self._pld = None
        self._ok_level = pld_power_ok_level
        self._warned: set[str] = set()

        try:
            from smbus2 import SMBus
            self._bus = SMBus(i2c_bus)
        except Exception as e:  # noqa: BLE001 - 하드웨어 없음·권한 없음 모두 "끔"으로 처리
            log.warning("X1200 잔량 칩(I²C %d, 0x%02x) 열기 실패 → pi_battery_pct=null: %s", i2c_bus, i2c_addr, e)

        if pld_power_ok_level not in (0, 1):
            log.warning("X1200_PLD_POWER_OK_LEVEL 미설정 → 전원 차단 감지·pi_charging 끔 (docs/setup.md 2-6)")
        else:
            try:
                from gpiozero import (
                    DigitalInputDevice,  # apt python3-gpiozero (시스템 경로)
                )
                # X1200이 레벨을 직접 구동 → 내부 풀업/다운 안 씀. value: HIGH=1, LOW=0
                self._pld = DigitalInputDevice(pld_gpio, pull_up=None, active_state=True)
            except Exception as e:  # noqa: BLE001
                log.warning("GPIO%d(PLD) 열기 실패 → 전원 차단 감지 끔: %s", pld_gpio, e)

    def _warn_once(self, key: str, msg: str, *args) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning(msg, *args)

    def _read2(self, reg: int) -> tuple[int, int] | None:
        if self._bus is None:
            return None
        try:
            msb, lsb = self._bus.read_i2c_block_data(self._addr, reg, 2)
        except OSError as e:
            self._warn_once(f"i2c{reg}", "X1200 I²C 읽기 실패 (reg 0x%02x): %s", reg, e)
            return None
        self._warned.discard(f"i2c{reg}")
        return msb, lsb

    def battery_pct(self) -> float | None:
        raw = self._read2(REG_SOC)
        return None if raw is None else round(soc_pct(*raw), 1)

    def battery_voltage(self) -> float | None:
        """진단용 (status에는 안 보냄)."""
        raw = self._read2(REG_VCELL)
        return None if raw is None else round(vcell_v(*raw), 3)

    def pld_level(self) -> int | None:
        """GPIO6 원래 레벨 (진단용)."""
        return None if self._pld is None else int(self._pld.value)

    def power_ok(self) -> bool | None:
        level = self.pld_level()
        return None if level is None else level == self._ok_level

    def charging(self) -> bool | None:
        return self.power_ok()

    def cpu_temp_c(self) -> float | None:
        try:
            return round(int(CPU_TEMP_PATH.read_text().strip()) / 1000.0, 1)
        except (OSError, ValueError):
            return None

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
        if self._pld is not None:
            self._pld.close()


def _diagnose() -> None:
    """Pi에서 값 확인용. 충전기를 꽂았다 뺐다 하며 PLD 레벨이 바뀌는지 본다."""
    import time

    from pi.app.config import load_settings

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = load_settings()
    # 극성을 모를 때도 원래 레벨은 보이도록 임시로 1을 넣어 GPIO를 연다 (판정값은 무시)
    pm = X1200PowerMonitor(s.x1200_i2c_bus, s.x1200_i2c_addr, s.x1200_pld_gpio,
                           s.x1200_pld_power_ok_level if s.x1200_pld_power_ok_level in (0, 1) else 1)
    print("Ctrl+C로 종료. X1200 USB-C 충전기를 꽂았다 빼 보세요.")
    try:
        while True:
            print(f"SOC={pm.battery_pct()}%  VCELL={pm.battery_voltage()}V  "
                  f"GPIO{s.x1200_pld_gpio}={pm.pld_level()}  CPU={pm.cpu_temp_c()}°C")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        pm.close()


if __name__ == "__main__":
    _diagnose()

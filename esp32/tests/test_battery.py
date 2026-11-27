"""MechDog 배터리 전압 → dog_battery_pct (PC에서: pytest esp32/tests)."""
import sys
import types
from pathlib import Path

ESP32 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ESP32))
utime = types.ModuleType("utime")
utime.ticks_diff = lambda a, b: a - b
utime.ticks_ms = lambda: 0
utime.ticks_add = lambda a, b: a + b
sys.modules.setdefault("utime", utime)

import config  # noqa: E402
from drivers import battery as bat  # noqa: E402


def test_to_pct_linear_and_clamped():
    assert bat.to_pct(6400) == 0
    assert bat.to_pct(8400) == 100
    assert bat.to_pct(7400) == 50
    assert bat.to_pct(6000) == 0           # 기준보다 낮아도 0
    assert bat.to_pct(8700) == 100         # 만충 직후 살짝 높아도 100
    assert bat.to_pct(None) is None


def test_external_power_is_not_battery():
    assert bat.to_pct(12660) is None       # 보조배터리 12V 출력 (실기기 값)


def test_unset_thresholds_turn_off(monkeypatch):
    monkeypatch.setattr(config, "DOG_BATTERY_FULL_MV", None)
    assert bat.to_pct(7400) is None


def test_reads_every_interval_and_warns_once(monkeypatch):
    values = iter([12660, 12660, 7400])
    monkeypatch.setitem(sys.modules, "Hiwonder", types.SimpleNamespace(Battery_power=lambda: next(values)))
    logs = []
    b = bat.Battery(logs.append)
    assert b.pct(0) is None                               # 1번째 읽기: 보조배터리
    assert b.pct(1000) is None                            # 5초 안에는 다시 안 읽음
    assert len(logs) == 1 and "external power" in logs[0]
    assert b.pct(config.DOG_BATTERY_READ_MS) is None      # 2번째 읽기: 같은 이유 → 경고 다시 안 함
    assert len(logs) == 1
    assert b.pct(2 * config.DOG_BATTERY_READ_MS) == 50    # LiPo로 바꾸면 %
    assert len(logs) == 1


def test_no_firmware_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "Hiwonder", raising=False)
    b = bat.Battery()
    assert b.pct(0) is None

"""넘어짐 판단 (PC에서: pytest esp32/tests). 각도는 2026-11-27 실측값."""
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
from services import tilt as tilt_mod  # noqa: E402


class FakeImu:
    def __init__(self):
        self.angle = [0.0, 0.0]

    def read_angle(self):
        return list(self.angle)


def make(monkeypatch):
    imu = FakeImu()
    monkeypatch.setitem(sys.modules, "Hiwonder_IIC", types.SimpleNamespace(MPU=lambda: imu))
    logs = []
    return tilt_mod.Tilt(logs.append), imu, logs


def run(t, start, end, step=100):
    for now in range(start, end + 1, step):
        t.tick(now)


def test_flat_and_small_sway_is_not_tipped(monkeypatch):
    t, imu, _ = make(monkeypatch)
    assert t.tipped is False
    for a in ([0.2, -0.5], [16.9, 0.1], [0.4, 33.6], [-3.8, -1.2]):   # 실측: 바닥·살짝·앞뒤 34°·마지막 자세
        imu.angle = a
        run(t, 0, 5000)
        assert t.tipped is False, a


def test_side_lying_and_upside_down_are_tipped(monkeypatch):
    for a in ([-60.4, -2.3], [-178.2, -59.4], [1.1, -82.6]):           # 옆으로 눕힘·뒤집기·앞으로 넘어감
        t, imu, logs = make(monkeypatch)
        imu.angle = a
        run(t, 0, config.TIP_HOLD_MS - 100)
        assert t.tipped is False                                         # 1초 전에는 아직
        run(t, config.TIP_HOLD_MS, config.TIP_HOLD_MS + 200)
        assert t.tipped is True, a
        assert logs and logs[-1].startswith("tipped")


def test_brief_bump_ignored(monkeypatch):
    t, imu, _ = make(monkeypatch)
    imu.angle = [-60, 0]
    run(t, 0, 500)                                                       # 0.5초만 기울었다가
    imu.angle = [0, 0]
    run(t, 600, 3000)
    imu.angle = [-60, 0]
    run(t, 3100, 3600)
    assert t.tipped is False


def test_clears_only_after_upright_for_a_while(monkeypatch):
    t, imu, logs = make(monkeypatch)
    imu.angle = [-178, 0]
    run(t, 0, 2000)
    assert t.tipped is True
    imu.angle = [40, 0]                                                  # 45 아래지만 30 위 → 아직 넘어짐
    run(t, 2100, 6000)
    assert t.tipped is True
    imu.angle = [-3.8, -1.2]
    run(t, 6100, 6100 + config.TIP_CLEAR_MS - 200)
    assert t.tipped is True
    run(t, 6100 + config.TIP_CLEAR_MS, 6100 + config.TIP_CLEAR_MS + 200)
    assert t.tipped is False
    assert logs[-1].startswith("upright")


def test_no_imu_means_unknown(monkeypatch):
    def broken():
        raise OSError("no imu")
    monkeypatch.setitem(sys.modules, "Hiwonder_IIC", types.SimpleNamespace(MPU=broken))
    logs = []
    t = tilt_mod.Tilt(logs.append)
    t.tick(0)
    assert t.tipped is None
    assert "IMU unavailable" in logs[0]

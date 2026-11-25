"""X1200·배터리 정책 테스트 (하드웨어 없음)."""
from datetime import UTC, datetime

import pytest

from pi.app.adapters import mock
from pi.app.adapters.x1200 import soc_pct, vcell_v
from pi.app.controllers.robot_controller import RobotController
from pi.app.models.outbox import Outbox
from pi.app.services.power import BatteryPolicy, PowerGuard
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import AlertReport

T0 = datetime(2026, 11, 26, 1, 0, tzinfo=UTC)


def policy(on_loss=False):
    return BatteryPolicy(low_pct=20, low_clear_pct=25, shutdown_pct=10, confirm_checks=3,
                         shutdown_on_power_loss=on_loss)


def make_guard(pct=100.0, power_ok=False, on_loss=False, online=True):
    power = mock.MockPowerMonitor(pct=pct, power_ok=power_ok)
    esp32 = mock.MockEsp32Link()
    remote = mock.MockRemote(online=online)
    sync = SyncService(Outbox(":memory:"), remote)
    host = mock.MockHost()
    ids = iter(range(1, 1000))
    guard = PowerGuard(power, esp32, sync, host, policy(on_loss), lambda: next(ids))
    return guard, power, esp32, sync, host, remote


def sent_types(esp32):
    return [sm.decode(line)["t"] for line in esp32.sent]


# ── X1200 레지스터 변환 ──
def test_soc_and_vcell_conversion():
    assert soc_pct(87, 128) == pytest.approx(87.5)
    assert soc_pct(101, 0) == 100.0          # 100 초과는 자름 (DB check)
    assert vcell_v(0xD0, 0x00) == pytest.approx(4.16)


# ── 정책 ──
def test_low_warning_once_then_rearm_after_recovery():
    p = policy()
    assert p.update(19, False).warn_low is True
    assert p.update(18, False).warn_low is False      # 한 번만
    assert p.update(22, False).warn_low is False      # 20~25 사이: 아직 초기화 안 됨
    assert p.update(19, False).warn_low is False
    assert p.update(26, False).warn_low is False      # 회복 → 초기화
    assert p.update(19, False).warn_low is True


def test_charging_suppresses_warning_and_shutdown():
    p = policy()
    for _ in range(5):
        d = p.update(5, True)
        assert d.warn_low is False and d.shutdown_reason is None


def test_shutdown_needs_consecutive_checks_and_ignores_read_failures():
    p = policy()
    assert p.update(9, False).shutdown_reason is None
    assert p.update(None, False).shutdown_reason is None   # 읽기 실패 → 횟수 초기화
    assert p.update(9, False).shutdown_reason is None
    assert p.update(9, False).shutdown_reason is None
    assert p.update(9, False).shutdown_reason == "battery"


def test_power_loss_shutdown_only_when_enabled():
    off, on = policy(on_loss=False), policy(on_loss=True)
    for _ in range(3):
        assert off.update(80, False).shutdown_reason is None
        last = on.update(80, False)
    assert last.shutdown_reason == "power_loss"
    unknown = policy(on_loss=True)
    for _ in range(5):
        assert unknown.update(80, None).shutdown_reason is None   # GPIO6 미설정


def test_policy_rejects_bad_thresholds():
    with pytest.raises(ValueError):
        BatteryPolicy(low_pct=10, low_clear_pct=25, shutdown_pct=20, confirm_checks=3,
                      shutdown_on_power_loss=False)


# ── PowerGuard ──
def test_guard_sends_pi_low_to_esp32():
    guard, _power, esp32, *_ = make_guard(pct=15)
    assert guard.tick() is False
    assert sm.decode(esp32.sent[0]) == {"t": "pi_low", "id": 1, "pct": 15}


def test_guard_shutdown_sends_message_keeps_queue_and_powers_off(tmp_path):
    guard, _power, esp32, sync, host, _remote = make_guard(pct=8, online=False)
    db = tmp_path / "outbox.db"
    sync.outbox = Outbox(db)
    sync.submit(AlertReport("touch", T0).to_op())          # 오프라인 → 대기열에 남음

    results = [guard.tick() for _ in range(3)]
    assert results == [False, False, True]
    assert sent_types(esp32) == ["pi_low", "shutdown"]
    assert sm.decode(esp32.sent[-1])["reason"] == "battery"
    assert host.poweroff_calls == 1
    assert guard.tick() is True and host.poweroff_calls == 1   # 두 번 끄지 않음
    assert len(Outbox(db)) == 1                                # 재부팅 후 재전송할 항목 보존


def test_status_uses_x1200_values():
    remote = mock.MockRemote()
    ctrl = RobotController(SyncService(Outbox(":memory:"), remote),
                           remote, mock.MockPowerMonitor(pct=42.5, power_ok=True), esp32_timeout_s=3.0)
    st = ctrl.build_status(now_s=0.0)
    assert (st.pi_battery_pct, st.pi_charging) == (42.5, True)

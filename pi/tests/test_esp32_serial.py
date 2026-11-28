"""ESP32 시리얼 끊김·재연결 (T3, 2026-11-28). 실제 포트·Supabase 없이: `pytest pi/tests`

가짜 pyserial 모듈 + 가짜 시계로 USB 분리·MechDog 전원 꺼짐을 흉내 낸다.
"""
from __future__ import annotations

import dataclasses
import logging
import time
import types

import pi.main as pi_main
from pi.app.adapters import mock
from pi.app.adapters.esp32_serial import SerialEsp32Link
from pi.app.config import load_settings
from pi.app.views import serial_messages as sm

STATUS = b'{"t":"status","mode":"walking","dog_battery_pct":80,"bpm":96}\n'


# ── 가짜 pyserial ──
class FakeSerialException(OSError):
    pass


class FakeDevice:
    """USB 장치 하나. present=False면 열기 실패, 열린 포트는 read/write에서 예외."""

    def __init__(self) -> None:
        self.present = True
        self.incoming = b""           # ESP32 → Pi (지금 열린 포트가 읽을 것)
        self.ports: list[FakeSerial] = []
        self.open_attempts = 0
        self.fail_in_waiting = False  # True면 in_waiting에서 OSError (리눅스 ioctl EIO)
        self.fail_close = False

    def unplug(self) -> None:
        self.present = False
        self.incoming = b""

    def plug(self) -> None:
        self.present = True


class FakeSerial:
    def __init__(self, dev: FakeDevice) -> None:
        self.dev = dev
        self.port = self.baudrate = self.timeout = self.dtr = self.rts = None
        self.is_open = False
        self.written = b""
        self.reset_in = self.reset_out = 0

    def open(self) -> None:
        self.dev.open_attempts += 1
        if not self.dev.present:
            raise FakeSerialException(2, "could not open port: No such file or directory")
        self.is_open = True
        self.dev.ports.append(self)

    def reset_input_buffer(self) -> None:
        self.reset_in += 1

    def reset_output_buffer(self) -> None:
        self.reset_out += 1

    def _check(self) -> None:
        if not self.dev.present:
            raise FakeSerialException("device reports readiness to read but returned no data "
                                      "(device disconnected or multiple access on port?)")

    @property
    def in_waiting(self) -> int:
        if self.dev.fail_in_waiting and not self.dev.present:
            raise OSError(5, "Input/output error")
        self._check()
        return len(self.dev.incoming)

    def read(self, n: int) -> bytes:
        self._check()
        out, self.dev.incoming = self.dev.incoming[:n], self.dev.incoming[n:]
        return out

    def write(self, data: bytes) -> int:
        self._check()
        self.written += data
        return len(data)

    def close(self) -> None:
        self.is_open = False
        if self.dev.fail_close:
            raise OSError(5, "Input/output error")


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        self.t += 0.001   # 읽기 루프가 deadline에 닿도록 조금씩 흐름
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_link(present=True):
    dev = FakeDevice()
    dev.present = present
    module = types.SimpleNamespace(Serial=lambda: FakeSerial(dev), SerialException=FakeSerialException)
    clock = FakeClock()
    link = SerialEsp32Link("/dev/ttyUSB0", 115200, serial_module=module, clock=clock, sleep=clock.sleep)
    return link, dev, clock


def run_for(link, clock, seconds, timeout_s=0.05):
    """메인 루프처럼 read_message를 반복 (가짜 시계 기준 seconds 동안)."""
    end = clock.t + seconds
    msgs = []
    calls = 0
    while clock.t < end:
        calls += 1
        msg = link.read_message(timeout_s)
        if msg is not None:
            msgs.append(msg)
    return msgs, calls


# ── 끊김: 예외가 앱으로 올라가지 않음 ──
def test_open_sets_lines_low_and_clears_old_buffers():
    link, dev, _ = make_link()
    ser = dev.ports[0]
    assert link.connected and ser.dtr is False and ser.rts is False and ser.baudrate == 115200
    assert ser.reset_in == 1 and ser.reset_out == 1


def test_read_after_unplug_returns_none_and_marks_disconnected():
    link, dev, _ = make_link()
    dev.incoming = STATUS
    assert link.read_message(0.05)["t"] == "status"
    dev.unplug()
    assert link.read_message(0.05) is None          # SerialException을 올리지 않음
    assert link.connected is False
    assert dev.ports[0].is_open is False            # 끊긴 포트는 바로 닫음 (ttyUSB 번호 유지)


def test_in_waiting_oserror_is_handled():
    link, dev, _ = make_link()
    dev.fail_in_waiting = True
    dev.unplug()
    assert link.read_message(0.05) is None
    assert link.connected is False


def test_write_after_unplug_does_not_raise():
    link, dev, _ = make_link()
    dev.unplug()
    link.send(sm.heartbeat())                       # 예외 없음
    assert link.connected is False
    link.send(sm.heartbeat())                       # 끊긴 동안은 버림


def test_close_errors_are_swallowed():
    link, dev, _ = make_link()
    dev.fail_close = True
    dev.unplug()
    assert link.read_message(0.05) is None          # 끊김 처리 중 close 실패
    assert link.connected is False
    link2, dev2, _ = make_link()
    dev2.fail_close = True
    link2.close()                                   # 앱 종료 때 close 실패
    assert link2.connected is False


def test_start_without_port_keeps_running_and_connects_later():
    link, dev, clock = make_link(present=False)     # MechDog 꺼진 채 앱 시작
    assert link.connected is False
    assert link.read_message(0.05) is None
    dev.plug()
    run_for(link, clock, 6)
    assert link.connected is True


# ── 재연결 간격·CPU·로그 ──
def test_retry_backoff_1_2_4_5_seconds():
    link, dev, clock = make_link()
    t_down = clock.t
    dev.unplug()
    link.read_message(0.05)
    attempts_at = []
    end = t_down + 23
    last = dev.open_attempts
    while clock.t < end:
        link.read_message(0.05)
        if dev.open_attempts != last:
            last = dev.open_attempts
            attempts_at.append(round(clock.t - t_down))
    assert attempts_at[:6] == [1, 3, 7, 12, 17, 22]  # 간격 1→2→4→5→5


def test_disconnected_read_sleeps_instead_of_busy_loop():
    link, dev, clock = make_link()
    dev.unplug()
    link.read_message(0.05)
    _, calls = run_for(link, clock, 10)
    assert calls <= 10 / 0.05 + 5                  # 호출마다 timeout만큼 잠듦
    assert sum(clock.sleeps) >= 9.5
    assert dev.open_attempts <= 1 + 5               # 10초 동안 재시도 5번 이하 (1,3,7 + 여유)


def test_logs_once_per_disconnect_and_once_per_recovery(caplog):
    link, dev, clock = make_link()
    caplog.set_level(logging.DEBUG, logger="pi.app.adapters.esp32_serial")
    dev.unplug()
    run_for(link, clock, 50)                        # 50초 끊김: 재시도 여러 번
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    run_for(link, clock, 15)                        # 60초 넘음 → "아직 연결 안 됨" 1번
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2 and "아직" in warnings[-1].getMessage()
    dev.plug()
    run_for(link, clock, 6)
    dev.incoming = STATUS
    run_for(link, clock, 0.2)
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(infos) == 1 and "복구" in infos[0].getMessage()


def test_flapping_port_keeps_backing_off():
    """포트는 열리는데 바로 끊기는 경우: 메시지를 받기 전엔 간격을 1초로 되돌리지 않음."""
    link, dev, clock = make_link()
    dev.unplug()
    link.read_message(0.05)
    real_open = FakeSerial.open

    def flaky_open(self):
        real_open(self)
        self.dev.present = False     # 열자마자 끊김

    FakeSerial.open = flaky_open
    try:
        dev.plug()
        before = dev.open_attempts
        start = clock.t
        while clock.t - start < 30:
            dev.present = True
            link.read_message(0.05)
        assert dev.open_attempts - before <= 8       # 1초 간격이면 30번
    finally:
        FakeSerial.open = real_open


# ── 예전 데이터·예전 명령 ──
def test_partial_line_before_unplug_is_not_merged_after_reconnect():
    link, dev, clock = make_link()
    dev.incoming = b'{"t":"status","mode":"wal'
    assert link.read_message(0.05) is None          # 줄 끝 안 옴
    dev.unplug()
    link.read_message(0.05)
    dev.plug()
    run_for(link, clock, 2)
    assert link.connected
    dev.incoming = STATUS
    msgs, _ = run_for(link, clock, 0.2)
    assert msgs == [sm.decode(STATUS)]


def test_commands_sent_while_disconnected_are_not_replayed():
    link, dev, clock = make_link()
    dev.unplug()
    link.read_message(0.05)
    link.send(sm.walk(96, 7))                       # 끊긴 동안 보낸 이동 명령
    link.send(sm.heartbeat())
    dev.plug()
    run_for(link, clock, 2)
    assert link.connected
    new_port = dev.ports[-1]
    assert new_port is not dev.ports[0]
    assert new_port.written == b""                  # 재연결해도 walk가 나가지 않음
    assert new_port.reset_out == 1                  # OS 출력 버퍼도 비움
    link.send(sm.heartbeat())
    assert new_port.written == sm.heartbeat()


# ── controller: 끊기면 바로 esp32_ok=false, 새 status 전까지 유지 ──
def make_ctrl():
    from pi.app.controllers.robot_controller import RobotController
    from pi.app.models.outbox import Outbox
    from pi.app.services.sync import SyncService

    remote = mock.MockRemote()
    sync = SyncService(Outbox(":memory:"), remote)
    return RobotController(sync, remote, mock.MockPowerMonitor(), esp32_timeout_s=3.0)


def test_lost_clears_status_immediately_until_new_status():
    ctrl = make_ctrl()
    ctrl.handle_esp32_message(sm.decode(STATUS), now_s=10.0)
    assert ctrl.build_status(now_s=10.5).esp32_ok is True
    ctrl.esp32_lost()
    st = ctrl.build_status(now_s=10.6)              # 타임아웃(3초) 전이어도
    assert st.esp32_ok is False and st.mode is None and st.dog_battery_pct is None and st.bpm is None
    assert st.pi_battery_pct == 100.0               # Pi 자체 상태는 그대로
    assert ctrl.build_status(now_s=11.0).esp32_ok is False
    ctrl.handle_esp32_message({"t": "ack", "id": 1, "ok": True}, now_s=11.5)
    assert ctrl.build_status(now_s=11.6).esp32_ok is False   # status 아닌 메시지로는 복구 안 됨
    ctrl.handle_esp32_message({"t": "status", "mode": "idle"}, now_s=12.0)
    st = ctrl.build_status(now_s=12.1)
    assert st.esp32_ok is True and st.mode == "idle" and st.bpm is None   # 예전 값 안 섞임


# ── send 실패가 서비스에 미치는 영향 ──
def test_services_survive_disconnected_link():
    from pi.app.models.outbox import Outbox
    from pi.app.services.medication_sync import MedicationSync
    from pi.app.services.power import BatteryPolicy, PowerGuard
    from pi.app.services.settings_sync import SettingsSync
    from pi.app.services.sync import SyncService

    link, dev, _ = make_link()
    dev.unplug()
    link.read_message(0.05)
    remote = mock.MockRemote()
    sync = SyncService(Outbox(":memory:"), remote)
    ids = iter(range(1, 100))
    SettingsSync(remote, link.send, 20, 600, now_text=lambda: "12:00:00").tick(0, True)
    med = MedicationSync(sync.submit, link.send, lambda: next(ids), 1800, 120)
    med.handle({"t": "med_ok", "due": "08:00", "method": "touch"})   # 끊기기 직전 받은 것 처리
    host = mock.MockHost()
    guard = PowerGuard(mock.MockPowerMonitor(pct=5.0), link, sync, host,
                       BatteryPolicy(20, 25, 10, 1, False), lambda: next(ids))
    assert guard.tick() is True                     # shutdown 메시지 전송 실패해도 안전 종료 진행
    assert host.poweroff_calls == 1


# ── 메인 루프: 끊긴 동안 계속 돌고 서버 status 유지, 재연결 뒤 설정·시계 재전송 ──
class ScriptedLink(mock.MockEsp32Link):
    """실제 시간 기준: 0–0.4초 연결, 0.4–0.9초 USB 분리, 이후 재연결 (ESP32 리셋된 것처럼 새 status)."""

    DOWN, UP = 0.4, 0.9

    def __init__(self) -> None:
        super().__init__()
        self.t0 = time.monotonic()
        self.events: list[tuple[str, float, bytes]] = []

    def phase(self) -> str:
        t = time.monotonic() - self.t0
        return "before" if t < self.DOWN else "down" if t < self.UP else "after"

    def send(self, line: bytes) -> None:
        self.connected = self.phase() != "down"
        self.events.append((self.phase(), time.monotonic() - self.t0, line))
        super().send(line)

    def read_message(self, timeout_s: float):
        self.connected = self.phase() != "down"
        time.sleep(0.002)
        if not self.connected:
            return None
        return {"t": "status", "mode": "idle", "dog_battery_pct": 70}


def test_main_loop_keeps_running_and_recovers(monkeypatch, tmp_path):
    settings = dataclasses.replace(
        load_settings(tmp_path / "none.env"), mock_hardware=True,
        heartbeat_interval_s=0.02, status_interval_s=0.05, power_check_interval_s=0.05,
        queue_flush_interval_s=0.1, medication_check_interval_s=0.1)
    built = {}
    real_build = pi_main.build

    def build(s):
        out = real_build(s)
        built["esp32"], built["ctrl"] = out[0], out[1]
        return out

    monkeypatch.setattr(pi_main.mock, "MockEsp32Link", ScriptedLink)
    monkeypatch.setattr(pi_main, "build", build)
    started = time.monotonic()
    pi_main.run(settings, max_seconds=1.4)
    assert time.monotonic() - started >= 1.35       # 끊김으로 루프가 멈추지 않음

    link: ScriptedLink = built["esp32"]
    remote = built["ctrl"].remote
    rows = remote.status_rows
    assert len(rows) >= 20                          # 끊긴 동안에도 서버 status 계속 전송
    oks = [r["esp32_ok"] for r in rows]
    # 연결 → 끊김(false, ESP32 값 없음) → 복구 순서
    first_false = oks.index(False)
    assert any(oks[:first_false])
    down_rows = [r for r in rows if r["esp32_ok"] is False]
    assert all(r["mode"] is None and r["dog_battery_pct"] is None for r in down_rows)
    assert all(r["pi_battery_pct"] == 100.0 for r in rows)
    assert oks[-1] is True

    settings_full = [(ph, t) for ph, t, line in link.events
                     if sm.decode(line)["t"] == "settings" and "med_times" in sm.decode(line)]
    assert [ph for ph, _ in settings_full] == ["before", "after"]   # 처음 1번 + 재연결 뒤 1번
    assert all("now" in sm.decode(line) for _, _, line in link.events
               if sm.decode(line)["t"] == "settings")
    assert link.dropped and all(sm.decode(line)["t"] == "hb" for line in link.dropped)

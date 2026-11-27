"""Pi 배터리 부족·종료 신호 → 현장 소리, 하트비트 (PC에서: pytest esp32/tests)."""
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
utime = sys.modules["utime"]

import config  # noqa: E402
from controllers import heartbeat as hb_mod  # noqa: E402
from services import sounds  # noqa: E402


class FakeMp3:
    def __init__(self):
        self.played = []

    def play(self, track):
        self.played.append(track)
        return track is not None


class FakeBuzzer:
    def __init__(self, ok=True):
        self.ok = ok
        self.beeps = []

    def beep(self, tones, volume, gap_ms, now):
        if not self.ok:
            return False
        self.beeps.append((tones, volume))
        return True


def set_clock(monkeypatch, ms):
    monkeypatch.setattr(utime, "ticks_ms", lambda: ms)


# ── 소리 고르기 ──

def test_mp3_track_wins_when_set(monkeypatch):
    monkeypatch.setattr(config, "MP3_TRACK_PI_LOW", 12)
    mp3, bz = FakeMp3(), FakeBuzzer()
    assert sounds.play("pi_low", mp3, bz, 0) == "mp3"
    assert mp3.played == [12] and bz.beeps == []


def test_buzzer_when_no_track(monkeypatch):
    for kind, tones, vol in (("alarm", "ALARM_BEEP_TONES", "ALARM_BEEP_VOLUME"),
                             ("pi_low", "PI_LOW_BEEP_TONES", "NOTICE_BEEP_VOLUME"),
                             ("shutdown", "SHUTDOWN_BEEP_TONES", "NOTICE_BEEP_VOLUME")):
        monkeypatch.setattr(config, "MP3_TRACK_" + kind.upper(), None)
        mp3, bz = FakeMp3(), FakeBuzzer()
        assert sounds.play(kind, mp3, bz, 0) == "beep"
        assert bz.beeps == [(getattr(config, tones), getattr(config, vol))]


def test_nothing_when_no_track_and_no_buzzer(monkeypatch):
    monkeypatch.setattr(config, "MP3_TRACK_ALARM", None)
    assert sounds.play("alarm", FakeMp3(), FakeBuzzer(ok=False), 0) is None


# ── 하트비트 ──

def test_shutdown_marks_pi_down_until_reboot(monkeypatch):
    hb = hb_mod.Heartbeat(5000)
    set_clock(monkeypatch, 1000)
    assert hb.pi_alive() is False            # hb 한 번도 없음
    hb.beat()
    assert hb.pi_alive() is True
    hb.shutdown()
    assert hb.pi_alive() is False            # hb 끊기기 전부터 무응답
    set_clock(monkeypatch, 2000)
    hb.beat()                                # 꺼지는 중에 온 hb → 그대로 무응답
    assert hb.pi_alive() is False
    set_clock(monkeypatch, 30000)            # 한동안 끊겼다가
    hb.beat()                                # 다시 옴 = 재부팅
    assert hb.pi_alive() is True


def test_timeout(monkeypatch):
    hb = hb_mod.Heartbeat(5000)
    set_clock(monkeypatch, 0)
    hb.beat()
    set_clock(monkeypatch, 4999)
    assert hb.pi_alive() is True
    set_clock(monkeypatch, 5000)
    assert hb.pi_alive() is False


# ── 시리얼 명령 ──

def make_serial(monkeypatch):
    sys.modules.setdefault("ujson", __import__("json"))
    from controllers import serial_cmd
    fake_select = types.SimpleNamespace(POLLIN=1, poll=lambda: types.SimpleNamespace(register=lambda *a: None))
    monkeypatch.setattr(serial_cmd, "select", fake_select)   # Windows select에는 poll이 없음
    sent, logs = [], []
    monkeypatch.setattr(serial_cmd, "send", sent.append)
    monkeypatch.setattr(serial_cmd, "log", logs.append)
    hb = hb_mod.Heartbeat(5000)
    mp3, bz = FakeMp3(), FakeBuzzer()
    s = serial_cmd.SerialCommands(hb, None, None, mp3, bz)
    return types.SimpleNamespace(s=s, hb=hb, mp3=mp3, bz=bz, sent=sent, logs=logs)


def test_pi_low_plays_charge_notice(monkeypatch):
    monkeypatch.setattr(config, "MP3_TRACK_PI_LOW", None)
    e = make_serial(monkeypatch)
    e.s._handle_line('{"t":"pi_low","pct":18,"id":3}')
    assert e.s.pi_battery_low is True
    assert e.bz.beeps == [(config.PI_LOW_BEEP_TONES, config.NOTICE_BEEP_VOLUME)]
    assert e.sent == [{"t": "ack", "id": 3, "ok": True}]


def test_shutdown_plays_sound_and_marks_pi_down(monkeypatch):
    monkeypatch.setattr(config, "MP3_TRACK_SHUTDOWN", None)
    e = make_serial(monkeypatch)
    set_clock(monkeypatch, 1000)
    e.hb.beat()
    e.s._handle_line('{"t":"shutdown","reason":"battery","id":4}')
    assert e.hb.pi_alive() is False
    assert e.s.pi_shutting_down is True
    assert e.bz.beeps == [(config.SHUTDOWN_BEEP_TONES, config.NOTICE_BEEP_VOLUME)]
    assert e.sent == [{"t": "ack", "id": 4, "ok": True}]

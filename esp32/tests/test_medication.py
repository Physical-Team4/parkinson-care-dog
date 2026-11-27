"""F1 복약 로직 테스트 (PC에서: pytest esp32/tests). 보드 전용 모듈(utime)은 가짜로 바꿔 끼운다."""
import sys
import types
from pathlib import Path

import pytest

ESP32 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ESP32))
utime = types.ModuleType("utime")
utime.ticks_diff = lambda a, b: a - b
utime.ticks_ms = lambda: 0
utime.ticks_add = lambda a, b: a + b
sys.modules.setdefault("utime", utime)
sys.modules.setdefault("ujson", __import__("json"))

import config  # noqa: E402
from services import medication as med_mod  # noqa: E402

MIN = 60 * 1000
HOUR = 60 * MIN
TIMEOUT = config.MED_CONFIRM_TIMEOUT_MS


class FakeMp3:
    def __init__(self):
        self.played = []

    def play(self, track):
        self.played.append(track)
        return track is not None


class FakeEyes:
    def __init__(self):
        self.calls = []

    def color(self, r, g, b):
        self.calls.append((r, g, b))

    def off(self):
        self.calls.append("off")


class FakeBuzzer:
    def __init__(self):
        self.beeps = []

    def beep(self, tones, volume, gap_ms, now):
        self.beeps.append((now, volume))
        self.tones = tones
        return True


class FakeHb:
    def __init__(self, alive=True):
        self.alive = alive

    def pi_alive(self):
        return self.alive


@pytest.fixture
def env(monkeypatch):
    sent, logs = [], []
    monkeypatch.setattr(med_mod, "send", sent.append)
    monkeypatch.setattr(med_mod, "log", logs.append)
    monkeypatch.setattr(config, "MP3_TRACK_MEDICATION", 7)
    monkeypatch.setattr(config, "MP3_TRACK_ALARM", 9)
    mp3, eyes, buzzer = FakeMp3(), FakeEyes(), FakeBuzzer()
    m = med_mod.Medication(mp3, eyes, buzzer)
    m.set_times(["08:00"])
    return types.SimpleNamespace(m=m, sent=sent, logs=logs, mp3=mp3, eyes=eyes, buzzer=buzzer, hb=FakeHb())


def kinds(sent):
    return [(s["t"], s.get("due")) for s in sent]


def test_parse():
    assert med_mod.parse_hhmm("08:30") == (8 * 60 + 30) * MIN
    assert med_mod.parse_hhmm("23:59:59", with_seconds=True) == ((23 * 60 + 59) * 60 + 59) * 1000
    for bad in ("24:00", "8", "08:60", "ab:cd", None, "08:00:00"):
        assert med_mod.parse_hhmm(bad) is None


def test_no_clock_means_no_alarm(env):
    env.m.tick(10 * HOUR, None, env.hb)
    env.m.tick(10 * HOUR + 5, None, env.hb)
    assert env.sent == []
    assert sum("no clock" in s for s in env.logs) == 1


def test_due_then_touch_ok_once_per_day(env):
    env.m.set_clock("07:59:00", 0)
    env.m.tick(30 * 1000, None, env.hb)
    assert env.sent == []
    env.m.tick(MIN, None, env.hb)
    assert kinds(env.sent) == [("med_due", "08:00")]
    assert env.mp3.played == [7]
    assert env.m.pending_due == "08:00"
    assert env.m.confirm("08:00", "touch")
    assert env.sent[-1] == {"t": "med_ok", "due": "08:00", "method": "touch"}
    env.m.tick(MIN + 10 * MIN, None, env.hb)          # 같은 날 다시 알리지 않음
    assert len(env.sent) == 2
    env.m.tick(MIN + 24 * HOUR, None, env.hb)         # 다음 날 같은 시각
    assert kinds(env.sent)[-1] == ("med_due", "08:00")


def test_missed_after_timeout_and_alarm_only_when_pi_down(env):
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    env.m.tick(TIMEOUT - 1, None, env.hb)
    assert kinds(env.sent) == [("med_due", "08:00")]
    env.m.tick(TIMEOUT, None, env.hb)
    assert kinds(env.sent)[-1] == ("med_missed", "08:00")
    assert env.mp3.played == [7]                        # Pi가 살아 있으면 경보음 없음 (원격 알림)
    assert env.m.pending_due is None

    env.hb.alive = False
    env.m.tick(24 * HOUR, None, env.hb)
    env.m.tick(24 * HOUR + TIMEOUT, None, env.hb)
    assert kinds(env.sent)[-1] == ("med_missed", "08:00")
    assert env.mp3.played[-1] == 9


def test_missed_alarm_uses_buzzer_when_no_track(env, monkeypatch):
    monkeypatch.setattr(config, "MP3_TRACK_ALARM", None)
    env.hb.alive = False
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    env.m.tick(TIMEOUT, None, env.hb)
    assert kinds(env.sent)[-1] == ("med_missed", "08:00")
    assert env.buzzer.tones == config.ALARM_BEEP_TONES
    assert env.buzzer.beeps[-1] == (TIMEOUT, config.ALARM_BEEP_VOLUME)


def test_voice_ack_clears_without_med_ok(env):
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    assert not env.m.confirm("12:00", "voice")          # 다른 시각이면 무시
    assert env.m.confirm("08:00", "voice")
    assert kinds(env.sent) == [("med_due", "08:00")]
    assert not env.m.confirm(None, "touch")             # 대기 없으면 아무것도 안 함
    env.m.tick(TIMEOUT + MIN, None, env.hb)
    assert len(env.sent) == 1


@pytest.mark.parametrize("now, fires", [("08:20:00", True), ("08:31:00", False), ("07:00:00", False)])
def test_clock_set_late(env, now, fires):
    env.m.set_clock(now, 0)
    env.m.tick(0, None, env.hb)
    assert (kinds(env.sent) == [("med_due", "08:00")]) is fires


def test_across_midnight(env):
    env.m.set_times(["23:50"])
    env.m.set_clock("23:55:00", 0)
    env.m.tick(0, None, env.hb)
    assert kinds(env.sent) == [("med_due", "23:50")]
    env.m.confirm("23:50", "touch")
    env.m.tick(10 * MIN, None, env.hb)                  # 00:05 — 같은 복약을 다시 알리지 않음
    assert len(env.sent) == 2


def test_next_due_while_pending_marks_previous_missed(env):
    env.m.set_times(["08:00", "08:10"])
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    env.m.tick(10 * MIN, None, env.hb)
    assert kinds(env.sent) == [("med_due", "08:00"), ("med_missed", "08:00"), ("med_due", "08:10")]
    assert env.m.pending_due == "08:10"


def test_resync_does_not_repeat(env):
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    env.m.confirm("08:00", "touch")
    env.m.set_clock("08:05:02", 5 * MIN)                # 10분마다 시계 다시 맞춤 (약간 어긋남)
    env.m.tick(5 * MIN + 1000, None, env.hb)
    assert len(env.sent) == 2
    env.m.tick(24 * HOUR, None, env.hb)                 # 다음 날은 다시 알림
    assert kinds(env.sent)[-1] == ("med_due", "08:00")


def test_set_times_validation(env):
    assert not env.m.set_times(["08:00", "25:00"])      # 하나라도 틀리면 통째로 무시
    assert env.m.times == ["08:00"]
    assert not env.m.set_times(["%02d:00" % h for h in range(9)])   # 9개
    assert env.m.set_times(["12:00", "08:00", "08:00"])
    assert env.m.times == ["08:00", "12:00"]
    assert env.m.set_times([])                          # 복약 알림 없음
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    assert env.sent == []


def test_eyes_blink_while_pending_and_yield_to_touch(env):
    blue = config.MED_EYES_COLOR
    step = config.MED_BLINK_MS
    env.m.tick(0, None, env.hb)
    assert env.eyes.calls == []                         # 대기 없으면 눈 그대로
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)                         # med_due
    env.m.tick(1, None, env.hb)
    assert env.eyes.calls == [blue]
    env.m.tick(1 + step, None, env.hb)
    env.m.tick(1 + 2 * step, None, env.hb)
    assert env.eyes.calls == [blue, "off", blue]
    env.m.hold_eyes = True                              # 터치 중: 깜빡임이 덮어쓰지 않음
    env.m.tick(1 + 3 * step, None, env.hb)
    assert len(env.eyes.calls) == 3
    env.m.confirm("08:00", "touch")                     # 터치가 눈을 쓰는 중이면 끄지도 않음 (초록 표시 유지)
    assert len(env.eyes.calls) == 3
    env.m.hold_eyes = False
    env.m.tick(1 + 4 * step, None, env.hb)
    assert len(env.eyes.calls) == 3                     # 확인 후 더 깜빡이지 않음


def test_eyes_off_when_missed(env):
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    env.m.tick(1, None, env.hb)
    assert env.eyes.calls[-1] == config.MED_EYES_COLOR
    env.m.tick(TIMEOUT, None, env.hb)
    assert env.eyes.calls[-1] == "off"
    assert env.m.pending_due is None


def test_soft_beep_at_due_and_every_minute_until_confirmed(env):
    rep = config.MED_BEEP_REPEAT_MS
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    assert env.buzzer.beeps == [(0, config.MED_BEEP_VOLUME)]
    env.m.tick(rep - 1, None, env.hb)
    assert len(env.buzzer.beeps) == 1
    env.m.tick(rep, None, env.hb)
    env.m.tick(2 * rep, None, env.hb)
    assert [b[0] for b in env.buzzer.beeps] == [0, rep, 2 * rep]
    env.m.confirm("08:00", "touch")
    env.m.tick(3 * rep, None, env.hb)
    assert len(env.buzzer.beeps) == 3                   # 확인하면 그만


def test_buzzer_driver_plays_tones_without_blocking(monkeypatch):
    calls = []

    class FakeBz:
        def setVolume(self, v):
            calls.append(("vol", v))

        def playTone(self, f, ms, wait):
            calls.append((f, ms, wait))

    monkeypatch.setitem(sys.modules, "Hiwonder", types.SimpleNamespace(bz=FakeBz()))
    from drivers.buzzer import Buzzer
    b = Buzzer()
    assert b.beep([(1500, 120), (1800, 120)], 100, 80, 1000)
    b.tick(1000)
    assert calls == [("vol", 100), (1500, 120, False)]  # 기다리지 않음
    b.tick(1000 + 199)
    assert len(calls) == 2                              # 120ms + 간격 80ms 전에는 다음 음 안 냄
    b.tick(1000 + 200)
    assert calls[-1] == (1800, 120, False)
    b.tick(5000)
    assert len(calls) == 4                              # 끝


def test_beep_is_five_bibik_with_pauses(env):
    env.m.set_clock("08:00:00", 0)
    env.m.tick(0, None, env.hb)
    tones = env.buzzer.tones
    sounds = [t for t in tones if t[0]]
    rests = [t for t in tones if not t[0]]
    assert len(sounds) == len(config.MED_BEEP_TONES) * config.MED_BEEP_COUNT == 10
    assert rests == [(0, config.MED_BEEP_PAUSE_MS)] * (config.MED_BEEP_COUNT - 1)
    assert tones[-1][0] != 0                            # 쉼표로 끝나지 않음


def test_buzzer_rest_makes_no_sound(monkeypatch):
    calls = []

    class FakeBz:
        def setVolume(self, v):
            pass

        def playTone(self, f, ms, wait):
            calls.append((f, ms))

    monkeypatch.setitem(sys.modules, "Hiwonder", types.SimpleNamespace(bz=FakeBz()))
    from drivers.buzzer import Buzzer
    b = Buzzer()
    b.beep([(1500, 100), (0, 300), (1500, 100)], 100, 0, 0)
    for t in (0, 100, 400):
        b.tick(t)
    assert calls == [(1500, 100), (1500, 100)]          # 쉼표는 소리 없이 300ms만 기다림

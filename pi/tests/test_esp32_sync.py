"""F1 복약 기록·설정 전달 (Pi ↔ ESP32). 하드웨어·인터넷 없이: `pytest pi/tests`"""
from datetime import datetime, timedelta, timezone

from pi.app.adapters import mock
from pi.app.models.outbox import Outbox
from pi.app.services.medication_sync import MedicationSync, due_at
from pi.app.services.settings_sync import SettingsSync
from pi.app.services.sync import SyncService
from pi.app.views import serial_messages as sm

KST = timezone(timedelta(hours=9))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def make_med(local_time):
    remote = mock.MockRemote()
    sync = SyncService(Outbox(":memory:"), remote)
    sent = []
    clock = Clock(local_time.astimezone(timezone.utc))
    med = MedicationSync(sync.submit, sent.append, lambda: 7, 1800, 120, clock=clock, tz=KST)
    return med, remote, sent, clock


def logs(remote):
    out = []
    for op in remote.executed:
        if op.target == "medication_logs":
            out.append((op.kind, op.payload["due_at"], op.payload["status"]))
        elif op.target == "mark_medication_missed":
            out.append(("rpc", op.payload["p_due_at"], "missed"))
    return out


def alerts(remote):
    return [op.payload["p_source"] for op in remote.executed if op.target == "report_alert"]


# ── due "HH:MM" → 날짜 ──
def test_due_at_today_or_yesterday():
    now = datetime(2026, 11, 27, 0, 10, tzinfo=KST)
    assert due_at("00:05", now) == datetime(2026, 11, 27, 0, 5, tzinfo=KST)
    assert due_at("23:50", now) == datetime(2026, 11, 26, 23, 50, tzinfo=KST)    # 자정 넘김
    assert due_at("01:00", now) == datetime(2026, 11, 27, 1, 0, tzinfo=KST)      # 1시간 안 미래는 오늘


# ── 복약 기록 ──
def test_due_then_touch_confirm():
    med, remote, _, _ = make_med(datetime(2026, 11, 27, 8, 0, 3, tzinfo=KST))
    med.handle({"t": "med_due", "due": "08:00"})
    med.handle({"t": "med_ok", "due": "08:00", "method": "touch"})
    assert logs(remote) == [("insert", "2026-11-27T08:00:00+09:00", "pending"),
                            ("upsert", "2026-11-27T08:00:00+09:00", "confirmed")]
    ok = [op for op in remote.executed if op.payload.get("status") == "confirmed"][0]
    assert ok.payload["method"] == "touch" and ok.payload["confirmed_at"]
    assert ok.on_conflict == "due_at"
    assert alerts(remote) == []


def test_missed_writes_log_and_alert():
    med, remote, _, _ = make_med(datetime(2026, 11, 27, 8, 30, tzinfo=KST))
    med.handle({"t": "med_due", "due": "08:00"})
    med.handle({"t": "med_missed", "due": "08:00"})
    assert logs(remote)[-1] == ("rpc", "2026-11-27T08:00:00+09:00", "missed")   # pending일 때만 바꿈 (db 005)
    assert alerts(remote) == ["medication_missed"]
    alert = [op for op in remote.executed if op.target == "report_alert"][0]
    assert alert.payload["p_detail"] == {"due": "08:00"}
    assert alert.payload["p_occurred_at"].endswith("+00:00")      # 알람 시각은 UTC


def test_robot_reannounces_confirmed_dose_gets_med_ack():
    # 로봇 재부팅 → 30분 안의 복약을 다시 알림 → Pi가 이미 확인된 것을 알려 줌 (pending으로 덮지 않음)
    med, remote, sent, _ = make_med(datetime(2026, 11, 27, 8, 5, tzinfo=KST))
    med.handle({"t": "med_due", "due": "08:00"})
    med.handle({"t": "med_ok", "due": "08:00", "method": "touch"})
    n = len(remote.executed)
    med.handle({"t": "med_due", "due": "08:00"})
    assert len(remote.executed) == n
    assert sm.decode(sent[-1]) == {"t": "med_ack", "id": 7, "due": "08:00"}
    med.handle({"t": "med_missed", "due": "08:00"})                # 그래도 missed가 오면 무시
    assert len(remote.executed) == n


def test_pending_forgotten_by_robot_becomes_missed():
    med, remote, _, clock = make_med(datetime(2026, 11, 27, 8, 0, tzinfo=KST))
    med.handle({"t": "med_due", "due": "08:00"})                   # 그 뒤 로봇이 꺼졌다 켜짐 → 아무것도 안 옴
    clock.t += timedelta(minutes=31)
    med.tick()
    assert alerts(remote) == []                                    # 여유 2분 안
    clock.t += timedelta(minutes=2)
    med.tick()
    assert logs(remote)[-1][2] == "missed" and alerts(remote) == ["medication_missed"]
    med.tick()
    assert alerts(remote) == ["medication_missed"]                 # 한 번만


def test_bad_due_ignored():
    med, remote, _, _ = make_med(datetime(2026, 11, 27, 8, 0, tzinfo=KST))
    for due in (None, "8시", "25:00x", 800):
        med.handle({"t": "med_due", "due": due})
    assert remote.executed == []


# ── 설정·시계 전달 ──
def make_settings():
    remote = mock.MockRemote()
    remote.settings = {"target_bpm": 100, "target_db": 68, "follow_limit_cm": 180, "medication_times": ["14:48"]}
    sent = []
    s = SettingsSync(remote, sent.append, poll_s=20, clock_s=600, now_text=lambda: "16:00:00")
    return s, remote, [], sent


def msgs(sent):
    return [sm.decode(x) for x in sent]


def test_settings_sent_on_start_change_and_clock():
    s, remote, _, sent = make_settings()
    s.tick(0, esp32_ok=False)
    assert sent == []                                              # 보드가 아직 없으면 안 보냄
    s.tick(1, esp32_ok=True)
    assert msgs(sent) == [{"t": "settings", "now": "16:00:00", "med_times": ["14:48"],
                           "bpm": 100, "follow_limit_cm": 180}]
    s.tick(10, True)
    s.tick(21, True)                                               # 다시 읽었지만 같음 → 안 보냄
    assert len(sent) == 1
    remote.settings["medication_times"] = ["08:00", "20:00"]
    s.tick(42, True)                                               # 대시보드에서 바뀜
    assert msgs(sent)[-1]["med_times"] == ["08:00", "20:00"]
    s.tick(42 + 600, True)                                         # 10분 → 시계만
    assert msgs(sent)[-1] == {"t": "settings", "now": "16:00:00"}


def test_settings_resent_after_robot_restart_even_offline():
    s, remote, _, sent = make_settings()
    s.tick(0, True)
    remote.online = False
    s.tick(5, False)                                               # 로봇 재부팅 중
    s.tick(9, True)                                                # 다시 옴, 인터넷은 끊김
    assert len(sent) == 2
    assert msgs(sent)[-1] == {"t": "settings", "now": "16:00:00", "med_times": ["14:48"],
                              "bpm": 100, "follow_limit_cm": 180}


def test_settings_clock_only_when_never_fetched():
    s, remote, _, sent = make_settings()
    remote.online = False
    s.tick(0, True)
    assert msgs(sent) == [{"t": "settings", "now": "16:00:00"}]    # 인터넷 없이도 시계는
    remote.online = True
    s.tick(20, True)
    assert msgs(sent)[-1]["med_times"] == ["14:48"]

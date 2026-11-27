"""F6 낙상·F7 무움직임 판정 시나리오 테스트 (가짜 관절 시퀀스, 하드웨어 없음).

임계값은 Settings 기본값(임시값) 그대로 쓴다 → 값을 바꾸면 이 테스트로 동작을 다시 확인.
"""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from pi.app.adapters import mock
from pi.app.adapters.base import PersonPose
from pi.app.config import Settings
from pi.app.models.outbox import Outbox
from pi.app.services.sync import SyncService
from pi.app.services.vision.fall import FallConfig, FallDetector, classify
from pi.app.services.vision.monitor import VisionMonitor
from pi.app.services.vision.pose_features import extract, pick_primary

ASPECT = 640 / 480
T0 = datetime(2026, 11, 27, 3, 0, tzinfo=timezone.utc)
S = Settings(mock_hardware=True, supabase_url=None, supabase_service_key=None, esp32_serial_port=None,
             esp32_serial_baud=115200, queue_path=Path(":memory:"), log_dir=Path("."), model_dir=Path("."))

# 자세별 관절 (x, y), 프레임 기준 0~1. 인덱스: 0 코, 5·6 어깨, 11·12 엉덩이, 13·14 무릎, 15·16 발목
_PTS = {
    "standing": ({0: (.50, .20), 5: (.47, .30), 6: (.53, .30), 11: (.48, .55), 12: (.52, .55),
                  13: (.48, .75), 14: (.52, .75), 15: (.48, .95), 16: (.52, .95)}, (.42, .15, .58, .97)),
    "sitting": ({0: (.50, .35), 5: (.47, .45), 6: (.53, .45), 11: (.48, .70), 12: (.52, .70),
                 13: (.62, .70), 14: (.64, .70), 15: (.62, .90), 16: (.64, .90)}, (.42, .30, .68, .95)),
    "floor_sit": ({0: (.50, .60), 5: (.47, .68), 6: (.53, .68), 11: (.48, .90), 12: (.52, .90),
                   13: (.62, .88), 14: (.64, .88), 15: (.72, .92), 16: (.74, .92)}, (.42, .55, .78, .95)),
    "lying": ({0: (.20, .85), 5: (.30, .84), 6: (.30, .86), 11: (.55, .84), 12: (.55, .86),
               13: (.72, .84), 14: (.72, .86), 15: (.88, .84), 16: (.88, .86)}, (.15, .78, .92, .92)),
    # 소파에 누움: 엉덩이가 앉았을 때(sitting) 높이 그대로
    "sofa_lying": ({0: (.20, .66), 5: (.30, .69), 6: (.30, .71), 11: (.55, .69), 12: (.55, .71),
                    13: (.72, .69), 14: (.72, .71), 15: (.88, .69), 16: (.88, .71)}, (.15, .62, .92, .76)),
}


def pose(name, t=1.0, frm="standing", conf=0.9, dx=0.0, dy=0.0, score=0.9):
    """frm → name 사이를 t(0~1)로 보간한 PersonPose. 정의 안 된 관절은 신뢰도 0.1."""
    a_pts, a_box = _PTS[frm]
    b_pts, b_box = _PTS[name]
    k = np.zeros((17, 3), np.float32)
    k[:, 2] = 0.1
    for i in b_pts:
        (ax, ay), (bx, by) = a_pts[i], b_pts[i]
        k[i] = (ax + (bx - ax) * t + dx, ay + (by - ay) * t + dy, conf)
    box = tuple(a + (b - a) * t + (dx if j % 2 == 0 else dy) for j, (a, b) in enumerate(zip(a_box, b_box)))
    return PersonPose(box, score, k)


def feats(p):
    return extract(p, S.vision_kpt_min_conf, ASPECT)


def timeline(*segments, fps=10):
    """segments: (초, people 또는 t(0~1)→people 함수). [(now, people)] 생성."""
    out, now = [], 0.0
    for dur, src in segments:
        n = int(round(dur * fps))
        for i in range(n):
            out.append((now, src((i + 1) / n) if callable(src) else src))
            now += 1 / fps
    return out


def run_fall(frames, cfg=None):
    det = FallDetector(cfg or FallConfig.from_settings(S))
    states, alarms = [], []
    for now, people in frames:
        _, f = pick_primary(people, S.vision_kpt_min_conf, ASPECT)
        u = det.update(f, now)
        states.append(u.state)
        if u.alarm:
            alarms.append((now, u.alarm))
    return states, alarms


def make_monitor():
    remote = mock.MockRemote()
    sync = SyncService(Outbox(":memory:"), remote)
    return VisionMonitor.from_settings(S, sync, clock=lambda: T0), remote


STAND, SIT, LIE = [pose("standing")], [pose("sitting")], [pose("lying")]


# ── 자세 분류 ──
@pytest.mark.parametrize("name,expected", [("standing", "standing"), ("sitting", "sitting"),
                                           ("floor_sit", "sitting"), ("lying", "lying")])
def test_classify(name, expected):
    assert classify(feats(pose(name)), FallConfig.from_settings(S)) == expected


def test_torso_angle_uses_pixel_aspect():
    assert feats(pose("standing")).torso_deg == pytest.approx(0, abs=1)
    assert feats(pose("lying")).torso_deg == pytest.approx(90, abs=1)


def test_partial_body_is_not_judged():
    """팔만 보이는 경우 (어깨·엉덩이 없음) → 판정 불가."""
    k = np.zeros((17, 3), np.float32)
    k[[7, 9], :] = (0.3, 0.5, 0.9)
    arm = PersonPose((0.0, 0.3, 0.8, 1.0), 0.68, k)
    assert feats(arm) is None
    person, f = pick_primary([arm], S.vision_kpt_min_conf, ASPECT)
    assert person is arm and f is None


# ── F6 ──
def test_fall_then_lying_alarms_once():
    frames = timeline((2, STAND), (0.5, lambda t: [pose("lying", t)]), (6, LIE))
    states, alarms = run_fall(frames)
    assert "falling" in states and states[-1] == "lying"
    assert len(alarms) == 1
    when, a = alarms[0]
    assert a.path == "descent" and a.confidence == pytest.approx(0.9, abs=0.01)
    assert 2.0 <= a.event_s <= 2.5                          # 쓰러지기 시작한 시각
    assert when == pytest.approx(2.5 + S.fall_confirm_lying_s, abs=0.6)
    assert a.detail["descent_ratio"] >= S.fall_descent_ratio


def test_fast_sit_to_floor_no_alarm():
    """머리가 크게 내려가도 앉은 자세로 끝나면 알람 없음 (털썩 앉기)."""
    frames = timeline((2, STAND), (0.4, lambda t: [pose("floor_sit", t)]), (20, [pose("floor_sit")]))
    states, alarms = run_fall(frames)
    assert "falling" in states and alarms == [] and states[-1] == "sitting"


def test_chair_sit_no_alarm():
    _, alarms = run_fall(timeline((2, STAND), (0.8, lambda t: [pose("sitting", t)]), (30, SIT)))
    assert alarms == []


def test_lying_without_seen_fall_alarms_later_with_lower_conf():
    states, alarms = run_fall(timeline((S.fall_lying_only_s + 2, LIE)))
    assert len(alarms) == 1
    when, a = alarms[0]
    assert a.path == "lying_only" and when == pytest.approx(S.fall_lying_only_s, abs=0.2)
    assert a.confidence == pytest.approx(S.fall_conf_lying_only * 0.9, abs=0.01)


def test_lying_only_can_be_disabled():
    cfg = FallConfig.from_settings(S)
    cfg = FallConfig(**{**cfg.__dict__, "lying_only_s": None})
    assert run_fall(timeline((120, LIE)), cfg)[1] == []


def test_no_repeat_alarm_until_person_gets_up():
    fall = ((2, STAND), (0.5, lambda t: [pose("lying", t)]), (40, LIE))
    _, alarms = run_fall(timeline(*fall, (S.fall_rearm_upright_s + 2, STAND), *fall))
    assert [a.path for _, a in alarms] == ["descent", "descent"]


def test_brief_loss_keeps_lying_long_loss_resets():
    _, alarms = run_fall(timeline((2, STAND), (0.5, lambda t: [pose("lying", t)]),
                                  (1, LIE), (1, []), (3, LIE)))
    assert len(alarms) == 1                                   # 1초 가려져도 이어서 확정
    states, alarms = run_fall(timeline((2, LIE), (S.vision_lost_tolerance_s + 1, [])))
    assert states[-1] == "none" and alarms == []


# ── F7 ──
def run_monitor(frames, mode="idle", esp32_ok=True):
    mon, remote = make_monitor()
    for now, people in frames:
        mon.update(people, now, mode, esp32_ok)
    return [op.payload for op in remote.executed]


def jitter(seed=0):
    rng = np.random.default_rng(seed)
    return lambda t: [pose("sitting", dx=rng.uniform(-.004, .004), dy=rng.uniform(-.004, .004))]


def test_no_motion_alarm_after_n_minutes():
    n = S.no_motion_minutes_sitting * 60
    sent = run_monitor(timeline((n - 5, jitter()), fps=2))
    assert [p["p_source"] for p in sent] == []
    sent = run_monitor(timeline((n + 5, jitter()), fps=2))
    assert [p["p_source"] for p in sent] == ["no_motion"]
    assert sent[0]["p_confidence"] is None and sent[0]["p_detail"]["still_min"] >= S.no_motion_minutes_sitting


def test_movement_restarts_no_motion_timer():
    n = S.no_motion_minutes_sitting * 60
    moved = [pose("sitting", dx=0.1)]
    sent = run_monitor(timeline((n / 2, jitter()), (1, moved), (n - 10, [pose("sitting", dx=0.1)]), fps=2))
    assert sent == []


@pytest.mark.parametrize("mode,ok", [("walking", True), ("idle", False), (None, True)])
def test_no_motion_paused_when_robot_moving_or_unknown(mode, ok):
    assert run_monitor(timeline((S.no_motion_minutes_sitting * 60 + 30, jitter()), fps=2), mode, ok) == []


def test_absent_person_resets_no_motion_but_short_gap_does_not():
    n = S.no_motion_minutes_sitting * 60
    gap_long = S.no_motion_absent_reset_s + 5
    assert run_monitor(timeline((n / 2, jitter()), (gap_long, []), (n / 2, jitter(1)), fps=2)) == []
    sent = run_monitor(timeline((n / 2, jitter()), (3, []), (n / 2 + 5, jitter(1)), fps=2))
    assert [p["p_source"] for p in sent] == ["no_motion"]


# ── 묶음 ──
def test_monitor_sends_camera_alert_and_pose():
    mon, remote = make_monitor()
    frames = timeline((2, STAND), (0.5, lambda t: [pose("lying", t)]), (5, LIE))
    for now, people in frames:
        p = mon.update(people, now, "idle", True)
    assert p.state == "lying" and len(p.to_json()["keypoints"]) == 17
    [op] = remote.executed
    assert op.target == "report_alert" and op.payload["p_source"] == "camera"
    assert 0 < op.payload["p_confidence"] <= 1
    assert op.payload["p_occurred_at"] < T0.isoformat()      # 쓰러지기 시작한 시각 (확정보다 이전)
    assert "keypoints" not in op.payload["p_detail"]          # 키포인트 이력 금지
    assert mon.update([], frames[-1][0] + 10, "idle", True).to_json() == {"state": "none", "keypoints": []}


# ── F6 느린 낙상 vs 스스로 눕기 (엉덩이 높이) ──
SETTLE = S.fall_settle_s + 1


def test_slow_collapse_from_standing_alarms():
    """서 있다가 4초에 걸쳐 천천히 무너짐 → 빠른 하강은 아니지만 엉덩이가 크게 내려감 → slow_fall."""
    states, alarms = run_fall(timeline((SETTLE, STAND), (4, lambda t: [pose("lying", t)]), (8, LIE)))
    assert [a.path for _, a in alarms] == ["slow_fall"]
    when, a = alarms[0]
    assert a.detail["from"] == "standing" and a.detail["hip_drop"] >= S.slow_fall_hip_drop_ratio
    assert a.event_s == pytest.approx(SETTLE, abs=1.5)        # 기준 자세를 벗어난 때
    assert "falling" in states


def test_slide_off_chair_alarms():
    """의자에 앉아 있다가 3초에 걸쳐 바닥으로 미끄러져 누움 → slow_fall (from sitting)."""
    _, alarms = run_fall(timeline((SETTLE, SIT), (3, lambda t: [pose("lying", t, frm="sitting")]), (8, LIE)))
    assert [(a.path, a.detail["from"]) for _, a in alarms] == [("slow_fall", "sitting")]


def test_lie_down_on_sofa_no_alarm():
    """소파에 앉아 있다가 천천히 눕기 → 엉덩이 높이 그대로 → 알람 없음 (lying_only도 안 남)."""
    sofa = [pose("sofa_lying")]
    states, alarms = run_fall(timeline((SETTLE, SIT), (3, lambda t: [pose("sofa_lying", t, frm="sitting")]),
                                       (S.fall_lying_only_s + 30, sofa)))
    assert alarms == [] and states[-1] == "lying"


def test_flop_onto_sofa_no_alarm():
    """소파에 털썩 눕기: 머리는 빠르게 내려가지만(falling) 엉덩이 높이 그대로 → 취소, 알람 없음."""
    states, alarms = run_fall(timeline((SETTLE, SIT), (0.5, lambda t: [pose("sofa_lying", t, frm="sitting")]),
                                       (20, [pose("sofa_lying")])))
    assert "falling" in states and alarms == [] and states[-1] == "lying"


def test_floor_sit_then_lie_down_no_alarm():
    """바닥에 앉아 있다가 요에 눕기 (좌식 생활) → 엉덩이가 더 내려가지 않음 → 알람 없음."""
    _, alarms = run_fall(timeline((SETTLE, [pose("floor_sit")]),
                                  (3, lambda t: [pose("lying", t, frm="floor_sit")]), (S.fall_lying_only_s + 30, LIE)))
    assert alarms == []


def test_brief_crouch_during_slow_fall_does_not_reset_reference():
    """천천히 무너지다 2초 웅크림(앉음으로 분류) → settle 못 채움 → 기준은 서 있던 자세 그대로."""
    crouch = [pose("sitting", 0.6, frm="standing")]
    _, alarms = run_fall(timeline((SETTLE, STAND), (1, lambda t: [pose("sitting", 0.6 * t)]), (2, crouch),
                                  (3, lambda t: [pose("lying", t, frm="sitting")]), (8, LIE)))
    assert [a.path for _, a in alarms] == ["slow_fall"]


def test_unseen_onset_still_uses_lying_only():
    """오래 사람을 놓쳤다가(기준 자세 초기화) 누운 상태로 발견 → lying_only."""
    _, alarms = run_fall(timeline((SETTLE, SIT), (S.vision_lost_tolerance_s + 2, []), (S.fall_lying_only_s + 2, LIE)))
    assert [a.path for _, a in alarms] == ["lying_only"]


# ── 일어나자마자 쓰러짐 (기준 자세 바로 올림) ──
def test_rise_from_floor_then_fall_immediately_alarms():
    """요에 앉아 있다가(기준=바닥 앉음) 일어서서 2초 만에 쓰러짐 → 기준이 서 있는 높이로 올라가 있어 알람."""
    _, alarms = run_fall(timeline((SETTLE, [pose("floor_sit")]), (1.5, lambda t: [pose("standing", t, frm="floor_sit")]),
                                  (2, STAND), (0.5, lambda t: [pose("lying", t)]), (8, LIE)))
    assert len(alarms) == 1 and alarms[0][1].path in ("descent", "slow_fall")


def test_stand_up_from_sofa_and_flop_back_within_settle_alarms():
    """소파에서 일어섰다가 5초 안에 다시 털썩 눕기 → 기준이 서 있는 높이 → 알람 (안전한 쪽 오알람, 의도된 동작)."""
    _, alarms = run_fall(timeline((SETTLE, SIT), (1, lambda t: [pose("standing", t, frm="sitting")]), (2, STAND),
                                  (0.5, lambda t: [pose("sofa_lying", t)]), (8, [pose("sofa_lying")])))
    assert len(alarms) == 1


# ── 마지막 상태 기억 ──
def sofa_rest(extra=10):
    return ((SETTLE, SIT), (3, lambda t: [pose("sofa_lying", t, frm="sitting")]),
            (S.slow_fall_confirm_s + extra, [pose("sofa_lying")]))


def test_rest_on_sofa_sets_resting():
    det = FallDetector(FallConfig.from_settings(S))
    for now, people in timeline(*sofa_rest()):
        det.update(pick_primary(people, S.vision_kpt_min_conf, ASPECT)[1], now)
    assert det.resting


def test_found_again_resting_same_spot_no_alarm():
    """소파에서 쉬다가 로봇이 5분 놓침 → 다시 보니 같은 자리에 누워 있음 → 계속 쉬는 중, 알람 없음."""
    states, alarms = run_fall(timeline(*sofa_rest(), (300, []), (S.fall_lying_only_s + 60, [pose("sofa_lying")])))
    assert alarms == [] and states[-1] == "lying"


def test_found_lying_elsewhere_after_rest_alarms():
    """쉬다가 놓친 사이 자리가 바뀜 → 기억을 쓰지 않고 lying_only.
    다른 자리 = 엉덩이 높이 차이가 몸통 길이의 절반 이상 (소파 약 40cm vs 몸통 약 50cm)."""
    floor = [pose("lying", dy=0.08)]
    _, alarms = run_fall(timeline(*sofa_rest(), (300, []), (S.fall_lying_only_s + 2, floor)))
    assert [a.path for _, a in alarms] == ["lying_only"]


def test_rest_memory_expires():
    gap = S.vision_context_memory_s + 10
    _, alarms = run_fall(timeline(*sofa_rest(), (gap, []), (S.fall_lying_only_s + 2, [pose("sofa_lying")]), fps=2))
    assert [(a.path, a.detail["last_seen"]) for _, a in alarms] == [("lying_only", "unknown")]


def test_last_seen_standing_then_found_lying_alarms_fast():
    """서 있던 사람을 놓쳤다가 다시 보니 누워 있음 → 10초 후 알람 (60초 기다리지 않음)."""
    _, alarms = run_fall(timeline((SETTLE, STAND), (S.vision_lost_tolerance_s + 3, []),
                                  (S.fall_unseen_after_standing_s + 2, LIE)))
    assert len(alarms) == 1
    when, a = alarms[0]
    assert a.detail["last_seen"] == "standing" and a.confidence == pytest.approx(S.fall_conf_unseen_standing * 0.9, abs=.01)


def test_last_seen_sitting_then_found_lying_uses_normal_wait():
    _, alarms = run_fall(timeline((SETTLE, SIT), (S.vision_lost_tolerance_s + 3, []), (30, LIE)))
    assert alarms == []


# ── 자세별 F7 ──
def still(name, seed=0):
    rng = np.random.default_rng(seed)
    return lambda t: [pose(name, dx=rng.uniform(-.004, .004), dy=rng.uniform(-.004, .004))]


def test_no_motion_standing_is_short():
    n = S.no_motion_minutes_standing * 60
    sent = run_monitor(timeline((n + 5, still("standing")), fps=2))
    assert [(p["p_source"], p["p_detail"]["posture"]) for p in sent] == [("no_motion", "standing")]


def test_no_motion_sitting_tv_not_before_limit():
    sent = run_monitor(timeline((S.no_motion_minutes_sitting * 60 - 30, still("sitting")), fps=1))
    assert sent == []


def test_no_motion_off_while_resting():
    """소파에 스스로 누워 1시간 잠 → F7 알람 없음, F6 알람도 없음."""
    sent = run_monitor(timeline(*sofa_rest(), (3600, still("sofa_lying")), fps=1))
    assert sent == []


# ── 취침 선언 ──
def run_fall_sleep(frames, declare_at=0.0):
    det = FallDetector(FallConfig.from_settings(S))
    alarms, states = [], []
    for now, people in frames:
        if declare_at is not None and now >= declare_at:
            det.set_sleep_mode(True, now)
            declare_at = None
        u = det.update(pick_primary(people, S.vision_kpt_min_conf, ASPECT)[1], now)
        states.append((u.state, det.sleep_mode))
        if u.alarm:
            alarms.append(u.alarm)
    return det, states, alarms


def test_sleep_declared_then_lie_on_floor_from_standing_no_alarm():
    """"잘게" 후 서 있다가 천천히 요에 눕기 → 느린 하강이어도 잠."""
    det, _, alarms = run_fall_sleep(timeline((SETTLE, STAND), (4, lambda t: [pose("lying", t)]), (120, LIE)))
    assert alarms == [] and det.resting and det.sleep_mode == "asleep"


def test_sleep_declared_found_lying_unseen_no_alarm():
    """선언 후 로봇이 놓쳤다가 바닥에 누운 사람 발견 → 잠."""
    _, _, alarms = run_fall_sleep(timeline((SETTLE, STAND), (S.vision_lost_tolerance_s + 3, []), (300, LIE)))
    assert alarms == []


def test_sleep_mode_still_catches_fast_fall():
    _, _, alarms = run_fall_sleep(timeline((SETTLE, STAND), (0.5, lambda t: [pose("lying", t)]), (8, LIE)))
    assert [a.path for a in alarms] == ["descent"]


def test_wake_up_stand_then_slow_fall_alarms():
    """자다가(asleep) 일어서면 취침 모드 해제 → 그 뒤 천천히 쓰러지면 알람."""
    frames = timeline((3, [pose("floor_sit")]), (3, lambda t: [pose("lying", t, frm="floor_sit")]), (30, LIE),
                      (2, lambda t: [pose("standing", t, frm="lying")]), (SETTLE, STAND),
                      (4, lambda t: [pose("lying", t)]), (10, LIE))
    det, states, alarms = run_fall_sleep(frames)
    assert ("lying", "asleep") in states and det.sleep_mode is None
    assert [a.path for a in alarms] == ["slow_fall"]


def test_sleep_declaration_times_out():
    det, _, _ = run_fall_sleep(timeline((S.sleep_declared_timeout_s + 5, STAND), fps=1))
    assert det.sleep_mode is None


# ── 이불 단서 ──
def covered_lying():
    p = pose("lying")
    k = p.keypoints.copy()
    k[13:17, 2] = 0.1          # 무릎·발목 안 보임 (이불)
    return [PersonPose(p.bbox, p.score, k)]


def test_covered_lying_waits_longer():
    _, alarms = run_fall(timeline((S.fall_lying_only_s + 30, covered_lying())))
    assert alarms == []
    _, alarms = run_fall(timeline((S.fall_lying_only_covered_s + 2, covered_lying()), fps=2))
    assert [(a.path, a.detail["covered"]) for _, a in alarms] == [("lying_only", True)]


# ── 여러 사람 ──
from pi.app.services.vision.tracker import PersonTracker  # noqa: E402


def carer(score=0.95):
    """보호자: 화면 왼쪽에 서 있음, 검출 점수가 더 높음."""
    return pose("standing", dx=-0.3, score=score)


def patient(name="standing", t=1.0, frm="standing", score=0.7):
    return pose(name, t, frm=frm, dx=0.25, score=score)


def run_mon(frames, mode="idle"):
    mon, remote = make_monitor()
    poses = [mon.update(people, now, mode, True) for now, people in frames]
    return mon, [op.payload for op in remote.executed], poses


def test_tracker_keeps_ids_and_follows_fast_fall():
    tr = PersonTracker(S.track_iou_min, S.track_center_max_ratio, S.vision_lost_tolerance_s, ASPECT)
    ids = []
    for now, people in timeline((1, [carer(), patient()]), (0.5, lambda t: [carer(), patient("lying", t)]),
                                (1, [carer(), patient("lying")])):
        vis, _ = tr.update(people, now)
        ids.append(sorted((t.track_id, round(t.person.bbox[0], 2)) for t in vis))
    assert {i for f in ids for i, _ in f} == {1, 2}           # 쓰러지는 동안에도 새 번호가 안 생김


def test_patient_falls_while_carer_stands_alarms():
    """보호자(점수 높음)가 서 있고 환자가 쓰러짐 → 환자 쪽 알람 (예전에는 점수 1등만 봐서 놓침)."""
    frames = timeline((2, [carer(), patient()]), (0.5, lambda t: [carer(), patient("lying", t)]),
                      (6, [carer(), patient("lying")]))
    mon, sent, poses = run_mon(frames)
    [alarm] = sent
    assert alarm["p_source"] == "camera" and alarm["p_detail"]["people"] == 2
    lying_id = next(p.track_id for p in mon.people if p.state == "lying")
    assert alarm["p_detail"]["track"] == lying_id
    assert poses[-1].state == "lying"                          # 대시보드는 쓰러진 사람을 보여줌


def test_two_people_swapping_order_no_false_alarm():
    """서 있는 사람과 앉은 사람의 점수가 번갈아 1등 → 예전 방식은 머리가 '내려간' 것처럼 보였음."""
    a = lambda s: pose("standing", dx=-0.3, score=s)          # noqa: E731
    b = lambda s: pose("sitting", dx=0.25, score=s)           # noqa: E731
    frames = []
    for k, (now, _) in enumerate(timeline((30, [None]))):
        frames.append((now, [a(0.9), b(0.8)] if k % 2 else [b(0.92), a(0.85)]))
    _, sent, _ = run_mon(frames)
    assert sent == []


def test_no_motion_paused_with_two_people():
    n = S.no_motion_minutes_sitting * 60 + 60
    _, sent, _ = run_mon(timeline((n, [pose("sitting", dx=-0.3), pose("sitting", dx=0.25)]), fps=1))
    assert sent == []
    _, sent, _ = run_mon(timeline((n, [pose("sitting", dx=0.25)]), fps=1))
    assert [p["p_source"] for p in sent] == ["no_motion"]


def test_memory_handed_to_reappearing_person():
    """소파에서 쉬다 로봇이 5분 놓침 → 다시 나타나면 (새 추적 번호여도) 기억을 이어받아 알람 없음."""
    mon, sent, _ = run_mon(timeline(*sofa_rest(), (300, []), (S.fall_lying_only_s + 60, [pose("sofa_lying")]),
                                    fps=2))
    assert sent == [] and mon.resting


def test_sleep_mode_applies_to_new_person_and_clears_on_wake():
    mon, remote = make_monitor()
    now = 0.0
    mon.set_sleep_mode(True, now)
    for now, people in timeline((SETTLE, STAND), (4, lambda t: [pose("lying", t)]), (60, LIE)):
        mon.update(people, now, "idle", True)
    assert remote.executed == [] and mon.sleep_mode == "asleep"
    for now2, people in timeline((2, lambda t: [pose("standing", t, frm="lying")]), (3, STAND)):
        mon.update(people, now + 0.1 + now2, "idle", True)
    assert mon.sleep_mode is None


# ── 잠자리 마커 ──
from dataclasses import replace as _replace  # noqa: E402
from datetime import time as _time  # noqa: E402

from pi.app.adapters.base import MarkerObs  # noqa: E402
from pi.app.services.vision.monitor import in_hours, marker_near  # noqa: E402

S_SPOT = _replace(S, sleep_marker_ids=(10,), sleep_hours=(_time(22, 0), _time(7, 0)))


def marker(mid=10, cx=0.10, cy=0.80, half=0.02):
    c = np.array([[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half]],
                 np.float32)
    return MarkerObs(mid, c, cx, 20.0, 640, 480)


def spot_monitor(clock_time):
    remote = mock.MockRemote()
    mon = VisionMonitor.from_settings(S_SPOT, SyncService(Outbox(":memory:"), remote), clock=lambda: T0,
                                      local_time=lambda: clock_time)
    return mon, remote


def run_spot(frames, clock_time=_time(23, 30), markers=(marker(),)):
    mon, remote = spot_monitor(clock_time)
    for now, people in frames:
        mon.update(people, now, "idle", True, list(markers) if markers is not None else None)
    return mon, [op.payload for op in remote.executed]


def test_in_hours_crosses_midnight():
    h = (_time(22, 0), _time(7, 0))
    assert in_hours(_time(23, 30), h) and in_hours(_time(6, 59), h)
    assert not in_hours(_time(7, 0), h) and not in_hours(_time(14, 0), h)
    assert in_hours(_time(14, 0), (_time(0, 0), _time.max))


def test_marker_near_bbox():
    lying_box = (.15, .78, .92, .92)
    assert marker_near(lying_box, marker(cx=0.10, cy=0.80), 0.5)     # 머리맡 (bbox 바로 왼쪽)
    assert not marker_near(lying_box, marker(cx=0.50, cy=0.20), 0.5)  # 화면 위쪽 벽 멀리


def test_found_lying_at_sleep_spot_at_night_no_alarm():
    """밤에 요(잠자리 마커 옆)에 누운 사람을 발견 (눕는 과정 못 봄) → 잠, 알람 없음, F7도 끔."""
    mon, sent = run_spot(timeline((S.fall_lying_only_s + 60, LIE), fps=2))
    assert sent == [] and mon.resting and mon.people[0].at_sleep_spot


def test_sleep_spot_ignored_outside_hours():
    _, sent = run_spot(timeline((S.fall_lying_only_s + 2, LIE), fps=2), clock_time=_time(14, 0))
    assert [p["p_detail"]["path"] for p in sent] == ["lying_only"]


def test_lying_far_from_sleep_marker_alarms():
    _, sent = run_spot(timeline((S.fall_lying_only_s + 2, LIE), fps=2), markers=(marker(cx=0.5, cy=0.2),))
    assert [p["p_detail"]["path"] for p in sent] == ["lying_only"]


def test_no_markers_passed_alarms():
    _, sent = run_spot(timeline((S.fall_lying_only_s + 2, LIE), fps=2), markers=None)
    assert [p["p_detail"]["path"] for p in sent] == ["lying_only"]


def test_slow_lie_down_on_bedding_at_night_no_alarm():
    """밤에 서 있다가 천천히 요에 눕기 (선언 없음) → 잠자리라 느린 하강도 잠."""
    _, sent = run_spot(timeline((SETTLE, STAND), (4, lambda t: [pose("lying", t)]), (60, LIE)))
    assert sent == []


def test_fast_fall_at_sleep_spot_still_alarms():
    _, sent = run_spot(timeline((SETTLE, STAND), (0.5, lambda t: [pose("lying", t)]), (8, LIE)))
    assert [p["p_detail"]["path"] for p in sent] == ["descent"]


def test_wants_markers_only_when_needed():
    mon, _ = spot_monitor(_time(23, 30))
    mon.update([pose("standing")], 0.0, "idle", True)
    assert not mon.wants_markers                                  # 서 있음 → 마커 필요 없음
    mon.update([pose("lying")], 0.1, "idle", True)
    assert mon.wants_markers                                      # 누움 → 잠자리 확인 필요
    day, _ = spot_monitor(_time(14, 0))
    day.update([pose("lying")], 0.0, "idle", True)
    assert not day.wants_markers                                  # 취침 시간 아님

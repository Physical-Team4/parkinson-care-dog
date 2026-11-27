"""F6·F7 묶음 (담당: A). pose 결과 → 사람별 추적·판정 → 알람은 SyncService 대기열로, 대시보드 포즈 형식 반환.

메인 루프(main.py, 담당 B)에서 프레임마다:
    people = estimator.infer(frame); del frame
    pose = monitor.update(people, time.monotonic(), robot_mode, esp32_ok)
    (0.4초마다) sync.send_now(remote.broadcast, settings.pose_topic, "pose", pose.to_json())
프레임은 이 모듈에 들어오지 않는다. 알람 detail에는 숫자 요약만 (키포인트 이력 금지, api_schemas.AlertReport).

여러 사람 (docs/features.md):
- 사람마다 추적 번호(PersonTracker)와 F6 판정기를 따로 둔다 → **누가 쓰러지든 알람**, 사람이 바뀌어 생기던 오판 없음.
- 추적이 끝난(오래 안 보인) 사람의 판정기는 마지막 상태 기억과 함께 보관했다가, 다시 나타난 사람에게 넘긴다
  (보관된 게 하나면 그대로, 여럿이면 마지막 위치가 가장 가까운 것).
- 취침 선언은 누가 했는지 모르므로 보이는·보관된·새로 보이는 사람 모두에게 적용. 누군가 자다 일어나면 전체 해제.
- F7은 2명 이상 보이면 멈춤 (no_motion_pause_multi). 1명이면 그 사람 기준.
- 대시보드·F7의 "주목할 사람": 쓰러짐 의심 → 누움(쉬는 중 아님) → 누움 → 검출 점수 1등.
- 잠자리 마커: 취침 시간대(Pi 현지 시각)에 잠자리 마커가 누운 사람 근처에 보이면 그 사람은 "잠자리" (F6가 잠으로 봄).
  마커 인식은 CPU를 쓰므로 `wants_markers`가 True일 때만 돌려서 markers로 넘기면 된다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from pi.app.adapters.base import MarkerObs, PersonPose
from pi.app.services.sync import SyncService
from pi.app.services.vision.fall import FallConfig, FallDetector, FallUpdate
from pi.app.services.vision.no_motion import NoMotionConfig, NoMotionDetector
from pi.app.services.vision.pose_features import PoseFeatures, extract
from pi.app.services.vision.tracker import PersonTracker, Track
from pi.app.views.api_schemas import AlertReport, Pose

log = logging.getLogger(__name__)

# 주목할 사람 우선순위 (작을수록 먼저). 누움은 쉬는 중이 아니면 1로 올린다.
_PRIORITY = {"falling": 0, "lying": 2, "sitting": 3, "standing": 3, "none": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _local_time() -> time:
    return datetime.now().time()      # Pi 시스템 시간대 (취침 시간대 판단용)


def in_hours(now: time, hours: tuple[time, time]) -> bool:
    """hours=(시작, 끝). 자정을 넘는 구간(22:00-07:00)도 처리."""
    a, b = hours
    return a <= now < b if a <= b else (now >= a or now < b)


def marker_near(bbox: tuple[float, float, float, float], m: MarkerObs, margin: float) -> bool:
    """마커 중심이 bbox를 가로·세로 크기의 margin 비율만큼 넓힌 범위 안에 있는지 (프레임 기준 0~1)."""
    x1, y1, x2, y2 = bbox
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    cy = float(m.corners[:, 1].mean())
    return x1 - mx <= m.cx <= x2 + mx and y1 - my <= cy <= y2 + my


@dataclass
class _Parked:
    det: FallDetector
    t: float
    cx: float
    cy: float


@dataclass(frozen=True)
class PersonState:
    """화면 확인·디버그용 사람별 상태."""
    track_id: int
    state: str
    resting: bool
    bbox: tuple[float, float, float, float]
    focus: bool
    at_sleep_spot: bool = False


class VisionMonitor:
    def __init__(self, fall_cfg: FallConfig, no_motion: NoMotionDetector, sync: SyncService,
                 kpt_min_conf: float, frame_aspect: float, moving_modes: Sequence[str],
                 tracker: PersonTracker, pause_no_motion_multi: bool,
                 clock: Callable[[], datetime] = _utcnow,
                 sleep_marker_ids: Sequence[int] = (), sleep_hours: tuple[time, time] | None = None,
                 sleep_marker_margin: float = 0.5, local_time: Callable[[], time] = _local_time) -> None:
        self.fall_cfg = fall_cfg
        self.no_motion = no_motion
        self.sync = sync
        self.kpt_min_conf = kpt_min_conf
        self.frame_aspect = frame_aspect
        self.moving_modes = frozenset(moving_modes)
        self.tracker = tracker
        self.pause_no_motion_multi = pause_no_motion_multi
        self.clock = clock
        self.detectors: dict[int, FallDetector] = {}
        self._parked: list[_Parked] = []
        self._sleep_on = False
        self._sleep_t = 0.0
        self._asleep_ids: set[int] = set()
        self.people: list[PersonState] = []
        self._focus: FallDetector | None = None
        self.sleep_marker_ids = frozenset(sleep_marker_ids)
        self.sleep_hours = sleep_hours
        self.sleep_marker_margin = sleep_marker_margin
        self.local_time = local_time
        if self.sleep_marker_ids and sleep_hours is None:
            log.warning("SLEEP_MARKER_IDS는 있지만 SLEEP_HOURS가 없음 → 잠자리 마커 끔")

    @classmethod
    def from_settings(cls, s, sync: SyncService, clock: Callable[[], datetime] = _utcnow,
                      local_time: Callable[[], time] = _local_time) -> VisionMonitor:
        aspect = s.camera_width / s.camera_height
        tracker = PersonTracker(s.track_iou_min, s.track_center_max_ratio, s.vision_lost_tolerance_s, aspect)
        return cls(FallConfig.from_settings(s), NoMotionDetector(NoMotionConfig.from_settings(s), aspect),
                   sync, s.vision_kpt_min_conf, aspect, s.robot_moving_modes, tracker,
                   s.no_motion_pause_multi, clock, s.sleep_marker_ids, s.sleep_hours,
                   s.sleep_marker_margin, local_time)

    # ── 상태 조회 (뷰어·controller) ──
    @property
    def resting(self) -> bool:
        return self._focus.resting if self._focus else False

    @property
    def sleep_mode(self) -> str | None:
        if self._focus and self._focus.sleep_mode:
            return self._focus.sleep_mode
        return "declared" if self._sleep_on else None

    @property
    def sleep_spot_active(self) -> bool:
        return bool(self.sleep_marker_ids) and self.sleep_hours is not None

    @property
    def wants_markers(self) -> bool:
        """잠자리 판단에 마커가 필요한 때: 잠자리 기능이 켜져 있고 취침 시간대이며, 쉬는 중이 아닌데 누운 사람이 있음."""
        return (self.sleep_spot_active and in_hours(self.local_time(), self.sleep_hours)
                and any(p.state in ("lying", "falling") and not p.resting for p in self.people))

    def _at_sleep_spot(self, t: Track, markers: list[MarkerObs] | None, hours_ok: bool) -> bool:
        if not (hours_ok and markers):
            return False
        return any(m.marker_id in self.sleep_marker_ids and marker_near(t.bbox, m, self.sleep_marker_margin)
                   for m in markers)

    def robot_moving(self, mode: str | None, esp32_ok: bool) -> bool | None:
        """True=이동 중, False=정지, None=모름 (ESP32 status 끊김·mode 없음)."""
        if not esp32_ok or mode is None:
            return None
        return mode in self.moving_modes

    def _occurred_at(self, now_s: float, event_s: float) -> datetime:
        return self.clock() - timedelta(seconds=max(0.0, now_s - event_s))

    def set_sleep_mode(self, on: bool, now_s: float) -> None:
        """취침 선언·해제. controller가 음성 "잘게"·대시보드 버튼을 받으면 호출 (입력 방법은 B·D와 협의)."""
        log.info("취침 모드 %s", "선언" if on else "해제")
        self._sleep_on, self._sleep_t = on, now_s
        self._asleep_ids.clear()
        for d in [*self.detectors.values(), *(p.det for p in self._parked)]:
            d.set_sleep_mode(on, now_s)

    # ── 판정기 배정 ──
    def _adopt(self, t: Track, now: float) -> FallDetector:
        """새 추적에 판정기 배정: 보관된 판정기(마지막 상태 기억)가 있으면 넘겨받는다."""
        self._parked = [p for p in self._parked if now - p.t <= self.fall_cfg.context_memory_s]
        det = None
        if self._parked:
            x1, y1, x2, y2 = t.bbox
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

            def dist(p: _Parked) -> float:
                return ((p.cx - cx) ** 2 + (p.cy - cy) ** 2) ** 0.5
            best = min(self._parked, key=dist)
            if len(self._parked) == 1 or dist(best) < 0.25:
                self._parked.remove(best)
                det = best.det
        if det is None:
            det = FallDetector(self.fall_cfg)
        if self._sleep_on and det.sleep_mode is None:
            det.set_sleep_mode(True, self._sleep_t)
        return det

    def _park(self, t: Track) -> None:
        det = self.detectors.pop(t.track_id, None)
        if det is None:
            return
        det.lost()
        x1, y1, x2, y2 = t.bbox
        self._parked.append(_Parked(det, t.last_s, (x1 + x2) / 2, (y1 + y2) / 2))

    def _update_sleep(self, now: float) -> None:
        if not self._sleep_on:
            return
        modes = {i: d.sleep_mode for i, d in self.detectors.items()}
        if any(i in modes and modes[i] is None for i in self._asleep_ids):
            self.set_sleep_mode(False, now)   # 자던 사람이 일어남 → 전체 해제
            log.info("취침 모드 해제 (일어남)")
            return
        if now - self._sleep_t > self.fall_cfg.sleep_declared_timeout_s and "asleep" not in modes.values() \
                and not self._asleep_ids:
            self._sleep_on = False            # 선언 후 아무도 눕지 않음 → 취소
            return
        self._asleep_ids |= {i for i, m in modes.items() if m == "asleep"}

    # ── 프레임마다 ──
    def update(self, people: list[PersonPose], now_s: float, robot_mode: str | None, esp32_ok: bool,
               markers: list[MarkerObs] | None = None) -> Pose:
        """markers: 같은 프레임의 마커 인식 결과 (잠자리 판단용, 없으면 None)."""
        visible, expired = self.tracker.update(people, now_s)
        hours_ok = self.sleep_spot_active and in_hours(self.local_time(), self.sleep_hours)
        for t in expired:
            self._park(t)
        for t in visible:
            if t.track_id not in self.detectors:
                self.detectors[t.track_id] = self._adopt(t, now_s)

        results: list[tuple[Track, PoseFeatures | None, FallUpdate, FallDetector]] = []
        spots: dict[int, bool] = {}
        for tid, t in self.tracker.tracks.items():
            det = self.detectors[tid]
            feats = extract(t.person, self.kpt_min_conf, self.frame_aspect) if t.seen_now else None
            spots[tid] = t.seen_now and self._at_sleep_spot(t, markers, hours_ok)
            fu = det.update(feats, now_s, spots[tid])
            results.append((t, feats, fu, det))
            if fu.alarm:
                a = fu.alarm
                log.warning("F6 낙상 알람 (사람 %d) %s conf=%.2f %s", tid, a.path, a.confidence, a.detail)
                detail = {**a.detail, "track": tid, "people": len(visible)}
                self.sync.submit(AlertReport("camera", self._occurred_at(now_s, a.event_s),
                                             confidence=a.confidence, detail=detail).to_op())
        self._update_sleep(now_s)

        focus = self._pick_focus(results)
        self._focus = focus[3] if focus else None
        self.people = [PersonState(t.track_id, fu.state, det.resting, t.bbox, focus is not None and t is focus[0],
                                   spots[t.track_id])
                       for t, _, fu, det in results if t.seen_now]

        if self.pause_no_motion_multi and len(visible) >= 2:
            self.no_motion.reset()            # 다른 사람이 같이 있음 → F7 멈춤
        else:
            feats = focus[1] if focus else None
            context = None if focus is None else ("resting" if focus[3].resting else focus[2].state)
            nm = self.no_motion.update(feats, now_s, self.robot_moving(robot_mode, esp32_ok), context)
            if nm:
                log.warning("F7 무움직임 알람 %s", nm.detail)
                self.sync.submit(AlertReport("no_motion", self._occurred_at(now_s, nm.event_s),
                                             detail=nm.detail).to_op())

        if focus is None:
            return Pose(state="none", keypoints=[])
        t, _, fu, _ = focus
        return Pose(state=fu.state, keypoints=t.person.keypoints.round(4).tolist())

    @staticmethod
    def _pick_focus(results):
        """보이는 사람 중: 쓰러짐 의심 → 누움(쉬는 중 아님) → 누움(쉬는 중) → 나머지, 같으면 검출 점수 높은 순."""
        seen = [r for r in results if r[0].seen_now]
        if not seen:
            return None

        def key(r):
            t, _, fu, det = r
            pr = 1 if fu.state == "lying" and not det.resting else _PRIORITY.get(fu.state, 4)
            return (pr, -t.person.score)
        return min(seen, key=key)

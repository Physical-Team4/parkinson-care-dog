"""F6·F7 묶음 (담당: A). pose 결과 → 판정 → 알람은 SyncService 대기열로, 대시보드 포즈 형식 반환.

메인 루프(main.py, 담당 B)에서 프레임마다:
    people = estimator.infer(frame); del frame
    pose = monitor.update(people, time.monotonic(), robot_mode, esp32_ok)
    (0.4초마다) sync.send_now(remote.broadcast, settings.pose_topic, "pose", pose.to_json())
프레임은 이 모듈에 들어오지 않는다. 알람 detail에는 숫자 요약만 (키포인트 이력 금지, api_schemas.AlertReport).
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from pi.app.adapters.base import PersonPose
from pi.app.services.sync import SyncService
from pi.app.services.vision.fall import FallConfig, FallDetector
from pi.app.services.vision.no_motion import NoMotionConfig, NoMotionDetector
from pi.app.services.vision.pose_features import pick_primary
from pi.app.views.api_schemas import AlertReport, Pose

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VisionMonitor:
    def __init__(self, fall: FallDetector, no_motion: NoMotionDetector, sync: SyncService,
                 kpt_min_conf: float, frame_aspect: float, moving_modes: Sequence[str],
                 clock: Callable[[], datetime] = _utcnow) -> None:
        self.fall = fall
        self.no_motion = no_motion
        self.sync = sync
        self.kpt_min_conf = kpt_min_conf
        self.frame_aspect = frame_aspect
        self.moving_modes = frozenset(moving_modes)
        self.clock = clock

    @classmethod
    def from_settings(cls, s, sync: SyncService, clock: Callable[[], datetime] = _utcnow) -> VisionMonitor:
        aspect = s.camera_width / s.camera_height
        return cls(FallDetector(FallConfig.from_settings(s)),
                   NoMotionDetector(NoMotionConfig.from_settings(s), aspect),
                   sync, s.vision_kpt_min_conf, aspect, s.robot_moving_modes, clock)

    def robot_moving(self, mode: str | None, esp32_ok: bool) -> bool | None:
        """True=이동 중, False=정지, None=모름 (ESP32 status 끊김·mode 없음)."""
        if not esp32_ok or mode is None:
            return None
        return mode in self.moving_modes

    def _occurred_at(self, now_s: float, event_s: float) -> datetime:
        return self.clock() - timedelta(seconds=max(0.0, now_s - event_s))

    def update(self, people: list[PersonPose], now_s: float, robot_mode: str | None, esp32_ok: bool) -> Pose:
        person, feats = pick_primary(people, self.kpt_min_conf, self.frame_aspect)

        fu = self.fall.update(feats, now_s)
        if fu.alarm:
            a = fu.alarm
            log.warning("F6 낙상 알람 %s conf=%.2f %s", a.path, a.confidence, a.detail)
            self.sync.submit(AlertReport("camera", self._occurred_at(now_s, a.event_s),
                                         confidence=a.confidence, detail=a.detail).to_op())

        nm = self.no_motion.update(feats, now_s, self.robot_moving(robot_mode, esp32_ok))
        if nm:
            log.warning("F7 무움직임 알람 %s", nm.detail)
            self.sync.submit(AlertReport("no_motion", self._occurred_at(now_s, nm.event_s),
                                         detail=nm.detail).to_op())

        kpts = person.keypoints.round(4).tolist() if person is not None else []
        return Pose(state=fu.state, keypoints=kpts)

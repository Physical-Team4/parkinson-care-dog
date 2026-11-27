"""F7 무움직임 판정 (담당: A). 별도 모델 없이 F6와 같은 pose 요약으로 계산만 한다.

- "기준 자세"를 잡고, 이후 관절이 기준에서 얼마나 벗어났는지(bbox 높이 대비)를 본다.
  임계값보다 크게 움직이면 기준을 새로 잡는다. 기준이 N분 동안 유지되면 알람.
  (프레임 간 차이를 누적하면 관절 떨림이 쌓여 오판하므로 기준 대비 방식을 쓴다.)
- 로봇이 움직이는 중(ESP32 mode가 이동 모드)이거나 모드를 모를 때(esp32_ok=false)는 카메라가 흔들리므로
  누적을 멈추고 초기화한다 (docs/features.md).
- "사람 없음/판정 불가"와 "움직임 없음"을 구분: 사람이 absent_reset_s 넘게 안 보이면 초기화, 알람 안 냄.
- 기준 시간은 자세별 (서 있음 짧게, 앉음 길게(TV), 스스로 누워 쉬는 중(잠)은 끔). 자세는 F6 결과를 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pi.app.services.vision.pose_features import PoseFeatures


@dataclass(frozen=True)
class NoMotionConfig:
    still_s: float                  # 그 외 (누움 등)
    still_s_standing: float
    still_s_sitting: float
    still_s_resting: float | None   # None = 알람 안 함
    threshold: float
    absent_reset_s: float
    min_common_kpts: int

    @classmethod
    def from_settings(cls, s) -> NoMotionConfig:
        rest = s.no_motion_minutes_resting
        return cls(still_s=s.no_motion_minutes * 60, still_s_standing=s.no_motion_minutes_standing * 60,
                   still_s_sitting=s.no_motion_minutes_sitting * 60,
                   still_s_resting=rest * 60 if rest is not None else None, threshold=s.no_motion_threshold,
                   absent_reset_s=s.no_motion_absent_reset_s, min_common_kpts=s.no_motion_min_common_kpts)


@dataclass(frozen=True)
class NoMotionAlarm:
    event_s: float
    detail: dict


class NoMotionDetector:
    def __init__(self, cfg: NoMotionConfig, frame_aspect: float) -> None:
        self.cfg = cfg
        self.frame_aspect = frame_aspect
        self._ref: PoseFeatures | None = None
        self._ref_s = 0.0
        self._last_valid_s: float | None = None
        self._alarmed = False

    def reset(self) -> None:
        self._ref = None
        self._alarmed = False

    def limit_s(self, context: str | None) -> float | None:
        """context: F6 상태(standing/sitting/lying/falling/none) 또는 "resting"."""
        c = self.cfg
        return {"standing": c.still_s_standing, "sitting": c.still_s_sitting,
                "resting": c.still_s_resting}.get(context or "", c.still_s)

    def still_s(self, now: float) -> float:
        return now - self._ref_s if self._ref is not None else 0.0

    def displacement(self, f: PoseFeatures) -> float | None:
        """기준 자세 대비 공통 관절 평균 이동 (기준 bbox 높이 비율). 공통 관절이 적으면 None."""
        ref = self._ref
        common = ref.visible & f.visible
        if int(common.sum()) < self.cfg.min_common_kpts:
            return None
        d = f.keypoints[common, :2] - ref.keypoints[common, :2]
        dist = np.hypot(d[:, 0] * self.frame_aspect, d[:, 1])
        return float(dist.mean()) / ref.bbox_h

    def update(self, f: PoseFeatures | None, now: float, robot_moving: bool | None,
               context: str | None = None) -> NoMotionAlarm | None:
        if robot_moving is not False:          # 이동 중 또는 모름
            self.reset()
            return None
        if f is None or self._ref is None:
            pass
        else:
            disp = self.displacement(f)
            if disp is None:
                f = None                        # 비교 불가 → 안 보인 것과 같이 처리
            elif disp > self.cfg.threshold:
                self._ref, self._ref_s, self._alarmed = f, now, False
        if f is None:
            if self._last_valid_s is None or now - self._last_valid_s > self.cfg.absent_reset_s:
                self.reset()
            return None
        self._last_valid_s = now
        if self._ref is None:
            self._ref, self._ref_s = f, now
            return None
        limit = self.limit_s(context)
        if limit is not None and not self._alarmed and now - self._ref_s >= limit:
            self._alarmed = True
            return NoMotionAlarm(now, {"still_min": round((now - self._ref_s) / 60, 1),
                                       "posture": context, "threshold": self.cfg.threshold})
        return None

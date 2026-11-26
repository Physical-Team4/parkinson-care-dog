"""F6 낙상 판정 (담당: A). 입력은 pose 요약(PoseFeatures)뿐, 프레임은 받지 않는다.

흐름 (docs/features.md "F6·F7 비전 계획"):
  서 있기/앉기 ──머리가 빠르게 내려감──▶ falling ──누운 자세가 N초 유지──▶ 낙상 확정 (path="descent")
                                           └─ 다시 앉거나 일어서면 취소 (알람 없음)
  쓰러지는 장면을 못 봤어도 누운 자세가 오래 이어지면 낮은 confidence로 알람 (path="lying_only")

- 머리 하강은 픽셀이 아니라 **하강 직전 bbox 높이 대비 비율** → 사람이 멀든 가깝든 같은 기준.
- 판정 불가 프레임(어깨·엉덩이가 안 보임)은 lost_tolerance_s 동안 직전 상태를 유지하고, 넘으면 "none".
- 알람 후에는 일어서거나 앉은 상태가 rearm_upright_s 이어져야 다음 알람이 가능 (같은 낙상으로 반복 알람 안 함).
알려진 한계 (실측으로 확인할 것, docs/todo.md):
  - 카메라 쪽으로 머리/발을 두고 누우면 몸통이 짧게 보여 각도·bbox 비율로 누움을 못 잡을 수 있음.
  - 엉덩방아처럼 앉은 자세로 끝나는 낙상은 "앉음"으로 보여 알람이 안 남.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from pi.app.services.vision.pose_features import PoseFeatures

Posture = Literal["standing", "sitting", "lying"]
State = Literal["none", "standing", "sitting", "falling", "lying"]


@dataclass(frozen=True)
class FallConfig:
    lost_tolerance_s: float
    lying_angle_deg: float
    lying_min_aspect: float | None
    sit_thigh_max_ratio: float
    descent_window_s: float
    descent_ratio: float
    confirm_window_s: float
    confirm_lying_s: float
    lying_only_s: float | None
    conf_descent: float
    conf_lying_only: float
    rearm_upright_s: float

    @classmethod
    def from_settings(cls, s) -> FallConfig:
        return cls(
            lost_tolerance_s=s.vision_lost_tolerance_s, lying_angle_deg=s.fall_lying_angle_deg,
            lying_min_aspect=s.fall_lying_min_aspect, sit_thigh_max_ratio=s.sit_thigh_max_ratio,
            descent_window_s=s.fall_descent_window_s, descent_ratio=s.fall_descent_ratio,
            confirm_window_s=s.fall_confirm_window_s, confirm_lying_s=s.fall_confirm_lying_s,
            lying_only_s=s.fall_lying_only_s, conf_descent=s.fall_conf_descent,
            conf_lying_only=s.fall_conf_lying_only, rearm_upright_s=s.fall_rearm_upright_s,
        )


@dataclass(frozen=True)
class FallAlarm:
    path: Literal["descent", "lying_only"]
    confidence: float
    event_s: float          # 낙상 시작 시각 (monotonic, 쓰러지기 시작 또는 눕기 시작)
    detail: dict            # 판단 근거 요약 (숫자만, 키포인트 이력 없음)


@dataclass(frozen=True)
class FallUpdate:
    state: State
    alarm: FallAlarm | None = None


def classify(f: PoseFeatures, cfg: FallConfig) -> Posture:
    if f.torso_deg >= cfg.lying_angle_deg and (cfg.lying_min_aspect is None
                                               or f.bbox_aspect >= cfg.lying_min_aspect):
        return "lying"
    if f.thigh_ratio is not None and f.thigh_ratio < cfg.sit_thigh_max_ratio:
        return "sitting"
    return "standing"   # 무릎이 안 보이면 서기/앉기 구분 불가 → standing (표시용, 낙상 판정엔 영향 없음)


class FallDetector:
    def __init__(self, cfg: FallConfig) -> None:
        self.cfg = cfg
        self._hist: deque[tuple[float, float, float]] = deque()  # (t, head_y, bbox_h)
        self._last_valid_s: float | None = None
        self._posture: Posture | None = None
        self._falling_since: float | None = None
        self._descent = 0.0
        self._lying_since: float | None = None
        self._lying_conf: list[float] = []
        self._max_torso = 0.0
        self._upright_since: float | None = None
        self._alarmed = False

    def _descent_ratio(self, now: float, head_y: float) -> float:
        while self._hist and now - self._hist[0][0] > self.cfg.descent_window_s:
            self._hist.popleft()
        return max((head_y - y0) / h0 for _, y0, h0 in self._hist) if self._hist else 0.0

    def _reset_tracking(self) -> None:
        self._hist.clear()
        self._posture = None
        self._lying_since = None
        self._lying_conf = []
        self._upright_since = None

    def update(self, f: PoseFeatures | None, now: float) -> FallUpdate:
        cfg = self.cfg
        if self._falling_since is not None and now - self._falling_since > cfg.confirm_window_s:
            self._falling_since = None   # 확정 못 하고 시간 지남 → 취소

        if f is None:
            if self._last_valid_s is None or now - self._last_valid_s > cfg.lost_tolerance_s:
                self._reset_tracking()
                return FallUpdate("none")
            posture = self._posture   # 잠깐 안 보임 → 직전 자세 유지, 타이머는 계속
        else:
            self._last_valid_s = now
            posture = classify(f, cfg)
            self._posture = posture
            descent = self._descent_ratio(now, f.head_y)
            self._hist.append((now, f.head_y, f.bbox_h))
            if not self._alarmed and self._falling_since is None and descent >= cfg.descent_ratio:
                self._falling_since, self._descent = now, descent
            if posture == "lying":
                if self._lying_since is None:
                    self._lying_since, self._lying_conf, self._max_torso = now, [], 0.0
                self._lying_conf.append(f.core_conf)
                self._max_torso = max(self._max_torso, f.torso_deg)
                self._upright_since = None
            else:
                self._lying_since = None
                if self._upright_since is None:
                    self._upright_since = now
                # 하강 후 다시 앉거나 선 자세가 이어지면 (털썩 앉기 등) 취소
                if self._falling_since is not None and now - self._falling_since > cfg.descent_window_s:
                    self._falling_since = None
                if self._alarmed and now - self._upright_since >= cfg.rearm_upright_s:
                    self._alarmed = False

        alarm = None if self._alarmed else self._check_alarm(now)
        if alarm:
            self._alarmed, self._falling_since = True, None
        # falling = 쓰러짐 의심 (확정 전). 확정되거나 취소되면 실제 자세로.
        state: State = "falling" if self._falling_since is not None else (posture or "none")
        return FallUpdate(state, alarm)

    def _check_alarm(self, now: float) -> FallAlarm | None:
        cfg, ls = self.cfg, self._lying_since
        if ls is None:
            return None
        lying_s = now - ls
        mean_conf = sum(self._lying_conf) / len(self._lying_conf) if self._lying_conf else 0.0
        detail = {"lying_s": round(lying_s, 1), "torso_deg": round(self._max_torso),
                  "core_conf": round(mean_conf, 2)}
        fs = self._falling_since
        if fs is not None and ls >= fs - cfg.descent_window_s and lying_s >= cfg.confirm_lying_s:
            return FallAlarm("descent", min(1.0, cfg.conf_descent * mean_conf), fs,
                             {"path": "descent", "descent_ratio": round(self._descent, 2), **detail})
        if cfg.lying_only_s is not None and lying_s >= cfg.lying_only_s:
            return FallAlarm("lying_only", min(1.0, cfg.conf_lying_only * mean_conf), ls,
                             {"path": "lying_only", **detail})
        return None

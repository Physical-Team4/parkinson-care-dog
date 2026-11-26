"""F6 낙상 판정 (담당: A). 입력은 pose 요약(PoseFeatures)뿐, 프레임은 받지 않는다.

알람 경로 (docs/features.md "F6·F7 비전 계획"):
  1) descent    빠른 낙상: 머리가 빠르게 내려감 → falling → 누운 자세 N초 유지 → 알람
                (다시 앉거나 일어서면 취소 = 털썩 앉기)
  2) slow_fall  느린 낙상: 눕는 과정을 봤고, 기준 자세(앉기·서기 유지)보다 **엉덩이가 크게 내려가서** 누움
                (서 있다가 천천히 무너짐, 의자에서 미끄러짐) → 누운 자세 N초 유지 → 알람
     ─ 스스로 눕기: 눕는 과정을 봤는데 엉덩이 높이가 거의 그대로 (소파·침대·바닥 요에 앉았다가 눕기) → 알람 없음
  3) lying_only 눕는 과정을 못 봤는데 누운 자세가 오래 이어짐 → 낮은 confidence로 알람

- 높이·하강은 픽셀이 아니라 **사람 크기(bbox 높이, 몸통 길이) 대비 비율** → 거리와 무관.
- 기준 자세 = 앉기 또는 서기를 settle_s 이상 유지한 구간에서 엉덩이가 가장 높았던 때.
  (천천히 무너지는 도중 잠깐 웅크린 자세는 settle_s를 못 채워 기준이 되지 않는다)
- 판정 불가 프레임(어깨·엉덩이가 안 보임)은 lost_tolerance_s 동안 직전 상태를 유지하고, 넘으면 "none".
- 알람 후에는 일어서거나 앉은 상태가 rearm_upright_s 이어져야 다음 알람이 가능 (같은 낙상으로 반복 알람 안 함).
알려진 한계 (실측으로 확인할 것, docs/todo.md):
  - 카메라 쪽으로 머리/발을 두고 누우면 몸통이 짧게 보여 각도·bbox 비율로 누움을 못 잡을 수 있음.
  - 엉덩방아처럼 앉은 자세로 끝나는 낙상은 "앉음"으로 보여 알람이 안 남 (바닥 좌식 생활과 구분 어려움).
  - 엉덩이 높이 비교는 로봇(카메라)이 멈춰 있어야 정확하다.
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
    settle_s: float
    onset_max_gap_s: float
    slow_hip_drop_ratio: float
    slow_confirm_s: float
    lying_only_s: float | None
    conf_descent: float
    conf_slow: float
    conf_lying_only: float
    rearm_upright_s: float

    @classmethod
    def from_settings(cls, s) -> FallConfig:
        return cls(
            lost_tolerance_s=s.vision_lost_tolerance_s, lying_angle_deg=s.fall_lying_angle_deg,
            lying_min_aspect=s.fall_lying_min_aspect, sit_thigh_max_ratio=s.sit_thigh_max_ratio,
            descent_window_s=s.fall_descent_window_s, descent_ratio=s.fall_descent_ratio,
            confirm_window_s=s.fall_confirm_window_s, confirm_lying_s=s.fall_confirm_lying_s,
            settle_s=s.fall_settle_s, onset_max_gap_s=s.fall_onset_max_gap_s,
            slow_hip_drop_ratio=s.slow_fall_hip_drop_ratio, slow_confirm_s=s.slow_fall_confirm_s,
            lying_only_s=s.fall_lying_only_s, conf_descent=s.fall_conf_descent,
            conf_slow=s.fall_conf_slow, conf_lying_only=s.fall_conf_lying_only,
            rearm_upright_s=s.fall_rearm_upright_s,
        )


@dataclass(frozen=True)
class FallAlarm:
    path: Literal["descent", "slow_fall", "lying_only"]
    confidence: float
    event_s: float          # 낙상 시작 시각 (monotonic): 하강 시작 / 엉덩이가 기준 높이를 벗어난 때 / 눕기 시작
    detail: dict            # 판단 근거 요약 (숫자만, 키포인트 이력 없음)


@dataclass(frozen=True)
class FallUpdate:
    state: State
    alarm: FallAlarm | None = None


@dataclass(frozen=True)
class _Ref:
    """기준 자세: 앉기·서기를 유지하던 때의 엉덩이 높이."""
    hip_y: float
    torso_len: float
    posture: Posture
    bbox_h: float        # 그때의 키 (빠른 하강 비율의 분모)


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
        # 기준 자세 (느린 낙상 vs 스스로 눕기)
        self._seg_posture: Posture | None = None   # 지금 이어지는 자세 구간
        self._seg_since = 0.0
        self._seg_ref: _Ref | None = None
        self._ref: _Ref | None = None               # 마지막으로 settle_s를 채운 앉기·서기 구간
        self._last_upright_s: float | None = None
        self._ref_last_s = 0.0                      # 엉덩이가 기준 높이 근처에 있던 마지막 시각 = 낙상 시작
        self._onset_ref: _Ref | None = None         # 이번 누움 직전의 기준 자세 (못 봤으면 None)
        self._onset_s = 0.0
        self._hip_drop = 0.0

    def _descent_ratio(self, now: float, head_y: float) -> float:
        """descent_window_s 안의 머리 하강 / 키. 키는 그 시점 bbox 높이와 기준 자세(유지된 서기·앉기)의 bbox 높이 중
        큰 값 (천천히 무너질 때 막바지의 작아진 bbox로 나눠 "빠른 하강"으로 잘못 보지 않도록)."""
        while self._hist and now - self._hist[0][0] > self.cfg.descent_window_s:
            self._hist.popleft()
        up_h = (self._ref.bbox_h if self._ref is not None and self._last_upright_s is not None
                and now - self._last_upright_s <= self.cfg.onset_max_gap_s else 0.0)
        return max((head_y - y0) / max(h0, up_h) for _, y0, h0 in self._hist) if self._hist else 0.0

    def _reset_tracking(self) -> None:
        self._hist.clear()
        self._posture = None
        self._lying_since = None
        self._lying_conf = []
        self._upright_since = None
        self._seg_posture, self._seg_ref, self._ref = None, None, None
        self._last_upright_s = None
        self._onset_ref = None

    def _track_upright(self, f: PoseFeatures, posture: Posture, now: float) -> None:
        if posture != self._seg_posture:
            self._seg_posture, self._seg_since, self._seg_ref = posture, now, None
        if now - self._seg_since >= self.cfg.settle_s:
            if self._seg_ref is None or f.hip_y < self._seg_ref.hip_y:   # y가 작을수록 높음
                self._seg_ref = _Ref(f.hip_y, f.torso_len, posture, f.bbox_h)
            self._ref = self._seg_ref
        self._last_upright_s = now
        # 엉덩이가 아직 기준 높이 근처(느린 낙상 기준의 1/4 이내)면 "기준 자세에 있던 마지막 시각" 갱신
        r = self._ref
        if r is not None and (f.hip_y - r.hip_y) / r.torso_len < self.cfg.slow_hip_drop_ratio / 4:
            self._ref_last_s = now

    def _start_lying(self, now: float) -> None:
        self._lying_since, self._lying_conf, self._max_torso = now, [], 0.0
        self._seg_posture = "lying"
        seen = (self._ref is not None and self._last_upright_s is not None
                and now - self._last_upright_s <= self.cfg.onset_max_gap_s)
        self._onset_ref = self._ref if seen else None
        self._onset_s = self._ref_last_s if seen else now
        self._hip_drop = 0.0

    def _slow_pending(self) -> bool:
        return (not self._alarmed and self._lying_since is not None and self._onset_ref is not None
                and self._hip_drop >= self.cfg.slow_hip_drop_ratio)

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
                    self._start_lying(now)
                self._lying_conf.append(f.core_conf)
                self._max_torso = max(self._max_torso, f.torso_deg)
                if self._onset_ref is not None:
                    drop = (f.hip_y - self._onset_ref.hip_y) / self._onset_ref.torso_len
                    self._hip_drop = max(self._hip_drop, drop)
                self._upright_since = None
            else:
                self._lying_since = None
                self._track_upright(f, posture, now)
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
        suspect = self._falling_since is not None or self._slow_pending()
        state: State = "falling" if suspect else (posture or "none")
        return FallUpdate(state, alarm)

    def _check_alarm(self, now: float) -> FallAlarm | None:
        cfg, ls = self.cfg, self._lying_since
        if ls is None:
            return None
        lying_s = now - ls
        mean_conf = sum(self._lying_conf) / len(self._lying_conf) if self._lying_conf else 0.0
        detail = {"lying_s": round(lying_s, 1), "torso_deg": round(self._max_torso),
                  "core_conf": round(mean_conf, 2)}
        ref = self._onset_ref
        hips_dropped = ref is None or self._hip_drop >= cfg.slow_hip_drop_ratio
        fs = self._falling_since
        if fs is not None and ls >= fs - cfg.descent_window_s and lying_s >= cfg.confirm_lying_s:
            if hips_dropped:
                return FallAlarm("descent", min(1.0, cfg.conf_descent * mean_conf), fs,
                                 {"path": "descent", "descent_ratio": round(self._descent, 2),
                                  **({"hip_drop": round(self._hip_drop, 2)} if ref else {}), **detail})
            self._falling_since = None   # 소파·침대에 털썩 눕기: 머리는 빨리 내려갔지만 엉덩이 높이 그대로 → 취소
        if ref is not None:   # 눕는 과정을 봄 → 엉덩이 하강으로 판단 (작으면 스스로 눕기, 알람 없음)
            if self._hip_drop >= cfg.slow_hip_drop_ratio and lying_s >= cfg.slow_confirm_s:
                return FallAlarm("slow_fall", min(1.0, cfg.conf_slow * mean_conf), self._onset_s,
                                 {"path": "slow_fall", "hip_drop": round(self._hip_drop, 2),
                                  "from": ref.posture, **detail})
            return None
        if cfg.lying_only_s is not None and lying_s >= cfg.lying_only_s:
            return FallAlarm("lying_only", min(1.0, cfg.conf_lying_only * mean_conf), ls,
                             {"path": "lying_only", **detail})
        return None

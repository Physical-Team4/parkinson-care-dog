"""F6 낙상 판정, F7 무움직임 (담당: A).

입력은 포즈 결과(키포인트)만. 프레임은 받지 않는다 → 영상 저장 위험 없음.
포즈 추정 자체는 adapter(Hailo/CPU)가 하고, 여기서는 판정만 한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PoseResult:
    keypoints: list[list[float]]  # COCO 17 × [x, y, conf], 0~1
    score: float                  # 사람 검출 신뢰도


class FallDetector:
    """TODO(A): 판정 규칙 (몸통 각도, 머리 높이 변화 속도, 누운 상태 지속 시간 등).
    의심 시 입력 640 재확인 흐름은 controller가 adapter에 요청."""

    def update(self, pose: PoseResult | None, now_s: float) -> tuple[str, float | None]:
        """반환: (state: none/standing/sitting/falling/lying, 낙상 confidence 또는 None)"""
        raise NotImplementedError


class NoMotionDetector:
    """TODO(A): 키포인트 이동량이 N분 동안 임계값 미만이면 무움직임 (N, 임계값은 config)."""

    def update(self, pose: PoseResult | None, now_s: float) -> bool:
        raise NotImplementedError

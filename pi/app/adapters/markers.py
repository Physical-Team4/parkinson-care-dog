"""ArUco 마커 인식 adapter (담당: A, 로봇 이동 docs/navigation.md §4). MarkerDetector Protocol 구현.

- OpenCV `cv2.aruco` (OpenCV 4.7+ 본체). Hailo는 쓰지 않고 CPU에서 돈다.
- pose와 같은 프레임을 받아 흑백으로 바꿔 찾는다. 프레임·흑백 이미지는 보관하지 않는다 (영상 저장 금지).
- 거리·방향 추정은 마커 크기(cm)와 카메라 초점거리(px)가 둘 다 설정됐을 때만 (M0 실측 전에는 None).
"""
from __future__ import annotations

import math
import time

import numpy as np

from pi.app.adapters.base import MarkerObs


def side_px(c: np.ndarray) -> float:
    """corners (4, 2) px → 네 변 길이 평균."""
    return float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))


def estimate_distance_cm(m: MarkerObs, marker_cm: float | None, focal_px: float | None) -> float | None:
    """핀홀 근사: 거리 = 마커 크기 × 초점거리 / 화면상 크기. 값이 없으면 None."""
    if not marker_cm or not focal_px or m.side_px <= 0:
        return None
    return marker_cm * focal_px / m.side_px


def estimate_bearing_deg(m: MarkerObs, focal_px: float | None) -> float | None:
    """화면 가운데 기준 마커 방향. 양수 = 오른쪽 (MechDog move()의 각도 부호와 반대이니 주의)."""
    if not focal_px:
        return None
    return math.degrees(math.atan((m.cx - 0.5) * m.frame_w / focal_px))


class ArucoMarkerDetector:
    def __init__(self, dict_name: str = "DICT_4X4_50") -> None:
        import cv2   # environment.yml의 opencv

        self._cv2 = cv2
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
        self._detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        self.dict_name = dict_name
        self.last_ms = 0.0

    def detect(self, frame: np.ndarray) -> list[MarkerObs]:
        t0 = time.perf_counter()
        h, w = frame.shape[:2]
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2GRAY) if frame.ndim == 3 else frame
        corners, ids, _ = self._detector.detectMarkers(gray)
        del gray
        out: list[MarkerObs] = []
        if ids is not None:
            for c, i in zip(corners, ids.flatten()):
                c = c.reshape(4, 2).astype(np.float32)
                norm = c / np.array([w, h], np.float32)
                out.append(MarkerObs(int(i), norm, float(norm[:, 0].mean()), side_px(c), w, h))
        self.last_ms = (time.perf_counter() - t0) * 1e3
        return out

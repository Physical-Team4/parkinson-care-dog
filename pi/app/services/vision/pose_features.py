"""pose 1장에서 판정에 쓸 값을 계산한다 (F6·F7 공용). 프레임은 다루지 않는다.

좌표는 PersonPose 그대로 원본 프레임 기준 0~1 (y는 아래로 갈수록 큼).
x·y의 픽셀 비율이 달라서(640×480) 각도는 frame_aspect(가로/세로)로 보정해 계산한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pi.app.adapters.base import PersonPose

# COCO 17 인덱스
NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_KNEE, R_KNEE = 5, 6, 11, 12, 13, 14
HEAD = (NOSE, L_EYE, R_EYE, L_EAR, R_EAR)
CORE = (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)


@dataclass(frozen=True)
class PoseFeatures:
    """판정 가능한 pose의 요약. 판정 불가면 extract()가 None을 준다."""
    score: float
    head_y: float          # 머리(없으면 어깨) y, 0~1
    hip_y: float           # 엉덩이 중점 y, 0~1
    bbox_h: float          # bbox 높이, 0~1
    bbox_cx: float         # bbox 가로 중심, 0~1
    bbox_aspect: float     # bbox 가로/세로 (픽셀 기준)
    torso_deg: float       # 0 = 똑바로 섬, 90 = 수평
    torso_len: float       # 어깨 중점~엉덩이 중점 거리 (y 단위, 픽셀 비율 보정)
    thigh_ratio: float | None   # |무릎y - 엉덩이y| / torso_len, 무릎 안 보이면 None
    core_conf: float       # 핵심 관절(어깨·엉덩이) 평균 신뢰도
    visible: np.ndarray    # (17,) bool
    keypoints: np.ndarray  # (17, 3)


def _mid(k: np.ndarray, idx: tuple[int, ...], vis: np.ndarray) -> np.ndarray | None:
    pts = [k[i, :2] for i in idx if vis[i]]
    return np.mean(pts, axis=0) if pts else None


def extract(p: PersonPose, min_conf: float, frame_aspect: float) -> PoseFeatures | None:
    """어깨 1개 이상 + 엉덩이 1개 이상 보일 때만 값을 낸다 (팔만 보이는 경우 등은 None)."""
    k = p.keypoints
    vis = k[:, 2] >= min_conf
    sh = _mid(k, (L_SHOULDER, R_SHOULDER), vis)
    hip = _mid(k, (L_HIP, R_HIP), vis)
    if sh is None or hip is None:
        return None
    dx = (hip[0] - sh[0]) * frame_aspect   # x를 y와 같은 픽셀 비율로
    dy = hip[1] - sh[1]
    torso_len = math.hypot(dx, dy)
    if torso_len < 1e-6:
        return None
    torso_deg = math.degrees(math.atan2(abs(dx), abs(dy)))
    head = _mid(k, HEAD, vis)
    head_y = float(head[1]) if head is not None else float(sh[1])
    knee = _mid(k, (L_KNEE, R_KNEE), vis)
    thigh = abs(float(knee[1] - hip[1])) / torso_len if knee is not None else None
    x1, y1, x2, y2 = p.bbox
    bbox_h = max(y2 - y1, 1e-6)
    core = [k[i, 2] for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)]
    return PoseFeatures(
        score=p.score, head_y=head_y, hip_y=float(hip[1]), bbox_h=bbox_h, bbox_cx=(x1 + x2) / 2,
        bbox_aspect=(x2 - x1) * frame_aspect / bbox_h,
        torso_deg=torso_deg, torso_len=torso_len, thigh_ratio=thigh,
        core_conf=float(np.mean(core)), visible=vis, keypoints=k,
    )


def pick_primary(people: list[PersonPose], min_conf: float, frame_aspect: float
                 ) -> tuple[PersonPose | None, PoseFeatures | None]:
    """판정할 사람 1명: 판정 가능한 사람 중 검출 점수가 가장 높은 사람.
    판정 가능한 사람이 없으면 (점수 1등, None). 아무도 없으면 (None, None).
    TODO: 보호자와 환자가 같이 보일 때 누구를 볼지 (docs/todo.md)."""
    best: tuple[PersonPose, PoseFeatures] | None = None
    for p in people:
        f = extract(p, min_conf, frame_aspect)
        if f is not None and (best is None or p.score > best[0].score):
            best = (p, f)
    if best:
        return best
    return (max(people, key=lambda p: p.score) if people else None), None

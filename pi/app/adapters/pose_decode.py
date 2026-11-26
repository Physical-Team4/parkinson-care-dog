"""YOLOv8-pose 전처리(letterbox)·후처리(디코딩, NMS). numpy만 써서 PC에서도 테스트된다.

Hailo Model Zoo의 yolov8*_pose `.hef`는 NMS 없이 stride(8·16·32)마다 출력 3개를 낸다:
  - box  (H, W, 64): 4변 × DFL 16칸
  - cls  (H, W, 1) : 사람 점수
  - kpt  (H, W, 51): 17 × (x, y, conf)
출력 이름은 모델·버전마다 다르므로 **이름이 아니라 shape(채널 수·격자 크기)으로** 구분한다.
cls·kpt conf에 sigmoid가 칩 안에서 적용됐는지도 버전마다 다를 수 있어 첫 프레임 값 범위로 판단한다.
디코딩 식은 Ultralytics YOLOv8 Pose head와 같다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from pi.app.adapters.base import PersonPose

log = logging.getLogger(__name__)

NUM_KPT = 17
REG_MAX = 16
_BOX_C, _CLS_C, _KPT_C = 4 * REG_MAX, 1, NUM_KPT * 3
PAD_VALUE = 114  # Ultralytics letterbox 회색


@dataclass(frozen=True)
class Letterbox:
    scale: float
    pad_x: int
    pad_y: int
    src_w: int
    src_h: int


def _resize_nearest(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * (img.shape[0] / h)).astype(np.intp)
    xs = (np.arange(w) * (img.shape[1] / w)).astype(np.intp)
    return img[ys[:, None], xs[None, :]]


def letterbox(frame: np.ndarray, in_w: int, in_h: int) -> tuple[np.ndarray, Letterbox]:
    """비율 유지 축소 + 가운데 패딩 → (in_h, in_w, 3) uint8 C-contiguous.

    카메라를 640×480으로 찍으면 축소 없이 위아래 패딩만 한다 (가장 빠르고 화질 손실 없음).
    다른 크기면 최근접 축소 (opencv 의존성 없이).
    """
    h, w = frame.shape[:2]
    scale = min(in_w / w, in_h / h)
    nw, nh = round(w * scale), round(h * scale)
    img = frame if (nw, nh) == (w, h) else _resize_nearest(frame, nw, nh)
    pad_x, pad_y = (in_w - nw) // 2, (in_h - nh) // 2
    out = np.full((in_h, in_w, 3), PAD_VALUE, dtype=np.uint8)
    out[pad_y:pad_y + nh, pad_x:pad_x + nw] = img
    return out, Letterbox(scale, pad_x, pad_y, w, h)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _looks_like_prob(x: np.ndarray) -> bool:
    return bool(x.size) and float(x.min()) >= 0.0 and float(x.max()) <= 1.0


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float, max_det: int) -> list[int]:
    """단일 클래스 greedy NMS. boxes (N, 4) x1y1x2y2."""
    order = np.argsort(-scores)
    areas = (boxes[:, 2] - boxes[:, 0]).clip(0) * (boxes[:, 3] - boxes[:, 1]).clip(0)
    keep: list[int] = []
    while order.size and len(keep) < max_det:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = (xx2 - xx1).clip(0) * (yy2 - yy1).clip(0)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_threshold]
    return keep


class YoloV8PoseDecoder:
    """모델 원출력(dict 이름→배열) → list[PersonPose]."""

    def __init__(self, input_w: int, input_h: int, score_threshold: float,
                 iou_threshold: float, max_people: int) -> None:
        self.input_w, self.input_h = input_w, input_h
        self.score_threshold = score_threshold
        self.iou_threshold = iou_threshold
        self.max_people = max_people
        self._cls_needs_sigmoid: bool | None = None
        self._kpt_needs_sigmoid: bool | None = None

    def group_outputs(self, outputs: dict[str, np.ndarray]) -> list[tuple[int, np.ndarray, np.ndarray, np.ndarray]]:
        """[(stride, box, cls, kpt)] stride 오름차순. 모양이 YOLOv8-pose가 아니면 ValueError."""
        by_grid: dict[tuple[int, int], dict[int, np.ndarray]] = {}
        for name, arr in outputs.items():
            a = np.asarray(arr)
            if a.ndim == 4 and a.shape[0] == 1:
                a = a[0]
            if a.ndim != 3 or a.shape[2] not in (_BOX_C, _CLS_C, _KPT_C):
                raise ValueError(f"YOLOv8-pose 출력이 아님: {name} {np.shape(arr)}")
            by_grid.setdefault((a.shape[0], a.shape[1]), {})[a.shape[2]] = a
        groups = []
        for (gh, gw), chans in by_grid.items():
            if set(chans) != {_BOX_C, _CLS_C, _KPT_C}:
                raise ValueError(f"격자 {gh}x{gw}의 출력 채널 {sorted(chans)} (64·1·51 필요)")
            stride = self.input_h // gh
            if stride * gh != self.input_h or stride * gw != self.input_w:
                raise ValueError(f"격자 {gh}x{gw}가 입력 {self.input_w}x{self.input_h}와 맞지 않음")
            groups.append((stride, chans[_BOX_C], chans[_CLS_C], chans[_KPT_C]))
        if not groups:
            raise ValueError("출력 없음")
        return sorted(groups, key=lambda g: g[0])

    def _decide_sigmoid(self, groups) -> None:
        cls_all = np.concatenate([g[2].reshape(-1) for g in groups])
        kconf = np.concatenate([g[3].reshape(-1, NUM_KPT, 3)[:, :, 2].reshape(-1) for g in groups])
        self._cls_needs_sigmoid = not _looks_like_prob(cls_all)
        self._kpt_needs_sigmoid = not _looks_like_prob(kconf)
        log.info("pose 출력 sigmoid 적용: cls=%s kpt_conf=%s (False면 칩에서 이미 적용됨)",
                 self._cls_needs_sigmoid, self._kpt_needs_sigmoid)

    def decode(self, outputs: dict[str, np.ndarray], lb: Letterbox) -> list[PersonPose]:
        groups = self.group_outputs(outputs)
        if self._cls_needs_sigmoid is None:
            self._decide_sigmoid(groups)

        boxes_l, scores_l, kpts_l = [], [], []
        for stride, box, cls, kpt in groups:
            gh, gw = cls.shape[:2]
            score = cls.reshape(-1).astype(np.float32)
            if self._cls_needs_sigmoid:
                score = _sigmoid(score)
            idx = np.nonzero(score >= self.score_threshold)[0]
            if idx.size == 0:
                continue
            gy, gx = np.divmod(idx, gw)
            # box: DFL softmax 기댓값 → 앵커 중심(격자+0.5)에서 l,t,r,b 거리
            d = box.reshape(-1, 4, REG_MAX)[idx].astype(np.float32)
            d = np.exp(d - d.max(axis=2, keepdims=True))
            d = (d / d.sum(axis=2, keepdims=True)) @ np.arange(REG_MAX, dtype=np.float32)
            cx, cy = gx + 0.5, gy + 0.5
            boxes_l.append(np.stack([cx - d[:, 0], cy - d[:, 1], cx + d[:, 2], cy + d[:, 3]], axis=1) * stride)
            # kpt: (raw*2 + 격자) * stride, conf sigmoid
            k = kpt.reshape(-1, NUM_KPT, 3)[idx].astype(np.float32).copy()
            k[:, :, 0] = (k[:, :, 0] * 2.0 + gx[:, None]) * stride
            k[:, :, 1] = (k[:, :, 1] * 2.0 + gy[:, None]) * stride
            if self._kpt_needs_sigmoid:
                k[:, :, 2] = _sigmoid(k[:, :, 2])
            kpts_l.append(k)
            scores_l.append(score[idx])
        if not scores_l:
            return []

        boxes = np.concatenate(boxes_l)
        scores = np.concatenate(scores_l)
        kpts = np.concatenate(kpts_l)
        keep = nms(boxes, scores, self.iou_threshold, self.max_people)
        return [self._to_frame(boxes[i], float(scores[i]), kpts[i], lb) for i in keep]

    @staticmethod
    def _to_frame(box: np.ndarray, score: float, kpt: np.ndarray, lb: Letterbox) -> PersonPose:
        """모델 입력 픽셀 → 원본 프레임 0~1 (letterbox 되돌림)."""
        sx, sy = lb.scale * lb.src_w, lb.scale * lb.src_h
        b = box.copy()
        b[[0, 2]] = ((b[[0, 2]] - lb.pad_x) / sx).clip(0, 1)
        b[[1, 3]] = ((b[[1, 3]] - lb.pad_y) / sy).clip(0, 1)
        k = kpt.copy()
        k[:, 0] = ((k[:, 0] - lb.pad_x) / sx).clip(0, 1)
        k[:, 1] = ((k[:, 1] - lb.pad_y) / sy).clip(0, 1)
        return PersonPose(bbox=tuple(float(v) for v in b), score=score, keypoints=k.astype(np.float32))

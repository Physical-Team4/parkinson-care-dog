"""Hailo-8L 일반 물체 검출 adapter (담당: A). ObjectDetector Protocol 구현. 지금은 가구 확인용 (docs/features.md).

- Model Zoo `yolov8s.hef` (hailo8l): NMS까지 칩에서 하고 **종류별 박스 목록(HAILO_NMS_BY_CLASS)**을 준다.
  박스는 모델 입력(640×640) 기준 0~1, 순서 [y_min, x_min, y_max, x_max, score].
- HailoRT Python이 이 출력을 "종류별 배열 리스트"로 주는지 "평탄한 float 배열"로 주는지 버전마다 다를 수 있어
  parse_nms_by_class()가 둘 다 처리한다. 처음엔 pi/scripts/furniture_check.py --inspect로 실제 형식을 확인할 것.
- 종류 번호는 COCO 80종 0부터 (사람 0, 의자 56, 소파 57, 침대 59). 사람이 0번으로 잡히는지로 순서를 확인한다.
- 프레임·전처리 이미지는 보관하지 않는다.
- TODO: pose 모델(hailo.py)과 한 프로세스에서 같이 쓰려면 VDevice를 공유하도록 바꿔야 한다 (지금은 각자 생성).
"""
from __future__ import annotations

import logging
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from pi.app.adapters.base import Detection
from pi.app.adapters.pose_decode import Letterbox, letterbox

log = logging.getLogger(__name__)

COCO_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush",
)
FURNITURE = {"chair": 56, "couch": 57, "bed": 59}


def parse_nms_by_class(raw, num_classes: int = len(COCO_NAMES)) -> list[tuple[int, np.ndarray]]:
    """NMS 출력 → [(class_id, (N, 5) [y1, x1, y2, x2, score])].
    raw: 종류별 배열 리스트(길이 num_classes), 또는 평탄 배열 [개수, 박스×개수, 개수, ...]."""
    out: list[tuple[int, np.ndarray]] = []
    if isinstance(raw, (list, tuple)):
        if len(raw) == 1 and isinstance(raw[0], (list, tuple)):   # 배치 차원 [[class0, class1, ...]]
            raw = raw[0]
        for c, arr in enumerate(raw):
            a = np.asarray(arr, np.float32).reshape(-1, 5) if np.size(arr) else np.zeros((0, 5), np.float32)
            if len(a):
                out.append((c, a))
        return out
    flat = np.asarray(raw, np.float32).reshape(-1)
    pos = 0
    for c in range(num_classes):
        if pos >= flat.size:
            break
        n = int(round(float(flat[pos])))
        pos += 1
        if n < 0 or pos + n * 5 > flat.size:
            raise ValueError(f"NMS 출력 해석 실패: class {c}, 개수 {n} (--inspect로 형식 확인)")
        if n:
            out.append((c, flat[pos:pos + n * 5].reshape(n, 5)))
        pos += n * 5
    return out


def to_detections(parsed, lb: Letterbox, in_w: int, in_h: int, score_threshold: float) -> list[Detection]:
    """모델 입력 기준 0~1 박스 → 원본 프레임 기준 0~1 (letterbox 되돌림). 점수 높은 순."""
    sx, sy = lb.scale * lb.src_w, lb.scale * lb.src_h
    dets = []
    for c, boxes in parsed:
        for y1, x1, y2, x2, s in boxes:
            if s < score_threshold:
                continue
            fx1 = float(np.clip((x1 * in_w - lb.pad_x) / sx, 0, 1))
            fx2 = float(np.clip((x2 * in_w - lb.pad_x) / sx, 0, 1))
            fy1 = float(np.clip((y1 * in_h - lb.pad_y) / sy, 0, 1))
            fy2 = float(np.clip((y2 * in_h - lb.pad_y) / sy, 0, 1))
            name = COCO_NAMES[c] if 0 <= c < len(COCO_NAMES) else f"class{c}"
            dets.append(Detection(int(c), name, float(s), (fx1, fy1, fx2, fy2)))
    return sorted(dets, key=lambda d: -d.score)


class HailoObjectDetector:
    def __init__(self, hef_path: Path | str, score_threshold: float, timeout_ms: int = 1000) -> None:
        from hailo_platform import FormatType, HailoSchedulingAlgorithm, VDevice

        hef_path = Path(hef_path)
        if not hef_path.is_file():
            raise FileNotFoundError(f"{hef_path} 없음 → MZ_VERSION=v2.20.0 bash pi/scripts/download_models.sh yolov8s")
        self.score_threshold = score_threshold
        self.timeout_ms = timeout_ms
        self.last_ms = 0.0
        self._stack = ExitStack()
        try:
            params = VDevice.create_params()
            params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
            vdevice = self._stack.enter_context(VDevice(params))
            model = vdevice.create_infer_model(str(hef_path))
            model.set_batch_size(1)
            model.input().set_format_type(FormatType.UINT8)
            for out in model.outputs:
                out.set_format_type(FormatType.FLOAT32)
            self._model = model
            self._configured = self._stack.enter_context(model.configure())
            in_h, in_w, _ = model.input().shape
            self.input_size = (in_w, in_h)
            self._in_buf = np.empty((in_h, in_w, 3), np.uint8)
            self._names = list(model.output_names)
            self._out_bufs = {n: np.empty(model.output(n).shape, np.float32) for n in self._names}
            self._bindings = self._configured.create_bindings()
            for n, buf in self._out_bufs.items():
                self._bindings.output(n).set_buffer(buf)
        except Exception:
            self._stack.close()
            raise
        log.info("Hailo 검출 모델 %s 입력 %dx%d, 출력 %s", hef_path.name, in_w, in_h,
                 {n: b.shape for n, b in self._out_bufs.items()})

    def output_info(self) -> dict:
        return {n: {"shape": tuple(self._model.output(n).shape)} for n in self._names}

    def infer_raw(self, frame: np.ndarray):
        """(원출력 get_buffer() 결과, Letterbox). --inspect용."""
        img, lb = letterbox(frame, *self.input_size)
        np.copyto(self._in_buf, img)
        self._bindings.input().set_buffer(self._in_buf)
        self._configured.run([self._bindings], self.timeout_ms)
        return self._bindings.output(self._names[0]).get_buffer(), lb

    def detect(self, frame: np.ndarray) -> list[Detection]:
        t0 = time.perf_counter()
        raw, lb = self.infer_raw(frame)
        dets = to_detections(parse_nms_by_class(raw), lb, *self.input_size, self.score_threshold)
        self.last_ms = (time.perf_counter() - t0) * 1e3
        return dets

    def close(self) -> None:
        self._stack.close()

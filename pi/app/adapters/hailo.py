"""Hailo-8L pose 추론 adapter (담당: A). PoseEstimator Protocol 구현.

프레임 → letterbox → Hailo(.hef) → YOLOv8-pose 디코딩 → list[PersonPose].
- `.hef`는 hailo8l 대상만 (docs/setup.md 2-3-1). 받는 방법: pi/scripts/download_models.sh
- hailo_platform은 Pi에서만 있으므로 생성자 안에서 import.
- 프레임·전처리 이미지는 보관하지 않는다 (입력 버퍼는 매 프레임 덮어씀).
"""
from __future__ import annotations

import logging
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from pi.app.adapters.base import PersonPose
from pi.app.adapters.pose_decode import YoloV8PoseDecoder, letterbox

log = logging.getLogger(__name__)


class HailoPoseEstimator:
    def __init__(self, hef_path: Path | str, score_threshold: float, iou_threshold: float,
                 max_people: int, timeout_ms: int = 1000) -> None:
        from hailo_platform import FormatType, HailoSchedulingAlgorithm, VDevice

        hef_path = Path(hef_path)
        if not hef_path.is_file():
            raise FileNotFoundError(f"{hef_path} 없음 → bash pi/scripts/download_models.sh")
        self.hef_path = hef_path
        self.timeout_ms = timeout_ms
        # 마지막 infer()의 단계별 시간(ms). 벤치마크용.
        self.last_timing: dict[str, float] = {}

        self._stack = ExitStack()
        try:
            params = VDevice.create_params()
            params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
            self._vdevice = self._stack.enter_context(VDevice(params))
            model = self._vdevice.create_infer_model(str(hef_path))
            model.set_batch_size(1)
            model.input().set_format_type(FormatType.UINT8)
            for out in model.outputs:
                out.set_format_type(FormatType.FLOAT32)  # 역양자화는 HailoRT가
            self._model = model
            self._configured = self._stack.enter_context(model.configure())

            in_h, in_w, in_c = model.input().shape
            if in_c != 3:
                raise ValueError(f"입력 채널 {in_c} (RGB 3 필요): {model.input().shape}")
            self.input_size = (in_w, in_h)
            self._in_buf = np.empty((in_h, in_w, 3), dtype=np.uint8)
            self._out_bufs = {name: np.empty(model.output(name).shape, dtype=np.float32)
                              for name in model.output_names}
            self._bindings = self._configured.create_bindings()
            for name, buf in self._out_bufs.items():
                self._bindings.output(name).set_buffer(buf)

            self.decoder = YoloV8PoseDecoder(in_w, in_h, score_threshold, iou_threshold, max_people)
            self.decoder.group_outputs(self._out_bufs)  # 출력 모양이 YOLOv8-pose인지 미리 확인
        except Exception:
            self._stack.close()
            raise
        log.info("Hailo pose 모델 %s 입력 %dx%d, 출력 %s", hef_path.name, in_w, in_h,
                 {n: b.shape for n, b in self._out_bufs.items()})

    def infer_raw(self, img: np.ndarray) -> dict[str, np.ndarray]:
        """이미 입력 크기로 맞춘 uint8 이미지 → 원출력. (벤치마크 '추론만' 측정용)"""
        np.copyto(self._in_buf, img)
        self._bindings.input().set_buffer(self._in_buf)
        self._configured.run([self._bindings], self.timeout_ms)
        return self._out_bufs

    def infer(self, frame: np.ndarray) -> list[PersonPose]:
        t0 = time.perf_counter()
        img, lb = letterbox(frame, *self.input_size)
        t1 = time.perf_counter()
        outputs = self.infer_raw(img)
        t2 = time.perf_counter()
        people = self.decoder.decode(outputs, lb)
        t3 = time.perf_counter()
        self.last_timing = {"pre_ms": (t1 - t0) * 1e3, "infer_ms": (t2 - t1) * 1e3, "post_ms": (t3 - t2) * 1e3}
        return people

    def close(self) -> None:
        self._stack.close()

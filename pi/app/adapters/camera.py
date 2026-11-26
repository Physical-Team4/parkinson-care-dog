"""picamera2 캡처 adapter (담당: A). Camera Protocol 구현.

- 프레임은 메모리에서만. 파일 저장·녹화·스트리밍 기능을 넣지 말 것 (CLAUDE.md 안전·개인정보).
- picamera2 포맷 이름은 DRM 기준이라 numpy 채널 순서가 반대다:
  "RGB888" → [B, G, R], "BGR888" → [R, G, B]. 모델(Model Zoo .hef)은 RGB 입력이므로 "BGR888"을 쓴다.
- 기본 640×480: 모델 입력 640×640에 축소 없이 위아래 패딩만 하면 된다 (pose_decode.letterbox).
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class PiCamera:
    def __init__(self, size: tuple[int, int] = (640, 480)) -> None:
        from picamera2 import Picamera2  # Pi에서만 있음

        self.size = size
        self._cam = Picamera2()
        try:
            cfg = self._cam.create_video_configuration(main={"size": size, "format": "BGR888"})
            self._cam.configure(cfg)
            self._cam.start()
        except Exception:
            self._cam.close()
            raise
        log.info("camera %dx%d 시작", *size)

    def capture(self) -> np.ndarray:
        """RGB (H, W, 3) uint8. 호출한 쪽이 처리 후 바로 버린다."""
        return self._cam.capture_array("main")

    def close(self) -> None:
        try:
            self._cam.stop()
        finally:
            self._cam.close()

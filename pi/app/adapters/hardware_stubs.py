"""실기기 adapter 자리. 담당자가 구현한다. 각 클래스는 base.py의 Protocol을 따른다.

구현할 때 파일을 나눠도 된다 (camera.py, microphone.py, x1200.py, hailo.py ...).
"""
from __future__ import annotations

import numpy as np


class PiCamera:
    """TODO(A): picamera2. import는 생성자 안에서 (PC에서는 없음)."""

    def __init__(self, size: tuple[int, int] = (320, 320)) -> None:
        from picamera2 import Picamera2  # noqa: F401
        raise NotImplementedError

    def capture(self) -> np.ndarray:
        raise NotImplementedError


class UsbMicrophone:
    """TODO(B): sounddevice. 장치 이름은 Settings로."""
    sample_rate = 16000

    def record(self, seconds: float) -> np.ndarray:
        raise NotImplementedError

# X1200 → x1200.py, 안전 종료 → host.py

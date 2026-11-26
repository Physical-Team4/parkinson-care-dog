"""adapter 인터페이스. 실제 구현과 mock(mock.py)이 같은 메서드를 가진다.

services는 이 Protocol 타입만 알고, 어떤 구현이 들어오는지는 main.py가 정한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

if TYPE_CHECKING:
    from pi.app.views.api_schemas import Op


class RemoteError(Exception):
    """Supabase 호출 실패. permanent=False면 나중에 재시도 (네트워크 끊김, 5xx, 429)."""

    def __init__(self, message: str, permanent: bool) -> None:
        super().__init__(message)
        self.permanent = permanent


class RemoteStore(Protocol):
    """Supabase (adapters/supabase_rest.py). 실패 시 RemoteError."""
    def execute(self, op: Op) -> Any: ...
    def insert_status(self, row: dict) -> None: ...
    def broadcast(self, topic: str, event: str, payload: dict) -> None: ...
    def fetch_settings(self) -> dict: ...


class Esp32Link(Protocol):
    def send(self, line: bytes) -> None: ...
    def read_message(self, timeout_s: float) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


class Camera(Protocol):
    def capture(self) -> np.ndarray:
        """RGB 프레임 1장 (H, W, 3) uint8. 호출한 쪽은 처리 후 즉시 버린다 (저장 금지)."""
        ...

    def close(self) -> None: ...


# COCO 17 키포인트 순서 (YOLOv8-pose 출력 순서와 같음)
COCO_KEYPOINTS = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)


@dataclass(frozen=True)
class PersonPose:
    """사람 1명의 pose. 좌표는 모두 **원본 프레임 기준 0~1** (해상도·letterbox와 무관).

    프레임 자체는 담지 않는다 → 이 객체는 저장·전송해도 영상이 남지 않는다.
    """
    bbox: tuple[float, float, float, float]   # x1, y1, x2, y2
    score: float                              # 사람 검출 신뢰도 0~1
    keypoints: np.ndarray                     # (17, 3) float32: x, y, conf


class PoseEstimator(Protocol):
    """카메라 프레임 → 사람별 bbox + COCO 17 키포인트 (adapters/hailo.py, mock)."""
    input_size: tuple[int, int]   # 모델 입력 (W, H)

    def infer(self, frame: np.ndarray) -> list[PersonPose]:
        """RGB (H, W, 3) uint8. 신뢰도 높은 순. 사람 없으면 빈 리스트. frame은 보관하지 않는다."""
        ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class MarkerObs:
    """마커 1개 관측 (로봇 이동, docs/navigation.md). 좌표는 원본 프레임 기준 0~1."""
    marker_id: int
    corners: np.ndarray     # (4, 2) float32, 0~1 (x는 가로 비율, y는 세로 비율)
    cx: float               # 중심 x, 0~1 (0.5 = 화면 가운데)
    side_px: float          # 화면상 한 변 길이 (px) → 거리 추정용
    frame_w: int            # 원본 프레임 크기 (px)
    frame_h: int


class MarkerDetector(Protocol):
    """카메라 프레임 → ArUco 마커 (adapters/markers.py, mock)."""
    last_ms: float          # 마지막 detect() 처리 시간

    def detect(self, frame: np.ndarray) -> list[MarkerObs]:
        """RGB (H, W, 3) uint8. frame은 보관하지 않는다."""
        ...


@dataclass(frozen=True)
class Detection:
    """일반 물체 검출 1개 (COCO). bbox는 원본 프레임 기준 0~1 (x1, y1, x2, y2)."""
    class_id: int
    name: str
    score: float
    bbox: tuple[float, float, float, float]


class ObjectDetector(Protocol):
    """카메라 프레임 → COCO 물체 (adapters/hailo_detect.py, mock). 가구(침대·소파) 확인용."""

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """RGB (H, W, 3) uint8. frame은 보관하지 않는다."""
        ...

    def close(self) -> None: ...


class Microphone(Protocol):
    sample_rate: int

    def record(self, seconds: float) -> np.ndarray:
        """float32 모노, -1~1. 원본 저장 금지."""
        ...


class PowerMonitor(Protocol):
    """X1200 (I²C 0x36 잔량, GPIO6 전원 차단 감지). 읽기 실패·미설정이면 None."""
    def battery_pct(self) -> float | None: ...
    def power_ok(self) -> bool | None:
        """외부 전원(X1200 USB-C 충전기) 연결 여부. GPIO6 극성 미설정이면 None."""
        ...
    def charging(self) -> bool | None:
        """대시보드 pi_charging. 지금은 power_ok와 같음 (충전 상태 핀 미확정, docs/todo.md)."""
        ...
    def cpu_temp_c(self) -> float | None: ...


class HostSystem(Protocol):
    """Pi OS 자체 제어 (안전 종료)."""
    def poweroff(self) -> None: ...


class Notifier(Protocol):
    """보호자 메신저 (종류 미확정)."""
    def send(self, text: str) -> None: ...

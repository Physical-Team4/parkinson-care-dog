"""설정 읽기. .env와 환경변수에서만 읽고, 값을 하드코딩하지 않는다.

다른 모듈은 os.environ을 직접 읽지 말고 load_settings()로 받은 Settings를 쓴다.
새 변수가 필요하면 .env.example에 이름을 추가하고 여기에 필드를 추가한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv 없는 환경에서도 동작
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    return int(value) if value else default


def _opt_int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


@dataclass(frozen=True)
class Settings:
    mock_hardware: bool
    supabase_url: str | None
    # Pi 전용 service_role(secret) 키. RLS를 우회하므로 로그·예외 메시지에 절대 출력 금지
    supabase_service_key: str | None = field(repr=False)
    esp32_serial_port: str | None
    esp32_serial_baud: int
    queue_path: Path          # 오프라인 대기열 SQLite (Supabase 재전송용)
    log_dir: Path
    model_dir: Path

    # ── X1200 UPS (docs/hardware.md, docs/setup.md 2-6) ──
    # GPIO6 전원 차단 감지(PLD)에서 "외부 전원 있음"일 때 읽히는 값 (0 또는 1).
    # 미확정 → None이면 전원 차단 감지·pi_charging 끔 (경고). setup.md 2-6에서 실측 후 .env에.
    x1200_pld_power_ok_level: int | None = None
    # 외부 전원이 빠지면 종료할지. 로봇은 평소 배터리로 다니므로 기본 False (docs/todo.md)
    pi_shutdown_on_power_loss: bool = False
    x1200_i2c_bus: int = 1          # GPIO 2·3 (I²C1)
    x1200_i2c_addr: int = 0x36      # 잔량 칩
    x1200_pld_gpio: int = 6         # ⚠️ 다른 용도 금지

    # ── Pi 배터리 정책 (services/power.py) ──
    pi_battery_low_pct: float = 20.0        # 미만 → ESP32에 pi_low (대시보드 battery_low 기준과 같음)
    pi_battery_low_clear_pct: float = 25.0  # 이 이상으로 회복하면 pi_low 다시 보낼 수 있음
    pi_battery_shutdown_pct: float = 10.0   # 미만 → 안전 종료. 5~10 사이에서 부하 테스트 후 조정 (todo.md)
    pi_shutdown_confirm_checks: int = 3     # 연속 N번 확인돼야 종료 (순간 전압 강하 무시)
    power_check_interval_s: float = 5.0

    # ── 비전 F6·F7 (docs/features.md "F6·F7 비전 계획") ──
    # pose 모델 .hef 경로 (.env POSE_HEF, 상대 경로면 model_dir 기준. 예: hailo8l/yolov8s_pose.hef).
    # 모델은 벤치마크 후 선택(D-010) → 미정이면 None, 비전 기능 끔 (경고).
    pose_hef: Path | None = None
    camera_width: int = 640     # 640×480이면 모델 입력 640×640에 축소 없이 패딩만
    camera_height: int = 480
    # 카메라 장착 방향 보정 (.env CAMERA_HFLIP / CAMERA_VFLIP). 거꾸로 달았으면 둘 다 true = 180° 회전
    camera_hflip: bool = False
    camera_vflip: bool = False
    # 검출 후처리. 임시값 (Ultralytics 기본에 가까움) → 벤치마크·누운 자세 측정 후 조정 (docs/todo.md)
    pose_score_threshold: float = 0.5
    pose_iou_threshold: float = 0.7
    pose_max_people: int = 3

    # 주기 (docs/api.md)
    status_interval_s: float = 2.0
    pose_interval_s: float = 0.4
    pose_topic: str = "robot:pose"
    # ESP32 status가 이 시간 넘게 없으면 esp32_ok=false (docs/serial-protocol.md)
    esp32_status_timeout_s: float = 3.0
    heartbeat_interval_s: float = 1.0
    # 대기열 재전송
    queue_flush_interval_s: float = 5.0
    queue_max_backoff_s: float = 300.0


def load_settings(env_file: Path | None = None) -> Settings:
    if load_dotenv is not None:
        load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    env = os.environ
    data_dir = Path.home() / "pd-dog-data"
    model_dir = Path(env.get("PD_DOG_MODEL_DIR") or Path.home() / "pd-dog-models")
    pose_hef = Path(env["POSE_HEF"]) if env.get("POSE_HEF") else None
    if pose_hef is not None and not pose_hef.is_absolute():
        pose_hef = model_dir / pose_hef
    return Settings(
        mock_hardware=_bool(env.get("PD_DOG_MOCK_HARDWARE"), default=False),
        supabase_url=env.get("SUPABASE_URL") or None,
        supabase_service_key=env.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        esp32_serial_port=env.get("ESP32_SERIAL_PORT") or None,
        esp32_serial_baud=_int(env.get("ESP32_SERIAL_BAUD"), 115200),
        queue_path=Path(env.get("PD_DOG_QUEUE_PATH") or data_dir / "outbox.db"),
        log_dir=Path(env.get("PD_DOG_LOG_DIR") or data_dir / "logs"),
        model_dir=model_dir,
        pose_hef=pose_hef,
        camera_hflip=_bool(env.get("CAMERA_HFLIP"), default=False),
        camera_vflip=_bool(env.get("CAMERA_VFLIP"), default=False),
        x1200_pld_power_ok_level=_opt_int(env.get("X1200_PLD_POWER_OK_LEVEL")),
        pi_shutdown_on_power_loss=_bool(env.get("PI_SHUTDOWN_ON_POWER_LOSS"), default=False),
    )

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
    return Settings(
        mock_hardware=_bool(env.get("PD_DOG_MOCK_HARDWARE"), default=False),
        supabase_url=env.get("SUPABASE_URL") or None,
        supabase_service_key=env.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        esp32_serial_port=env.get("ESP32_SERIAL_PORT") or None,
        esp32_serial_baud=_int(env.get("ESP32_SERIAL_BAUD"), 115200),
        queue_path=Path(env.get("PD_DOG_QUEUE_PATH") or data_dir / "outbox.db"),
        log_dir=Path(env.get("PD_DOG_LOG_DIR") or data_dir / "logs"),
        model_dir=Path(env.get("PD_DOG_MODEL_DIR") or Path.home() / "pd-dog-models"),
    )

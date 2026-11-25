"""Pi ↔ ESP32 시리얼 메시지 형식 (docs/serial-protocol.md 초안 v0).

형식만 정의한다. 업무 로직은 services, 송수신은 adapters/esp32_serial.py.
"""
from __future__ import annotations

import json
from typing import Any

MAX_LINE_BYTES = 256
DEBUG_PREFIX = "#"

# Pi → ESP32
HEARTBEAT = "hb"
WALK = "walk"
STOP = "stop"
SET_BPM = "bpm"
LASER = "laser"
SETTINGS = "settings"
MED_ACK = "med_ack"
SOUND = "sound"
PI_LOW = "pi_low"
SHUTDOWN = "shutdown"
SHUTDOWN_REASONS = ("battery", "power_loss")

# ESP32 → Pi
STATUS = "status"
TOUCH_SOS = "touch_sos"
MED_DUE = "med_due"
MED_OK = "med_ok"
MED_MISSED = "med_missed"
GAIT_END = "gait_end"
ACK = "ack"

BPM_MIN, BPM_MAX = 80, 110


def encode(t: str, msg_id: int | None = None, **fields: Any) -> bytes:
    msg: dict[str, Any] = {"t": t}
    if msg_id is not None:
        msg["id"] = msg_id
    msg.update(fields)
    line = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    if len(line) > MAX_LINE_BYTES:
        raise ValueError(f"serial message too long: {len(line)} bytes")
    return line


def decode(line: bytes | str) -> dict[str, Any] | None:
    """한 줄을 메시지로. 빈 줄·디버그(#)·깨진 줄은 None."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line or line.startswith(DEBUG_PREFIX):
        return None
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(msg, dict) or "t" not in msg:
        return None
    return msg


def walk(bpm: int, msg_id: int) -> bytes:
    if not BPM_MIN <= bpm <= BPM_MAX:
        raise ValueError(f"bpm must be {BPM_MIN}~{BPM_MAX}")
    return encode(WALK, msg_id, bpm=bpm)


def stop(msg_id: int) -> bytes:
    return encode(STOP, msg_id)


def heartbeat() -> bytes:
    return encode(HEARTBEAT)


def pi_low(pct: float, msg_id: int) -> bytes:
    """Pi 배터리 부족 → ESP32 경보 모드 준비 + MP3 안내."""
    return encode(PI_LOW, msg_id, pct=round(pct))


def shutdown(reason: str, msg_id: int) -> bytes:
    """Pi가 곧 꺼짐. 이후 hb가 끊기므로 ESP32는 MP3 경보 경로로 (D-001)."""
    if reason not in SHUTDOWN_REASONS:
        raise ValueError(f"reason must be one of {SHUTDOWN_REASONS}")
    return encode(SHUTDOWN, msg_id, reason=reason)

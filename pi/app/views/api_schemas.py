"""로봇 → Supabase로 보내는 데이터 형식 (docs/api.md).

필드 이름은 대시보드 명세·Supabase 표 컬럼과 정확히 일치해야 한다. 모르는 값은 None(null).
각 형식은 Op(어디로 어떻게 보낼지)로 바뀐다. 대기열에 넣을 수 있는 것은 Op뿐이다.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

AlertSource = Literal["camera", "no_motion", "touch", "voice", "medication_missed"]
PoseState = Literal["none", "standing", "sitting", "falling", "lying"]

COCO_KEYPOINTS = 17


@dataclass(frozen=True)
class Op:
    """Supabase 호출 1건.
    kind: rpc (함수 호출) / insert (on_conflict 컬럼 중복 시 무시) / upsert (on_conflict 기준 병합)
    """
    kind: Literal["rpc", "insert", "upsert"]
    target: str
    payload: dict[str, Any]
    on_conflict: str | None = None


def _iso(t: datetime) -> str:
    if t.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return t.isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class AlertReport:
    """원래 명세 POST /api/falls → RPC report_alert.
    대기열을 거쳐 늦게 도착할 수 있으므로 발생 시각(occurred_at)을 Pi가 보낸다."""
    source: AlertSource
    occurred_at: datetime
    confidence: float | None = None  # camera만 0~1
    detail: dict | None = None       # 판단 근거 요약. 영상·키포인트 이력 금지
    client_id: str = field(default_factory=_new_id)

    def to_op(self) -> Op:
        conf = self.confidence if self.source == "camera" else None
        if conf is not None and not 0.0 <= conf <= 1.0:
            raise ValueError("confidence must be 0~1")
        return Op("rpc", "report_alert", {
            "p_source": self.source,
            "p_confidence": conf,
            "p_occurred_at": _iso(self.occurred_at),
            "p_detail": self.detail,
            "p_client_id": self.client_id,
        })


@dataclass
class RobotStatus:
    """원래 명세 POST /api/robot/status → robot_status insert. 2초마다, 대기열에 넣지 않음."""
    esp32_ok: bool
    mode: str | None = None
    dog_battery_pct: float | None = None
    pi_battery_pct: float | None = None
    pi_charging: bool | None = None
    pi_temp_c: float | None = None
    follow_distance_cm: float | None = None
    laser_on: bool | None = None
    bpm: int | None = None
    robot_tipped: bool | None = None

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Pose:
    """원래 명세 POST /api/robot/pose → Realtime Broadcast (저장 안 함)."""
    state: PoseState
    keypoints: list[list[float]] = field(default_factory=list)

    def to_json(self) -> dict:
        if self.keypoints and len(self.keypoints) != COCO_KEYPOINTS:
            raise ValueError(f"keypoints must have {COCO_KEYPOINTS} entries")
        return asdict(self)


@dataclass
class MedicationLog:
    due_at: datetime
    status: Literal["pending", "confirmed", "missed"]
    confirmed_at: datetime | None = None
    method: Literal["touch", "voice"] | None = None

    def to_op(self) -> Op:
        return Op("upsert", "medication_logs", {
            "due_at": _iso(self.due_at),
            "status": self.status,
            "confirmed_at": _iso(self.confirmed_at) if self.confirmed_at else None,
            "method": self.method,
        }, on_conflict="due_at")


@dataclass
class GaitSession:
    started_at: datetime
    ended_at: datetime
    avg_bpm: float | None
    target_bpm: int | None
    stop_count: int
    restart_count: int
    client_id: str = field(default_factory=_new_id)

    def to_op(self) -> Op:
        d = asdict(self)
        d["started_at"], d["ended_at"] = _iso(self.started_at), _iso(self.ended_at)
        return Op("insert", "gait_sessions", d, on_conflict="client_id")


@dataclass
class VoiceSession:
    started_at: datetime
    ended_at: datetime | None
    peak_db: float | None
    target_db: int | None
    attempts: int
    success_count: int
    client_id: str = field(default_factory=_new_id)

    def to_op(self) -> Op:
        d = asdict(self)
        d["started_at"] = _iso(self.started_at)
        d["ended_at"] = _iso(self.ended_at) if self.ended_at else None
        return Op("insert", "voice_sessions", d, on_conflict="client_id")


@dataclass
class SpeakerEvent:
    """F5 인식 결과만. 임베딩·이름은 절대 보내지 않는다."""
    occurred_at: datetime
    speaker_local_id: int | None
    score: float
    accepted: bool
    client_id: str = field(default_factory=_new_id)

    def to_op(self) -> Op:
        d = asdict(self)
        d["occurred_at"] = _iso(self.occurred_at)
        return Op("insert", "speaker_events", d, on_conflict="client_id")

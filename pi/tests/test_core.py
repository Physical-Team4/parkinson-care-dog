"""하드웨어·인터넷 없이 도는 기본 테스트. 실행: 레포 루트에서 `pytest pi/tests`
Supabase SQL은 여기서 검사하지 않는다 (docs/db.md "검증" 참고)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from pi.app.adapters import mock
from pi.app.adapters.base import RemoteError
from pi.app.controllers.robot_controller import RobotController
from pi.app.models.outbox import Outbox
from pi.app.services.sync import SyncService, backoff_s
from pi.app.services.voice import loudness
from pi.app.views import serial_messages as sm
from pi.app.views.api_schemas import AlertReport, GaitSession, MedicationLog

T0 = datetime(2026, 11, 26, 1, 0, tzinfo=timezone.utc)


def make_ctrl(online=True):
    remote = mock.MockRemote(online=online)
    sync = SyncService(Outbox(":memory:"), remote)
    ctrl = RobotController(sync, remote, mock.MockPowerMonitor(), esp32_timeout_s=3.0, clock=lambda: T0)
    return ctrl, remote, sync


# ── dB ──
def test_loudness_full_scale_sine():
    sr = 16000
    sine = np.sin(2 * np.pi * 440 * np.arange(sr) / sr).astype(np.float32)
    assert loudness.dbfs(sine) == pytest.approx(-3.01, abs=0.05)
    assert loudness.peak_db(sine, sr, calibration_offset_db=90) == pytest.approx(86.99, abs=0.1)


# ── 시리얼 메시지 ──
def test_serial_roundtrip_and_debug_lines():
    assert sm.decode(sm.walk(96, msg_id=3)) == {"t": "walk", "id": 3, "bpm": 96}
    assert sm.decode(b"# debug: tof=120\n") is None
    assert sm.decode(b"garbage") is None
    with pytest.raises(ValueError):
        sm.walk(150, msg_id=1)


# ── Supabase 전송 형식 ──
def test_alert_report_op():
    op = AlertReport("touch", T0, confidence=0.9, client_id="c1").to_op()
    assert op.kind == "rpc" and op.target == "report_alert"
    assert op.payload == {"p_source": "touch", "p_confidence": None,
                          "p_occurred_at": "2026-11-26T01:00:00+00:00",
                          "p_detail": None, "p_client_id": "c1"}
    with pytest.raises(ValueError):
        AlertReport("camera", datetime(2026, 1, 1)).to_op()  # 시간대 없는 시각 금지


def test_log_ops_are_idempotent_on_retry():
    gait = GaitSession(T0, T0 + timedelta(minutes=10), 95.0, 96, 1, 1).to_op()
    assert (gait.kind, gait.on_conflict) == ("insert", "client_id")
    assert gait.payload["client_id"]
    med = MedicationLog(T0, "confirmed", T0, "touch").to_op()
    assert (med.kind, med.on_conflict) == ("upsert", "due_at")
    assert MedicationLog(T0, "pending").to_op().kind == "insert"          # 있으면 무시 (confirmed 안 덮음)
    missed = MedicationLog(T0, "missed").to_op()
    assert (missed.kind, missed.target) == ("rpc", "mark_medication_missed")


# ── 오프라인 대기열 ──
def test_queue_holds_ops_while_offline_and_resends_in_order():
    ctrl, remote, sync = make_ctrl(online=False)
    ctrl.handle_esp32_message({"t": "touch_sos"})
    ctrl.handle_esp32_message({"t": "med_missed", "due": "08:00"})
    assert len(sync.outbox) == 3 and remote.executed == []   # touch 알람, 복약 missed 기록 + 알람

    remote.online = True
    assert sync.flush(now=10**10) == 3
    alerts = [op.payload["p_source"] for op in remote.executed if op.target == "report_alert"]
    assert alerts == ["touch", "medication_missed"]
    assert [op.target for op in remote.executed][1] == "mark_medication_missed"
    assert len(sync.outbox) == 0


def test_queue_backoff_blocks_until_retry_time():
    remote = mock.MockRemote(online=False)
    sync = SyncService(Outbox(":memory:"), remote, max_backoff_s=60)
    sync.submit(AlertReport("voice", T0).to_op(), now=1000.0)   # 실패 → 1초 뒤 재시도
    remote.online = True
    assert sync.flush(now=1000.5) == 0
    assert sync.flush(now=1001.0) == 1
    assert backoff_s(10, 60) == 60


def test_permanent_error_moves_to_dead_without_blocking():
    class Rejecting(mock.MockRemote):
        def execute(self, op):
            if op.payload.get("p_source") == "voice":
                raise RemoteError("HTTP 400", permanent=True)
            return super().execute(op)

    remote = Rejecting()
    sync = SyncService(Outbox(":memory:"), remote)
    sync.outbox.enqueue(AlertReport("voice", T0).to_op(), now=0)
    sync.outbox.enqueue(AlertReport("touch", T0).to_op(), now=0)
    assert sync.flush(now=1) == 1
    assert sync.outbox.dead_count() == 1 and len(sync.outbox) == 0


# ── controller ──
def test_status_marks_esp32_offline_after_timeout():
    ctrl, _, _ = make_ctrl()
    ctrl.handle_esp32_message({"t": "status", "mode": "walking", "bpm": 96}, now_s=10.0)
    assert ctrl.build_status(now_s=11.0).esp32_ok is True
    assert ctrl.build_status(now_s=11.0).bpm == 96
    late = ctrl.build_status(now_s=20.0)
    assert late.esp32_ok is False and late.bpm is None


def test_status_is_dropped_when_offline():
    ctrl, remote, sync = make_ctrl(online=False)
    assert ctrl.send_status() is False
    assert len(sync.outbox) == 0  # 상태는 대기열에 넣지 않음

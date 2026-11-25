"""Supabase 전송 + 오프라인 재전송 (담당: B).

- 알람·훈련 기록(Op)은 항상 대기열에 먼저 넣고 바로 flush → 끊겨 있으면 남아서 나중에 재전송.
- 순서 보장: 앞 항목이 실패하면 뒤 항목도 보내지 않는다 (복약 pending → confirmed 순서 등).
- 재전송해도 중복 저장되지 않게 Op마다 client_id / on_conflict를 둔다 (api_schemas.py).
- 상태(2초)·포즈(0.4초)는 대기열에 넣지 않는다. 실패하면 버린다.
"""
from __future__ import annotations

import logging
import time

from pi.app.adapters.base import RemoteError, RemoteStore
from pi.app.models.outbox import Outbox
from pi.app.views.api_schemas import Op

log = logging.getLogger(__name__)


def backoff_s(attempts: int, max_s: float) -> float:
    """1, 2, 4, 8 ... 초, 최대 max_s."""
    return min(max_s, 2.0 ** max(0, attempts))


class SyncService:
    def __init__(self, outbox: Outbox, remote: RemoteStore, max_backoff_s: float = 300.0) -> None:
        self.outbox = outbox
        self.remote = remote
        self.max_backoff_s = max_backoff_s

    def submit(self, op: Op, now: float | None = None) -> None:
        self.outbox.enqueue(op, now)
        self.flush(now)

    def flush(self, now: float | None = None) -> int:
        """보낸 개수 반환. 첫 실패에서 멈춘다."""
        now = time.time() if now is None else now
        sent = 0
        for item in self.outbox.due(now):
            try:
                self.remote.execute(item.op)
            except RemoteError as e:
                if e.permanent:
                    # 형식 오류 등 재시도해도 안 되는 것 → 대기열을 막지 않게 따로 빼 두고 기록
                    log.error("dead op %s %s: %s", item.op.kind, item.op.target, e)
                    self.outbox.mark_dead(item.id, str(e))
                    continue
                self.outbox.mark_failed(item.id, str(e), now + backoff_s(item.attempts, self.max_backoff_s))
                break
            self.outbox.mark_sent(item.id)
            sent += 1
        return sent

    def send_now(self, fn, *args) -> bool:
        """대기열 없이 한 번만 시도 (상태·포즈). 실패해도 예외를 올리지 않는다."""
        try:
            fn(*args)
            return True
        except RemoteError as e:
            log.debug("send_now failed: %s", e)
            return False

"""Supabase REST 연결 (PostgREST + Realtime Broadcast REST). 업무 판단 없음.

- service_role(secret) 키를 쓰므로 RLS를 우회한다 → Pi의 .env에만 두고 로그에 출력 금지.
- 새 형식 키(sb_secret_...)는 apikey 헤더만, 예전 JWT 키(eyJ...)는 Authorization도 함께 보낸다.
"""
from __future__ import annotations

from typing import Any

import requests

from pi.app.adapters.base import RemoteError
from pi.app.views.api_schemas import Op


class SupabaseRest:
    def __init__(self, url: str, service_key: str, timeout_s: float = 3.0) -> None:
        self._base = url.rstrip("/")
        self._s = requests.Session()
        self._s.headers["apikey"] = service_key
        if service_key.startswith("eyJ"):
            self._s.headers["Authorization"] = f"Bearer {service_key}"
        self._timeout = timeout_s

    def _call(self, method: str, path: str, **kw: Any) -> requests.Response:
        try:
            resp = self._s.request(method, self._base + path, timeout=self._timeout, **kw)
        except requests.RequestException as e:  # 네트워크 끊김 → 재시도 대상
            raise RemoteError(type(e).__name__, permanent=False) from None
        if resp.status_code >= 400:
            # 4xx(429 제외)는 요청 자체가 잘못됨 → 재시도해도 실패
            permanent = 400 <= resp.status_code < 500 and resp.status_code not in (408, 429)
            raise RemoteError(f"HTTP {resp.status_code}: {resp.text[:200]}", permanent=permanent)
        return resp

    def execute(self, op: Op) -> Any:
        if op.kind == "rpc":
            return self._call("POST", f"/rest/v1/rpc/{op.target}", json=op.payload).json()
        if op.kind in ("insert", "upsert"):
            resolution = "ignore-duplicates" if op.kind == "insert" else "merge-duplicates"
            params = {"on_conflict": op.on_conflict} if op.on_conflict else None
            headers = {"Prefer": f"resolution={resolution},return=minimal"}
            self._call("POST", f"/rest/v1/{op.target}", json=op.payload, params=params, headers=headers)
            return None
        raise ValueError(f"unknown op kind: {op.kind}")

    def insert_status(self, row: dict) -> None:
        self._call("POST", "/rest/v1/robot_status", json=row, headers={"Prefer": "return=minimal"})

    def broadcast(self, topic: str, event: str, payload: dict) -> None:
        body = {"messages": [{"topic": topic, "event": event, "payload": payload, "private": True}]}
        self._call("POST", "/realtime/v1/api/broadcast", json=body)

    def fetch_settings(self) -> dict:
        s = self._call("GET", "/rest/v1/settings",
                       params={"select": "target_bpm,target_db,follow_limit_cm", "id": "eq.1"}).json()
        times = self._call("GET", "/rest/v1/medication_schedule",
                           params={"select": "time_of_day", "enabled": "eq.true",
                                   "order": "time_of_day"}).json()
        out = s[0] if s else {}
        out["medication_times"] = [t["time_of_day"][:5] for t in times]  # "08:00:00" → "08:00"
        return out

# 대시보드 API → Supabase 대응 (명세: D)

대시보드 팀원 명세의 **필드 이름·주기는 그대로** 지킨다. 다만 별도 HTTP 서버 대신 Supabase를 쓰므로
각 엔드포인트는 Supabase 표·RPC·Realtime으로 대응된다. 보안 구조는 [db.md](db.md#보안-구조-rls).

- Pi: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` → `pi/app/adapters/supabase_rest.py`
- 대시보드: `SUPABASE_URL` + `SUPABASE_ANON_KEY` + 로그인 → `@supabase/supabase-js` 등

## 1. 기존 명세 대응

### 로봇 → 서버

| 원래 API | 주기 | 본문 | Supabase | 보내는 사람 | 대기열 |
|---|---|---|---|---|---|
| `POST /api/falls` | 발생 시 | `source`: camera / no_motion / touch / voice / medication_missed, `confidence` (0~1, camera만) | `rpc report_alert` (+ `p_occurred_at`, `p_client_id`) | A(camera, no_motion), B(voice, ESP32의 touch·복약) | ✓ |
| `POST /api/robot/status` | 2초 | `esp32_ok`(필수), `mode`, `dog_battery_pct`, `pi_battery_pct`, `pi_charging`, `pi_temp_c`, `follow_distance_cm`, `laser_on`, `bpm`, `robot_tipped` | `insert robot_status` | B | ✗ (버림) |
| `POST /api/robot/pose` | 약 0.4초 | `state`: none / standing / sitting / falling / lying, `keypoints`: COCO 17 × `[x, y, conf]` (0~1) | Realtime Broadcast `robot:pose` / `pose` | A | ✗ (버림) |
| `GET /api/settings` | 로봇이 가져감 | 아래 형식 | `select settings`, `medication_schedule` | B (→ ESP32 `settings`) | — |

- "시각은 서버가 기록" → 대기열 때문에 바뀜: 알람은 Pi가 `occurred_at`을 보내고, 도착 시각은 `received_at`에 따로 남는다.
- "같은 종류 30초 내 중복은 1건으로" → `report_alert`가 처리 ([db.md](db.md#알람)).

settings 형식 (Pi `fetch_settings()` 반환):
```json
{ "medication_times": ["08:00", "12:30", "18:00", "22:00"],
  "target_bpm": 96, "target_db": 68, "follow_limit_cm": 150 }
```
범위: 복약 1~8개, `target_bpm` 80~110, `target_db` 50~90, `follow_limit_cm` 50~300 (DB 제약으로 강제).
TODO(D): 원래 명세의 실제 키 이름 확인 ([todo.md](todo.md)).

### 서버 자동 규칙 → Supabase 안에서 처리

| 규칙 | 구현 |
|---|---|
| status 10초 없음 → 연결 끊김 | pg_cron 10초마다 `check_robot_disconnected()`; 대시보드는 `robot_latest.connected`로도 표시 |
| 배터리 < 20% → 주의, 30분에 1번 | `robot_status` insert 트리거 → `report_alert('battery_low')` |
| `robot_tipped` → 주의, 5분에 1번 | 〃 `robot_tipped` |
| `pi_temp_c` ≥ 75 → 과열 경고 | 〃 `overheat` |
| 위급(빨강) / 주의(주황) | `alerts.severity` = critical / warning (`alert_rules`) |

### 사람 입력 (대시보드)

| 원래 기능 | Supabase |
|---|---|
| 알람 확인 메모 (200자, 처음 것만) | `rpc ack_alert({ p_alert_id, p_note })` → true(확인됨) / false(이미 확인) |
| 설정값 변경 | `update settings set target_bpm/target_db/follow_limit_cm where id=1` |
| 복약 시간 추가·수정·삭제 | `insert/update/delete medication_schedule` (1~8개는 DB가 막음) |

## 2. 새로 추가 (기존에 API 없던 F1·F3·F4·F5 기록)

### Pi → Supabase (모두 대기열 사용)

| 기록 | Supabase | 본문 | 중복 방지 |
|---|---|---|---|
| F1 복약 | `upsert medication_logs` | `due_at`, `status`: pending / confirmed / missed, `confirmed_at`, `method`: touch / voice | `on_conflict=due_at` |
| F3 보행 | `insert gait_sessions` | `client_id`, `started_at`, `ended_at`, `avg_bpm`, `target_bpm`, `stop_count`, `restart_count` | `client_id` |
| F4 발성 | `insert voice_sessions` | `client_id`, `started_at`, `ended_at`, `peak_db`, `target_db`, `attempts`, `success_count` | `client_id` |
| F5 인식 | `insert speaker_events` | `client_id`, `occurred_at`, `speaker_local_id`, `score`, `accepted` | `client_id` |
| F5 등록 수 | `update speaker_stats set registered_count` | — | — |

- 형식 정의: `pi/app/views/api_schemas.py` (`MedicationLog`, `GaitSession`, `VoiceSession`, `SpeakerEvent`).
- ESP32 `gait_end`의 `started_ms`/`ended_ms`(부팅 후 ms)는 Pi가 수신 시각 기준으로 실제 시각으로 바꾼다.
- 복약 미확인은 알람(`report_alert medication_missed`)과 기록(`medication_logs status=missed`)을 **둘 다** 보낸다.
- 화자 임베딩·이름은 보내지 않는다.

### 대시보드 ← Supabase

| 용도 | Supabase |
|---|---|
| 알람 목록 | `select alerts order by occurred_at desc limit 50` |
| 알람 실시간 | Realtime `postgres_changes` on `alerts` (INSERT, UPDATE) |
| 최신 상태 + 연결 여부 | `select robot_latest` (2~5초 주기 조회) |
| 따라오기 거리 1분 그래프 | `select received_at, follow_distance_cm from robot_status where received_at > now() - 1분` |
| 자세 | Realtime Broadcast `robot:pose` (private) |
| 7일 카드 | `rpc daily_stats({ p_days: 7 })` |

`daily_stats` 반환:
```json
{
  "registered_speakers": 2,
  "days": [
    { "day": "2026-11-26",
      "medication": {"scheduled": 4, "confirmed": 3},
      "gait": {"sessions": 2, "minutes": 18.5, "avg_bpm": 95.2, "restart_count": 3},
      "voice": {"peak_db": 71.4, "target_db": 68},
      "speaker": {"success_rate_pct": 92.0} }
  ]
}
```
기록 없는 날도 포함 (횟수는 0, 값은 null). 오래된 날짜부터 순서대로.

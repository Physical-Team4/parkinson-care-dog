# DB 설계 — Supabase (초안 v2, 최종 결정: D)

원본 SQL: [db/migrations/](../db/migrations/). API 대응: [api.md](api.md).

## 전체 구조

```
[Pi 5] ──service_role 키──▶ Supabase PostgREST  (알람 RPC, 기록 insert, status insert)
   │                     ▶ Realtime Broadcast  (포즈 0.4초, 저장 안 함)
   └─ 로컬 SQLite outbox.db : 인터넷 끊김 동안 알람·기록 대기열 → 연결되면 순서대로 재전송

[대시보드] ──anon 키 + 로그인──▶ Supabase (authenticated 역할, RLS로 care_team만)
                              ◀ Realtime: alerts 변경, 포즈 Broadcast
Supabase 안: 트리거(서버 자동 규칙), pg_cron(연결 끊김 10초 검사, status 정리)
```

## 원칙
- 원본 저장소는 **Supabase**. Pi의 SQLite는 **오프라인 대기열 전용** (`pi/app/models/outbox.py`).
- 영상·음성 원본은 어디에도 저장하지 않는다. **화자 임베딩·이름은 Supabase에 올리지 않는다** (Pi 로컬 전용, 저장 방식은 B 결정 → [todo.md](todo.md)). Supabase에는 인식 결과(`speaker_events`)와 등록 수(`speaker_stats`)만.
- 포즈(0.4초)는 표에 저장하지 않고 **Realtime Broadcast**로 보낸다 (아래).
- `robot_status`는 24시간만 보관 (pg_cron이 매시 삭제). 2초 주기 → 하루 약 43,200행.
- 시각은 `timestamptz`. 일별 집계는 `at time zone 'Asia/Seoul'`.

## 보안 구조 (RLS)

| 사용자 | 키 | 역할 | 할 수 있는 것 |
|---|---|---|---|
| Pi | service_role (새 형식: secret `sb_secret_...`) | `service_role` | RLS 우회. 전부 |
| 대시보드, 로그인 전 | anon (새 형식: publishable `sb_publishable_...`) | `anon` | **아무것도 못 읽음** |
| 대시보드, 로그인 + `care_team`에 등록 | anon + 로그인 세션 | `authenticated` | 읽기, 설정·복약 시간 변경, `ack_alert()` |
| 로그인했지만 `care_team` 아님 | 〃 | `authenticated` | 0건 보임 |

- **anon 키는 프론트엔드 코드에 들어가므로 공개된 것으로 간주한다.** 그래서 anon 역할에는 아무 권한도 주지 않고, 데이터는 로그인 + `care_team` 등록 사용자만 본다.
- Supabase Auth 설정: **공개 가입(Allow new users to sign up) 끄기**, 보호자·치료사는 초대로만 추가 후 SQL Editor에서 `insert into care_team (user_id, role) values ('<uuid>', 'guardian');`
- service_role 키는 Pi의 `.env`에만. 대시보드 서버 코드에도 넣지 않는다 (대시보드는 RLS 안에서 동작).
- 알람 확인은 표 직접 수정이 아니라 `ack_alert(id, note)` RPC로만 (메모 처음 1번만).
- 설정은 `target_bpm`, `target_db`, `follow_limit_cm` 컬럼만 수정 가능 (컬럼 단위 권한).

## 표

| 표 | 용도 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| `care_team` | 대시보드 접근 허용 목록 | 관리자(SQL Editor) | RLS |
| `alert_rules` | 알람 source별 심각도·합침 창 | 관리자 | `report_alert`, 대시보드 |
| `alerts` | 위급·주의 알람 | `report_alert()`만 | 대시보드 |
| `alert_reports` | 재전송 중복 방지 (client_id) | `report_alert()` | — |
| `robot_status` | 상태 이력 24시간 | Pi (2초) | 대시보드 (`robot_latest` 뷰) |
| `settings` | 목표값 단일 행 | 대시보드 | Pi |
| `medication_schedule` | 복약 시간 1~8개 | 대시보드 | Pi → ESP32 |
| `medication_logs` | F1 (`due_at` 기준 upsert) | Pi | 대시보드 |
| `gait_sessions` | F3 | Pi | 대시보드 |
| `voice_sessions` | F4 | Pi | 대시보드 |
| `speaker_events` | F5 인식 결과 | Pi | 대시보드 |
| `speaker_stats` | F5 등록 목소리 수 | Pi | 대시보드 |

SQLite 초안 대비: `pose_latest` 제거(→ Broadcast), `speakers` 제거(→ Pi 로컬), `care_team`·`alert_rules`·`alert_reports`·`speaker_stats` 추가, 재전송되는 표에 `client_id uuid unique` 추가, `alerts`에 `occurred_at`(Pi 발생 시각)과 `received_at`(도착 시각) 분리.

## 알람

`report_alert(p_source, p_confidence, p_occurred_at, p_detail, p_client_id)` → `{"alert_id", "merged", "duplicate"}`
- 같은 source의 최근 알람과 `occurred_at` 차이가 `alert_rules.window_seconds` 미만이면 새 행 대신 `merged_count+1`.
- `merge_into_acked=false`(낙상 등): **확인 안 된** 알람에만 합침 → 확인 후 새로 넘어지면 새 알람.
- `merge_into_acked=true`(배터리 등 "N분에 1번"): 확인된 알람에도 합침 → 확인해도 창 안에서는 다시 울리지 않음.
- `p_client_id`가 이미 처리된 보고면 아무것도 바꾸지 않음 (대기열 재전송 안전).

| source | 심각도 | 창 | 확인된 알람에도 합침 | 생성 |
|---|---|---|---|---|
| camera, no_motion, touch, voice | critical | 30초 | ✗ | Pi |
| medication_missed | warning | 30초 | ✗ | Pi |
| battery_low (< 20%) | warning | 30분 | ✓ | `robot_status` insert 트리거 |
| robot_tipped | warning | 5분 | ✓ | 〃 |
| overheat (≥ 75°C) | warning ⚠️ 임시 | 5분 ⚠️ 임시 | ✓ | 〃 |
| disconnected (status 10초 없음) | warning ⚠️ 임시 | 5분 ⚠️ 임시 | ✓ | pg_cron 10초 |

⚠️ 임시값은 `alert_rules.provisional = true`. 확정되면 `update alert_rules ...`만 하면 된다 (마이그레이션 불필요).

## 포즈: Realtime Broadcast (검토 결과)

- **채택 제안.** 0.4초 × 하루 = 약 216,000행을 쓰고 지울 필요가 없고, 최신값만 필요하다는 원칙과 맞다.
- 토픽 `robot:pose`, 이벤트 `pose`, **private 채널**. 받는 권한은 `realtime.messages` 정책으로 care_team만 (004).
- Pi 전송: `POST {SUPABASE_URL}/realtime/v1/api/broadcast` (REST, `adapters/supabase_rest.py`). 지연이 문제면 WebSocket 클라이언트로 교체.
- 대시보드: `supabase.channel('robot:pose', { config: { private: true } }).on('broadcast', { event: 'pose' }, …)`. 접속 직후에는 다음 메시지(최대 0.4초)까지 빈 화면.
- ⚠️ **메시지 수 한도**: 0.4초마다 24시간 보내면 월 약 650만 건(+ 받는 사람 수만큼). Supabase 무료 플랜 Realtime 메시지 한도를 넘을 수 있다 (정확한 한도는 Supabase 요금 페이지 확인). 대책 후보:
  1. 대시보드가 열려 있을 때만 보냄 (Presence로 시청자 확인)
  2. 자세 `state`가 바뀔 때 + 몇 초마다 1번만 보냄
  → A·D 결정 필요 ([todo.md](todo.md)).

## 오프라인 대기열 (Pi)

| 데이터 | 끊겼을 때 |
|---|---|
| 알람 (`report_alert`), F1·F3·F4·F5 기록 | `outbox.db`에 쌓고 연결되면 **순서대로** 재전송 (지수 백오프 1초~5분) |
| status (2초), 포즈 (0.4초) | 버림 (오래된 상태는 의미 없음, 재전송하면 서버 규칙이 엉뚱하게 발동) |

- 재전송 중복 방지: 알람은 `alert_reports.client_id`, 기록은 `client_id unique` + `on_conflict=client_id` (ignore), 복약은 `due_at` upsert.
- 4xx 같은 영구 오류는 지우지 않고 `dead=1`로 남겨 대기열을 막지 않는다 (사람이 확인).
- 대기 중 알람은 시각이 늦게 도착하므로 **Pi가 `occurred_at`을 보낸다** → Pi 시계가 맞아야 함 (NTP. 오프라인 부팅 시 RTC 필요 여부 [todo.md](todo.md)).
- 오프라인 동안은 보호자 원격 알림도 불가 (메신저도 인터넷 필요). 현장 경보는 ESP32 MP3.

## 일별 집계 (7일)

뷰 `daily_medication`, `daily_gait`, `daily_voice`, `daily_speaker` (모두 `security_invoker` → RLS 적용).
대시보드는 `rpc('daily_stats', { p_days: 7 })` 한 번으로 받는다 (기록 없는 날도 채움, 형식은 [api.md](api.md)).

## 검증
로컬 PostgreSQL 16에서 001~003 적용 + [db/test/checks.sql](../db/test/checks.sql)로 합침·재전송 중복·서버 규칙·메모 1회·복약 8개 제한·RLS(anon / 비회원 / care_team)·7일 집계를 확인함. 004(Realtime·pg_cron)와 Pi adapter(`supabase_rest.py`)는 로컬 Supabase(CLI 2.122.1, Postgres 17)에서 확인함: 알람 합치기·재전송, 배터리 트리거, 연결 끊김 cron, Broadcast 전송, settings 조회, anon 차단. 클라우드 프로젝트에는 첫 적용 때 한 번 더 확인.

# 대시보드 수정 계획 — 팀 회의 요청 반영 (담당: D 신효섭)

작성 2026-11-26. 진행 기록은 [progress.md](progress.md). 팀 공통 규칙은 [../CLAUDE.md](../CLAUDE.md), 대시보드 규칙은 [CLAUDE.md](CLAUDE.md).

## 1. 기존 프로젝트 분석

### 1-1. 기존 대시보드 (이관 당시, `pd-dog-dashboard` cb636aa)
| 구분 | 내용 |
|---|---|
| 서버 | `server.py` — Python 표준 라이브러리 HTTP 서버. SQLite(`falls.db`) 저장, 관리자 1명 비밀번호 로그인, 로봇 키(`X-Robot-Key`) |
| API | `GET/POST /api/falls`, `POST /api/falls/<id>/ack`, `GET /api/robot`, `POST /api/robot/status`, `GET/POST /api/robot/pose`, `GET/POST /api/settings`, `GET /api/report` |
| 화면 | `/` 보호자 대시보드, `/settings` 설정, `/report` 주간 리포트, `/login` |
| 실시간 | 알람 1초 폴링, 로봇 상태 1초 폴링, **자세 0.4초 폴링을 항상** (화면을 안 봐도 계속) |
| 예시 데이터 | F1 복용 여부, F3 보행 기록, F4 발성, F5 인식률 → `static/demo-data.js` |
| 시연 | 시연 패널(가짜 알람), 가상 로봇(상태·자세를 서버에 POST) |

### 1-2. 팀 프로젝트 최신 설계 (main 1abe5da 기준)
| 항목 | 팀 설계 | 문서·코드 |
|---|---|---|
| DB | Supabase. 표 11개 + 뷰 5개 + RPC (`report_alert`, `ack_alert`, `daily_stats`) | `db/migrations/001~004`, `docs/db.md` |
| 보안 | 대시보드는 **anon 키 + Supabase Auth 로그인**, `care_team`에 있는 사람만 읽기 (RLS). service_role 금지 | `003_rls.sql` |
| API | 별도 API 서버 없이 Supabase 직접. 기존 `/api/*` → 표·RPC·Realtime 대응표 | `docs/api.md` |
| 실시간 | 알람 = Realtime `postgres_changes`, 상태 = `robot_latest` 2~5초 조회, 자세 = Broadcast `robot:pose`(private) | `004_realtime_cron.sql` |
| 오프라인 | Pi SQLite 대기열(`outbox.db`) → 재연결 시 순서대로 재전송. 알람·기록만, status·자세는 버림. `occurred_at`(발생)·`received_at`(도착) 분리 | `pi/app/models/outbox.py`, `services/sync.py` (B) |
| 연결 끊김 | `robot_latest.connected` (10초), pg_cron이 10초마다 `disconnected` 알람 | `002`, `004` |
| 영상 | **대시보드는 영상을 받지도 보여 주지도 않음. 키포인트만** | `CLAUDE.md`, `dashboard/CLAUDE.md`, D-011 |
| 하드웨어 | MechDog 본체 보드 = ESP32. **ESP32-S3 비전 모듈은 사용 안 함** | `docs/hardware.md` |

### 1-3. 차이·충돌 정리
| # | 기존 대시보드 | 팀 설계 | 처리 |
|---|---|---|---|
| 1 | 자체 서버 + SQLite + 자체 로그인 | Supabase 직접 + Auth + RLS | 데이터 계층을 Supabase로 교체 (사용자 결정: "Supabase + 브라우저 Mock") |
| 2 | 알람 필드 `created_at`, `status`, `note`, `simulated` | `occurred_at`, `received_at`, `acknowledged_at`, `ack_note`, `severity`, `merged_count` | 모델 계층에서 변환, 화면 코드는 유지 |
| 3 | 알람 종류 `low_battery`, `test` | `battery_low`, `overheat`, `disconnected` (test 없음) | 종류표에 팀 source 추가 |
| 4 | 설정 `walk_bpm`, `follow_max_cm`, `voice_target_db`, `doses[[시각, 이름]]` | `settings.target_bpm/target_db/follow_limit_cm`, `medication_schedule(time_of_day, name, enabled)` | 팀 이름으로 저장 |
| 5 | 자세 0.4초 상시 폴링 | Broadcast, 메시지 한도 문제로 "열려 있을 때만" 검토 중 (db.md) | **자세 보기를 열었을 때만 구독** + Presence로 시청 여부 공개 |
| 6 | 요청 3: "실시간 카메라 영상" | 영상 전송 금지 | **영상은 만들지 않음.** 요청의 취지(필요할 때만 받기·중단·재연결·저장 안 함)를 키포인트 자세 보기에 적용 |
| 7 | 요청 7: "ESP32-S3 연결 상태" | ESP32-S3 사용 안 함 | ESP32(MechDog) 연결로 표시, S3는 표시하지 않음 |
| 8 | 요청 5: 복용 요일·사용자별 알림 | `medication_schedule`에 요일·사용자 컬럼 없음, 로봇 1대 = 환자 1명 | 스키마를 임의로 바꾸지 않음. 지원되는 항목만 구현, 요일은 제안으로 남김 |
| 9 | 요청 6: 리듬 큐잉 시작/중지 원격 명령 | 대시보드 → 로봇 명령 통로 없음 (설정값만 DB로 전달) | 인터페이스 + Mock만 (사용자 결정). 실제 전송은 "미연동" 표시 |
| 10 | 요청 4: 동기화 대기 건수 | Pi가 대기열 길이를 Supabase에 보내지 않음 | 보낼 수 있는 값만 표시 (마지막 수신, 지연 도착 알람). 대기 건수는 B에게 요청 |
| 11 | 시연 패널·가상 로봇 | anon 키로는 로봇 데이터를 쓸 수 없음 (RLS) | Mock 모드에서만 표시 |

## 2. 구조 (MVC)

```
dashboard/
  server.py              정적 파일 + /config.js (환경변수의 URL·anon 키, 데이터 소스) 만 제공
  static/
    index.html settings.html report.html login.html   View + Controller (화면·이벤트)
    js/model.js          Model: 순수 함수 (DB 행 → 화면 값 변환, 검증, 상태 판단). node로 테스트
    js/store.js          데이터 소스 선택 + 공통 오류 처리
    js/store-supabase.js 실제 연동 (supabase-js, RLS 안에서)
    js/store-mock.js     하드웨어·Supabase 없이 동작하는 Mock (시연·테스트)
    demo-data.js         Mock 예시 값
  tests/                 node 테스트 (model, mock store)
  test_server.py         서버 테스트 (설정 주입·키 보호·정적 파일)
```
- 화면은 `store`의 같은 함수만 부른다 → Supabase·Mock을 바꿔도 화면 코드는 같다 (팀의 adapter + mock 규칙과 같은 방식).
- 키: `SUPABASE_URL`, `SUPABASE_ANON_KEY`를 `.env`에서 읽음. `SUPABASE_SERVICE_ROLE_KEY`는 읽지 않고, anon 자리에 secret 키가 들어 있으면 서버가 시작을 거부.

## 3. 작업 계획 (단계)
| 단계 | 내용 | 요청 |
|---|---|---|
| 0 | Supabase 클라우드 프로젝트 `pd-dog`(서울) 생성, 001~004 적용, 테스트 계정 | 2 |
| 1 | `server.py` 단순화, `/config.js`, `.env.example`에 `DASHBOARD_DATA_SOURCE` 이름 추가 | 2, 10 |
| 2 | `model.js`, `store*.js` 작성 (알람·상태·설정·복약·통계·자세·리듬 명령) | 2 |
| 3 | 로그인 → Supabase Auth (이메일·비밀번호), 로그아웃 | 2 |
| 4 | index: 알람(Realtime + 5초 확인), 오늘 요약, 기능 카드 실제 값, 데이터 없음 표시 | 2, 8 |
| 5 | 자세 보기: 열었을 때만 구독, 탭 숨김·페이지 이동 시 중단, 5분 자동 종료, 상태·재연결 | 3 |
| 6 | 오프라인: 로봇 온라인/오프라인, 마지막 수신, 동기화 상태, 지연 도착 표시, 재연결 시 새로고침, 중복 방지 | 4 |
| 7 | 복약: 추가·수정·삭제(확인 메시지)·켜기/끄기·이름, 오늘 복용 기록, 주간 이력 | 5 |
| 8 | 리듬 큐잉: 설정값 저장(실제 전달), 시작/중지 인터페이스 + Mock, 안전 조건·결과 표시 | 6 |
| 9 | 로봇 연결 상태: Pi·ESP32(USB)·모드·배터리·충전·마지막 통신, 미연동 구분 | 7 |
| 10 | report: daily_stats·alerts·medication_logs 실제 값 | 8 |
| 11 | 테스트 (node, python, 브라우저 Mock·Supabase, 모바일 폭), 문서 정리 | 11, 12 |

## 4. 하지 않는 것 (근거)
- 영상 스트리밍·영상 저장 (팀 규칙).
- 새 표·컬럼 추가 (요청 2 "임의로 새 DB 구조 금지"). 필요한 변경은 제안으로만 [progress.md](progress.md)에 기록.
- Pi·ESP32 코드 수정 (B·C 담당). 필요한 연동은 협조 요청으로 기록.
- 디자인 변경. 색·카드·메뉴 그대로, 필요한 버튼·입력만 추가.

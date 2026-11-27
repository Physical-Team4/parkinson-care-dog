# 대시보드 수정 진행 기록 (담당: D 신효섭)

기준 커밋: main `1abe5da` + 이관 커밋. 작업 브랜치 `feat/dashboard-supabase`. 날짜 2026-11-26~27.
분석·계획 원문은 [PROJECT_PLAN.md](PROJECT_PLAN.md).

## 1. 기존 프로젝트 분석 결과 (요약)
- 기존 대시보드는 **자체 Python 서버 + SQLite + 자체 로그인**, 팀 설계는 **Supabase 직접 연결 + Auth + RLS** → 데이터 계층을 바꿔야 했음.
- 필드 이름이 다름: `created_at/status/note` ↔ `occurred_at/received_at/acknowledged_at/ack_note/severity/merged_count`, 설정 `walk_bpm` ↔ `target_bpm` 등.
- 자세는 0.4초마다 **항상** 받고 있었음 (화면을 안 봐도).
- 회의 요청 중 팀 규칙과 충돌하는 것:
  - 요청 3 "실시간 카메라 영상" → 팀 규칙상 **영상 전송 금지, 키포인트만**. 영상은 만들지 않고 자세(키포인트)에 같은 원칙 적용.
  - 요청 7 "ESP32-S3" → 하드웨어 문서상 **ESP32-S3 비전 모듈 사용 안 함**, 본체는 MechDog ESP32. S3 항목은 만들지 않음.
  - 요청 5 "복용 요일·사용자별" → 스키마에 없음. 임의로 표를 바꾸지 않음 (제안으로 기록).
  - 요청 6 "원격 시작/중지" → 대시보드→로봇 명령 통로 없음. 인터페이스 + Mock만 (사용자 결정).

## 2. 수정 작업 계획
[PROJECT_PLAN.md](PROJECT_PLAN.md) 3장 단계 0~11. 사용자 결정 3가지:
1. 서버 구조: **Supabase + 브라우저 Mock** (server.py는 정적 파일·설정만)
2. 테스트 DB: **클라우드 새 프로젝트** `pd-dog` (서울, 무료)
3. 리듬 시작/중지: **인터페이스 + Mock만**, 실제 통로는 팀 합의

## 3. 수정한 기능
| 요청 | 결과 |
|---|---|
| 2 DB 구조 | 모든 화면이 팀 스키마(001~004)로 읽고 씀. 알람 확인은 `rpc ack_alert`, 7일 통계는 `rpc daily_stats`, 상태는 `robot_latest`. 로그인은 Supabase Auth, `care_team` 아닌 계정은 경고 띠 |
| 3 자세(영상 대신) | 버튼을 눌렀을 때만 private Broadcast 구독. 탭 숨김 → 일시 멈춤(돌아오면 재개), 페이지 이동 → 중단, 5분 → 자동 종료. 상태: 꺼짐·연결 중·신호 기다리는 중·실시간·신호 없음(5초)·연결 실패, "다시 연결" 버튼. 저장 없음 |
| 4 오프라인 | 로봇 온라인/오프라인(`connected` 10초), 마지막 통신 시각, 동기화 상자(정상·로봇 오프라인·대시보드 오프라인·신호 없음), **늦게 도착 표시**(발생→도착 60초 넘으면 "📶 늦게 도착"), 재연결(브라우저 online·로봇 복귀·DB 복구) 시 전체 새로고침, Realtime+폴링 결과를 id로 합쳐 **중복 없음**, 끊겨도 마지막 기록 유지 + "몇 시까지 받은 내용" 표시 |
| 5 복약 | 추가·수정(시각·약 이름)·삭제(줄 안 확인 메시지)·켜기/끄기 즉시 저장, 1~8개·시각 중복은 화면과 DB 둘 다 막음, 오늘 복용 상태는 `medication_logs` 기록대로(없으면 "기록 없음", 지어내지 않음), 리포트에 7일 복약 이력 표. "의사·약사가 정한 시간만" 안내 |
| 6 리듬 큐잉 | 목표 박자·거리 한도는 `settings`에 저장 → Pi가 가져가 ESP32로 전달(팀 설계). 대시보드에 "로봇 보행" 상자: 목표값·로봇 지금 상태·안전 확인 체크·시작/정지·전달 성공/실패 문구. Supabase 모드는 "원격 명령 미연동"으로 버튼 꺼짐(실제처럼 꾸미지 않음), Mock에서 성공·로봇 오프라인·시간 초과·범위 거절 확인. 안전 조건: 80~110보/분, 로봇 연결, ESP32 응답, 넘어짐 아님, 경보·복약 중 아님, MechDog 배터리 20% 이상(값 있을 때) |
| 7 로봇 연결 | Pi(인터넷)·MechDog/ESP32(USB 통신, 하나의 신호로 판단함을 표시)·모드·MechDog/Pi 배터리·충전·마지막 통신. 없는 값은 "미연동 (ESP32가 아직 안 보냄)", "측정 안 됨 (X1200 미연결)", "데이터 없음" |
| 8 기존 기능 | 알람·메모·빠른 메모·경보음·오늘 요약·낙상/위급 카드·박자 미리보기·ToF 거리 그래프·발성 그래프·리포트·인쇄 유지. 예시 데이터 → 실제 `daily_stats` 값 |
| 9 디자인 | 색·카드·메뉴·그래프 그대로. 추가: 자세 버튼, 로봇 보행 상자, 충전·마지막 통신 줄, 동기화 상자, 늦게 도착·합침(×n) 표시, 복약 편집 칸 |
| 시연 | 시연 패널·가상 로봇은 **Mock 모드에서만** (+ 로봇 인터넷 끊기·대시보드 인터넷 끊기·명령 실패 흉내 버튼) |

## 4. 변경된 파일
| 파일 | 변경 |
|---|---|
| `dashboard/server.py` | 다시 작성: 정적 파일 + `/config.js`. SQLite·로그인·로봇 키·`/api/*` 제거. secret 키 거부, CSP·보안 헤더 |
| `dashboard/static/js/model.js` | 새 파일 (Model) |
| `dashboard/static/js/store.js`, `store-supabase.js`, `store-mock.js` | 새 파일 (데이터 소스) |
| `dashboard/static/index.html` | 데이터 계층 교체 + 요청 3·4·6·7 UI |
| `dashboard/static/settings.html` | 복약 CRUD, settings 저장 |
| `dashboard/static/report.html` | 실제 기록, 복약 이력 |
| `dashboard/static/login.html` | Supabase Auth |
| `dashboard/static/demo-data.js` | 주석 (Mock 전용) |
| `dashboard/test_server.py` | 다시 작성 (15개) |
| `dashboard/tests/*.test.mjs` | 새 파일 (node 22개) |
| `dashboard/simulate_fall.py` | **삭제** — 없어진 `/api/falls`로 보내는 도구. 로봇 쪽 알람은 Pi `supabase_rest.py`(`report_alert`)가 담당 |
| `dashboard/README.md`, `PROJECT_PLAN.md`, `progress.md` | 문서 |
| `.env.example` | `DASHBOARD_DATA_SOURCE` 이름만 추가 |
| `docs/decisions.md` | DB 적용 기록 1줄 |
| `docs/todo.md` | 합의 필요 항목 4개 추가, 2개 갱신 |
- 다른 팀원 폴더(`pi/`, `esp32/`)와 `db/migrations/`는 바꾸지 않음. `CLAUDE.md`도 바꾸지 않음 (아래 6번 참고).

## 5. DB·API 연동 사항
- 프로젝트 `pd-dog` (`uydylirzdacakdrfyeep`, 서울). 001~004 적용 (004는 Realtime 초기화 뒤).
- 화면별 표·RPC·주기: [README.md](README.md) "화면 ↔ Supabase".
- 대시보드는 publishable(anon) 키 + 로그인 세션만. 로그인 전 조회는 `permission denied`로 막히는 것 확인.
- 테스트 계정 `pd-dog-test@example.com` (care_team guardian, 비밀번호는 레포·문서에 없음). **실제 운영 전에 삭제**하고 보호자 계정은 초대로 추가.
- 테스트 데이터가 들어 있음: 알람 3, robot_status 1, 복약 기록(어제), 보행 2, 발성 2, 인식 2, 복약 일정·설정 변경(21:15 일정 추가·꺼짐, 박자 100, 거리 180). 남은 robot_status 1줄 때문에 24시간 동안 5분마다 "연결 끊김" 알람이 생김 → 정리 SQL은 아래 9번.

## 6. 테스트 결과
| # | 항목 | 방법 | 결과 |
|---|---|---|---|
| 1 | 대시보드 실행 | 서버 테스트, 브라우저(Mock·Supabase) | ✅ |
| 2 | 기존 기능 (알람·메모·합침·경보·카드·리포트·로그인/로그아웃) | 브라우저 Mock·Supabase | ✅ |
| 3 | 복약 추가·수정·삭제 (확인 메시지, 중복·최대 8개·최소 1개) | node + 브라우저 Mock·Supabase + DB 조회 | ✅ |
| 4 | 복약 저장·조회 (새로고침 후 유지) | 브라우저 Supabase + DB 조회 | ✅ |
| 5 | 자세 시작·중단·탭 숨김·신호 없음·다시 연결 | 브라우저 Mock·Supabase (`realtime.send`로 실제 Broadcast) | ✅ |
| 6 | 인터넷 끊김 표시 (로봇·대시보드) | Mock 흉내 + Supabase(요청 차단, 로봇 신호 중단) | ✅ |
| 7 | 재연결 시 갱신, 늦게 도착 표시 | Mock(대기열 재전송) + Supabase(6분 전 발생 알람) | ✅ |
| 8 | 리듬 명령 성공·실패·미연동 | Mock(성공·시간 초과·오프라인·범위) + Supabase(미연동, 버튼 꺼짐) | ✅ |
| 9 | 로봇 연결 상태, 미연동 구분 | 브라우저 Mock·Supabase | ✅ |
| 10 | DB 연동 (RLS·컬럼 권한·RPC·Realtime·pg_cron) | 브라우저 + SQL 확인 | ✅ |
| 11 | API 오류 처리 (권한·범위·중복·네트워크 → 쉬운 문장) | node | ✅ |
| 12 | 기존·새 기능 충돌 | 전체 E2E 한 흐름, 콘솔 오류 0건 | ✅ |
| 13 | 모바일 375px·PC 1280px | 브라우저, 가로 스크롤 없음 + 스크린샷 확인 | ✅ |
- 자동 테스트: node 22/22, 서버 15/15, Pi `pytest pi/tests` 27/27 (영향 없음 확인), pre-commit 통과.
- 브라우저 E2E (헤드리스 Chrome + DevTools Protocol, 스크립트는 레포 밖 임시 폴더):
  - Mock 23/23 (콘솔 오류 0건 포함, 마지막 수정 뒤 다시 실행).
  - Supabase 기능 검사 26/26 (A 로그인·복약·설정 13, B 상태·알람·자세 6, C 오프라인·리포트·로그아웃 5, D 자세 반복 2).
    콘솔: A의 400 1건은 일부러 넣은 틀린 비밀번호, B의 재귀 오류 1건은 아래 7번에서 고친 뒤 C·D 0건.
- 수동 확인 권장: 실제 휴대폰에서 경보음(브라우저 자동재생 정책), 고령 사용자 글자 크기 체감.

## 7. 발견된 오류와 해결
| 오류 | 원인 | 해결 |
|---|---|---|
| 004 적용 실패 `relation "realtime.messages" does not exist` | 새 프로젝트는 Realtime이 첫 접속 때 초기화됨 | 대시보드 첫 접속 뒤 다시 적용 (decisions.md 기록) |
| 자세 멈춤 때 `Maximum call stack size exceeded` | 채널을 닫으면 Supabase가 곧바로 `CLOSED`를 알림 → 다시 멈춤 함수 호출 | 구독 변수를 먼저 비운 뒤 닫기. 3회 반복 테스트로 확인 |
| 모바일에서 약 이름 칸이 너무 좁음 | 한 줄에 시각·이름·체크·버튼 | 이름 칸 기본 너비 150px, 좁으면 다음 줄 |
| favicon 404 콘솔 오류 | 아이콘 파일 없음 | 빈 아이콘 지정 |
| (테스트) 늦게 도착 표시 안 뜸 | 테스트에서 14초만 끊음 (기준 60초) | 테스트를 60초 넘게 끊도록 수정 |

## 8. 다른 팀원의 협조가 필요한 부분
| 누구 | 내용 |
|---|---|
| A (영상) | 자세를 "보는 사람이 있을 때만" 보내려면 Pi가 Presence로 시청자 수를 확인해야 함 → `realtime.messages` presence 정책 마이그레이션(D) + Pi 송신 조건(A). 지금은 대시보드만 열었을 때 구독 |
| B (Pi 통합) | ① 대기열 길이를 status에 포함하면 "동기화 대기 N건" 표시 가능 (스키마 변경 필요, D와 함께) ② 설정을 부팅 때만 가져옴 → 대시보드에서 바꾼 복약·박자가 반영되는 주기 결정 ③ 복약 요일을 넣으려면 `fetch_settings`·ESP32 F1 수정 |
| B·C (명령) | 리듬 큐잉 원격 시작/정지 통로 (명령 표 + Pi 조회 또는 Broadcast) 와 안전 조건 합의. 대시보드 `sendRhythmCommand(cmd, {bpm})` 인터페이스는 준비됨 |
| D (본인) | ESP32 `dog_battery_pct`(MechDog 배터리) 전송 → 대시보드 "미연동"이 실제 값으로 바뀜 |
| 팀 | `docs/todo.md`의 Supabase 항목 확인 |

## 9. 실제 하드웨어 연동 후 확인할 것
- Pi `robot_status` 2초 전송 → 연결·배터리·모드·ToF 거리 표시, 10초 끊김 → 오프라인.
- Pi 인터넷을 끊었다 다시 연결 → 그동안 알람이 "늦게 도착"으로, 기록이 7일 통계에 반영되는지 (Pi 시계 NTP 정확도 포함).
- Pi `broadcast("robot:pose")` → 자세 보기 지연·끊김, 무료 플랜 Realtime 메시지 사용량.
- ESP32 `status`의 `mode` 값이 화면 이름표(MODE_LABEL)와 맞는지, `dog_battery_pct`·`robot_tipped` 실제 값.
- 복약 일정 변경 → Pi `fetch_settings` → ESP32 `settings` → 실제 알림 시각.
- 휴대폰(같은 와이파이, `--host 0.0.0.0`)에서 경보음·화면.

테스트 데이터 정리 SQL (D가 SQL Editor에서, 실행 전 확인):
```sql
delete from public.robot_status; delete from public.alerts; delete from public.medication_logs;
delete from public.gait_sessions; delete from public.voice_sessions; delete from public.speaker_events;
update public.speaker_stats set registered_count = 0 where id = 1;
update public.settings set target_bpm = 96, follow_limit_cm = 150 where id = 1;
delete from public.medication_schedule where time_of_day = '21:15';
-- 테스트 계정: Authentication → Users에서 pd-dog-test@example.com 삭제 (care_team은 자동 삭제)
```

## 10. 남은 작업
- [ ] Supabase Auth: 공개 가입 끄기, 유출 비밀번호 검사 켜기, Realtime "Allow public access" 끄기 (대시보드 설정 화면, setup.md 3번)
- [ ] 보호자·치료사 계정 초대 + `care_team` 등록, 테스트 계정·테스트 데이터 정리
- [ ] `dashboard/CLAUDE.md` 첫 줄(실행 명령)을 새 구조로 갱신 — CLAUDE.md는 임의 수정 금지라 이번에 바꾸지 않음. 승인 후 수정
- [ ] 8번 협조 항목 합의 → 리듬 명령 통로 연결, Presence, 대기열 길이, 복약 요일 (필요하면 005 마이그레이션)
- [ ] 트리거 함수 `search_path` 지정 (보안 점검 경고) — 005 후보
- [ ] 실제 하드웨어 연동 확인 (9번)

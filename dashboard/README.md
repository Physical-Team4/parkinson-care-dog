# dashboard/ — PD-Dog 보호자·치료사 대시보드 (담당: D 신효섭)

보호자·치료사가 알람을 받고 확인하며, 로봇 상태·훈련 기록을 보고, 복약 알림과 훈련 목표를 정하는 웹 화면.
데이터는 **Supabase에 직접 연결**한다 (별도 API 서버 없음, [docs/api.md](../docs/api.md) · [docs/db.md](../docs/db.md)).

- 수정 계획·분석: [PROJECT_PLAN.md](PROJECT_PLAN.md) · 진행·테스트 기록: [progress.md](progress.md) · 관리자 페이지 계획(미구현): [ADMIN_PLAN.md](ADMIN_PLAN.md)
- 원본: `steve5781-a11y/pd-dog-dashboard` (cb636aa)에서 이관 (2026-11-26). 이관 당시 설계 기록: [PLAN.md](PLAN.md), [PLAN-REVIEW-LOG.md](PLAN-REVIEW-LOG.md) — SQLite·자체 로그인 시절 문서라 지금 구조와 다름.

## 실행

레포 루트 `.env`에 이름만 있는 값을 채운다 (커밋 금지, 값은 D에게 받기):
```
SUPABASE_URL=https://<프로젝트>.supabase.co
SUPABASE_ANON_KEY=<anon / publishable 키>     ← service_role(secret) 키는 절대 넣지 말 것 (넣으면 서버가 시작을 거부)
```
```bash
conda activate pd-dog
cd dashboard
python server.py              # http://127.0.0.1:8000  (.env에 키가 있으면 Supabase, 없으면 Mock)
python server.py --mock       # Supabase 없이 예시 데이터 + 시연 패널(가상 로봇·인터넷 끊김 흉내)
python server.py --host 0.0.0.0   # 같은 와이파이의 휴대폰에서 보기
python server.py --dev-login      # 개발용: 로그인 화면 없이 테스트 계정으로 자동 로그인 (아래)
```
- `--dev-login`: `.env`의 `DASHBOARD_DEV_EMAIL`·`DASHBOARD_DEV_PASSWORD`(**테스트 계정만**)로 자동 로그인.
  계정 비밀번호가 `/config.js`로 브라우저에 가므로 **127.0.0.1에서만** 켜진다 (`--host 0.0.0.0`과 같이 쓰면 시작 거부,
  다른 기기에서 온 요청에는 넣지 않음). DB 권한(RLS)은 그대로. 시연·실사용에서는 쓰지 않는다.
- 로그인: Supabase Auth 이메일·비밀번호. **초대받고 `care_team`에 등록된 계정만** 데이터가 보인다 ([docs/setup.md](../docs/setup.md) 3번).
- 브라우저는 `supabase-js@2.45.4`를 jsDelivr에서 받는다 (Supabase 모드만, 버전 고정). Mock 모드는 인터넷 없이 동작.

## 테스트
```bash
cd dashboard
node --test "tests/*.test.mjs"           # Model·Mock store (22개)
python -m unittest -v test_server.py     # 서버: 설정 주입·secret 키 거부·정적 파일·자동 로그인 제한 (16개)
```
브라우저 E2E(Mock·Supabase) 결과는 [progress.md](progress.md).

## 구조 (MVC)
```
server.py                 정적 파일 + /config.js(데이터 소스, URL, anon 키)만. 저장·로그인·권한은 Supabase
static/index.html         보호자 대시보드      ┐
static/settings.html      복약 알림·훈련 목표  │ View + Controller (화면·이벤트)
static/report.html        치료사용 주간 리포트 │
static/login.html         로그인               ┘
static/js/model.js        Model: DB 행 → 화면 값, 검증, 연결·동기화 판단 (순수 함수)
static/js/store.js        데이터 소스 선택 (공통 함수 목록은 파일 맨 위)
static/js/store-supabase.js  실제 연동 (anon 키 + 로그인 세션, RLS 안에서)
static/js/store-mock.js   Mock (DB 규칙 흉내, 가상 로봇, 오프라인·명령 실패 흉내)
static/demo-data.js       Mock 예시 값
tests/                    node 테스트
```

## 화면 ↔ Supabase
| 화면 | 읽기·쓰기 | 주기 |
|---|---|---|
| 알람 상태·기록·확인 메모 | `alerts` + Realtime `postgres_changes`, `rpc ack_alert` | Realtime + 5초 확인 (id로 합쳐 중복 없음) |
| 알람 모두 확인 (미확인 2건 이상) | `rpc ack_alert`를 건마다, 메모 "모두 확인". **삭제 아님** (기록 보존, 대시보드는 삭제 권한 없음) | 누를 때 (한 번 더 묻기) |
| 로봇 연결·배터리·모드·충전·마지막 통신 | `robot_latest` | 2초 |
| 따라오는 거리 1분 그래프 | `robot_status` (최근 60초) | 2초 |
| 자세 보기 (키포인트, 영상 없음) | Realtime Broadcast `robot:pose` (private) | **버튼을 눌렀을 때만**, 탭 숨김·페이지 이동·5분 뒤 자동 중단 |
| 복약 알림 추가·수정·삭제·켜기/끄기 | `medication_schedule` (1~8개, 시각 중복 금지) | 즉시 저장 |
| 오늘 복약·복약 이력 | `medication_logs` (Pi가 씀) | 30초 |
| 훈련 목표 (박자·거리 한도·목소리 크기) | `settings` | 저장 버튼 |
| 보행·발성·인식률 7일 | `rpc daily_stats` | 60초 |
| 리듬 큐잉 시작/정지 | **미연동** (명령 통로 없음, progress.md 협조 요청) | — |

## 지켜야 할 것
- 영상은 받지도 보여 주지도 않는다. 자세는 키포인트만, 저장하지 않는다.
- 받지 못한 값은 "데이터 없음 / 미연동"으로 표시한다. 예시 값을 실제처럼 보이게 하지 않는다 (Mock 모드에는 항상 "예시 데이터" 표시).
- 시스템이 복용량·복용 시간을 정하지 않는다. 사람이 넣은 일정만 저장한다.
- 원격 보행 시작은 안전 조건(연결·ESP32 응답·넘어짐·배터리·보호자 확인 체크)을 통과해야만 보낸다. 정지는 언제나 허용.

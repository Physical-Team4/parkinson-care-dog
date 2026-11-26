# 관리자 페이지 개발 계획 (초안, 팀 협의용)

작성 2026-11-27, D 신효섭. 상태: **계획만 있음, 구현 전**. 요구사항이 확정되지 않아서 "지금 가능한 것"과 "협의가 필요한 것"을 나눴다.
기준: DB `db/migrations/001~004`, [docs/db.md](../docs/db.md), [docs/api.md](../docs/api.md), 대시보드 구조 [README.md](README.md).

## 1. 현재 상태 점검 결과

**관리자 페이지는 없다.**

| 확인한 곳 | 결과 |
|---|---|
| 대시보드 화면 | `/`(보호자), `/settings`, `/report`(치료사용), `/login` 4개. 관리자 화면 없음 |
| 이관 전 대시보드 | "관리자 로그인"은 공용 계정 1개로 들어가는 로그인이었고, 관리 기능 화면은 없었음 |
| DB 역할 | `care_team.role`에 `guardian`·`therapist`·`admin` 값은 있음. **그러나 RLS는 `is_care_team()` 하나만 봐서 세 역할의 권한이 같다** |
| 관리 작업 | 계정 초대·`care_team` 등록·알람 규칙(`alert_rules`) 수정은 Supabase 웹(Authentication, SQL Editor)에서 직접 함 |
| 접근 기록 | 없음. `auth.audit_log_entries`는 비어 있음 (Supabase 로그 탐색기에 로그인 이벤트만 있음) |
| 로봇 등록 | 로봇 표 없음. **로봇 1대 = 환자 1명** 전제로 모든 표가 설계됨 |

→ 지금은 "관리자"가 따로 없고, 돌봄팀 누구나 같은 화면·같은 데이터를 본다. 관리 작업은 Supabase 웹 접근 권한(D)에 의존한다.

## 2. 설계 원칙
- **디자인**: 기존 대시보드의 색·카드·배지·표 스타일을 그대로 쓴다. 새 화면 `/admin` 1개 + 머리글에 "🛠 관리" 칩(관리자에게만 보임).
- **구조**: 기존 MVC 그대로. `js/model.js`에 판단 함수, `js/store-*.js`에 관리용 함수 추가, Mock도 함께 만든다.
- **보안**: 브라우저에는 지금처럼 anon 키 + 로그인 세션만. **service_role 키는 관리자 화면에도 넣지 않는다.** 관리자 권한은 DB(RLS·함수)에서 확인한다. 화면에서 버튼을 숨기는 것만으로 권한을 나누지 않는다.
- **개인정보 최소화**: 관리자 화면은 시스템 운영 정보(연결·오류·이용량)를 보여 주고, 환자 기록 원본(메모 내용·복약 이력 등)은 보여 주지 않는다. 필요하면 집계만.
- **새 표·권한은 `db/migrations/005_*.sql`** 새 파일로만 (적용된 파일 수정 금지), 같은 파일에서 RLS 정책까지.

## 3. 기능별 구분

범례: 🟢 지금 가능 (스키마 변경 없음) · 🟡 D가 만들 수 있음 (005 마이그레이션 필요, 팀 검토 후) · 🔴 팀 협의·다른 담당 작업 필요

| 요청 기능 | 구분 | 무엇으로 | 비고 |
|---|---|---|---|
| **로봇·센서 연결 상태 모니터링** | 🟢 | `robot_latest`, `robot_status`(24시간) | 최근 24시간 연결 비율, ESP32 응답 비율, 마지막 통신, 배터리·온도 추이. ToF·레이저·배터리 값이 `null`이면 "미연동" |
| **통신 장애 기록** (연결 끊김 등) | 🟢 | `alerts` 중 `disconnected`·`overheat`·`battery_low`·`robot_tipped` | 발생 시각·지속(합침 횟수)·확인 여부. 늦게 도착한 알람 건수(대기열 재전송 흔적) |
| **전체 서비스 이용 현황** | 🟢 | `rpc daily_stats(최대 90일)`, `alerts` 집계 | 기능별 사용 횟수(보행·발성·복약 확인률), 알람 건수·평균 확인 시간 |
| **DB 상태 확인** (부분) | 🟢 | 브라우저 → Supabase 응답 시간, 표별 최신 기록 시각 | "DB에 닿는가 / 데이터가 들어오고 있는가"까지. 용량·연결 수는 🟡 |
| **일반 사용자 / 관리자 권한 분리** | 🟡 | `is_admin()` 함수 + 정책 | **이것이 먼저 있어야 아래 🟡가 안전함.** 없으면 위 🟢 화면도 돌봄팀 누구나 볼 수 있음 (데이터는 이미 볼 수 있는 것이라 유출은 아님) |
| **사용자 계정 관리** — 역할 변경·돌봄팀 해제·목록 | 🟡 | `care_team` 관리자 정책 + `admin_list_members()` RPC(이메일·역할·마지막 로그인) | 이메일은 `auth.users`에 있어 security definer 함수로만 관리자에게 보여 줌 |
| 사용자 계정 관리 — **초대·생성·비밀번호 재설정·삭제** | 🔴 | Supabase Auth 관리 API = service_role 필요 | 브라우저에서 불가. ① 계속 Supabase 웹에서 하기 ② Edge Function(서버 쪽에서 관리자 확인 후 처리) 새로 만들기 중 선택 |
| **관리자 접근 기록** | 🟡 | `admin_access_log` 표 (누가·언제·무엇을), 관리 RPC 안에서 기록 | 기록은 관리자도 수정·삭제 못 하게 (insert만, 정책 없음). 무엇을 남길지·보관 기간은 🔴 |
| **알람 규칙 관리** (추가 제안) | 🟡 | `alert_rules` 관리자 update 정책 | 지금 SQL Editor로 하는 일. 임시값(`provisional`) 확정 화면 |
| **서버(라즈베리파이) 상태** | 🔴 | 지금 오는 값은 `pi_temp_c`·`pi_battery_pct`뿐 | CPU·메모리·디스크·가동 시간·앱 버전·대기열 길이는 Pi가 보내야 함 (B). `robot_status` 컬럼 추가 |
| **시스템 오류 기록** (Pi·ESP32) | 🔴 | 새 표 `system_events` (Pi가 씀) | 대기열 영구 실패(`dead`), ESP32 크래시(`log("crash")`), 카메라·Hailo 오류 등. 무엇을 보낼지 B·A·C 합의 |
| **등록된 로봇 관리** | 🔴 | 로봇 표 없음 | 여러 대를 관리하려면 모든 표에 `robot_id` + RLS 재설계 + Pi 전송 변경 (큰 변경). 지금 구조(1대)에서는 "로봇 정보 카드"(이름·설치일·펌웨어 버전)만 제안 |
| **환자 개인정보 보호 정책** | 🔴 | — | 관리자가 환자 기록을 볼 수 있는지, 보관 기간, 내보내기 허용 여부, 동의 범위. 건강정보는 민감정보 → 지도교수·팀 결정 |

## 4. 제안: 005 마이그레이션 개요 (초안, 적용 안 함)
```sql
-- 관리자 판단 (care_team.role = 'admin')
create function public.is_admin() returns boolean language sql stable security definer set search_path = public
  as $$ select exists (select 1 from public.care_team where user_id = auth.uid() and role = 'admin') $$;

-- 관리자 접근 기록: 쓰기는 함수로만, 읽기는 관리자만, 수정·삭제 정책 없음
create table public.admin_access_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  user_id uuid not null references auth.users(id),
  action text not null,          -- 'view_admin', 'change_role', 'remove_member', 'update_alert_rule' ...
  target text,                   -- 대상 id (환자 기록 내용은 넣지 않음)
  detail jsonb
);
alter table public.admin_access_log enable row level security;
create policy admin_read_log on public.admin_access_log for select to authenticated using (public.is_admin());

-- 관리 RPC (security definer, 첫 줄에서 is_admin() 확인 + admin_access_log 기록)
--   admin_list_members()            → user_id, email, role, added_at, last_sign_in_at
--   admin_set_role(user_id, role)   → 자기 자신의 admin 해제 금지 (관리자 0명 방지)
--   admin_remove_member(user_id)    → care_team에서만 제거 (Auth 계정 삭제는 별도)
--   admin_system_health()           → cron 최근 실행 성공/실패, 표별 행 수·최신 시각, DB 크기
--   admin_log_view(page)            → 관리자 화면 열람 기록
-- alert_rules: 관리자 update 정책 (severity, window_seconds, merge_into_acked, provisional)
```
- 함수마다 `set search_path` 지정 (보안 점검 경고 반영).
- 테스트: `db/test/checks.sql`에 "admin이 아닌 care_team은 0건/거절" 검사 추가.

## 5. 화면 구성 (기존 디자인 재사용)
```
/admin  (관리자만, 아니면 "권한 없음" 안내 후 / 로 이동)
┌ 머리글: 기존과 같음 + "🛠 관리" 칩
├ 상단 타일 4개 (기존 '오늘 요약' 타일):  로봇 연결률(24h) · 미확인 장애 알람 · 오늘 이용 · DB 응답(ms)
├ 카드 그리드 (기존 fcard)
│   🤖 로봇·센서 상태      : Pi·ESP32·센서별 연결/미연동, 24h 연결 막대
│   📶 통신 장애 기록      : disconnected 등 표 (기존 '알람 기록' 표 스타일)
│   🗄 서버·DB 상태        : 응답 시간, 표별 최신 기록, cron 실행 결과(🟡)
│   📊 이용 현황 (7/30/90일): 기존 리포트 막대 표 재사용
│   👥 돌봄팀 계정 (🟡)    : 이메일·역할·마지막 로그인, 역할 변경·해제
│   ⚙️ 알람 규칙 (🟡)      : 심각도·합침 간격, '임시값' 배지
│   🔒 관리자 접근 기록 (🟡): 최근 100건
└ 모바일 375px 한 줄 배치, 버튼 크기·글자 크기는 기존과 같게
```

## 6. 단계
| 단계 | 내용 | 조건 |
|---|---|---|
| 1 | 🟢 기능으로 `/admin` "운영 현황" (읽기 전용) + Mock | 바로 가능. 권한 분리 전이므로 돌봄팀 누구나 열람 가능함을 명시 |
| 2 | 005: `is_admin()`·접근 기록·계정 목록/역할 변경·알람 규칙 → `/admin`을 관리자 전용으로 | 팀 검토 (스키마·RLS 경계 변경) |
| 3 | 계정 초대·재설정 (Edge Function 또는 Supabase 웹 유지) | 3-1 결정 후 |
| 4 | Pi·ESP32 시스템 상태·오류 보고 → 서버 상태·오류 기록 카드 | B·A·C 작업 후 |
| 5 | 여러 로봇 | 필요하다고 결정될 때만 (큰 재설계) |

## 7. 팀에서 정할 것
1. **관리자는 누구인가?** (D만 / 팀원 전원 / 지도교수) 관리자 계정에 2단계 인증(Supabase MFA)을 요구할지.
2. **관리자가 환자 기록을 볼 수 있나?** (운영 정보만 / 집계까지 / 원본까지) — 정하기 전에는 운영 정보만.
3. **접근 기록 범위·보관 기간** (관리 동작만 / 관리자 화면 열람까지, 예: 1년).
4. **계정 초대·재설정 방식**: Supabase 웹 유지(추가 작업 없음) vs Edge Function(서버 코드 추가, service_role은 함수 안에만).
5. **Pi·ESP32가 보낼 시스템 정보·오류 목록** (B·C·A): 대기열 길이, 앱 버전, 디스크, 카메라·Hailo 오류, ESP32 재부팅 등.
6. **로봇 여러 대를 지원할지** (발표·시연 범위 밖이면 1대 유지 권장).
7. 1단계(권한 분리 전 읽기 전용 운영 현황)를 먼저 만들어도 되는지.

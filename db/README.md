# db/ — Supabase(PostgreSQL) 스키마 (담당: D)

설계 설명: [docs/db.md](../docs/db.md) · API 대응: [docs/api.md](../docs/api.md)

## 마이그레이션
`migrations/`의 파일을 **번호 순서대로** 한 번씩 적용한다. 적용된 파일은 수정하지 말고, 바꿀 때는 다음 번호 새 파일.

| 파일 | 내용 |
|---|---|
| `001_schema.sql` | 표, 제약, 트리거 |
| `002_functions.sql` | `report_alert`, `ack_alert`, 서버 자동 규칙, 집계 뷰, `daily_stats` |
| `003_rls.sql` | RLS 켜기, 권한, 정책 |
| `004_realtime_cron.sql` | Realtime(알람·포즈 Broadcast 정책), pg_cron (Supabase 전용) |

적용 방법 (둘 중 하나):
- Supabase Dashboard → SQL Editor에 파일 내용을 붙여 넣고 순서대로 Run.
- `psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f db/migrations/001_schema.sql` … (psql 별도 설치)

적용한 파일 번호는 [docs/decisions.md](../docs/decisions.md) 아래 "DB 적용 기록"에 남긴다 (도구가 기록해 주지 않음).
TODO(D): 파일이 많아지면 Supabase CLI(`supabase/migrations/`, `supabase db push`)로 옮길지 검토.

## 로컬 검증 (Supabase 없이)
`test/000_supabase_stub.sql`이 Supabase의 역할(anon·authenticated·service_role)과 `auth.uid()`만 흉내 낸다.
```bash
createdb pdtest
psql -d pdtest -f db/test/000_supabase_stub.sql
for f in db/migrations/00[123]_*.sql; do psql -d pdtest -v ON_ERROR_STOP=1 -f "$f"; done
psql -d pdtest -f db/test/checks.sql      # ERROR 줄은 "막혀야 정상"인 검사
```
004는 Supabase 전용(`realtime` 스키마, pg_cron)이라 로컬에서 돌리지 않는다.

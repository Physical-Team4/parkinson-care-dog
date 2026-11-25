# dashboard/ 규칙

루트 [CLAUDE.md](../CLAUDE.md)를 먼저 따른다.

- TODO: 대시보드 코드 이관 후, 스택에 맞는 실행·빌드 명령을 여기에 적는다.
- API 명세는 [docs/api.md](../docs/api.md)가 기준. 필드 이름을 바꾸면 문서부터 수정하고 A·B에 알린다.
- 데이터는 Supabase. 스키마는 [db/](../db/)와 [docs/db.md](../docs/db.md). 변경은 `db/migrations/`에 새 번호 파일로 (기존 파일 수정 금지), 새 표는 RLS 정책까지 함께.
- 대시보드는 `SUPABASE_ANON_KEY` + 로그인 세션만 쓴다. **service_role 키 사용 금지** (RLS 우회).
- 알람 확인은 `rpc('ack_alert')`, 7일 카드는 `rpc('daily_stats')`, 자세는 Realtime Broadcast `robot:pose`(private).
- 보호자 연락처·토큰은 `.env`에서만 읽는다. 프론트엔드 번들에는 URL·anon 키 외 비밀 값이 들어가지 않게 할 것.
- 영상은 받지도 보여 주지도 않는다. 자세는 키포인트로만 그린다.

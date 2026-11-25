# dashboard/

보호자·치료사 대시보드 자리입니다. 담당: D 신효섭.

## TODO
- [ ] 기존 대시보드 코드를 이 폴더로 옮기기 (git 이력이 필요하면 `git subtree add` 사용)
- [ ] 기술 스택·실행 방법을 이 README에 적기
- [ ] Supabase 연결: `@supabase/supabase-js` (또는 스택에 맞는 클라이언트) + `SUPABASE_URL`, `SUPABASE_ANON_KEY`
  - 별도 API 서버 없이 Supabase에 직접 접근 (RLS가 권한 처리)
  - 로그인(Supabase Auth) 화면 필요 — 로그인 전에는 데이터가 보이지 않음
- [ ] `environment.yml` 또는 별도 패키지 파일(`package.json` 등)에 의존성 반영
- [ ] [docs/api.md](../docs/api.md)의 대응표대로 기존 `/api/*` 호출을 Supabase 호출로 교체

API 명세: [docs/api.md](../docs/api.md) · DB: [docs/db.md](../docs/db.md)

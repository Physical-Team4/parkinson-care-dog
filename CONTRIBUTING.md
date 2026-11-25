# 기여 규칙 (브랜치·PR)

## 브랜치
- `main`: 항상 Pi/ESP32에 올려서 돌아가는 상태. **직접 push 금지**, PR로만 merge.
- 작업 브랜치: `<종류>/<영역>-<내용>`
  - 종류: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
  - 영역: `vision`, `voice`, `serial`, `esp32`, `dashboard`, `db`, `env`
  - 예: `feat/vision-fall`, `feat/voice-command`, `feat/esp32-rhythm`, `feat/dashboard-alerts`, `docs/serial-protocol`

## PR
- **PR로 merge, 승인 불필요.** 본인이 PR을 열고 바로 merge해도 된다.
- 경계가 겹치는 변경(시리얼 메시지, Supabase 스키마·API)은 **문서부터** 바꾸고, 상대 담당자에게 PR 링크를 알린다 ([docs/team.md](docs/team.md)).
  - 시리얼: [docs/serial-protocol.md](docs/serial-protocol.md) — B(파이)·D(ESP32)·C(F3 명령) 합의
  - API: [docs/api.md](docs/api.md) — D가 명세, A·B는 따름
  - DB: [docs/db.md](docs/db.md), [db/](db/) — D가 최종 결정
- 패키지를 추가하면 `environment.yml`도 같은 PR에서 수정.
- 커밋 전 `pre-commit run --all-files` 통과 (비밀 정보 검사 포함).

## 커밋 메시지
`<종류>(<영역>): <요약>` 예: `feat(vision): 320 입력 낙상 판정 추가`

## GitHub 브랜치 보호 설정 (관리자 1회)
Settings → Branches(또는 Rules → Rulesets) → `main` 대상 규칙:

| 항목 | 값 |
|---|---|
| Require a pull request before merging | ✅ 켜기 |
| Required approvals | **0** |
| Require review from Code Owners | 끄기 |
| Allow force pushes | ❌ 끄기 |
| Allow deletions | ❌ 끄기 |
| Do not allow bypassing the above settings | 선택 (관리자도 PR 강제하려면 켜기) |

무료 플랜 비공개 레포는 브랜치 보호가 적용되지 않을 수 있다 → 그 경우 이 규칙은 팀 약속으로 지킨다.

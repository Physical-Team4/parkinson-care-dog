# PD-Dog — Claude Code 공통 규칙

파킨슨병 환자 재활돌봄로봇. Hiwonder MechDog(ESP32, MicroPython) + Raspberry Pi 5(Python 엣지 서버) + 보호자 대시보드.
Pi ↔ ESP32는 USB 시리얼 케이블 하나. 데이터는 Supabase(PostgreSQL): Pi가 쓰고 대시보드가 읽는다.

**작업 전에 관련 docs 파일을 먼저 읽을 것.** 이 파일에는 항상 지킬 규칙만 있다.
폴더별 규칙: [pi/CLAUDE.md](pi/CLAUDE.md), [esp32/CLAUDE.md](esp32/CLAUDE.md), [dashboard/CLAUDE.md](dashboard/CLAUDE.md)

## 문서 위치

| 필요할 때 | 문서 |
|---|---|
| 부품·전원 | [docs/hardware.md](docs/hardware.md) |
| 핀·포트 배정 | [docs/pinmap.md](docs/pinmap.md) |
| 기능 F1~F7, 모델 | [docs/features.md](docs/features.md) |
| 모델 벤치마크 결과 | [docs/benchmarks.md](docs/benchmarks.md) |
| 환경 세팅, Pi 특이사항 | [docs/setup.md](docs/setup.md) |
| 대시보드 API ↔ Supabase 대응 | [docs/api.md](docs/api.md) |
| DB·RLS·오프라인 대기열 | [docs/db.md](docs/db.md), [db/](db/) |
| Pi ↔ ESP32 메시지 | [docs/serial-protocol.md](docs/serial-protocol.md) |
| 로봇 이동 (마커 길찾기) | [docs/navigation.md](docs/navigation.md) |
| 집 실측 순서 (비전·마커·M0) | [docs/home-test-checklist.md](docs/home-test-checklist.md) |
| 결정 기록 | [docs/decisions.md](docs/decisions.md) |
| 팀 역할·담당 폴더 | [docs/team.md](docs/team.md) |
| 미확정 항목 | [docs/todo.md](docs/todo.md) |

## 폴더
```
pi/        Pi 5 앱 (app/models, views, controllers, services, adapters, config.py), tests/, main.py
esp32/     MechDog MicroPython (controllers, services, drivers, config.py, main.py)
dashboard/ 대시보드 (스택 미확정)
db/        Supabase 마이그레이션 SQL (스키마·RPC·RLS·Realtime)
docs/      상세 문서
```

## 하드웨어 금지 사항
- ESP32: **배터리 3핀(NC·+·−)**, **빈 4핀 커넥터(UART 추정)** 사용 금지.
- Pi: **물리 핀 27·28**(AI HAT+ EEPROM), **GPIO6**(X1200 전원 차단 감지) 다른 용도 금지.
- 미확정 하드웨어 값(포트 1·3 핀 순서·전압, 터치 IO 번호, 레이저 IO)은 **하드코딩 금지**. `esp32/config.py` / `pi/app/config.py`에서만 읽는다. 값이 `None`이면 해당 기능을 끄고 경고.
- 확정 안 된 값을 추측으로 채우지 말 것. TODO로 남기고 [docs/todo.md](docs/todo.md)에 추가.

## 안전·개인정보
- 영상 저장·전송 금지 (프레임은 처리 후 폐기, 대시보드엔 키포인트만).
  예외: 개발용 `pi/scripts/pose_viewer.py --video`만 SSH 터널로 화면 전송 허용, 저장은 여전히 금지 ([D-011](docs/decisions.md)).
- 음성 원본 저장 금지. 화자 임베딩은 Pi 로컬에만 (Supabase에 올리지 말 것).
- 음성 인식·dB 측정은 **서보 정지 상태**에서만 (측정 전 ESP32에 `stop`).
- 레이저는 **기본 꺼짐**, 바닥만 향하게. 눈 높이로 향하는 코드·설정 금지.

## 언어·환경
- Pi: Python. ESP32: MicroPython (Hiwonder 펌웨어). 주석·문서는 한국어 OK.
- 개발 환경은 conda 하나: `conda env create -f environment.yml && conda activate pd-dog`.
- 패키지 추가 시 `environment.yml`도 같이 수정. pip 단독 설치 후 끝내지 말 것.
- ESP32 코드는 conda와 별개로 업로드 ([esp32/README.md](esp32/README.md)). CPython 전용 문법·라이브러리 쓰지 말 것.

## 계층 분리 (MVC 비슷하게)

| 계층 | 함 | 금지 |
|---|---|---|
| models | DB 테이블, 데이터 클래스, 저장·조회 | 하드웨어, HTTP |
| views | API 요청/응답 형식, 시리얼 메시지 형식 | 업무 로직 |
| controllers | API 라우트, 모드 전환, 이벤트 → 서비스 호출 | 계산·판정 로직 |
| services | 낙상·무움직임 판정, dB, 화자 인식, Supabase 전송·재전송 | 하드웨어·DB 직접 접근 (adapters·models 경유) |
| adapters | 시리얼, 카메라, 마이크, X1200, Hailo, 메신저 | 업무 판단 |

- adapters는 `adapters/base.py` 인터페이스를 따르고 mock 구현을 함께 둔다 → 하드웨어 없이 `pytest pi/tests`.
- ESP32도 `controllers`(명령) / `services`(동작) / `drivers`(센서)로 나눈다.

## 민감 정보
- `.env`, API 키, 메신저 토큰, Wi-Fi 비밀번호, 보호자 연락처, DB 파일, 화자 임베딩, 로그는 **커밋 금지**.
- 민감 정보 파일을 만들거나 수정하지 말 것. 값이 필요하면 `.env.example`에 **이름만** 추가하고 `config.py`에서 읽는다.
- 모델 가중치(`*.pt`, `*.onnx`, `*.hef`)는 레포에 넣지 않는다. 받는 방법만 문서화.
- Supabase 키: Pi는 `SUPABASE_SERVICE_ROLE_KEY`(RLS 우회, Pi `.env`에만), 대시보드는 `SUPABASE_ANON_KEY`만. service_role 키를 대시보드·프론트엔드·로그에 넣지 말 것.
- 새 표를 만들면 같은 마이그레이션에서 RLS를 켜고 정책을 작성한다 (`db/migrations/003_rls.sql` 참고).
- 커밋 전 `pre-commit run --all-files` (gitleaks).

## 협업
- main 직접 push 금지. 기능 브랜치 → **PR로 merge, 승인 불필요** (본인이 바로 merge 가능).
- **Claude는 `git push` 전에 반드시 사용자에게 묻는다.** 커밋까지만 하고, push할 브랜치·커밋 목록을 보여준 뒤 허락받으면 push. 한 번 허락은 그 push에만 해당.
- 경계 인터페이스(시리얼 메시지, Supabase 스키마·API)는 **docs 먼저** 바꾸고 상대 담당자에게 알린다.
- Supabase 스키마는 `db/migrations/`에 새 번호 파일로만 바꾼다 (적용된 파일 수정 금지).
- 대시보드 API 필드 이름·주기는 [docs/api.md](docs/api.md) 명세를 그대로 따른다.
- 작업자의 담당 폴더([docs/team.md](docs/team.md)) 밖을 크게 바꿔야 하면 **먼저 알릴 것**.
- 브랜치: `feat/vision-fall`, `feat/voice-command`, `feat/esp32-rhythm`, `feat/dashboard-alerts` ([CONTRIBUTING.md](CONTRIBUTING.md)).

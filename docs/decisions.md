# 결정 기록

형식: `D-번호 | 날짜 | 결정 | 이유 | 상태(확정/예정/보류)`

## D-001 보호자 원격 알림은 Pi 동작 중에만 (확정)
- Pi가 응답 없으면 ESP32가 MP3 경보음으로 현장 경보만 한다.
- ESP32는 하트비트로 Pi 상태를 감시한다 ([serial-protocol.md](serial-protocol.md)).

## D-002 레이저 연결 방법 (예정: 방법 1)

| | 방법 | 필요한 것 | 장점 | 단점 | 상태 |
|---|---|---|---|---|---|
| 1 | ESP32 포트 3을 터치와 공유 (VCC·GND Y자 분기, 터치가 안 쓰는 IO를 레이저 S로) | 남는 키트 4핀 케이블 + 점퍼 3가닥, 납땜·수축튜브 | 추가 구매 없음, F3 박자와 같은 보드라 타이밍 정확, Pi 꺼져도 동작 | 이음 작업, 터치 IO·포트 3 전압 확인 필요 | **채택 예정** |
| 2 | Pi GPIO (핀 4=5V, 14=GND, 12=GPIO18 PWM) | 롱핀 스태킹 헤더 (몸통 8~9mm, 핀 17mm+) | 제어 쉬움 | 맞는 헤더 없음 (시중 10~12mm), HAT 빼면 가능 | 보류 |
| 3 | 빈 4핀 커넥터 / 서보 포트 9~11 | — | — | UART 충돌 가능, 서보 포트는 50Hz 펄스·배터리 전압 | 비추천 |

- 방법 1 코드 예: `from machine import Pin; laser = Pin(<IO>, Pin.OUT); laser.on()` — IO 번호는 `esp32/config.py`의 `LASER_PIN`.
- 레이저 상태는 ESP32 → Pi `status`의 `laser_on`으로 보고 → 대시보드.

## D-003 개발 환경은 conda 하나로 통일 (확정)
- 레포 루트 `environment.yml`. Pi 5는 Miniforge.
- picamera2·hailort 연결 방식은 실기기 확인 후 [setup.md](setup.md)에 기록.

## D-004 DB는 Supabase(PostgreSQL) (확정, 2026-11-26)
- 원본 저장소는 Supabase. Pi의 SQLite는 인터넷 끊김 동안의 대기열 전용.
- RLS 켜기: 대시보드는 anon 키 + 로그인(care_team), Pi는 service_role 키.
- 포즈(0.4초)는 표 저장 대신 Realtime Broadcast (메시지 수 대책은 [todo.md](todo.md)).
- 화자 임베딩은 Supabase에 올리지 않음.
- 상세 [db.md](db.md). (이전 제안: Pi 로컬 SQLite 단독 → 대체됨)

## D-005 Git: PR 필수, 승인 불필요 (확정, 2026-11-26)
- main 직접 push 금지, 기능 브랜치 → PR → 본인이 바로 merge 가능.
- CODEOWNERS 사용 안 함. 브랜치 보호: PR 필수, 승인 0명, force push 금지 ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## D-006 Pi 로봇 코드에는 Docker를 쓰지 않는다 (확정, 2026-11-26)
- Pi 로봇 코드(`pi/`)는 Docker 없이 실행한다.
  - 이유: 카메라·Hailo(PCIe)·USB 시리얼·마이크·I²C를 컨테이너에 연결하기 번거롭고, Pi 5 램 4GB에 부담.
- Pi 환경은 conda로 통일한다 (D-003).
- Docker는 하드웨어와 무관한 곳에서 필요할 때만 쓴다. 예: 대시보드 백엔드, Supabase 로컬 테스트(supabase CLI).

## DB 적용 기록
Supabase에 마이그레이션을 적용하면 여기에 남긴다.

| 날짜 | 파일 | 적용한 사람 | 비고 |
|---|---|---|---|
| | | | |

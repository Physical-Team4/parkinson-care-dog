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
- picamera2·hailort 연결 방식: **방법 A(시스템 dist-packages를 `.pth`로 연결)로 확정** (2026-11-26, Pi 5 trixie).
  picamera2·libcamera·hailo_platform import와 카메라 캡처·Hailo VDevice 동작 확인, numpy는 conda 것 사용.
  방법 B(Pi만 venv)는 쓰지 않음. 상세 [setup.md](setup.md) 2-3.

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

## D-007 conda 환경 Python은 3.13 (확정, 2026-11-26)
- Pi 5 OS가 Raspberry Pi OS Lite (Debian 13 trixie), 시스템 Python 3.13.5로 확인됨.
- `environment.yml`의 `python=3.11` → `python=3.13`. PC·Pi 같은 값.
  - 이유: apt로 설치되는 picamera2·libcamera·hailort(`hailo_platform`)는 시스템 Python용으로 빌드됨.
    conda 환경에서 쓰려면 minor 버전이 같아야 한다 ([setup.md](setup.md) 2-3 방법 A).
- Hailo 모델 변환(DFC)은 이 환경과 별도 (x86 Linux/WSL2, DFC가 요구하는 Python).
- aarch64 + 3.13 전체 설치 확인은 [todo.md](todo.md)에 남김.

## D-008 Pi 배터리는 무보호 플랫탑 18650 (확정, 2026-11-26)
- X1200 v1.2에 **무보호(보호회로 없는) 플랫탑 18650 3000~3500mAh × 2**.
  - 이유: 보호회로 셀은 AI 추론(Hailo)·카메라·서보가 겹치는 순간 고부하에서 보호회로가 과전류로 판단해
    전원을 끊을 수 있다 → Pi 재부팅·SD 손상 위험. 무보호 셀은 순간 전류를 그대로 공급.
  - 플랫탑: X1200 홀더 길이에 맞음 (보호회로 셀은 보통 버튼탑이고 더 길다).
  - 대신 과방전 보호가 셀에 없으므로: 잔량 10% 미만이면 Pi가 스스로 안전 종료 ([setup.md](setup.md) 2-6),
    정품 셀만 사용, 단락 주의, 장기 보관 시 분리.
- 충전은 X1200 USB-C에 Pi 5용 27W PD 어댑터. Pi 본체 USB-C는 사용 안 함.

## D-009 포즈 추론은 AI HAT+ (Hailo-8L)로 한다 (확정, 2026-11-26)
- AI HAT+ 13T(Hailo-8L)를 구매·장착했고 Pi에서 동작 확인 (드라이버·conda 연결·VDevice, [setup.md](setup.md) 2-3).
- F6·F7 포즈 추론은 Hailo에서 돌린다. "CPU 벤치마크 후 사용 여부 결정"은 폐기.
- 남은 일: Hailo-8L용 포즈 모델 `.hef` 준비([todo.md](todo.md))와 FPS·지연 측정 (0.4초 주기 충족 확인).
- CPU 추론은 PC 개발·테스트용으로만 (Pi 운영 경로 아님).

## D-010 pose 모델은 n에 한정하지 않고 벤치마크로 선택, 기본 입력 640 (확정, 2026-11-26)
- 이전 안 "YOLO11n-pose, 입력 320 / 의심 시 640"은 CPU 추론 기준이었다 → Hailo-8L 사용(D-009)으로 대체.
- 후보: n·s·m 크기. Model Zoo의 hailo8l 기성 pose 모델(yolov8s_pose, yolov8m_pose 등)로 시작하고,
  YOLO11·YOLO26은 hailo8l `.hef`가 있거나 DFC 변환이 되면 비교에 넣는다.
- 기준: **초당 10프레임 이상 중 누운 자세 인식이 가장 좋은 모델** (낙상 감지는 5~10fps면 충분).
  칩에 다 안 들어가 나눠 실행되는 모델, 전력·발열이 큰 모델은 벤치마크 결과로 판단.
- 입력 크기는 `.hef`에 고정되므로 **기본 640 하나** (320/640 전환용 `.hef` 두 개는 쓰지 않음).
- F6·F7은 규칙 기반. 학습(파인튜닝 또는 보조 "넘어진 사람" 검출 모델)은 카메라 각도·거리 조정 후에도
  누운 자세를 자주 놓칠 때만 검토. 상세 [features.md](features.md#f6f7-비전-계획), 결과 [benchmarks.md](benchmarks.md).

## D-011 개발 중 pose 확인용 영상 전송은 예외로 허용 (확정, 2026-11-26)
- "영상 저장·전송 금지"의 예외. pose 인식이 되는지 노트북에서 카메라 화면 + 뼈대로 직접 보기 위해.
- 범위는 `pi/scripts/pose_viewer.py`(개발용 뷰어) 하나로 한정:
  - `--video`를 직접 켰을 때만 화면을 보낸다. 기본은 키포인트만.
  - Pi에서 `127.0.0.1`에만 열고 SSH 터널(`ssh -L`)로만 본다. 외부·같은 와이파이 기기에서 직접 접속 불가.
  - 디스크 저장 없음 (메모리에 최신 1장만, 다음 프레임이 덮어씀). 녹화·스크린샷 기능을 넣지 않는다.
  - 앱 본체(`pi.main`)·대시보드·Supabase 경로에는 넣지 않는다. 운영에서는 기존 규칙 그대로 (키포인트만).
  - 화면에 찍히는 사람은 동의한 팀원만. 환자 시연·실사용 때는 쓰지 않는다.
- 제안: A. 팀 공지 필요.

## D-012 로봇 이동은 마커 길찾기로 한다 (제안, 2026-11-27)
- 담당 A. SLAM·지도 작성 대신 벽에 붙인 ArUco 마커와 마커 연결표(설정 파일)로 길목만 따라간다.
- 판단(마커·사람 인식, 경로, 상태 전환)은 Pi, 안전 반사(앞 초음파 정지, 명령 유효시간 지나면 정지, 넘어짐)는 ESP32.
- 이유: 작은 4족 로봇 + Pi 5에서 라이다·SLAM은 무겁고, 집에서는 길목 몇 개만 알면 충분하다.
- 확정 조건: M0 실측(제자리 회전, 초음파·IMU, 마커 인식 거리)과 시리얼 메시지 C·D 합의. 상세 [navigation.md](navigation.md).

## DB 적용 기록
Supabase에 마이그레이션을 적용하면 여기에 남긴다.

| 날짜 | 파일 | 적용한 사람 | 비고 |
|---|---|---|---|
| 2026-11-26 | 001~004 | D (Claude Code, Supabase MCP) | 클라우드 프로젝트 `pd-dog` (서울 ap-northeast-2, 무료 플랜) 새로 생성. 004는 Realtime 초기화(첫 클라이언트 접속) 뒤에 적용해야 `realtime.messages`가 있음. 테스트 계정 1개(care_team guardian)·테스트 데이터 있음 → [dashboard/progress.md](../dashboard/progress.md) |

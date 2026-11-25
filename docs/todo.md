# 미확정 항목

확정되면 이 표에서 지우고 [decisions.md](decisions.md)에 결정 기록을 남기세요.
미확정 값은 코드에 하드코딩하지 말고 설정(`esp32/config.py`, `pi/app/config.py`, `.env`, `alert_rules` 표)으로 둡니다.

## D와 정할 것 (DB·API)

| 항목 | 현재 상태 | 영향 |
|---|---|---|
| settings 키 이름 | 원래 명세의 JSON 키 확인 필요. 지금은 DB 컬럼 이름(`medication_times`, `target_bpm`, `target_db`, `follow_limit_cm`) 가정 | `fetch_settings()`, 대시보드 |
| 알림 합침 기준 | 제안: 같은 source 최근 알람의 `occurred_at`부터 창 안이면 합침. 낙상류는 확인 안 된 알람에만, "N분에 1번"류는 확인된 알람에도 | `report_alert()` |
| 과열·연결 끊김 알람 심각도 | 임시 warning, 재알림 5분 (`alert_rules.provisional=true`) | `alert_rules` 값만 수정 |
| F5 인식 성공률 정의 | 지금은 `accepted / 전체 시도`. 정답 화자를 모르므로 오인식 미반영 → B와 합의 | `daily_speaker` |

## Supabase 관련

| 항목 | 현재 상태 | 담당 | 영향 |
|---|---|---|---|
| 포즈 Broadcast 메시지 수 | 24시간 0.4초 전송 시 월 약 650만 건 → 무료 한도 초과 가능. 시청 중일 때만 / 상태 변화 시만 보내기 중 선택 | A·D | [db.md](db.md#포즈-realtime-broadcast-검토-결과) |
| Supabase 요금제 | 무료 플랜은 1주 미사용 시 프로젝트 일시정지 가능, DB 500MB 등 → 시연 일정에 맞춰 확인 | D | 운영 |
| 대시보드 로그인 방식 | Supabase Auth (이메일 초대 제안), 공개 가입 끄기 | D | RLS (`care_team`) |
| 004 적용 확인 | Realtime 정책·pg_cron은 Supabase에서만 확인 가능 | D | 첫 적용 때 |
| 화자 임베딩 저장 위치 | Supabase에 올리지 않음(Pi 로컬). SQLite는 대기열 전용이므로 파일(예: `~/pd-dog-data/speakers/`) 등 B가 결정 | B | F5 |
| Pi 시계 | 대기열 알람은 Pi `occurred_at` 사용 → NTP 필수. 오프라인 부팅 시 Pi 5 RTC 배터리 필요 여부 | B | 알람 시각 |

## 하드웨어·환경

| 항목 | 현재 상태 | 담당 | 영향 |
|---|---|---|---|
| ESP32 포트 1(IIC2) 핀 순서·VCC 전압 | 멀티미터 확인 예정 | C | VL53L1X 배선 |
| ESP32 포트 3 핀 순서·VCC 전압 | 확인 예정 | D | 터치, 레이저 방법 1 |
| 터치 센서가 쓰는 IO (IO32/IO33) | 확인 예정 | D | `TOUCH_PIN`, 레이저 IO |
| 레이저 연결 방법 | 방법 1(포트 3 공유) 채택 예정 | C·D | [decisions.md](decisions.md) D-002 |
| ESP32 내장 Wi-Fi 사용 가능 여부 | `import network` 테스트 예정 | D | Pi 꺼짐 시 알림 경로 |
| AI HAT+ 사용 여부 | CPU 벤치마크 예정 | A | `hailo` adapter, conda 연결 |
| 대시보드 기술 스택 | 대시보드 README 확인 필요 | D | Supabase 클라이언트 |
| Pi OS 버전·Python 버전 | `python3 --version` 확인 필요 | B | `environment.yml` python 고정값 |
| conda에서 picamera2·hailort import 가능 여부 | 실기기 확인 필요 | A·B | [setup.md](setup.md) |
| 시리얼 baud·메시지 형식 | 초안 작성됨 | B·D | [serial-protocol.md](serial-protocol.md) |
| 보호자 메신저 종류 (Telegram 등) | 미정 | D | `.env` 변수, notifier adapter |
| 라이선스 | 미정 | 전원 | `LICENSE` |
| X1200 `PSU_MAX_CURRENT=5000` | 위키 재확인 필요 | D | Pi EEPROM |

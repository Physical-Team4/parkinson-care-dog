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
| 004 적용 확인 | 로컬 Supabase에서는 확인됨. 클라우드 첫 적용 때 pg_cron 확장 켜져 있는지 확인 | D | 첫 적용 때 |
| 화자 임베딩 저장 위치 | Supabase에 올리지 않음(Pi 로컬). SQLite는 대기열 전용이므로 파일(예: `~/pd-dog-data/speakers/`) 등 B가 결정 | B | F5 |
| Pi 시계 | 대기열 알람은 Pi `occurred_at` 사용 → NTP 필수. 오프라인 부팅 시 Pi 5 RTC 배터리 필요 여부 | B | 알람 시각 |

## 하드웨어·환경

| 항목 | 현재 상태 | 담당 | 영향 |
|---|---|---|---|
| ESP32 포트 1(IIC2) 핀 순서·VCC 전압 | 멀티미터 확인 예정 | C | VL53L1X 배선 |
| MP3 모듈 I²C 버스 | pinmap은 IIC1(포트 2). F3 테스트에서는 IIC2로도 재생됨 → 실제 연결 포트 확인 | C·D | `MP3_I2C_BUS` |
| F3 박자음 트랙 번호 | SD 카드에서 박수 소리 트랙 확인 필요 (테스트 때 30 사용) | C·D | `MP3_TRACK_BEAT` |
| ESP32 포트 3 핀 순서·VCC 전압 | 확인 예정 | D | 터치, 레이저 방법 1 |
| 터치 짧은 톡 의미 충돌 | `esp32/mainboard.py`(C)는 톡 = 박자 보행 시작/정지, `esp32/services/touch.py`(D)는 톡 = 복약 확인·3초 = SOS. 같은 센서(IO33) → 하나로 합칠 때 규칙 합의 필요 | C·D | F1·F2·F3 |
| 터치 최소 시간 `TOUCH_MIN_TAP_MS` | 잠정 80ms. 실측(2026-11-26, D): 1차 정상 톡 100ms 이상·스침 53ms, 2차 무시된 접촉 19~72ms(7번). 60~72ms가 의도한 톡인지 → 어르신 사용 테스트로 재확인 | D | F1 오인식·누락 |
| 레이저 연결 방법 | 방법 1(포트 3 공유) 채택 예정 | C·D | [decisions.md](decisions.md) D-002 |
| ESP32 내장 Wi-Fi 사용 가능 여부 | `import network` 테스트 예정 | D | Pi 꺼짐 시 알림 경로 |
| Model Zoo hailo8l pose 모델 벤치마크 | yolov8s_pose, yolov8m_pose 등으로 FPS·지연·누운 자세 인식·전력 측정 → [benchmarks.md](benchmarks.md). 10fps 이상 중 가장 정확한 모델 선택 (D-010) | A | `hailo` adapter, F6·F7 |
| Model Zoo 버전 (HailoRT 4.23) | 공식 대응표 없음. `download_models.sh --probe`로 열리는 버전 확인 후 [setup.md](setup.md) 2-3-2에 기록 | A | `.hef` 출처 |
| pose 검출 점수·NMS 임계값 | 임시 0.5 / 0.7 (`pi/app/config.py`). 누운 자세 측정 후 조정 | A | `hailo` adapter |
| picamera2 채널 순서 | `BGR888` = numpy RGB로 가정 (picamera2 문서). Pi에서 빨간 물체로 확인 필요 | A | 모델 입력 색 |
| 카메라 각도·거리 조정 테스트 | 학습 전에 카메라 각도, 사용자 거리 2~3m, 입력 해상도로 누운 자세 인식률 확인 ([features.md](features.md#f6f7-비전-계획)) | A | F6·F7, 카메라 장착 위치 |
| F6·F7 판정 임계값 | 하강 속도·몸통 각도·누운 지속 시간, 무움직임 N분·이동량 임계값 → 실측 후 `pi/app/config.py` | A | F6·F7 |
| 로봇 이동 모드 목록 | F7은 이동 중 모드에서 누적 중단. 지금 프로토콜 이동 모드는 `walking`뿐. `approaching` 등 추가되면 [serial-protocol.md](serial-protocol.md) `mode`와 `pi/app/config.py` 목록에 같이 반영 | A·C·D | F7 |
| 대시보드 기술 스택 | 이관 완료(2026-11-26): 지금은 Python 서버 + 정적 HTML + SQLite. Supabase 직접 연결로 바꿀 때 프론트 방식(정적 HTML + supabase-js CDN / 빌드 도구) 결정 | D | Supabase 클라이언트 |
| environment.yml 새 패키지의 aarch64 + Python 3.13 설치 | 지금 목록은 Pi에서 설치 확인됨 (2026-11-26). 앞으로 추가할 패키지(onnxruntime, ultralytics 등)는 추가할 때 Pi에서 `conda env update` 확인 | A·B | `environment.yml` |
| YOLO11·YOLO26 pose의 hailo8l `.hef` | 기성 `.hef` 존재 여부 확인. 없으면 DFC 변환 환경 준비 (x86 Linux/WSL2, 공용 conda와 분리, 대상 `hailo8l`) | A | F6·F7, [setup.md](setup.md) 2-3-1 |
| 시리얼 baud·메시지 형식 | 초안 작성됨 | B·D | [serial-protocol.md](serial-protocol.md) |
| 보호자 메신저 종류 (Telegram 등) | 미정 | D | `.env` 변수, notifier adapter |
| 라이선스 | 미정 | 전원 | `LICENSE` |
| X1200 `PSU_MAX_CURRENT=5000` | 위키 재확인 필요 | D | Pi EEPROM |
| X1200 v1.2가 GPIO6 외에 쓰는 핀 | 미확정 (충전 제어 핀 등). 위키·회로도 확인 후 [pinmap.md](pinmap.md)에 기록 | D | Pi GPIO 배정 |
| X1200 GPIO6 극성 | 충전기 연결 시 0/1 실측 → `.env` `X1200_PLD_POWER_OK_LEVEL` ([setup.md](setup.md) 2-6) | D·B | `pi_charging`, 전원 차단 감지 |
| X1200 잔량 칩 값 | SOC(0x04)·VCELL(0x02) 형식이 맞는지 멀티미터 전압과 비교 | D·B | `pi_battery_pct` |
| 충전 중 여부 | 지금 `pi_charging` = 충전기 연결 여부 (실제 충전 중인지와 다를 수 있음, 만충 후에도 true) | D | 대시보드 표시 |
| 외부 전원 차단 시 종료 여부 | 로봇은 평소 배터리로 주행 → 충전기 뽑을 때마다 종료되면 안 됨. 기본 꺼짐(`PI_SHUTDOWN_ON_POWER_LOSS=false`), 팀 합의 필요 | D·B | `services/power.py` |
| Pi 안전 종료 잔량 기준 | 임시 10% (5~10% 사이). 부하 테스트 결과로 `pi/app/config.py` 조정 | D·B | 종료 시점 |
| AI 추론 중 부하 테스트 | Hailo 추론 + 카메라 + 서보 동작 상태로 10~20분, `vcgencmd get_throttled`로 저전압(0x50005 등) 확인, 잔량 감소 속도 기록 | A·D | 전원, 배터리 정책 |
| ESP32 `pi_low` 처리 | 플래그만 세움. MP3 트랙(`MP3_TRACK_PI_LOW`)·경보 모드 전환 구현 필요 | D | F1·F2 경보 |

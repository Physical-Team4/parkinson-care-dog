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
| 포즈 Broadcast 메시지 수 | 24시간 0.4초 전송 시 월 약 650만 건 → 무료 한도 초과 가능. **대시보드는 자세 보기를 열었을 때만 구독하도록 바꿈 (2026-11-26).** Pi(A)가 "보는 사람 있을 때만" 보내려면 Presence 정책(`realtime.messages` presence insert/select) 마이그레이션 필요 → A·D 합의 | A·D | [db.md](db.md#포즈-realtime-broadcast-검토-결과), dashboard/progress.md |
| Supabase 요금제 | 무료 플랜은 1주 미사용 시 프로젝트 일시정지 가능, DB 500MB 등 → 시연 일정에 맞춰 확인 | D | 운영 |
| 대시보드 로그인 방식 | Supabase Auth (이메일 초대 제안), 공개 가입 끄기 | D | RLS (`care_team`) |
| 004 적용 확인 | 클라우드 `pd-dog`에 적용함 (2026-11-26). pg_cron 동작 확인(연결 끊김 알람 생성). 새 프로젝트는 Realtime이 첫 접속 뒤 초기화돼야 004가 성공 | D | 완료 |
| 대시보드 → 로봇 명령 통로 | 리듬 큐잉 원격 시작/정지 통로 없음 (설정값만 DB로 전달). 대시보드는 인터페이스+Mock만 있음. 방식(명령 표 + Pi 조회 / Broadcast) 과 안전 조건 합의 필요 | B·C·D | F3, dashboard/progress.md |
| Pi 대기열 상태 보고 | 대시보드에 "동기화 대기 N건"을 보이려면 Pi가 `outbox` 길이를 status에 보내야 함 (`robot_status`에 컬럼 추가 필요) | B·D | 오프라인 표시 |
| 복약 요일·Pi 설정 반영 | `medication_schedule`에 요일 없음 (요청됨). 추가 시 Pi `fetch_settings`·ESP32 F1도 수정. Pi가 설정을 부팅 때만 가져옴 → 변경 반영 주기 결정 (B) | B·D | F1 |
| Supabase 보안 점검 경고 | 트리거 함수 3개 `search_path` 미지정(경고), 유출 비밀번호 검사 꺼짐(Auth 설정). 나머지 경고는 설계상 의도 | D | 005 마이그레이션 후보 |
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
| F6·F7 판정 임계값 | 구현됨, 값은 임시 (`pi/app/config.py`의 `fall_*`·`no_motion_*`·`vision_*`). 뷰어로 서기·앉기·눕기·넘어짐(매트) 연기하며 조정 | A | F6·F7 |
| F6 알려진 한계 | 카메라 방향으로 누움(몸통 짧게 보임), 엉덩방아 낙상(앉음으로 끝남), 로봇 보행 중 카메라 흔들림 → 실측 후 대응 결정 | A | F6 |
| `lying_only` 알람 | 눕는 과정을 **못 본** 경우만 60초 후 알람 (본 경우는 엉덩이 높이로 느린 낙상/스스로 눕기 구분). 낮잠 오알람 가능성 남음 → 가구 검출·확인 질문으로 보완 | A | F6 오알람 |
| 느린 낙상 엉덩이 기준 | 엉덩이 하강 0.5×몸통 길이, 기준 자세 유지 5초 → 소파 눕기·의자 미끄러짐·서서 무너짐을 매트 위에서 연기해 조정 | A | F6 |
| 확인 질문 ("괜찮으세요?") | 2026-11-27 A 결정: **터치 응답은 쓰지 않음**, **밤(요 위 잠)에 작은 소리로 묻는 것도 안 함**. 낮 F7 무움직임 등에 음성 응답으로만 쓸지는 미정 | A·B·D | F6·F7 오알람 |
| 취침 선언 입력 | 판단 로직은 구현됨 (`VisionMonitor.set_sleep_mode`). 입력: 음성 "잘게"(B) 또는 대시보드 버튼(D) → controller가 호출. 시험은 pose_viewer 버튼 | A·B·D | 요 위 잠 오알람 |
| 밤 카메라 | 지금 카메라(일반형)는 어두우면 사람을 거의 못 찾음 → 밤 낙상(자다 깨서 쓰러짐) 감지 불가. NoIR 카메라 + 적외선 조명 또는 취침등 → 팀 결정 | A·전원 | F6·F7 밤 동작, 하드웨어 |
| 잠자리 마커 | 구현됨 (`SLEEP_MARKER_IDS`·`SLEEP_HOURS`). 집에서: 마커 붙일 위치(가려지지 않게), 근처 범위(`sleep_marker_margin`) 실측. 취침 시간대를 대시보드에서 정하려면 D와 협의 | A·D | F6 "발견 시 이미 누움" 판단 |
| 취침 시간대 설정 | 잠자리 마커·F7과 함께 사용. 대시보드 설정이면 DB 변경 필요 | A·D | F6·F7 |
| 로봇 이동 (마커 길찾기) | 설계 초안 [navigation.md](navigation.md), D-012 제안. 다음: M0 실측(§11, 스크립트 `esp32/m0/`, `pi/scripts/marker_test.py`), `nav_move`·`nav_stop` 시리얼 메시지 C·D 검토 | A·C·D | 이동, 카메라 공유(이동 중 마커 / 도착 후 사람) |
| MechDog 배터리 전압 읽기 | 공식 시리얼 `CMD|6|$`(mV)는 사용 금지 프로토콜. Python API 확인 → `dog_battery_pct` (6.4V=0%, 8.4V=100%, `esp32/config.py`) | D | 대시보드 배터리 |
| `robot_tipped` 임계값 | IMU `read_angle()` 기울기(X·Y)로 판단. M0 `sonar_imu_test.py`로 측정 후 `esp32/config.py` | C·D | 넘어짐, 이동 안전 정지 |
| `move()` 범위 밖 각도 | 위키 범위 -30~30, 원본 코드는 ±40·±50 사용 → 잘림/오류 확인 (M0) | A·C | 걷기 값 |
| E-FPDS (넘어진 사람 데이터셋) | 바닥에 쓰러짐 vs 쓰러지지 않음(소파·침대에 누움 포함) 2클래스, 6,982장. 공식 페이지에 라이선스 없음 → 저자 문의 후 사용. 제공 가중치는 YOLOv3 → YOLOv8 재학습 + DFC 변환 필요. pose 모델이 누운 사람을 잘 못 잡을 때 검토 | A | F6 보조 모델 |
| 가구 검출 확인 | `MZ_VERSION=v2.20.0 bash pi/scripts/download_models.sh yolov8s` → `python -m pi.scripts.furniture_check --inspect`(출력 형식 확인) → `--seconds 20`을 로봇 위치·각도별로. 사람이 person(0)으로 잡히는지로 종류 번호 확인. 결과로 본격 구현 여부 결정. pose와 같이 쓰려면 VDevice 공유 필요 | A | F6 "발견 시 이미 누움" |
| 가구 검출 (bed·couch) | 눕는 과정을 못 본 경우 바닥/소파 구분용 COCO 검출 모델(hailo8l yolov8s). 낮은 카메라 시점에서 인식되는지 확인 필요 | A | F6 |
| 여러 사람이 보일 때 | 구현됨 (사람별 추적·F6, 2명 이상이면 F7 멈춤). 남은 것: 겹침·엇갈림 때 번호 뒤바뀜 실측, 대시보드에 여러 명 표시가 필요하면 api.md 변경(D와 협의). 환자 본인 구분(얼굴 등)은 하지 않음 | A·D | F6·F7 |
| 비전 루프 main.py 연결 | `VisionMonitor`를 카메라·Hailo와 메인 루프에 연결, 0.4초 포즈 전송. `main.py`는 B 담당 → 먼저 알리고 진행 | A·B | F6·F7 동작 |
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
| AI 추론 중 부하 테스트 | 배터리 2개를 따로 본다. **Pi(X1200)**: Hailo 추론 + 카메라 + 마커 인식 10~20분, `vcgencmd get_throttled` 저전압(0x50005 등)·X1200 잔량 감소 속도. **MechDog(LiPo)**: 걷기 시간당 잔량 감소 (서보는 Pi 배터리와 무관) | A·D | 전원, 배터리 정책 |
| 마이크 입력 볼륨 | 원인 확인됨 (2026-11-27): ALSA Mic Capture Volume이 낮았음 → 80% + `sudo alsactl store` ([setup.md](setup.md) 2-7). B 쪽 Pi에서도 같은 설정 적용·확인. 녹음 후 숫자 증폭은 쓰지 않음 | B | 음성 명령, F4, F5 |
| 마이크 거리별 인식 | 30cm 목소리·잡음 차이 약 20dB(양호). 1~2m는 예상 5~15dB로 부족할 수 있음 → 1m·2m 실측 + Vosk 인식률 시험. 부족하면 ① 마이크를 팬·서보에서 떨어뜨리기 ② 원거리용 마이크(회의용 USB·마이크 배열) ③ 음성 명령 때 로봇이 1m 안으로 다가가기 | B (+A 이동) | 음성 명령, 장비 |
| F4 dB 보정 순서 | 입력 볼륨(80%)을 고정한 **뒤에** 소음계로 `calibration_offset_db` 결정. 볼륨을 바꾸면 다시 보정 | B | F4 발성 훈련 |
| ESP32 `pi_low` 처리 | 플래그만 세움. MP3 트랙(`MP3_TRACK_PI_LOW`)·경보 모드 전환 구현 필요 | D | F1·F2 경보 |

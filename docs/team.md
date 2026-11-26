# 팀 역할 (변경될 수 있음)

| 팀원 | 장비 | 영역 | 담당 기능 | 주 작업 폴더 |
|---|---|---|---|---|
| A 김세광 | Pi 5 + AI HAT+ + 마이크 + 카메라 | 영상 | F6 낙상 감지 (pose 모델 벤치마크·선택, 필요 시 파인튜닝 또는 보조 검출 모델), F7 무움직임 | `pi/app/services/vision/`, `pi/app/adapters/camera.py`, `hailo.py` |
| B 우지현 | Pi 5 + 마이크 + 카메라 | 음성 + Pi 통합 | VAD·Vosk 음성 명령, F5 화자 인식, F4 발성, UART(Pi 쪽) | `pi/app/services/voice/`, `pi/app/adapters/microphone.py`, `esp32_serial.py`, `pi/main.py` |
| C 김정윤 | ESP32 + ToF + 레이저 | 리듬 큐잉 | F3 박자 보행, 레이저 연동, ToF 추적·속도 | `esp32/services/rhythm.py`, `gait.py`, `esp32/drivers/vl53l1x.py`, `laser.py` |
| D 신효섭 | ESP32 + ToF + 레이저 | 알림·안전·전원 + 대시보드 | F1, F2 + 메신저, 배터리 감시·종료 신호, UART(ESP32 쪽), 전원, 대시보드 | `esp32/controllers/`, `esp32/services/medication.py`, `touch.py`, `dashboard/`, `db/` |

## 경계 인터페이스 (먼저 합의)

| 경계 | 문서 | 정하는 사람 |
|---|---|---|
| Pi ↔ ESP32 시리얼 | [serial-protocol.md](serial-protocol.md) | B + D (C의 F3 명령 포함) |
| 로봇 → Supabase (대시보드 API 대응) | [api.md](api.md) | D가 명세, B(status)·A(pose·낙상)가 따름 |
| Supabase 스키마·RLS | [db.md](db.md) | D 최종 결정, A·B·C는 필요한 항목 요청 |

Claude Code 사용 시: 담당 폴더 밖을 크게 바꿔야 하면 작업 전에 먼저 알릴 것.

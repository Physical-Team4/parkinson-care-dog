# parkinson-care-dog (PD-Dog)

파킨슨병 환자 재활돌봄로봇. Hiwonder MechDog(ESP32) 위에 Raspberry Pi 5를 얹어
복약 알림, 위급 신고, 리듬 큐잉 보행, 발성 훈련, 낙상 감지를 합니다.

```
[보호자/치료사 대시보드] ←→ [Supabase] ←→ [Raspberry Pi 5 (엣지, pd-dog)]
                                        │ USB (A→C, 시리얼)
                                        ▼
                                [MechDog ESP32]  → 서보 8개, 센서
```

| ID | 기능 | 위치 |
|---|---|---|
| F1 | 복약 알림 (타이머 + 터치, 30분 미확인 시 보호자 알림) | ESP32 (+ Pi 전송) |
| F2 | 위급 신고 (터치 3초 / "도와줘") | ESP32 + Pi |
| F3 | 리듬 큐잉 보행 (80~110 BPM, 박자음 + 레이저, ToF 대기) | ESP32 + Pi 음성 |
| F4 | 발성 훈련 (dB 측정) | Pi |
| F5 | 사용자(화자) 인식 | Pi |
| F6 | 낙상 감지 (YOLO pose) | Pi + AI HAT+ |
| F7 | 무움직임 확인 | Pi |

## 폴더

| 폴더 | 내용 |
|---|---|
| [pi/](pi/) | Raspberry Pi 5 Python 앱 (MVC 계층: models / views / controllers / services / adapters) |
| [esp32/](esp32/) | MechDog MicroPython 코드 (controllers / services / drivers) |
| [dashboard/](dashboard/) | 보호자·치료사 대시보드 (팀원 코드 이관 예정) |
| [db/](db/) | Supabase(PostgreSQL) 마이그레이션: 스키마, RPC, RLS, Realtime |
| [docs/](docs/) | 하드웨어, 핀맵, 기능, API, DB, 시리얼 프로토콜, 결정 기록 |

## 빠른 시작

```bash
conda env create -f environment.yml
conda activate pd-dog
pre-commit install
cp .env.example .env          # 값은 각자 채우기 (커밋 금지)

# 하드웨어 없이 실행·테스트
PD_DOG_MOCK_HARDWARE=true python -m pi.main
pytest pi/tests
```

- Pi 5 세팅, picamera2·Hailo 연결 문제: [docs/setup.md](docs/setup.md)
- ESP32 업로드 방법: [esp32/README.md](esp32/README.md)
- 팀 역할·담당 폴더: [docs/team.md](docs/team.md)
- 브랜치·PR 규칙: [CONTRIBUTING.md](CONTRIBUTING.md)
- 미확정 항목: [docs/todo.md](docs/todo.md)

## 개인정보

영상은 저장·전송하지 않고, 음성은 원본 없이 화자 임베딩만 Pi 로컬에 저장합니다 (Supabase에 올리지 않음).
Supabase는 RLS로 보호되며, 로그인한 보호자·치료사만 데이터를 볼 수 있습니다.
`.env`, Supabase 키, 토큰, DB 파일, 로그, 모델 가중치는 커밋하지 않습니다.

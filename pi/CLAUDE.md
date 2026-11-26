# pi/ 규칙

루트 [CLAUDE.md](../CLAUDE.md)를 먼저 따른다. 여기는 Pi 앱 전용 규칙.

- 실행: 레포 루트에서 `python -m pi.main` (mock: `PD_DOG_MOCK_HARDWARE=true`). 테스트: `pytest pi/tests`.
- 설정은 `app/config.py`의 `Settings`로만 읽는다. `os.environ`을 다른 파일에서 직접 읽지 말 것.
- 하드웨어·외부 연결은 `app/adapters/`에만. 새 adapter는 `base.py`의 Protocol을 구현하고 `mock.py`에 가짜를 추가.
- `services/`는 adapter·model 객체를 생성자로 받는다 (직접 import해서 생성하지 말 것) → 테스트에서 mock 주입.
- 서비스 하위 폴더: `services/vision/`(A: F6·F7), `services/voice/`(B: 명령·F4·F5), `services/sync.py`(공통: Supabase 전송·재전송).
- Supabase로 보내는 알람·기록은 `views/api_schemas.py`의 형식 → `Op` → `SyncService.submit()`. adapter를 직접 부르지 말 것 (대기열을 건너뜀).
- status(2초)·포즈(0.4초)만 대기열 없이 `send_now`. 알람 중복 합치기는 DB의 `report_alert`가 하므로 Pi에서 따로 하지 않는다.
- 로컬 SQLite(`models/outbox.py`)는 오프라인 대기열 전용. 다른 데이터를 저장하지 말 것.
- 알람은 발생 시각(`occurred_at`, timezone-aware UTC)을 반드시 넣는다.
- 대시보드로 보내는 데이터 형식은 `app/views/api_schemas.py`(Supabase), ESP32 메시지는 `app/views/serial_messages.py`. 필드 이름은 [docs/api.md](../docs/api.md), [docs/serial-protocol.md](../docs/serial-protocol.md)와 일치해야 한다.
- 카메라 프레임은 메모리에서 처리 후 버린다. 파일로 쓰지 말 것 (디버그 저장도 커밋 금지 + 기본 꺼짐).
  화면 전송은 개발용 `scripts/pose_viewer.py --video`만 예외 (D-011). `pi.main`에서 import하지 말 것.
- dB 측정·음성 인식 전에 ESP32 `stop`을 보내고 ack를 확인.
- `picamera2`, `hailo_platform`은 Pi에서만 import 가능할 수 있다 → adapter 안에서 지연 import.

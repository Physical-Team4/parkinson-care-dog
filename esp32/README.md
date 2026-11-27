# esp32/ — MechDog MicroPython

Hiwonder MechDog 펌웨어(MicroPython) 위에서 동작. conda 환경과 별개로 보드에 파일을 올린다.

```
main.py          진입점 (모드 루프, 부팅 시 자동 실행)
config.py        핀·주소·타이밍 (미확정 값은 None)
controllers/     시리얼 명령(serial_cmd.py), 하트비트(heartbeat.py)
services/        F3 박자(rhythm.py), 보행(gait.py), F1(medication.py), F2(touch.py)
drivers/         VL53L1X, MP3, 레이저, 터치(touch_pad.py), 눈 RGB(eyes.py)
```

## 업로드 방법

### 방법 1: mpremote (권장, conda 환경에 포함)
```bash
conda activate pd-dog
mpremote connect list                    # 포트 확인 (Windows: COM3 등, Pi: /dev/ttyUSB0)
mpremote connect <PORT> fs ls            # 보드 파일 목록 — 먼저 기존 파일 확인/백업!
mpremote connect <PORT> fs cp -r esp32/controllers esp32/services esp32/drivers :
mpremote connect <PORT> fs cp esp32/config.py esp32/main.py :
mpremote connect <PORT> reset
mpremote connect <PORT> repl             # 출력 보기 (Ctrl-] 종료)
```
- ⚠️ 보드에 이미 있는 `main.py`(Hiwonder 기본 동작)를 덮어쓴다. 처음 한 번은 `mpremote fs cp :main.py backup_main.py`로 백업.
- 포트를 다른 프로그램(Pi 앱, Hiwonder Editor)이 쓰고 있으면 실패한다. 먼저 닫을 것.
- ⚠️ MechDog 펌웨어는 mpremote의 소프트 리셋 중에 멈추고 재부팅될 수 있다 (`Guru Meditation Error`, `could not enter raw repl`).
  → 포트 뒤에 `resume`을 붙여 리셋 없이 실행: `mpremote connect <PORT> resume run test.py` (보드에 저장 안 하고 실행만).
- 업로드 중 펌웨어가 꼬이면: 위키 "MechDog Resources > Firmware Flashing Tool and Firmware"로 복구.

### 방법 2: Hiwonder Python Editor
위키의 Python 강의대로 Editor에서 보드 연결 → 각 파일을 같은 폴더 구조로 업로드.
TODO(D): Editor가 하위 폴더 업로드를 지원하는지 확인. 안 되면 mpremote 사용.

## PC 테스트
보드 없이 로직만 검사 (보드 전용 `utime`은 테스트에서 가짜로 바꿔 끼움). 레포 루트에서:
```bash
pytest esp32/tests          # F1 복약: 시각 도래·터치 확인·30분 미확인·자정 넘김·시계 다시 맞춤
```

## 주의
- USB 시리얼 = REPL 포트 = Pi 통신 포트. 디버그 출력은 `log()`(`#` 접두어)만.
- 레이저는 부팅 시·예외 시 꺼짐. 미확정 핀(`None`)이면 관련 기능 비활성.
- 프로토콜: [docs/serial-protocol.md](../docs/serial-protocol.md)

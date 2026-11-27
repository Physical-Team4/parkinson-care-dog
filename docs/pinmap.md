# 핀맵·포트 배정

⚠️ = 사용 금지. ❓ = 미확정 (코드에서는 설정값으로만 참조).

## MechDog ESP32 (몸통 옆 4핀 포트, 위키 Python 강의 기준)

| 포트 | 버스/핀 | 연결 | 비고 |
|---|---|---|---|
| 포트 1 | IIC2 | VL53L1X (0x29) | JST-PH 2.0 → 이음 → 점퍼 암. ❓ 핀 순서·VCC 전압 |
| 포트 2 | IIC1 (내장 초음파와 같은 버스) | MP3 모듈 | `Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(1))` |
| 포트 3 | IO32, IO33 | 터치 센서 | 터치 = **IO33**, 누르면 0 / 떼면 1, 내부 PULL_UP (2026-11-26 D 확인). IO32는 비어 있음 |
| 내부 포트 | **IO23** (+ 3.62V 핀 1개 미확인) | 레이저 KY-008 (S) | 레이저 = **IO23**, 1 = 켜짐 (2026-11-27 C 핀 찾기 테스트로 확인, D-002). 핀 전압은 [validation/2026-11-26-mechdog-port-validation.md](validation/2026-11-26-mechdog-port-validation.md). ❓ 나머지 핀 용도 |
| 내장 | IIC1 | 발광 초음파 | 앞 장애물, RGB 점멸 |
| Type-C | USB 시리얼 | Pi 5 | MicroPython REPL과 같은 포트 ([serial-protocol.md](serial-protocol.md)) |
| NC·+·− 3핀 | — | ⚠️ 배터리 입력 | 사용 금지 |
| 빈 4핀 커넥터 | UART 추정 (외장 BT 자리) | ⚠️ | USB 시리얼과 충돌 가능 |

- 공식 슬레이브 프로토콜(UART 9600 8N1, `CMD|...|$`)은 포트 3(IO32/33) 전용 → 우리는 사용 안 함. USB 시리얼 명령 처리는 직접 작성.

## Raspberry Pi 5

| 포트/핀 | 연결 |
|---|---|
| USB-A | ESP32 (HDTOP 0.15m) |
| USB-A | USB 핀마이크 |
| CAM/DISP 0 | 카메라 모듈 3 (HAT 장착 전에 FFC 연결) |
| PCIe | AI HAT+ |
| FAN | 액티브 쿨러 |
| 밑면 포고 핀 | X1200 전원 |
| GPIO 2·3 (물리 핀 3·5, I²C1) | X1200 잔량 칩 0x36 |
| ⚠️ GPIO6 (물리 핀 31) | X1200 전원 차단 감지. 다른 용도 금지. 극성은 `.env` `X1200_PLD_POWER_OK_LEVEL` (실측) |
| ❓ X1200 추가 핀 | 충전 제어 등 X1200 v1.2가 쓰는 다른 GPIO 미확정 → 확인 전까지 GPIO 새 배선 금지 ([todo.md](todo.md)) |
| ⚠️ 물리 핀 27·28 | AI HAT+ EEPROM. 사용 금지 |

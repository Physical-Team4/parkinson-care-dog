# 하드웨어 구성

핀·포트 배정은 [pinmap.md](pinmap.md). 구성도 HTML은 `docs/hardware-diagram.html` (TODO: 추가 예정).

## 부품 (확정)

| 부품 | 역할 | 연결 |
|---|---|---|
| Hiwonder MechDog (Advanced) | 본체, ESP32, 서보 8개, IMU(QMI8658), 발광 초음파, 터치, MP3 | — |
| Raspberry Pi 5 (4GB) | 엣지 서버, Raspberry Pi OS Lite, 호스트명 `pd-dog` | — |
| Pi 카메라 모듈 3 | F6, F7 | CAM/DISP 0 (Pi 5용 22↔15핀 FFC) |
| AI HAT+ 13 TOPS (Hailo-8L) | 포즈 추정 가속 (사용 여부 벤치마크 후 결정) | PCIe |
| Pi 5 액티브 쿨러 | 발열 | FAN |
| Suptronics X1200 v1.2 (18650 UPS 5V 5A) | Pi 전원, 잔량 | 밑면 포고 핀, 잔량 칩 I²C 0x36, 전원 차단 감지 GPIO6 |
| 18650 × 2 (무보호, 플랫탑, 3000~3500mAh) | X1200용 | — |
| USB 핀마이크 | 음성 명령, F4, F5 | Pi USB-A |
| HDTOP USB A→C 0.15m | Pi ↔ ESP32 시리얼 | Pi USB-A ↔ ESP32 Type-C |
| VL53L1X ToF (CJMCU-531) | 뒤따라오는 사용자 거리 | ESP32 포트 1 (IIC2), 0x29 |
| 레이저 모듈 (Red) | F3 바닥 점 깜빡임 | **미확정** ([decisions.md](decisions.md) D-002) |
| 점퍼와이어 (24AWG F/F, 26AWG M/F·F/F) | 이음, 예비 | — |

**사용 안 함**: WonderEcho 음성 모듈, 도트 매트릭스, 조도 센서, ESP32-S3 비전 모듈, WiFi 모듈(보류)

## 통신
- Pi ↔ ESP32: USB 케이블 하나 (시리얼). GND만 USB로 공유, 전원은 각자.
- Pi ↔ 대시보드: HTTP.

## 전원
- Pi: 18650 × 2 → **Suptronics X1200 v1.2** → Pi 5 밑면 포고 핀으로 5.1V 5A.
  - 배터리: **무보호 플랫탑 18650 3000~3500mAh × 2**. 보호회로 셀은 AI 추론 같은 순간 고부하에서 보호회로가
    전원을 끊어 Pi가 재부팅될 수 있어 제외 ([decisions.md](decisions.md) D-008).
  - 충전: **Pi 5용 27W PD 어댑터를 X1200의 USB-C**에 연결. **Pi 본체 USB-C는 사용 안 함.**
  - 잔량: I²C 0x36 잔량 칩 → 대시보드 `pi_battery_pct`. 외부 전원 감지: GPIO6 → `pi_charging`.
  - 배터리 부족 시 동작·설정 절차: [setup.md](setup.md#2-6-x1200-ups).
- MechDog: 기본 7.4V 1500mAh LiPo.
- Pi EEPROM: `PSU_MAX_CURRENT=5000` (X1200 위키에서 재확인).
- 추가 적재 약 270~280 g, 보행 테스트 통과.

## 주의
- AI HAT+ 위 헤더는 핀 끝이 소켓 블록과 같은 높이라 점퍼를 꽂을 수 없음 (실물 확인). Pi GPIO 새 배선은 어렵다.
- MechDog 펌웨어 복구: Hiwonder 위키 "MechDog Resources > Firmware Flashing Tool and Firmware".

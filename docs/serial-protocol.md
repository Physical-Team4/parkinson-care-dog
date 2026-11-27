# Pi ↔ ESP32 시리얼 프로토콜 (초안 v0)

> **상태: 초안.** B(Pi 쪽)와 D(ESP32 쪽)가 합의 후 확정. C의 F3 명령 포함.
> 바꿀 때는 이 문서부터 수정하고 양쪽 담당자에게 알린다. 양쪽 코드의 메시지 정의:
> `pi/app/views/serial_messages.py`, `esp32/controllers/serial_cmd.py`.

## 물리 계층
- USB-C (ESP32 쪽 USB-시리얼 칩) ↔ Pi `/dev/ttyUSB0` 또는 `/dev/ttyACM0`. 고정 이름은 udev 규칙으로 (TODO).
- Baud: **115200 8N1** (제안. Hiwonder 펌웨어 REPL 기본값 확인 필요).
- 이 포트는 **MicroPython REPL과 같은 포트**다. 그래서:
  - ESP32 코드에서 `print()` 디버그 출력을 그대로 쓰면 Pi가 메시지로 오해한다 → 디버그 출력은 `#`로 시작하게 하고 Pi는 `#` 줄을 무시.
  - 메시지에 `0x03`(Ctrl-C), `0x04`(Ctrl-D) 바이트를 넣지 않는다 (REPL 인터럽트·리셋). JSON 텍스트는 해당 없음.
  - Pi에서 포트를 열 때 DTR/RTS가 바뀌면 ESP32가 **리셋**될 수 있다 → pyserial에서 `dtr=False`, `rts=False`로 설정 후 open (adapter에 반영).

## 프레임
- 한 줄 = 메시지 하나. UTF-8 JSON + `\n`. 최대 256바이트.
- 공통 필드: `t`(종류, 필수), `id`(정수, 응답이 필요한 명령에만).
- 응답: `{"t":"ack","id":<id>,"ok":true}` 또는 `{"t":"ack","id":<id>,"ok":false,"err":"..."}`.
- 모르는 `t`는 무시하고 `ack ok:false err:"unknown"`.

## Pi → ESP32

| t | 필드 | 설명 | 담당 |
|---|---|---|---|
| `hb` | — | 하트비트, 1초마다 | B |
| `walk` | `bpm` (80~110) | F3 박자 보행 시작 ("출발/걷자") | C |
| `stop` | — | 보행·박자 정지 ("멈춰"). 음성·dB 측정 전에도 보냄 | C |
| `bpm` | `bpm` | 박자 변경 | C |
| `laser` | `on` (bool) | 레이저 강제 켜기/끄기 (기본은 박자 연동) | C |
| `settings` | `med_times` (["HH:MM", ...] 0~8개), `bpm`, `follow_limit_cm`, `now` ("HH:MM:SS", Pi 현지 시각) | 대시보드 설정 전달. 부팅·변경 시. **모든 필드 선택** — 있는 것만 반영. `med_times: []`이면 복약 알림 없음. `now`는 ESP32 시계 맞추기용(ESP32에는 시계가 없음) → 부팅 때 + **10분마다** `{"t":"settings","now":...}`만 보내도 됨 (2026-11-27 추가). Pi 구현 `pi/app/services/settings_sync.py`: ESP32 status가 끊겼다 다시 오면(로봇 재부팅) 바로 전체 재전송, 대시보드 설정은 20초마다 확인해 바뀌면 전송, 인터넷이 끊겨도 시계는 보냄 | D |
| `med_ack` | `due` ("HH:MM") | 음성으로 복약 확인됨. 또 Pi가 이미 확인을 받은 복약을 로봇이 다시 알리면(로봇 재부팅) Pi가 보내 바로 끝냄 | D |
| `sound` | `track` (int) | MP3 재생 | D |
| `pi_low` | `pct` (int) | Pi 배터리 20% 미만 (값은 `pi/app/config.py`). 한 번만 보내고, 회복·충전 후 다시 내려가면 또 보냄. ESP32는 경보 모드 준비 + MP3 안내 (`MP3_TRACK_PI_LOW`) | B·D |
| `shutdown` | `reason` (`"battery"` / `"power_loss"`) | Pi가 곧 안전 종료. 이후 `hb`가 끊기므로 ESP32는 MP3 경보 경로로 (D-001) | B·D |

## ESP32 → Pi

| t | 필드 | 설명 | 주기 |
|---|---|---|---|
| `status` | `mode`, `dog_battery_pct`, `follow_distance_cm`, `laser_on`, `bpm`, `robot_tipped` | Pi가 대시보드 `status`에 합쳐 보냄 | 1초 |
| `touch_sos` | — | F2 터치 3초 | 발생 시 |
| `med_due` | `due` | F1 복약 시간 도래 | 발생 시 |
| `med_ok` | `due`, `method`:"touch" | F1 터치로 확인 | 발생 시 |
| `med_missed` | `due` | F1 30분 미확인 | 발생 시 |
| `gait_end` | `started_ms`, `ended_ms`, `avg_bpm`, `stop_count`, `restart_count` | F3 세션 종료 요약 | 발생 시 |
| `ack` | `id`, `ok`, `err?` | 명령 응답 | — |

- `mode`: `idle` / `walking` / `paused`(ToF 대기) / `medication` / `alarm` / `charging` (초안)
  - `charging` (2026-11-27 추가, D): 대기 중에 전원 전압이 `DOG_BATTERY_MAX_VALID_MV`보다 높음 = 충전기·외부 전원 연결. 이때 `dog_battery_pct`는 `null`.
    우선순위 보행 > 복약 알림 > 충전 > 대기. 멈춰 있는 모드라 F7 누적에는 영향 없음 (이동 모드 아님). 대시보드는 "충전 중"으로 표시.
- F1 복약 (`esp32/services/medication.py`):
  - `now`를 한 번도 못 받았으면 복약 알림을 하지 않는다 (`# warn:` 출력). 시각을 추측하지 않는다.
  - 복약 시각이 되면 `med_due` 1번 + MP3 `MP3_TRACK_MEDICATION`. 시각을 막 맞췄을 때 30분 안에 지난 복약은 바로 알리고, 그보다 오래된 것은 건너뛴다.
  - 대기 중 짧은 터치 → `med_ok`(`method:"touch"`). Pi의 `med_ack`(음성)는 대기만 끝내고 `med_ok`는 보내지 않는다 (Pi가 이미 앎).
  - `MED_CONFIRM_TIMEOUT_MS`(30분) 안에 확인이 없거나 다음 복약 시각이 먼저 오면 `med_missed`. 이때 Pi 무응답이면 MP3 경보.
- `dog_battery_pct`: MechDog 배터리 전압을 2S 기준 약 6.4V = 0%, 8.4V = 100%로 직선 변환 (두 값은 `esp32/config.py`).
  전압은 펌웨어 `Hiwonder.Battery_power()`(mV, 2026-11-27 확인). `DOG_BATTERY_MAX_VALID_MV`(8.9V)보다 높으면 LiPo가 아닌 외부 전원(보조배터리 등)으로 보고 `null` ([mechdog-motion.md](mechdog-motion.md#배터리-전압)).
- `robot_tipped` (`esp32/services/tilt.py`): IMU `read_angle()` 기울기 X(좌우)나 Y(앞뒤)가 `TIP_ANGLE_DEG`(45°) 이상인 상태가
  `TIP_HOLD_MS`(1초) 이어지면 true, 둘 다 `TIP_CLEAR_DEG`(30°) 미만으로 `TIP_CLEAR_MS`(2초) 이어지면 false (잠깐 들거나 부딪힌 것은 무시).
  IMU를 못 쓰면 `null`. IMU는 기울기만 주고 방향(yaw)은 없음. true가 되면 Supabase 트리거가 `robot_tipped` 알람(warning)을 만든다.

## 제안 중 (합의 전, 아직 구현 안 함)
- **로봇 이동** (A, 2026-11-27): `nav_move`(보폭 mm·각도 °·TTL)·`nav_stop`, `nav_blocked`, `status.front_cm`, `mode: navigating`,
  ESP32 안전 규칙(초음파 정지·TTL 정지·기울기 정지). 상세는 [navigation.md](navigation.md) §6. C·D 검토 후 위 표로 옮긴다.

## 하트비트·장애 처리
- ESP32는 `hb`가 **5초**(제안, `esp32/config.py` `PI_TIMEOUT_MS`) 넘게 안 오면 Pi 무응답으로 판단.
  - 이때 `touch_sos`, `med_missed`가 발생하면 MP3 경보음으로 현장 경보 (원격 알림 불가, [decisions.md](decisions.md) D-001).
- Pi는 ESP32 `status`가 3초 넘게 안 오면 대시보드 `esp32_ok=false`.

## 예
```
Pi  → {"t":"walk","id":7,"bpm":96}
ESP → {"t":"ack","id":7,"ok":true}
ESP → {"t":"status","mode":"walking","dog_battery_pct":82,"follow_distance_cm":120,"laser_on":true,"bpm":96,"robot_tipped":false}
ESP → # debug: tof=1203mm      (Pi는 무시)
```

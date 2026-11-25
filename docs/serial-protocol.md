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
| `settings` | `med_times` (["HH:MM", ...] 1~8개), `bpm`, `follow_limit_cm` | 대시보드 설정 전달. 부팅·변경 시 | D |
| `med_ack` | `due` ("HH:MM") | 음성으로 복약 확인됨 | D |
| `sound` | `track` (int) | MP3 재생 | D |
| `shutdown` | — | Pi 배터리 부족으로 종료 예정 | D |

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

- `mode`: `idle` / `walking` / `paused`(ToF 대기) / `medication` / `alarm` (초안)

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

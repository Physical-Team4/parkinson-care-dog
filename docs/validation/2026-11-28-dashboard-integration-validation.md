# 실제 Pi·MechDog ↔ 대시보드 연동 검증 (T0~T3)

- 시험일: 2026-11-28
- 목적: 실제 Raspberry Pi 5와 MechDog(ESP32)의 데이터가 Supabase를 거쳐 대시보드에 정상 표시되는지 확인
- 시험 코드: Pi·ESP32 `6f80917`, 대시보드 `77efd49` (#40 병합 시점)
  - `6f80917` → `77efd49` 사이 `pi/`·`esp32/`·`db/` 변경 없음. 이후 #41(`7d87c79`)은 대시보드 자동 로그인만 바뀜
- 범위: T0~T3만 진행. **T4~T8(설정 변경·복약·SOS·넘어짐·인터넷 끊김)은 진행하지 않음**
- 변경 범위: 이 문서는 검증 기록만 추가한다. 시험 중 기존 코드·DB 설정·공유 DB 데이터는 수정·삭제하지 않았다.

**결론:** 정상 연결 상태에서 Pi → Supabase → 대시보드 표시(연결 상태, ESP32 응답, 모드, 배터리, Pi 온도, 마지막 통신, 설정 전달)는
기대대로 동작했다. 연결이 끊긴 뒤 대시보드의 "로봇 연결 끊김" 표시와 연결 끊김 알람도 10초 안팎에 나왔다.
다만 **ESP32 USB를 분리하면 Pi 앱이 `SerialException`으로 종료**되어 "Pi는 살아 있고 ESP32만 끊긴" 상태(`esp32_ok=false`)를 확인하지 못했고,
**MechDog 충전기 연결이 감지되지 않아** #40의 "충전 중" 표시도 확인하지 못했다. 두 건은 후속 작업으로 분리한다 (6절).

## 1. 시험 환경

| 항목 | 조건 |
|---|---|
| Pi | Raspberry Pi 5, Conda `pd-dog`, `pi/main.py` (`pi/scripts/run.sh`) |
| 로봇 | Hiwonder MechDog Advanced, ESP32에 `esp32/` main 코드 업로드 (기존 `boot.py`·펌웨어 유지) |
| 연결 | Pi USB ↔ MechDog USB, CH340 `1a86:7523`, `/dev/ttyUSB0`, 115200 |
| 비활성 기능 | `TOF_ENABLED=False`, `LASER_PIN=None` (설정 그대로, 켜지 않음) → ToF·레이저 값 null |
| 미장착 | X1200 UPS → `pi_battery_pct`·`pi_charging` null (예상대로), 카메라 미사용 |
| Supabase | 공유 클라우드 프로젝트. Pi는 service_role 키(Pi `.env`), 대시보드는 anon 키 + 로그인 |
| 대시보드 | Windows, `dashboard/server.py --dev-login` (`.env`의 테스트 계정), 브라우저 `127.0.0.1` |
| 로봇 쓰기 | 시험 중 Supabase에 로봇 상태를 쓰는 곳은 이 Pi 한 대 |

## 2. T0 — 자동화 테스트

| 위치 | 명령 | 결과 |
|---|---|---|
| Windows | `node --test` (dashboard) | 22/22 통과 |
| Windows | `python -m unittest -v test_server.py` (dashboard) | 16/16 통과 |
| Pi | `pytest pi/tests esp32/tests` | 144 passed |

## 3. T1 — ESP32 → Pi 시리얼 원본

Pi 앱 없이 시리얼 줄만 읽음.

| 항목 | 결과 |
|---|---|
| `status` 주기 | 약 1초 (`STATUS_INTERVAL_MS=1000`) |
| JSON 오류 | 0 |
| 값 | `mode=idle`, `robot_tipped=false`, `dog_battery_pct` 숫자, ToF·레이저·`bpm` null (비활성 설정대로) |
| 포트 열기 | ESP32가 다시 시작되는 것으로 보임 (`POWERON_RESET` 로그 후 약 6초 뒤 `status` 시작). 2026-11-26 시리얼 검증의 관찰과 같음, 원인 미확정 |

## 4. T2 — Pi 앱 → Supabase → 대시보드

### 4-1. 정상 연결

| 항목 | 기대 | 결과 |
|---|---|---|
| `robot_status` 기록 주기 | 2초 | 1.8~2.1초 ✅ |
| `robot_latest.connected` | true | true ✅ |
| `esp32_ok` | true | 앱 시작 직후 ESP32 재시작 동안 2행 false → 이후 true ✅ |
| `mode` | idle | idle ✅ |
| `pi_temp_c` | 값 | 약 35~40°C ✅ |
| 설정 전달 (`settings`) | DB 설정 → ESP32 | 앱 시작 약 6초 뒤 `med_times`, `bpm`, `follow_limit_cm`, `now` 전송 ✅ |
| 대시보드 화면 | 연결·값 표시 | 라즈베리파이 "응답 중", MechDog 몸 "응답 중", 모드 "대기", 마지막 통신 "방금", MechDog 배터리 %, 데이터 동기화 "정상" ✅ |
| 라즈베리파이 배터리 | X1200 없음 | "측정 안 됨 (X1200 미연결)" ✅ |
| "충전" 줄 | `pi_charging` null | "데이터 없음" ✅ (이 줄은 Pi X1200 충전기 상태. MechDog 충전은 모드·배터리 칸에 표시) |

### 4-2. 배터리 부족 알람

- 배터리가 낮은 상태에서 시작한 1차 시험(약 3분, 87행)에서 `dog_battery_pct`가 **10~35% 사이**로 기록됐다.
- 20% 미만 값이 들어온 시점에 `battery_low` 알람이 생성되어 대시보드 알람 목록·알람음까지 이어졌다 ✅
- 다만 값이 2초 간격 행 사이에서도 크게 오르내렸다 (예: 23 → 10 → 24 → 23 → 15). 6-2 참고.

### 4-3. MechDog 충전 표시 (#40) — 미통과

| 항목 | 기대 | 결과 |
|---|---|---|
| 충전기 연결 | MechDog 충전 후 충전기 연결 (약 15:47) | — |
| `mode` | `charging` | 이후 1분간 30행 모두 `idle` ❌ |
| `dog_battery_pct` | null (충전 중에는 잔량을 모름) | 84~100 숫자 ❌ |
| 대시보드 | 모드 "충전 중", 배터리 칸 "🔌 충전 중" | 표시 안 됨 ❌ |

ESP32는 배터리 전압이 `DOG_BATTERY_MAX_VALID_MV`(8900mV)를 넘을 때만 외부 전원으로 판단한다 (`esp32/drivers/battery.py` `external_power()`).
이번 충전기 연결 상태에서는 이 기준을 넘지 않은 것으로 보인다. 실제 전압(mV)은 `status`에 없고,
포트를 따로 열면 ESP32가 다시 시작되며 실행 중인 앱과 겹쳐서 측정하지 않았다 → **원인 미확정** (6-2).

## 5. T3 — ESP32 분리 → Pi 앱 정지

MechDog 전원을 켠 채로 Pi에서 USB만 분리. 1초마다 `robot_latest`와 미확인 알람을 읽어 기록.

| 시각 | 사건 |
|---|---|
| 15:54:53 | 마지막 `robot_status` 수신 |
| 15:54:54 | USB 분리 (커널 로그 `USB disconnect`) → Pi 앱 종료 (5-1) |
| 15:55:03 | `robot_latest.connected=false` 처음 관측 |
| 15:55:09 | "연결 끊김" 알람 생성 관측 |

| 항목 | 기대 (시험 계획) | 결과 |
|---|---|---|
| ① ESP32 분리 감지 | 3초 안에 `esp32_ok=false`, 대시보드 "MechDog 몸: 응답 없음" (Pi는 "응답 중") | **확인 못 함 ❌** — `esp32_ok=false` 행이 한 번도 기록되지 않음 |
| ② Pi 앱 정지 | 10초 안에 대시보드 "로봇 연결 끊김" | 앱이 ①에서 이미 종료되어 별도 정지 생략. 분리 후 약 9초에 `connected=false`, 대시보드 "로봇 연결 끊김" ✅ |
| 연결 끊김 알람 | 생성 | 분리 후 약 15초 ✅ (pg_cron 10초 주기) |

12:12에 로봇 전원을 꺼서 USB가 끊겼을 때도 같은 종료가 있었다 (재현 2회).

### 5-1. ESP32 USB 분리 시 Pi 앱 종료 (`SerialException`)

| 구분 | 내용 |
|---|---|
| 재현 조건 | `pi/main.py` 실행 중(ESP32와 정상 통신) Pi ↔ MechDog USB 케이블 분리. 또는 MechDog 전원을 꺼서 USB 장치가 사라짐. 2회 모두 재현 |
| 발생 위치 | `pi/app/adapters/esp32_serial.py:41` `read_message()`의 `self._ser.read(...)` → `pi/main.py:82` 메인 루프 `esp32.read_message(timeout_s=0.05)`에서 처리 없이 전파 |
| 오류 | `serial.serialutil.SerialException: device reports readiness to read but returned no data (device disconnected or multiple access on port?)` |
| 기대 동작 | 앱은 계속 실행. `status`가 3초 넘게 안 오면 `esp32_ok=false`로 계속 보고 ([serial-protocol.md](../serial-protocol.md)). 대시보드는 Pi "응답 중" + MechDog 몸 "응답 없음". USB가 다시 연결되면 포트를 다시 열어 통신 복귀 |
| 실제 동작 | 앱이 트레이스백과 함께 즉시 종료 → `robot_status` 기록 중단 → 대시보드는 Pi까지 "로봇 연결 끊김"으로 표시. 이후 Pi 앱을 수동으로 다시 켜기 전까지 앱이 꺼진 동안 서버 규칙에 따라 "연결 끊김" 알람이 약 5분마다 새로 생성됨 |
| 영향 | ESP32만 끊긴 상황과 Pi까지 끊긴 상황을 보호자가 구분할 수 없음. 로봇 전원을 끄거나 케이블이 흔들리면 Pi 쪽 기능(알람 재전송·설정 동기화 등)도 같이 멈춤 |
| 처리 | 이번 작업에서는 코드 수정 안 함 → 후속 작업 (6-1) |

## 6. 후속 작업 (코드 수정 없이 분리)

### 6-1. ESP32 시리얼 끊김 처리 — B (`pi/app/adapters/esp32_serial.py`, `pi/main.py`)
- `read`·`send`에서 `SerialException`(장치 사라짐) 처리, 앱 종료 대신 끊김 상태 유지
- 끊긴 동안 `esp32_ok=false`로 `robot_status` 계속 보고
- 일정 간격으로 포트 재연결 시도, 재연결 후 `settings` 재전송 (`settings_sync`의 ESP32 재시작 처리와 연결)
- 재검증: 이 문서 T3 ① (분리 후 3초 안에 `esp32_ok=false`, Pi "응답 중" 유지, 다시 꽂으면 복귀)

### 6-2. MechDog 충전 감지·배터리 값 흔들림 — D (`esp32/drivers/battery.py`, `esp32/config.py`, #40)
- 충전기 연결 상태에서 `Hiwonder.Battery_power()` mV 실측 → 8900mV 기준이 이 충전기에서 맞는지 확인, 다른 판단 방법 필요 여부 검토
- 배터리 % 흔들림(2초 사이 10%p 이상) 확인: 원시 mV 기록, 평균·필터 필요 여부. `battery_low` 오알람·대시보드 표시에 영향
- 재검증: 이 문서 4-3 (충전기 연결 시 모드 "충전 중", 배터리 칸 "🔌 충전 중")

### 6-3. 참고 — 대시보드 (D)
- Pi 앱이 꺼져 있으면 "연결 끊김" 알람이 약 5분마다 새 행으로 쌓여 미확인 알람 목록이 길어짐 (서버 알람 합침 규칙 `window_seconds=300`). 의도된 재알림인지, 목록에서 묶어 보일지 검토

## 7. 시험 데이터

- 공유 Supabase에 시험 중 생긴 `robot_status` 행과 알람(`battery_low` 1건, "연결 끊김" 여러 건)은 **삭제하지 않았다.** 정리 여부는 D와 합의.
- 로그·키·계정 정보는 레포에 넣지 않았다.

## 8. 미검증

- T4~T8: 대시보드 설정 변경 → 로봇 반영, 복약 알림·터치 확인, 터치 3초 SOS, 넘어짐 알람, Pi 인터넷 끊김 후 대기열 재전송
- ESP32만 끊긴 상태의 대시보드 표시 (6-1 이후)
- MechDog 충전 중 표시 (6-2 이후)
- 대시보드 #41(자동 로그인) 버전에서의 화면 (이번 시험은 `77efd49` + `--dev-login`)

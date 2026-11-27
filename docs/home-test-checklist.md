# 집 실측 체크리스트 (담당 A)

외부에서 만든 F6·F7·마커·가구·이동 코드를 **실제 하드웨어로 확인**하는 순서. 위에서부터 진행하고 칸에 결과를 적는다.
끝나면 이 파일과 아래 "기록할 곳"을 커밋한다. 출력이 이상하면 그대로 복사해서 Claude에게 붙인다.

## 0. 준비

**안전·개인정보 (먼저 읽기)**
- 넘어지는 연기는 **두꺼운 매트 위에서만**, 옆에 한 명이 지켜본다. 무리하지 않는다.
- 화면에 찍히는 사람은 **동의한 팀원만**. `--video` 화면은 **캡처·녹화 금지** (D-011). 스크린샷이 필요하면 `--video` 없이(뼈대만).

**준비물**
- [ ] 매트(또는 이불 여러 겹), 의자, 소파 또는 침대, 요/이불
- [ ] 줄자, 테이프, 각도기(또는 휴대폰 각도 앱)
- [ ] 인쇄한 마커 (1-3 참고), 함께 테스트할 사람 1명 (두 사람 테스트용)

**Pi 준비** (SSH 접속 직후는 `(base)` → 꼭 `pd-dog`)
```bash
cd ~/parkinson-care-dog
conda activate pd-dog
git switch main && git pull
bash pi/scripts/check_pi_env.sh        # 모두 ✅, numpy가 conda 경로
pytest pi/tests -q                     # 전부 passed
cat .env                               # POSE_HEF, CAMERA_HFLIP/VFLIP 확인
```
- [ ] 위 결과 정상 (passed 수: ____ )

**뷰어 켜기** (대부분의 확인에 사용)
```bash
# Pi
python -m pi.scripts.pose_viewer --video --markers
# (AI HAT+ 없는 Pi: 마커만) python -m pi.scripts.pose_viewer --video --markers-only
# 노트북 (새 창, 켜 둔 채로)
ssh -L 8765:127.0.0.1:8765 jjjkk24@<pi 주소>
# 브라우저: http://localhost:8765
```
- 사람 이름표: `P1 서 있음`, `★` = 대시보드·F7 기준인 사람, `·쉼` = 쉬는 중, `·잠자리`
- 패널: 판정 상태, 안 움직인 시간, 취침 선언 버튼, 알람 목록(전송 안 함), 마커
- **카메라 가리기** = 손으로 렌즈를 덮어 "로봇이 못 본 상황"을 만든다 (2초 넘게 가리면 놓친 것으로 처리)

---

## 1. 비전 (F6 낙상·F7 무움직임) — 약 1시간

카메라에서 **2~3m**, 로봇 카메라 높이 그대로. 각 항목 3번씩 해 보고 맞은 횟수를 적는다.
"알람"은 뷰어 패널의 알람 목록. 알람이 나면 `detail` 숫자(descent_ratio, hip_drop, torso_deg, core_conf)도 적는다 → 임계값 조정에 씀.

| # | 동작 | 기대 결과 | 결과 (맞음/3) | 알람 detail·메모 |
|---|---|---|---|---|
| V1 | 서 있기 | `서 있음`, 검출 점수·관절 신뢰도 높음 | | 점수 __ / 관절 __ |
| V2 | 의자에 앉기 | `앉음` | | |
| V3a | 바닥에 옆으로 눕기 | `누움`, 몸통 각도 ~90° | | 각도 __ |
| V3b | 머리를 카메라 쪽으로 두고 눕기 | `누움`? (알려진 한계) | | 각도 __ / bbox 비율 __ |
| V4 | 서 있다가 **빠르게** 매트에 넘어짐 | `쓰러짐 의심` → 3초 후 알람 `descent` | | |
| V5 | 의자·바닥에 **털썩** 앉기 | 알람 없음 | | |
| V6 | 서 있다가 **천천히**(4~5초) 무너져 누움 | 알람 `slow_fall` (from standing) | | hip_drop __ |
| V7 | 의자에서 바닥으로 **미끄러져** 누움 | 알람 `slow_fall` (from sitting) | | hip_drop __ |
| V8a | 소파에 5초 넘게 앉았다가 천천히 눕기 | 알람 없음, `·쉼` | | |
| V8b | 소파에 **털썩** 눕기 | 알람 없음 | | |
| V9 | 바닥(요)에 5초 넘게 앉았다가 눕기 | 알람 없음, `·쉼` | | |
| V10 | 바닥에 앉아 있다 일어서서 **바로**(5초 안) 매트에 넘어짐 | 알람 | | |
| V11 | 팔만 보이게 하기 | `판정 불가` (사람 없음) | | |

**마지막 상태 기억·취침**

| # | 동작 | 기대 결과 | 결과 | 메모 |
|---|---|---|---|---|
| M1 | 소파에 누워 `·쉼` 확인 → 카메라 10초 가리기 → 떼기 (같은 자리) | 알람 없음, `·쉼` 유지 | | |
| M2 | 소파에서 쉼 → 카메라 가리고 **바닥으로 옮겨 누움** → 떼기 | 60초 후 알람 `lying_only` | | |
| M3 | 서 있기 → 카메라 가리고 매트에 누움 → 떼기 | **10초 후** 알람 (`last_seen=standing`) | | |
| S1 | 패널 "취침 선언" → 서 있다가 천천히 바닥에 눕기 | 알람 없음, `잠듦` | | |
| S2 | (S1 이어서) 일어서기 | 취침 해제 | | |
| S3 | 취침 선언 상태에서 **빠르게** 넘어짐 | 알람 `descent` | | |
| B1 | 뷰어를 끄고 → 다리를 이불로 덮고 누움 → **카메라를 가린 채로** 뷰어 다시 켜기 → 떼기 (기억 없는 상태) | 60초엔 알람 없음, 5분 후 `lying_only` (`covered: true`) | | (5분 기다리기 선택) |

> 기억 주의: 카메라를 가리기 직전에 **서 있는 모습**이 보였으면 "마지막에 서 있었음"으로 기억돼 10초 만에 알람이 난다 (M3).
> "아무 기억 없는 상태"를 시험하려면 B1처럼 뷰어를 다시 켠다 (기억은 메모리에만 있어서 다시 켜면 비워짐).

**F7 무움직임** (오래 걸리는 것은 선택)

| # | 동작 | 기대 결과 | 결과 | 메모 |
|---|---|---|---|---|
| F1 | 가만히 앉아 있기 1분 | "안 움직인 시간"이 늘어남 | | |
| F2 | 고개 돌리기·팔 움직이기 | 시간이 0으로 다시 시작 | | 몇 cm 움직여야 초기화? |
| F3 | 숨만 쉬며 가만히 (흔들림 확인) | 초기화 안 됨 | | 오초기화 있으면 기록 |
| F4 | (선택) 서서 5분 가만히 | 알람 `no_motion` (posture standing) | | |

**두 사람**

| # | 동작 | 기대 결과 | 결과 | 메모 |
|---|---|---|---|---|
| P1 | 한 명은 서 있고, 다른 한 명이 매트에 넘어짐 | 넘어진 사람 번호로 알람, `★`가 넘어진 사람 | | |
| P2 | 두 사람이 엇갈려 지나가기 | 번호가 바뀌는지 | | 바뀜/유지 |
| P3 | 두 사람이 겹쳐 서기 | 번호 유지 여부 | | |
| P4 | 두 명이 1분 가만히 | "안 움직인 시간" 0 유지 (F7 멈춤) | | |

**임계값 조정 메모** (`pi/app/config.py` 기본값과 비교, 바꿀 값만)

| 설정 | 기본값 | 관찰 | 바꿀 값 |
|---|---|---|---|
| `fall_descent_ratio` | 0.4 | V4 descent_ratio __, V5 털썩 앉기 때 __ | |
| `slow_fall_hip_drop_ratio` | 0.5 | V6·V7 hip_drop __, V8·V9 쉼 때 __ | |
| `fall_lying_angle_deg` | 60 | V3 각도 __ | |
| `vision_kpt_min_conf` | 0.5 | V1 관절 신뢰도 __ | |
| `no_motion_threshold` | 0.05 | F2·F3 | |

---

## 2. 모델 비교 (s vs m) — 약 30분

```bash
python -m pi.scripts.bench_pose --hef ~/pd-dog-models/hailo8l/yolov8s_pose.hef        # 60초
python -m pi.scripts.bench_pose --hef ~/pd-dog-models/hailo8l/yolov8m_pose.hef        # 60초
python -m pi.scripts.pose_viewer --video --hef ~/pd-dog-models/hailo8l/yolov8m_pose.hef   # V3a·V3b·V6을 m으로 다시
```
- [ ] 두 출력의 마지막 줄 → [benchmarks.md](benchmarks.md) "결과: 속도·자원" 표에 붙이기
- 누운 자세 비교:

| 모델 | V3a 누움 | V3b 카메라 쪽 누움 | V6 느린 낙상 | 관절 신뢰도 (누움) |
|---|---|---|---|---|
| yolov8s_pose | | | | |
| yolov8m_pose | | | | |

- [ ] 고른 모델로 10분 발열: `--seconds 600` → 온도 __ °C, throttled __
- [ ] 결정: ______ (→ `.env` `POSE_HEF`, [decisions.md](decisions.md)에 기록)

**결정 갈림길**: 두 모델 다 누운 사람을 자주 못 잡으면 → 카메라 높이·각도 조정 → 그래도 안 되면 E-FPDS·파인튜닝 검토 ([todo.md](todo.md)).

---

## 3. 마커 — 약 40분

**3-1. 마커 인쇄**
```bash
python -m pi.scripts.marker_test --generate 1 2 3 10 --out ~/pd-dog-data/markers
```
- [ ] PNG를 노트북으로 옮겨 인쇄 (`scp jjjkk24@<pi 주소>:~/pd-dog-data/markers/*.png .`)
- [ ] 검은 사각형 한 변 실제 길이: ____ cm

**3-2. 거리별 인식** (마커를 벽 아래쪽, 카메라 높이 근처에 붙이고 정면에서)
```bash
python -m pi.scripts.marker_test --marker-cm <한 변> --at-cm 100 --seconds 10 --note "정면"
```
- [ ] 50·100·200·300·400cm 각각 → 마지막 줄을 [navigation.md](navigation.md) §11-③ 표에
- [ ] 마커 인식 시간: 중앙값 __ ms, 최대 __ ms
- [ ] "초점거리 추정" 중앙값 __ px → `.env`에 `CAMERA_FOCAL_PX=`, `MARKER_SIZE_CM=`
- [ ] 비스듬히 (45°, 200cm): 인식률 __ %, 뷰어 거리 표시 __ cm (실제 200) → 오차 크면 카메라 보정 필요

**3-3. 뷰어 확인** (`.env` 수정 후 뷰어 다시 켜기)
- [ ] 마커 거리 표시가 줄자와 비슷한가: 실제 __ cm / 표시 __ cm
- [ ] 방향: 마커가 화면 오른쪽이면 + 각도

**3-4. 잠자리 마커** — 시험 동안만 `.env`에:
```
SLEEP_MARKER_IDS=10
SLEEP_HOURS=00:00-24:00
```
| # | 동작 | 기대 결과 | 결과 | 메모 |
|---|---|---|---|---|
| SP1 | 10번 마커를 요 머리맡 벽 아래쪽에 붙임 → 카메라 가리고 요에 누움 → 떼기 | 이름표 `·잠자리`, 60초 지나도 알람 없음 | | |
| SP2 | 마커에서 먼 바닥에 같은 방법으로 누움 | 알람 (가리기 전 서 있었으면 10초, 기억 없으면 60초) | | |
| SP3 | 잠자리에서 빠르게 넘어짐 (매트) | 알람 | | |
| SP4 | 이불·사람에 마커가 가려지는지 | 가려지면 위치 조정 | | 좋은 위치: |

- [ ] 시험 후 `SLEEP_HOURS`를 실제 취침 시간대로 (예: `22:00-07:00`)

---

## 4. 가구 검출 확인 — 약 20분
```bash
MZ_VERSION=v2.20.0 bash pi/scripts/download_models.sh yolov8s
python -m pi.scripts.furniture_check --inspect
```
- [ ] `--inspect` 출력 정상 / 오류 → **출력 전체를 Claude에게**
- [ ] 사람이 서서 `person`으로 잡힘 (종류 번호 확인): 예 / 아니오

```bash
python -m pi.scripts.furniture_check --seconds 20 --note "침대 2m 정면"
```
| 대상 | 거리 | 각도 | 인식률 | 점수 중앙값 | 메모 |
|---|---|---|---|---|---|
| 침대 | 1m | 정면 | | | |
| 침대 | 2m | 정면 | | | |
| 침대 | 2m | 비스듬히 | | | |
| 소파 | 1m | 정면 | | | |
| 소파 | 2m | 정면 | | | |
| 소파 | 2m | 비스듬히 | | | |
| 사람이 누운 소파 | 2m | 정면 | | | 사람에 가려도 잡히나 |

- [ ] 결정: 잘 잡힘 → 본격 구현 / 안 잡힘 → 접고 잠자리 마커·"잘게"로

---

## 5. MechDog M0 — 약 40분
Pi 앱·뷰어는 끄고 진행 (시리얼 포트를 같이 쓰면 안 됨). MechDog 배터리 충전 확인.
```bash
mpremote connect list                                           # 포트 확인 (Pi: /dev/ttyUSB0 등)
mpremote connect <PORT> resume run esp32/m0/turn_test.py        # 보드에 저장 안 하고 실행만
mpremote connect <PORT> resume run esp32/m0/sonar_imu_test.py
```
- [ ] 회전: 테이프로 앞 방향 표시 → 각 동작 후 돈 각도·밀린 거리 → [navigation.md](navigation.md) §11-① 표
  - 제자리 회전 되는 명령: ______ / 회전 속도 ____ °/s
- [ ] 초음파: 안내대로 판자 이동 → §11-② 표. 단위 (cm/mm): ____, 최대 거리 ____, 낮은 장애물 감지: 예/아니오
- [ ] IMU: 손으로 기울일 때 `read_angle` 값 범위 ____ → 넘어짐 임계값 제안 ____ °
- [ ] 카메라 장착 높이 ____ cm, 숙임 각도 ____ ° → §11-④

---

## 6. (X1200 장착 후) 부하 테스트
- [ ] Pi: `bench_pose --seconds 1200` 동안 X1200 잔량 변화 ___ % / 20분, throttled ___
- [ ] MechDog: 걷기 10분 동안 배터리 변화 ___

---

## 끝나고
- [ ] `.env` 정리: `POSE_HEF`, `CAMERA_FOCAL_PX`, `MARKER_SIZE_CM`, `SLEEP_MARKER_IDS`, `SLEEP_HOURS` (`.env`는 커밋 안 함)
- [ ] 기록할 곳: 이 파일, [benchmarks.md](benchmarks.md), [navigation.md](navigation.md) §11, [decisions.md](decisions.md)(모델 선택)
- [ ] 기록이 끝나면 Pi에서 브랜치를 만들어 커밋하거나, 결과를 Claude에게 붙여서 PC에서 정리
- [ ] Pi 종료: 뷰어 `Ctrl+C` → `sudo shutdown -h now` → 초록 LED 꺼진 뒤 전원 분리, MechDog 전원 스위치 끄기

# MechDog 모션 제어

Hiwonder MechDog의 걷기·자세·동작 제어 방법 정리입니다. F3 보행 코드는 [esp32/services/gait.py](../esp32/services/gait.py)에서 이 API를 감싸서 씁니다.
보드에 코드 올리는 방법은 [esp32/README.md](../esp32/README.md)를 따릅니다.

## 기본 사용법

```python
from HW_MechDog import MechDog
import time

mechdog = MechDog()      # 생성 시 모터가 켜지며 기본 자세로 움직임
time.sleep(1)
```

## 걷기

```python
mechdog.move(보폭, 각도)   # 보폭: mm, -100~100 (+앞 / -뒤), 각도: 도, -30~30 (양수 = 왼쪽)
mechdog.move(0, 0)         # 멈춤
```

- 단위·범위는 Hiwonder 위키 기준 (2026-11-27 확인).
- **제자리 회전 API는 문서에 없다.** 공식 시리얼 이동 명령도 전진/후진 + 회전 조합 8종뿐이고 제자리 회전은 없다.
  → `move(0, 각도)`, `move(1, 30)`(보폭 1mm = 제자리걸음에 가까움)으로 되는지 [navigation.md](navigation.md) M0에서 시험.
- 아래 원본 코드는 각도 ±40·±50도 쓰는데 위키 범위는 -30~30 → 범위 밖 값이 잘리는지·오류인지 M0에서 확인.

원본 코드에서 쓰는 값:

| 동작 | 값 |
|---|---|
| 직진 | move(120, 0) |
| 왼쪽/오른쪽으로 크게 | move(80, -40) / move(80, 40) |
| 왼쪽/오른쪽으로 약하게 | move(90, -25) / move(90, 25) |
| 후진 | move(-40, 0) |
| 후진하며 회전 | move(-40, -20) / move(-40, 20) |

- move()는 "이 속도로 계속 걸어"라는 명령이라, move(0, 0)을 보낼 때까지 계속 걸음
- 첫 번째 값이 클수록 걸음이 크고 빨라짐

**앞/뒤 전환 시 몸 중심 이동** (원본 코드 방식)

```python
mechdog.transform([10, 0, 0], [0, 0, 0], 100)    # 앞으로 걸을 자세
mechdog.transform([-10, 0, 0], [0, 0, 0], 100)   # 뒤로 걸을 자세
```

## 걸음 타이밍 (박자 맞추기)

```python
mechdog.set_gait_params(공중시간ms, 착지시간ms, 다리높이mm)
```

- 걸음 1번 시간 = 공중 시간 + 착지 시간. F3에서는 이 값을 박자 간격에 맞춰 발이 박자마다 닿게 함
- 공중 시간이 짧고 다리 높이가 낮을수록 덜 흔들림
- 실기기 테스트 값(공중 150ms, 높이 25mm, 보폭 25)은 [esp32/config.py](../esp32/config.py)의 `GAIT_*`에 있음

## 자세 조절

```python
mechdog.transform([x, y, z], [roll, pitch, yaw], 시간ms)
```

- 위치(mm)와 기울기를 현재 자세에서 상대적으로 변경
- 원본 앱 코드 제한: 좌우/앞뒤 기울기 ±17단계, 높이 +15 ~ -25

```python
mechdog.set_default_pose()                 # 기본 자세로 복귀
mechdog.set_default_pose(duration=500)     # 0.5초에 걸쳐 복귀
```

## 미리 저장된 동작

```python
mechdog.action_run("이름")
```

stand_four_legs, sit_dowm(철자 그대로), go_prone, stand_two_legs, handshake,
scrape_a_bow, nodding_motion, stretch_oneself, press_up, boxing, pee,
left_foot_kick, right_foot_kick, rotation_pitch, rotation_roll

- 동작 전에 set_default_pose() 후 1초 대기하는 것이 원본 방식
- 동작 시간(2~4초) 동안 다른 명령을 보내면 run_status busy 발생
- 철자가 틀리면 err:except 발생

## 자동 균형 잡기

```python
mechdog.homeostasis(True)            # 켜기
mechdog.homeostasis(False)           # 끄기
mechdog.read_homeostasis_status()    # 작동 중인지 확인
```

- 보드 내장 자세 센서(IMU) 사용: IIC(1), 주소 106 (0x6A)

## 자세 센서 (IMU) 읽기

```python
import Hiwonder_IIC
imu = Hiwonder_IIC.MPU()
imu.read_angle()        # 기울기 (X·Y)
```

- 위키 기준 **기울기(X·Y)만 제공**한다. 자이로(회전 속도)·yaw(향하는 방향) API는 없다 (2026-11-27 확인).
  → 로봇 이동에서 방향은 IMU가 아니라 **마커를 보며 바로잡는다** ([navigation.md](navigation.md)).
- `robot_tipped`(넘어짐)는 `read_angle()` 기울기가 임계값을 넘는지로 판단한다. 임계값은 `esp32/config.py` (M0에서 측정).
- 참고: 공식 시리얼 명령 `CMD|5|$`도 같은 값을 준다. 단 **공식 슬레이브 UART 프로토콜은 우리 프로젝트에서 사용 금지**
  ([esp32/CLAUDE.md](../esp32/CLAUDE.md)) → 단위 참고용으로만 적는다.

## 배터리 전압

- 공식 시리얼 `CMD|6|$`는 **mV**를 준다 (참고용, 위 이유로 사용하지 않음). Python에서 읽는 API는 아직 확인 안 함 (TODO).
- 대시보드 `dog_battery_pct` 변환: 2S LiPo 기준 **약 6.4V = 0%, 8.4V = 100%** 사이 직선 변환. 두 전압은 `esp32/config.py` 설정값으로 둔다.

## F3 박자음 (MP3 모듈)

- MP3 모듈 버스는 `esp32/config.py`의 `MP3_I2C_BUS`. [pinmap.md](pinmap.md) 기준 IIC1이지만, 실기기 테스트에서는 IIC2로도 재생됨 → 실제 연결 포트 확인 필요 ([todo.md](todo.md))
- mp3 파일은 MP3 모듈의 SD 카드에 저장. 원하는 소리가 SD 카드에서 몇 번째 트랙인지 찾아서 `MP3_TRACK_BEAT`에 번호를 입력하면 됨
- 레포의 [esp32/sounds/](../esp32/sounds/)는 SD 카드에 복사할 원본 보관용 (보드에 업로드하는 파일 아님)

## 자주 겪는 문제

- **run_status busy:1**: 이전 동작이 끝나기 전에 명령이 들어감 → 명령 사이 대기 시간 늘리기
- **err:except**: 없는 동작 이름 → 위 목록 확인
- **USB 연결 시 반복해서 꿈틀거림**: 전원 부족 → 배터리 충전 후 전원 켜고 연결
- **걸음이 약해짐**: 배터리 부족
- **Hiwonder 에디터 업로드 시 한글 사라짐**: 주석·출력 문구는 영어로 작성
- **원래 앱 조종으로 되돌리기**: 처음 업로드 전에 백업한 `backup_main.py`를 보드의 `main.py`로 다시 업로드 ([esp32/README.md](../esp32/README.md))

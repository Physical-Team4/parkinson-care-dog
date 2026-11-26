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
mechdog.move(속도, 방향)   # 속도: +앞 / -뒤, 방향: 회전량
mechdog.move(0, 0)         # 멈춤
```

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

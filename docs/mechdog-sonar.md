# MechDog 초음파 거리 센서

Hiwonder MechDog 내장 초음파 거리 센서(sonar) 사용법과 원본 장애물 회피 로직 정리입니다.
sonar는 초음파를 쏴서 돌아오는 시간으로 거리를 재는 방식을 뜻함.

- 앞 장애물 감지용 내장 센서 ([pinmap.md](pinmap.md) "내장" 행). 뒤따라오는 사용자 거리는 VL53L1X ToF가 담당 (F3)
- 아직 `esp32/drivers/`에 드라이버는 없음. 코드에서 쓰게 되면 주소·주기는 `esp32/config.py`에 둘 것
- 보드에 코드 올리는 방법은 [esp32/README.md](../esp32/README.md)를 따름

## 하드웨어 연결

- 코드에서 `Hiwonder_IIC.IIC(1)` 사용, I2C 주소 `119` (0x77). MP3 모듈과 같은 IIC1 버스
- 연결 확인: `print(Hiwonder_IIC.IIC(1).scan())` 결과에 `119`가 있으면 정상
  (106은 보드 내장 자세 센서이므로 함께 보이는 것이 정상)
- 케이블은 반드시 MechDog 전원을 끈 상태에서 꽂을 것

## 기본 사용법

```python
import Hiwonder_IIC

i2c1 = Hiwonder_IIC.IIC(1)
sonar = Hiwonder_IIC.I2CSonar(i2c1)

distance = sonar.getDistance()       # 거리 (원본 코드상 cm 단위로 추정)
sonar.setRGB(0, R, G, B)             # 센서 LED 색 (0~255)
```

- 원본 코드는 0.08초 간격으로 계속 읽음
- 앱 전송 시 ×10 해서 mm로 바꾸고 최대 5000mm로 제한
- 단위는 실제 자로 재서 확인 필요

## 거리 계속 읽기 예시 (원본 코드 방식)

```python
import Hiwonder
import Hiwonder_IIC
import time

i2c1 = Hiwonder_IIC.IIC(1)
sonar = Hiwonder_IIC.I2CSonar(i2c1)
distance = 0

def read_sonar():
    global distance
    time.sleep(2)
    while True:
        distance = sonar.getDistance()
        time.sleep(0.08)

Hiwonder.startMain(read_sonar)
```

- 원본 코드는 거리 읽기를 별도 작업으로 분리하고, 전역 변수 distance로 다른 작업과 값을 공유
- 우리 `esp32/main.py`는 블로킹 없는 `tick(now_ms)` 루프 구조이므로, 붙일 때는 `sleep` 대신 마지막 측정 시각을 기억해 80ms마다 읽는 방식으로 바꿀 것

## 장애물 회피 (원본 코드 로직)

| 거리 | LED | 동작 |
|---|---|---|
| 10 미만 | 빨강 (255, 0, 0) | 뒤로 걷는 자세 전환 후 move(-40, 0) 3초 |
| 10 ~ 40 | 노랑 (255, 204, 0) | move(80, -50)으로 5초간 방향 틀기 |
| 40 이상 | 보라 (204, 51, 204) | move(120, 0) 직진 |
| 종료 시 | 파랑 (51, 51, 255) | move(0, 0) 정지 |

- 모션 제어 함수(move, transform)는 [mechdog-motion.md](mechdog-motion.md) 참고

## 자주 겪는 문제

- **scan 결과에 119가 없음**: 케이블 연결 확인, 전원 끄고 다시 꽂기
- **거리 값이 이상하게 튐**: 센서 앞이 너무 가깝거나 비스듬한 면, 푹신한 물체는 초음파 반사가 약함
- **USB 연결 시 반복해서 꿈틀거림**: 전원 부족 → 배터리 충전 후 전원 켜고 연결
- **Hiwonder 에디터 업로드 시 한글 사라짐**: 주석·출력 문구는 영어로 작성
- **원래 앱 조종으로 되돌리기**: 처음 업로드 전에 백업한 `backup_main.py`를 보드의 `main.py`로 다시 업로드 ([esp32/README.md](../esp32/README.md))

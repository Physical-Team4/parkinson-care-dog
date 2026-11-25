# MechDog 초음파 거리 센서

Hiwonder MechDog의 초음파 거리 센서(sonar) 사용법과 장애물 회피 로직 정리입니다.
sonar는 초음파를 쏴서 돌아오는 시간으로 거리를 재는 방식을 뜻함.

## 하드웨어 연결

- 코드에서 `Hiwonder_IIC.IIC(1)` 사용, I2C 주소 `119` (0x77)
- 연결 확인: `print(Hiwonder_IIC.IIC(1).scan())` 결과에 `119`가 있으면 정상
  (106은 보드 내장 자세 센서이므로 함께 보이는 것이 정상)
- 케이블은 반드시 MechDog 전원을 끈 상태에서 꽂을 것

## 보드에 코드 올리는 방법

보드에는 `main.py` 하나만 저장되며, 마지막에 올린 코드가 이전 코드를 덮어씀.
파이썬으로 올리든 블록 코딩으로 올리든 동일하므로, 올리기 전에 기존 코드는 저장소에 보관할 것.

**mpremote (추천)**

처음 한 번 설치:

```bash
pip install mpremote
```

pull 받은 폴더에서 실행:

```bash
mpremote connect COM3 cp main.py :main.py
mpremote connect COM3 reset
```

- COM3은 장치 관리자의 USB-SERIAL CH340 포트 번호로 변경
- 보드의 코드를 노트북으로 가져오기: `mpremote connect COM3 cp :main.py main.py`

**WonderCode**

MechDog 연결 → 파이썬 모드 편집창에 코드 붙여넣기 → 업로드

- 한글이 지워지므로 주석과 출력 문구는 영어로 작성
- 업로드 시 편집창 내용이 main.py로 저장되므로, 다른 예제가 열려 있지 않은지 확인

**Thonny**

인터프리터를 MicroPython (ESP32) + CH340 포트로 설정
→ 파일 열기 → 다른 이름으로 저장 → MicroPython 장치 → main.py

- 저장하지 않고 실행(▶)만 하면 테스트용으로 잠깐 실행됨 (main.py 유지)

**공통 주의사항**

- 연결이 안 되면 장치 관리자에서 CH340 포트 확인, 데이터 전송용 USB 케이블 사용
- 다른 프로그램(WonderCode, Thonny 등)이 포트를 쓰고 있으면 연결 안 됨 → 하나만 실행
- 배터리 전원을 켠 상태로 연결해야 재시작 반복이 없음

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

## 거리 계속 읽기 예시

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

- 원본 코드와 같이 거리 읽기를 별도 작업으로 분리하고, 전역 변수 distance로 다른 작업과 값을 공유

## 장애물 회피 (원본 코드 로직)

| 거리 | LED | 동작 |
|---|---|---|
| 10 미만 | 빨강 (255, 0, 0) | 뒤로 걷는 자세 전환 후 move(-40, 0) 3초 |
| 10 ~ 40 | 노랑 (255, 204, 0) | move(80, -50)으로 5초간 방향 틀기 |
| 40 이상 | 보라 (204, 51, 204) | move(120, 0) 직진 |
| 종료 시 | 파랑 (51, 51, 255) | move(0, 0) 정지 |

- 모션 제어 함수(move, transform)는 feature/motion-control 브랜치 문서 참고

## 자주 겪는 문제

- **scan 결과에 119가 없음**: 케이블 연결 확인, 전원 끄고 다시 꽂기
- **거리 값이 이상하게 튐**: 센서 앞이 너무 가깝거나 비스듬한 면, 푹신한 물체는 초음파 반사가 약함
- **USB 연결 시 반복해서 꿈틀거림**: 전원 부족 → 배터리 충전 후 전원 켜고 연결
- **WonderCode 업로드 시 한글 사라짐**: 주석·출력 문구는 영어로 작성
- **원래 앱 조종으로 되돌리기**: 저장소의 원본 main.py(앱 블루투스 조종용)를 다시 업로드

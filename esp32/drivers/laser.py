# 레이저 모듈 KY-008 (담당: C). ESP32 내부 포트 IO23 (decisions D-002 방법 4).
# 안전: 기본 꺼짐, 바닥만 향하게 장착. pin이 None이면 아무 동작 안 함.
from machine import Pin


class Laser:
    def __init__(self, pin_no):
        self._pin = Pin(pin_no, Pin.OUT, value=0) if pin_no is not None else None
        self._on = False

    def on(self):
        if self._pin is not None:
            self._pin.on()
            self._on = True

    def off(self):
        if self._pin is not None:
            self._pin.off()
        self._on = False

    def is_on(self):
        # 연결 안 됐으면 None (대시보드 laser_on=null)
        return self._on if self._pin is not None else None

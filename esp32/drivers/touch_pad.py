# 터치 센서 (담당: D). 포트 3. 핀·눌림 값은 config.TOUCH_PIN / TOUCH_ACTIVE_LEVEL.
# pin이 None이면 항상 안 눌림.
from machine import Pin


class TouchPad:
    def __init__(self, pin_no, active_level):
        self._pin = Pin(pin_no, Pin.IN, Pin.PULL_UP) if pin_no is not None else None
        self._active = active_level

    def pressed(self):
        return self._pin is not None and self._pin.value() == self._active

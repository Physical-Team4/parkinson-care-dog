# 머리 발광 초음파의 RGB 눈 (담당: D). 내장, IIC1. 위키 예제: Hiwonder_IIC.I2CSonar(Hiwonder_IIC.IIC(1))
# setRGB(0, r, g, b)는 실기기에서 동작 확인함 (D, 터치 테스트). 모듈이 없으면 아무 동작 안 함.
import config


class Eyes:
    def __init__(self):
        self._dev = None
        try:
            import Hiwonder_IIC
            self._dev = Hiwonder_IIC.I2CSonar(Hiwonder_IIC.IIC(config.EYES_I2C_BUS))
        except Exception:
            self._dev = None

    def color(self, r, g, b):
        if self._dev is None:
            return
        try:
            self._dev.setRGB(0, r, g, b)   # 0 = 두 눈 모두
        except Exception:
            pass

    def off(self):
        self.color(0, 0, 0)

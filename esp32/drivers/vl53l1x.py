# VL53L1X ToF 거리 센서 (담당: C). 포트 1 (IIC2), 주소 0x29.
# TODO(C): 핀 순서·VCC 전압 확인 후 config.TOF_ENABLED = True.
# TODO(C): 드라이버 구현 — Hiwonder_IIC.IIC(2) 객체로 읽을지 machine.I2C로 직접 읽을지 확인.
import config


class VL53L1X:
    def __init__(self):
        self.enabled = config.TOF_ENABLED

    def distance_cm(self):
        """사용자까지 거리(cm). 비활성·측정 실패 시 None."""
        if not self.enabled:
            return None
        raise NotImplementedError

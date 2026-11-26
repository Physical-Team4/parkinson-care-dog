# MP3 모듈 (담당: C). 포트 2 (IIC1). 위키 예제: Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(1))
# play(track) / volume(v) / pause()는 실기기에서 동작 확인함 (C, F3 박자음 테스트).
# 트랙 번호 = SD 카드 파일 번호. 번호는 config.MP3_TRACK_* 에서만 읽는다.
import config


class Mp3:
    def __init__(self):
        self._dev = None
        try:
            import Hiwonder_IIC
            self._dev = Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(config.MP3_I2C_BUS))
            self._dev.volume(config.MP3_VOLUME)
        except Exception:
            self._dev = None

    def play(self, track):
        """track을 처음부터 재생. 모듈이 없거나 track이 None이면 False."""
        if self._dev is None or track is None:
            return False
        try:
            self._dev.play(track)
            return True
        except Exception:
            return False

    def pause(self):
        if self._dev is None:
            return
        try:
            self._dev.pause()
        except Exception:
            pass

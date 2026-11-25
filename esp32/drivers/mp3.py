# MP3 모듈 (담당: D). 포트 2 (IIC1). 위키 예제: Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(1))
# TODO(D): 재생 메서드 이름을 위키에서 확인 후 play() 구현.


class Mp3:
    def __init__(self):
        self._dev = None
        try:
            import Hiwonder_IIC
            self._dev = Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(1))
        except Exception:
            pass

    def play(self, track):
        if self._dev is None or track is None:
            return False
        raise NotImplementedError

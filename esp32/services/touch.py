# F2 터치 위급 신고 (담당: D). 3초 누르기 → touch_sos. 짧게 누르기 → 복약 확인.
# TODO(D): 터치 IO 확정(config.TOUCH_PIN) 후 구현. Hiwonder.Button(2) 예제 참고.
import config


class Touch:
    def __init__(self):
        self.enabled = config.TOUCH_PIN is not None
        self._pressed_at = None

    def tick(self, now, serial, hb):
        if not self.enabled:
            return
        # TODO(D): 누름 시간 측정 → TOUCH_SOS_HOLD_MS 이상이면 touch_sos 전송
        #          Pi 무응답이면 MP3 경보
        pass

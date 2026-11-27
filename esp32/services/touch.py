# F2 터치 위급 신고 + F1 터치 복약 확인 (담당: D).
#   TOUCH_SOS_HOLD_MS 이상 누름 → touch_sos (손 떼기 전에 1번만). Pi 무응답이면 현장 경보 (D-001, services/sounds.py)
#   짧게 터치 → 복약 대기 중이면 medication.confirm(due, "touch")
#   TOUCH_MIN_TAP_MS 미만 → 스침·신호 튐으로 보고 무시
# 눈 색: 누르는 중 주황, SOS 빨강, 짧은 터치 인식 초록(TOUCH_TAP_FEEDBACK_MS 동안).
#   터치가 눈을 쓰는 동안 medication.hold_eyes=True → 복약 대기 파랑 깜빡임이 덮어쓰지 않음
# 블로킹 없음: 초록 불은 끌 시각을 기억했다가 다음 tick에서 끈다.
import utime

import config
from controllers.serial_cmd import send, log
from drivers.touch_pad import TouchPad
from services import sounds

ORANGE = (0xFF, 0x60, 0x00)
RED = (0xFF, 0x00, 0x00)
GREEN = (0x00, 0xFF, 0x00)


class Touch:
    def __init__(self, medication, mp3, eyes, buzzer):
        self.enabled = config.TOUCH_PIN is not None
        if not self.enabled:
            log("warn: TOUCH_PIN None -> touch off")
        self._pad = TouchPad(config.TOUCH_PIN, config.TOUCH_ACTIVE_LEVEL)
        self._medication = medication
        self._mp3 = mp3
        self._eyes = eyes
        self._buzzer = buzzer
        self._pressed_at = None    # 누르기 시작한 시각 (안 누르면 None)
        self._sos_sent = False     # 이번 누름에서 touch_sos를 보냈는지
        self._eyes_off_at = None   # 초록 불 끌 시각

    def tick(self, now, serial, hb):
        if not self.enabled:
            return
        pressing = self._pad.pressed()

        if pressing and self._pressed_at is None:            # 방금 누름
            self._pressed_at = now
            self._sos_sent = False
            self._eyes_off_at = None
            self._medication.hold_eyes = True     # 복약 깜빡임보다 터치 표시가 먼저
            self._eyes.color(*ORANGE)
        elif (pressing and not self._sos_sent
              and utime.ticks_diff(now, self._pressed_at) >= config.TOUCH_SOS_HOLD_MS):
            self._sos_sent = True                             # 3초 → 위급 신고
            self._eyes.color(*RED)
            send({"t": "touch_sos"})
            if not hb.pi_alive():
                # 원격 알림 불가 → 현장 경보 (MP3_TRACK_ALARM, None이면 부저)
                how = sounds.play("alarm", self._mp3, self._buzzer, now)
                log("touch_sos: pi down -> alarm " + str(how))
        elif not pressing and self._pressed_at is not None:  # 방금 뗌
            held = utime.ticks_diff(now, self._pressed_at)
            self._pressed_at = None
            if self._sos_sent:
                self._eyes_release()
            elif held < config.TOUCH_MIN_TAP_MS:
                log("touch ignored " + str(held) + "ms")
                self._eyes_release()
            else:
                due = self._medication.pending_due
                if due is not None:
                    self._medication.confirm(due, "touch")
                self._eyes.color(*GREEN)
                self._eyes_off_at = utime.ticks_add(now, config.TOUCH_TAP_FEEDBACK_MS)

        if self._eyes_off_at is not None and utime.ticks_diff(now, self._eyes_off_at) >= 0:
            self._eyes_release()
            self._eyes_off_at = None

    def _eyes_release(self):
        self._eyes.off()
        self._medication.hold_eyes = False    # 복약 대기 중이면 깜빡임 다시 시작

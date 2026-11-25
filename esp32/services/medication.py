# F1 복약 알림 (담당: D). 시간 도래 → 알림음 → 터치/음성 확인. 30분 미확인 → med_missed.
# TODO(D): ESP32 시계 맞추기 (Pi가 settings와 함께 현재 시각을 보내도록 프로토콜에 추가 검토).
import config


class Medication:
    def __init__(self):
        self.times = list(config.MED_TIMES_DEFAULT)
        self.pending_due = None

    def set_times(self, times):
        if times and 1 <= len(times) <= 8:
            self.times = list(times)

    def confirm(self, due, method):
        # TODO(D): pending_due와 맞으면 med_ok 전송
        self.pending_due = None

    def tick(self, now, serial, hb):
        # TODO(D): 시간 도래 → med_due 전송 + MP3, 30분 경과 → med_missed
        #          Pi 무응답(hb.pi_alive()==False)이면 MP3 경보로 대체
        pass

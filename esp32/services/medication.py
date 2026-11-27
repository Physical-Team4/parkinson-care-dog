# F1 복약 알림 (담당: D). 형식·규칙: docs/serial-protocol.md "F1 복약".
#   시각 도래 → med_due + MP3 + 확인할 때까지 눈 파랑 깜빡임·작은 부저 "삐빅"(1분마다)
#   → 짧은 터치(med_ok) 또는 음성(Pi med_ack)으로 확인
#   30분 미확인(또는 다음 복약 시각이 먼저 옴) → med_missed, Pi 무응답이면 MP3 경보 (D-001)
# ESP32에는 시계가 없다 → Pi가 settings의 now("HH:MM:SS")로 알려 준 시각 + 그 뒤 흐른 ticks로 계산.
# now를 못 받았으면 알림을 하지 않는다 (시각을 추측하지 않음).
# 블로킹 없음: tick()은 비교만 하고 바로 돌아온다.
import utime

import config
from controllers.serial_cmd import send, log

DAY_MS = 24 * 60 * 60 * 1000


def parse_hhmm(text, with_seconds=False):
    """"HH:MM" → 하루 중 ms. with_seconds면 "HH:MM:SS"도 허용. 형식이 틀리면 None."""
    try:
        parts = [int(p) for p in str(text).split(":")]
    except ValueError:
        return None
    if len(parts) == 2 or (with_seconds and len(parts) == 3):
        h, m = parts[0], parts[1]
        s = parts[2] if len(parts) == 3 else 0
        if 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60:
            return ((h * 60 + m) * 60 + s) * 1000
    return None


class Medication:
    def __init__(self, mp3, eyes, buzzer):
        self._mp3 = mp3
        self._eyes = eyes
        self._buzzer = buzzer
        self._beep_at = None        # 마지막 "삐빅" 시각 (대기 중 MED_BEEP_REPEAT_MS마다 다시)
        self.hold_eyes = False      # 터치가 눈을 쓰는 중이면 True (Touch가 세움) → 깜빡임 멈춤
        self._blink_on = False
        self._blink_at = None
        self.times = []
        self.set_times(config.MED_TIMES_DEFAULT)
        self.pending_due = None     # 확인 기다리는 복약 시각 "HH:MM" (터치가 본다)
        self._pending_since = None
        self._clock_ref = None      # (now 받은 ticks, 그때 하루 중 ms)
        self._done = {}             # "HH:MM" → 알린 날 번호 (하루 한 번만)
        self._warned = False

    def set_times(self, times):
        """["HH:MM", ...] 0~8개. 형식이 틀린 값이 하나라도 있으면 통째로 무시 (지금 목록 유지)."""
        if times is None or len(times) > 8:
            return False
        parsed = [t for t in times if parse_hhmm(t) is not None]
        if len(parsed) != len(times):
            log("med: bad times ignored " + str(times))
            return False
        self.times = sorted(set(parsed))
        self._due_ms = [(t, parse_hhmm(t)) for t in self.times]
        return True

    def set_clock(self, now_text, now):
        """Pi가 준 현지 시각 "HH:MM:SS". 30분 넘게 지난 복약은 tick()에서 알아서 건너뛴다."""
        tod = parse_hhmm(now_text, with_seconds=True)
        if tod is None:
            log("med: bad now " + str(now_text))
            return False
        if self._clock_ref is not None:
            # 다시 맞추면 날 번호가 0부터 다시 시작 → 이미 알린 기록도 같은 기준으로 옮긴다
            shift = self._day_and_tod(now)[0]
            self._done = {k: v - shift for k, v in self._done.items()}
        self._clock_ref = (now, tod)
        return True

    def _day_and_tod(self, now):
        ref_tick, ref_tod = self._clock_ref
        total = ref_tod + utime.ticks_diff(now, ref_tick)
        return total // DAY_MS, total % DAY_MS

    def confirm(self, due, method):
        """터치(method="touch") 또는 음성(Pi med_ack, method="voice")으로 확인. 대기 중인 시각과 맞을 때만."""
        if self.pending_due is None or (due is not None and due != self.pending_due):
            return False
        if method == "touch":
            send({"t": "med_ok", "due": self.pending_due, "method": "touch"})
        log("med ok " + self.pending_due + " " + method)
        self._clear()
        return True

    def _clear(self):
        self.pending_due = None
        self._pending_since = None
        self._blink_at = None
        if self._blink_on and not self.hold_eyes:
            self._eyes.off()
        self._blink_on = False

    def _blink(self, now):
        """대기 중 눈 깜빡임. 터치가 눈을 쓰는 동안(hold_eyes)은 건드리지 않는다."""
        if self.pending_due is None or self.hold_eyes:
            return
        if self._blink_at is None or utime.ticks_diff(now, self._blink_at) >= config.MED_BLINK_MS:
            self._blink_at = now
            self._blink_on = not self._blink_on
            if self._blink_on:
                self._eyes.color(*config.MED_EYES_COLOR)
            else:
                self._eyes.off()

    def _beep(self, now):
        if config.MED_BEEP_TONES:
            # "삐빅" × MED_BEEP_COUNT, 사이에 쉼((0, ms) = 소리 없이 기다림)
            one = list(config.MED_BEEP_TONES) + [(0, config.MED_BEEP_PAUSE_MS)]
            tones = (one * max(1, config.MED_BEEP_COUNT))[:-1]
            self._buzzer.beep(tones, config.MED_BEEP_VOLUME, config.MED_BEEP_GAP_MS, now)
        self._beep_at = now

    def tick(self, now, serial, hb):
        self._blink(now)
        if (self.pending_due is not None and config.MED_BEEP_REPEAT_MS
                and utime.ticks_diff(now, self._beep_at) >= config.MED_BEEP_REPEAT_MS):
            self._beep(now)                      # 확인할 때까지 작게 다시
        if self._clock_ref is None:
            if not self._warned and self.times:
                log("warn: no clock from Pi (settings.now) -> medication off")
                self._warned = True
            return
        day, tod = self._day_and_tod(now)

        if (self.pending_due is not None
                and utime.ticks_diff(now, self._pending_since) >= config.MED_CONFIRM_TIMEOUT_MS):
            self._miss(hb)

        for due, due_ms in self._due_ms:
            elapsed = (tod - due_ms) % DAY_MS            # 자정을 넘겨도 (23:50 → 00:05 = 15분)
            due_day = day if tod >= due_ms else day - 1  # 그 복약 시각이 속한 날
            if elapsed < config.MED_CONFIRM_TIMEOUT_MS and self._done.get(due) != due_day:
                self._done[due] = due_day
                if self.pending_due is not None:   # 앞 복약을 아직 안 먹었는데 다음 시각이 옴
                    self._miss(hb)
                self.pending_due = due
                self._pending_since = now
                send({"t": "med_due", "due": due})
                self._mp3.play(config.MP3_TRACK_MEDICATION)   # None이면 Mp3가 생략
                self._beep(now)
                log("med due " + due)
                break

    def _miss(self, hb):
        send({"t": "med_missed", "due": self.pending_due})
        log("med missed " + self.pending_due)
        if not hb.pi_alive():
            self._mp3.play(config.MP3_TRACK_ALARM)
            log("med_missed: pi down -> mp3 alarm")
        self._clear()

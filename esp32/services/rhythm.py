# F3 리듬 큐잉 보행 (담당: C): 박자 타이머 + 레이저 깜빡임 + MP3 박자음 + ToF 대기.
import utime

import config


class Rhythm:
    def __init__(self, laser, gait, mp3):
        self.laser = laser
        self.gait = gait
        self.mp3 = mp3
        self.mode = "idle"            # idle / walking / paused
        self.bpm = config.BPM_DEFAULT
        self.follow_limit_cm = config.FOLLOW_LIMIT_CM_DEFAULT
        self.follow_distance_cm = None
        self.beat_count = 0
        self._next_beat = None
        self._laser_off_at = None
        self._forced_laser = None

    def _beat_ms(self):
        return 60000 // self.bpm

    def start(self, bpm):
        ok, err = self.set_bpm(bpm)
        if not ok:
            return ok, err
        self.mode = "walking"
        self.beat_count = 0
        self._next_beat = utime.ticks_ms()
        self.gait.set_tempo(self._beat_ms())
        self.gait.walk(config.GAIT_SPEED)
        return True, None

    def stop(self):
        self.mode = "idle"
        self._next_beat = None
        self.laser.off()
        self.gait.stop()
        self.mp3.pause()

    def set_bpm(self, bpm):
        if bpm is None or not (config.BPM_MIN <= bpm <= config.BPM_MAX):
            return False, "bpm range"
        self.bpm = bpm
        if self.mode == "walking":
            self.gait.set_tempo(self._beat_ms())
        return True, None

    def force_laser(self, on):
        self._forced_laser = on
        self.laser.on() if on else self.laser.off()

    def apply_settings(self, msg):
        if msg.get("bpm") is not None:
            self.set_bpm(msg["bpm"])
        if msg.get("follow_limit_cm") is not None:
            self.follow_limit_cm = msg["follow_limit_cm"]

    def tick(self, now):
        self.gait.tick(now)
        if self._laser_off_at is not None and utime.ticks_diff(now, self._laser_off_at) >= 0:
            if self._forced_laser is None:
                self.laser.off()
            self._laser_off_at = None
        if self.mode != "walking" or self._next_beat is None:
            return
        # TODO(C): ToF 거리 > follow_limit_cm 이면 mode="paused", 가까워지면 재개 (stop/restart 횟수 집계)
        if utime.ticks_diff(now, self._next_beat) >= 0:
            if self._forced_laser is None:
                self.laser.on()
                self._laser_off_at = utime.ticks_add(now, config.LASER_BLINK_MS)
            self.mp3.play(config.MP3_TRACK_BEAT)   # 트랙 번호 None이면 소리 없이 진행
            self.beat_count += 1
            # 예정 시각 기준으로 다음 박자를 잡아 밀리지 않게 함
            self._next_beat = utime.ticks_add(self._next_beat, self._beat_ms())

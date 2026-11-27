# 보드 내장 부저 (담당: D). 펌웨어 Hiwonder.bz (2026-11-27 실기기 확인: playTone(주파수Hz, 길이ms, 기다림), setVolume(v), 기본 volume 500).
# 블로킹 없음: beep()은 음 목록을 기억만 하고, tick(now)가 차례가 된 음을 기다리지 않고(wait=False) 낸다.
# 모듈이 없으면 아무 동작 안 함.
import utime


class Buzzer:
    def __init__(self):
        self._bz = None
        try:
            import Hiwonder
            self._bz = Hiwonder.bz
        except Exception:
            self._bz = None
        self._queue = []        # [(주파수, 길이ms), ...] 남은 음
        self._gap_ms = 0
        self._volume = None
        self._next_at = None

    def beep(self, tones, volume, gap_ms, now):
        """tones = [(Hz, ms), ...]를 gap_ms 간격으로. 이미 울리는 중이면 새 것으로 바꾼다."""
        if self._bz is None or not tones:
            return False
        self._queue = list(tones)
        self._gap_ms = gap_ms
        self._volume = volume
        self._next_at = now
        return True

    def tick(self, now):
        if not self._queue or utime.ticks_diff(now, self._next_at) < 0:
            return
        freq, ms = self._queue.pop(0)
        try:
            self._bz.setVolume(self._volume)
            self._bz.playTone(freq, ms, False)
        except Exception:
            self._queue = []
            return
        self._next_at = utime.ticks_add(now, ms + self._gap_ms)

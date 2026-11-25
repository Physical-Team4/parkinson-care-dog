# Pi 하트비트 감시 (담당: D). Pi 무응답이면 원격 알림 대신 MP3 경보 (decisions D-001)
import utime


class Heartbeat:
    def __init__(self, timeout_ms):
        self.timeout_ms = timeout_ms
        self._last = None

    def beat(self):
        self._last = utime.ticks_ms()

    def pi_alive(self):
        if self._last is None:
            return False
        return utime.ticks_diff(utime.ticks_ms(), self._last) < self.timeout_ms

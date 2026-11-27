# Pi 하트비트 감시 (담당: D). Pi 무응답이면 원격 알림 대신 현장 경보 (decisions D-001)
# Pi가 shutdown을 보내면 hb가 끊기기 전부터 무응답으로 본다. 꺼지는 중에 hb가 몇 번 더 와도 그대로이고,
# hb가 timeout 넘게 끊겼다가 다시 오면(= Pi 재부팅) 정상으로 돌아온다.
import utime


class Heartbeat:
    def __init__(self, timeout_ms):
        self.timeout_ms = timeout_ms
        self._last = None
        self._shutdown = False

    def _recent(self, now):
        return self._last is not None and utime.ticks_diff(now, self._last) < self.timeout_ms

    def beat(self):
        now = utime.ticks_ms()
        if self._shutdown and not self._recent(now):
            self._shutdown = False
        self._last = now

    def shutdown(self):
        self._shutdown = True

    def pi_alive(self):
        return not self._shutdown and self._recent(utime.ticks_ms())

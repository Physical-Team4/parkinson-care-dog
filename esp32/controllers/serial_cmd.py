# USB 시리얼 명령 처리 (담당: D, F3 명령은 C와 합의). 형식: docs/serial-protocol.md
# USB = REPL 포트. 디버그는 log()로 '#' 붙여 출력.
import sys
import select
import ujson
import utime

import config

MAX_LINE = 256


def log(text):
    sys.stdout.write("# " + str(text) + "\n")


def send(msg):
    sys.stdout.write(ujson.dumps(msg) + "\n")


class SerialCommands:
    def __init__(self, heartbeat, rhythm, medication):
        self.hb = heartbeat
        self.rhythm = rhythm
        self.medication = medication
        self._poll = select.poll()
        self._poll.register(sys.stdin, select.POLLIN)
        self._buf = ""
        # Pi 배터리 상태 (pi_low / shutdown). 서비스가 보고 경보 모드를 준비한다 (D-001)
        self.pi_battery_low = False
        self.pi_shutting_down = False

    def poll(self):
        # 읽을 수 있는 동안만 한 글자씩 (블로킹 금지)
        while self._poll.poll(0):
            ch = sys.stdin.read(1)
            if ch == "\n":
                line, self._buf = self._buf, ""
                self._handle_line(line)
            elif len(self._buf) < MAX_LINE:
                self._buf += ch
            else:
                self._buf = ""

    def _handle_line(self, line):
        line = line.strip()
        if not line:
            return
        try:
            msg = ujson.loads(line)
            t = msg["t"]
        except Exception:
            log("bad line")
            return
        msg_id = msg.get("id")
        ok, err = True, None
        if t == "hb":
            self.hb.beat()
        elif t == "walk":
            ok, err = self.rhythm.start(msg.get("bpm", config.BPM_DEFAULT))
        elif t == "stop":
            self.rhythm.stop()
        elif t == "bpm":
            ok, err = self.rhythm.set_bpm(msg.get("bpm"))
        elif t == "laser":
            self.rhythm.force_laser(bool(msg.get("on")))
        elif t == "settings":
            # 모든 필드 선택: 있는 것만 반영 (now만 오는 시계 맞추기 메시지도 있음)
            if "now" in msg:
                self.medication.set_clock(msg["now"], utime.ticks_ms())
            if "med_times" in msg:
                self.medication.set_times(msg["med_times"])
            self.rhythm.apply_settings(msg)
        elif t == "med_ack":
            self.medication.confirm(msg.get("due"), "voice")
        elif t == "pi_low":
            # TODO(D): MP3 안내 config.MP3_TRACK_PI_LOW 재생 (트랙 번호 미정 → None이면 생략)
            self.pi_battery_low = True
            log("pi battery low " + str(msg.get("pct")))
        elif t == "shutdown":
            # Pi가 곧 꺼짐 → hb 끊김 전에 경보 모드로. TODO(D): 경보 모드 전환·MP3
            self.pi_battery_low = True
            self.pi_shutting_down = True
            log("pi shutdown " + str(msg.get("reason")))
        else:
            # TODO(D): sound
            ok, err = False, "unknown"
        if msg_id is not None:
            reply = {"t": "ack", "id": msg_id, "ok": ok}
            if err:
                reply["err"] = err
            send(reply)

    def send_status(self, rhythm, laser, battery, tilt, now):
        mode = rhythm.mode
        if mode == "idle" and self.medication.pending_due is not None:
            mode = "medication"           # 복약 확인 기다리는 중 (보행 중이면 보행이 먼저)
        elif mode == "idle" and battery.external_power(now):
            mode = "charging"             # 충전기(외부 전원) 연결됨. 우선순위: 보행 > 복약 > 충전 > 대기
        send({
            "t": "status",
            "mode": mode,
            "dog_battery_pct": battery.pct(now),   # LiPo가 아니거나 못 읽으면 None (drivers/battery.py)
            "follow_distance_cm": rhythm.follow_distance_cm,
            "laser_on": laser.is_on(),
            "bpm": rhythm.bpm if rhythm.mode == "walking" else None,
            "robot_tipped": tilt.tipped,  # IMU 기울기 (services/tilt.py). IMU 없으면 None
        })

# 로봇 넘어짐 판단 → status.robot_tipped (담당: D, 기준값은 C와 보행 중 재확인). 형식: docs/serial-protocol.md
# IMU: 펌웨어 Hiwonder_IIC.MPU() = 보드 QMI8658. read_angle() → [X 좌우 기울기°, Y 앞뒤 기울기°] (yaw 없음).
#   실측 (2026-11-27, D, 서 있는 자세): 바닥 ±0.5°, 옆으로 눕힘 X -60°, 앞뒤 Y 34°/-42°, 뒤집기 X ±178°.
# 판단: X나 Y가 TIP_ANGLE_DEG 이상인 상태가 TIP_HOLD_MS 이어지면 넘어짐,
#       둘 다 TIP_CLEAR_DEG 미만으로 TIP_CLEAR_MS 이어지면 해제 (잠깐 들거나 부딪힌 것은 무시).
# IMU를 못 쓰면 tipped = None ("데이터 없음"). 블로킹 없음: TIP_READ_MS마다 한 번 읽음.
import utime

import config


class Tilt:
    def __init__(self, log=None):
        self._imu = None
        try:
            import Hiwonder_IIC
            self._imu = Hiwonder_IIC.MPU()
        except Exception:
            self._imu = None
        self._log = log
        self.tipped = None if self._imu is None else False
        self.angle = None           # 마지막 [X, Y]
        self._read_at = None
        self._since = None          # 지금 상태와 반대 조건이 시작된 시각
        if self._imu is None and log:
            log("warn: IMU unavailable -> robot_tipped off")

    def tick(self, now):
        if self._imu is None:
            return
        if self._read_at is not None and utime.ticks_diff(now, self._read_at) < config.TIP_READ_MS:
            return
        self._read_at = now
        try:
            a = self._imu.read_angle()
            x, y = abs(a[0]), abs(a[1])
        except Exception:
            return                  # 한 번 못 읽은 것은 상태를 바꾸지 않음
        self.angle = a
        if self.tipped:
            flipping = x < config.TIP_CLEAR_DEG and y < config.TIP_CLEAR_DEG
            need = config.TIP_CLEAR_MS
        else:
            flipping = x >= config.TIP_ANGLE_DEG or y >= config.TIP_ANGLE_DEG
            need = config.TIP_HOLD_MS
        if not flipping:
            self._since = None
            return
        if self._since is None:
            self._since = now
        if utime.ticks_diff(now, self._since) >= need:
            self.tipped = not self.tipped
            self._since = None
            if self._log:
                self._log(("tipped " if self.tipped else "upright ") + str(a))

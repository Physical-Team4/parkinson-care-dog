# MechDog 보행 제어 (담당: C). Hiwonder 펌웨어 보행 API(HW_MechDog)를 감싼다.
# 박자에 맞춰 발이 닿도록 걸음 타이밍(set_gait_params)을 BPM에 맞춘다.
# 블로킹 대신 tick(now)에서 출발·자세 복귀를 처리한다.
import utime

import config
from controllers.serial_cmd import log


class Gait:
    def __init__(self):
        self._dog = None
        self._speed = 0
        self._walk_at = None          # 걸음 설정 후 출발할 시각
        self._pose_at = None          # 정지 후 기본 자세로 돌아갈 시각
        try:
            from HW_MechDog import MechDog
            self._dog = MechDog()     # 생성 시 모터가 켜지며 기본 자세로 움직임
            self._dog.set_default_pose()
        except Exception as e:
            log("warn: MechDog init failed " + repr(e))

    def set_tempo(self, beat_ms):
        """걸음 1번 시간 = beat_ms × GAIT_STEP_BEAT_RATIO. 공중 시간은 고정, 나머지는 땅에 닿는 시간."""
        if self._dog is None:
            return
        step_ms = int(beat_ms * config.GAIT_STEP_BEAT_RATIO)
        touchdown_ms = step_ms - config.GAIT_LIFT_MS
        if touchdown_ms <= 0:
            log("warn: beat too short for GAIT_LIFT_MS")
            return
        self._dog.set_gait_params(config.GAIT_LIFT_MS, touchdown_ms, config.GAIT_LIFT_HEIGHT_MM)

    def walk(self, speed):
        """걸음 설정이 적용될 시간을 두고 GAIT_START_DELAY_MS 뒤에 출발."""
        if self._dog is None:
            return
        self._speed = speed
        self._pose_at = None
        self._walk_at = utime.ticks_add(utime.ticks_ms(), config.GAIT_START_DELAY_MS)

    def stop(self):
        if self._dog is None:
            return
        self._walk_at = None
        self._dog.move(0, 0)
        self._pose_at = utime.ticks_add(utime.ticks_ms(), config.GAIT_STOP_POSE_DELAY_MS)

    def tick(self, now):
        if self._dog is None:
            return
        if self._walk_at is not None and utime.ticks_diff(now, self._walk_at) >= 0:
            self._walk_at = None
            self._dog.move(self._speed, 0)
        if self._pose_at is not None and utime.ticks_diff(now, self._pose_at) >= 0:
            self._pose_at = None
            self._dog.set_default_pose()

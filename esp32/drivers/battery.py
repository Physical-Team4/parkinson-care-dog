# MechDog 배터리 전압 → dog_battery_pct (담당: D). 형식: docs/serial-protocol.md
# 펌웨어 Hiwonder.Battery_power() = 전원 전압 mV (위키, 공식 시리얼 CMD|6|$와 같은 값).
#   실기기 (2026-11-27): 보조배터리(12V 출력)로 켰을 때 12660으로 고정 → LiPo가 아니면 잔량을 알 수 없음.
# 변환: DOG_BATTERY_EMPTY_MV = 0%, DOG_BATTERY_FULL_MV = 100% 직선. DOG_BATTERY_MAX_VALID_MV보다 높으면
#   LiPo가 아닌 외부 전원으로 보고 None ("데이터 없음") — 100%로 잘못 보이지 않게.
# 읽기는 DOG_BATTERY_READ_MS마다 한 번만 (status는 1초마다지만 전압은 천천히 변함).
import utime

import config


def to_pct(mv):
    """mV → 0~100 정수. 기준값이 없거나 범위 밖(외부 전원)이면 None."""
    empty, full, max_valid = config.DOG_BATTERY_EMPTY_MV, config.DOG_BATTERY_FULL_MV, config.DOG_BATTERY_MAX_VALID_MV
    if mv is None or empty is None or full is None or full <= empty:
        return None
    if max_valid is not None and mv > max_valid:
        return None
    pct = (mv - empty) * 100 / (full - empty)
    return int(round(max(0, min(100, pct))))


class Battery:
    def __init__(self, log=None):
        self._read = None
        try:
            import Hiwonder
            self._read = Hiwonder.Battery_power
        except Exception:
            self._read = None
        self._log = log
        self._at = None
        self._mv = None
        self._warned = None

    def mv(self, now):
        if self._read is None:
            return None
        if self._at is None or utime.ticks_diff(now, self._at) >= config.DOG_BATTERY_READ_MS:
            self._at = now
            try:
                self._mv = int(self._read())
            except Exception:
                self._mv = None
        return self._mv

    def pct(self, now):
        mv = self.mv(now)
        pct = to_pct(mv)
        # 처음 한 번, 그리고 상태가 바뀔 때만 경고 (매초 출력 금지)
        reason = None
        if mv is None:
            reason = "no reading"
        elif config.DOG_BATTERY_EMPTY_MV is None or config.DOG_BATTERY_FULL_MV is None:
            reason = "DOG_BATTERY_*_MV None"
        elif pct is None:
            reason = "external power? " + str(mv) + "mV > DOG_BATTERY_MAX_VALID_MV"
        if reason != self._warned:
            self._warned = reason
            if reason and self._log:
                self._log("warn: battery pct off (" + reason + ")")
        return pct

# 현장 소리 알림 (담당: D). MP3 트랙이 정해져 있으면 MP3, 아니면(None·모듈 없음) 내장 부저로 대신.
#   "alarm"    : Pi 무응답일 때 touch_sos·med_missed 현장 경보 (D-001)
#   "pi_low"   : Pi 배터리 부족 → "로봇을 충전해 주세요"
#   "shutdown" : Pi가 곧 꺼짐 (이후 원격 알림 불가)
# 소리 값은 config.py (MP3_TRACK_*, *_BEEP_TONES). 블로킹 없음 (부저는 Buzzer.tick이 냄).
import config

_KINDS = {
    "alarm": ("MP3_TRACK_ALARM", "ALARM_BEEP_TONES", "ALARM_BEEP_VOLUME"),
    "pi_low": ("MP3_TRACK_PI_LOW", "PI_LOW_BEEP_TONES", "NOTICE_BEEP_VOLUME"),
    "shutdown": ("MP3_TRACK_SHUTDOWN", "SHUTDOWN_BEEP_TONES", "NOTICE_BEEP_VOLUME"),
}


def play(kind, mp3, buzzer, now):
    """kind 소리를 낸다. 반환: "mp3" / "beep" / None(낼 수단 없음)."""
    track, tones, volume = _KINDS[kind]
    if mp3.play(getattr(config, track)):
        return "mp3"
    if buzzer.beep(getattr(config, tones), getattr(config, volume), 0, now):
        return "beep"
    return None

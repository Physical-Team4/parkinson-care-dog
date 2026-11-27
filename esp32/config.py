# MechDog ESP32 설정. 핀·주소·타이밍은 여기에만 둔다.
# None = 미확정 → 해당 기능 비활성 (docs/todo.md). 추측으로 채우지 말 것.

# ── 시리얼 (docs/serial-protocol.md) ──
HEARTBEAT_EXPECT_MS = 1000
PI_TIMEOUT_MS = 5000        # 이 시간 hb 없으면 Pi 무응답 → MP3 경보로 대체
STATUS_INTERVAL_MS = 1000

# ── 포트 3: 터치 + 레이저 (D-002 방법 1 예정) ──
TOUCH_PIN = 33              # 확인됨 (2026-11-26, D): 핀 찾기 테스트에서 IO33만 반응
TOUCH_ACTIVE_LEVEL = 0      # 누르면 0, 떼면 1 (내부 PULL_UP)
TOUCH_SOS_HOLD_MS = 3000    # F2: 3초 누르기
TOUCH_MIN_TAP_MS = 80       # 이보다 짧은 접촉은 스침·신호 튐으로 무시. 실측: 정상 톡 100ms~, 스침 53ms (todo.md)
TOUCH_TAP_FEEDBACK_MS = 500 # 짧은 터치 인식 후 눈 초록 불 켜 두는 시간
LASER_PIN = None            # TODO(C·D): 터치가 안 쓰는 IO. 방법 1 확정 전까지 None

# ── 내장: 머리 발광 초음파 RGB 눈 (IIC1). 터치 피드백 ──
EYES_I2C_BUS = 1

# ── 포트 1: VL53L1X (IIC2) ──
TOF_I2C_BUS = 2
TOF_ADDR = 0x29
TOF_ENABLED = False         # TODO(C): 핀 순서·VCC 전압 확인 후 True

# ── 포트 2: MP3 (IIC1) ──
MP3_I2C_BUS = 1             # pinmap 기준 IIC1. TODO(C·D): 실기기 테스트에서는 IIC2로도 재생됨 → 실제 연결 포트 확인
MP3_VOLUME = 25             # F3 테스트에서 쓴 값
MP3_TRACK_BEAT = None       # TODO(C·D): SD카드에서 박자음(박수) 트랙 번호 확인 후 입력 (테스트 때는 30 사용, 박수 소리 아님)
MP3_TRACK_ALARM = None
MP3_TRACK_MEDICATION = None
MP3_TRACK_PI_LOW = None     # TODO(D): "로봇 배터리를 충전해 주세요" 안내 (pi_low)
MP3_TRACK_SHUTDOWN = None   # TODO(D): "로봇을 끕니다" 안내 (shutdown)

# ── MP3 트랙이 None일 때 내장 부저로 대신 (services/sounds.py). (Hz, ms), Hz 0 = 쉼 ──
# 2026-11-27 D 실기기에서 세 소리 모두 확인 (PC 중계로 pi_low·shutdown 흉내, Pi 꺼짐 중 터치 SOS → 경보). 음량 기준: 복약 "삐빅" 100(작게), 펌웨어 기본 500
ALARM_BEEP_TONES = [(2000, 150), (0, 100)] * 10        # Pi 무응답 위급 경보: 빠른 삐삐삐 약 2.5초
ALARM_BEEP_VOLUME = 300
PI_LOW_BEEP_TONES = [(1200, 200), (900, 300), (0, 400)] * 3   # 배터리 부족: 내려가는 "띠-리" 3번
SHUTDOWN_BEEP_TONES = [(1000, 300), (800, 300), (600, 600)]   # 꺼짐: 낮아지는 3음 1번
NOTICE_BEEP_VOLUME = 150

# ── MechDog 배터리 → status.dog_battery_pct (docs/serial-protocol.md, drivers/battery.py) ──
# Hiwonder.Battery_power() = mV. 2S LiPo 기준 6.4V = 0%, 8.4V = 100% (serial-protocol.md에 정한 값)
DOG_BATTERY_EMPTY_MV = 6400
DOG_BATTERY_FULL_MV = 8400
# 이보다 높으면 LiPo가 아닌 외부 전원(예: 보조배터리 12V 출력에서 12660 고정, 2026-11-27) → None
DOG_BATTERY_MAX_VALID_MV = 8900
DOG_BATTERY_READ_MS = 5000

# ── 넘어짐 → status.robot_tipped (services/tilt.py). IMU read_angle() 기울기 ──
# 실측 2026-11-27 (D, 정지·서 있는 자세): 바닥 ±0.5°, 옆으로 눕힘 -60°, 앞뒤 34°/-42°, 뒤집기 ±178°.
# 보행 중 흔들림은 아직 안 잼 → C와 F3 보행하며 확인 후 조정 (todo.md)
TIP_ANGLE_DEG = 45          # X나 Y가 이 이상이면 넘어짐 후보
TIP_HOLD_MS = 1000          # 그 상태가 이만큼 이어져야 넘어짐 (들거나 부딪힌 순간 무시)
TIP_CLEAR_DEG = 30          # 둘 다 이 미만으로
TIP_CLEAR_MS = 2000         # 이만큼 이어지면 해제
TIP_READ_MS = 100

# ── F1 복약 (Pi가 settings로 덮어씀) ──
MED_TIMES_DEFAULT = ["08:00", "12:30", "18:00", "22:00"]
MED_CONFIRM_TIMEOUT_MS = 30 * 60 * 1000
MED_EYES_COLOR = (0x00, 0x40, 0xFF)   # 복약 대기 중 눈 깜빡임 색 (파랑. 터치 주황·SOS 빨강·확인 초록과 구분)
MED_BLINK_MS = 500                    # 켜짐/꺼짐 간격
# 복약 대기 중 내장 부저 "삐빅" (MP3 안내음 트랙이 정해지기 전에도 소리로 알림). None이면 소리 끔
MED_BEEP_TONES = [(1500, 120), (1800, 120)]   # (Hz, ms). 2026-11-27 실기기에서 음량 100으로 시험
MED_BEEP_VOLUME = 100         # 부저 음량 (펌웨어 기본 500). 작게
MED_BEEP_GAP_MS = 80
MED_BEEP_COUNT = 5            # 한 번 알릴 때 "삐빅"을 몇 번 (2026-11-27 D 요청: 5번)
MED_BEEP_PAUSE_MS = 300       # "삐빅"과 "삐빅" 사이 쉼
MED_BEEP_REPEAT_MS = 60 * 1000   # 확인할 때까지 이 간격으로 다시 울림. None이면 처음 1번만

# ── F3 박자 보행 ──
BPM_MIN = 80
BPM_MAX = 110
BPM_DEFAULT = 96
FOLLOW_LIMIT_CM_DEFAULT = 150
LASER_BLINK_MS = 100        # 박자마다 켜지는 시간

# ── F3 보행 (services/gait.py). 실기기 테스트 값 ──
GAIT_SPEED = 25             # move() 첫 번째 값 (보폭)
GAIT_STEP_BEAT_RATIO = 1    # 걸음 1번 시간 = 박자 간격 × 이 값. 발이 박자보다 2배 자주 닿으면 2, 절반이면 0.5
GAIT_LIFT_MS = 150          # 다리가 공중에 있는 시간 (짧을수록 덜 흔들림)
GAIT_LIFT_HEIGHT_MM = 25    # 다리 드는 높이 (낮을수록 안정적)
GAIT_START_DELAY_MS = 100   # 걸음 설정 후 출발까지 대기
GAIT_STOP_POSE_DELAY_MS = 1000  # 정지 후 기본 자세로 돌아가기까지

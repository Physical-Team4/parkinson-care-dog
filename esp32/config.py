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

# ── F1 복약 (Pi가 settings로 덮어씀) ──
MED_TIMES_DEFAULT = ["08:00", "12:30", "18:00", "22:00"]
MED_CONFIRM_TIMEOUT_MS = 30 * 60 * 1000

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
